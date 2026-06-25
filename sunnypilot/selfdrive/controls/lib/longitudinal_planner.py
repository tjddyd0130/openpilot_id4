"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""

from cereal import messaging, custom
from opendbc.car import structs
from openpilot.common.constants import CV
from openpilot.selfdrive.car.cruise import V_CRUISE_MAX
from openpilot.sunnypilot.selfdrive.controls.lib.dec.dec import DynamicExperimentalController
from openpilot.sunnypilot.selfdrive.controls.lib.e2e_alerts_helper import E2EAlertsHelper
from openpilot.sunnypilot.selfdrive.controls.lib.smart_cruise_control.smart_cruise_control import SmartCruiseControl
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_assist import SpeedLimitAssist
from openpilot.sunnypilot.selfdrive.controls.lib.speed_limit.speed_limit_resolver import SpeedLimitResolver
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP
from openpilot.sunnypilot.models.helpers import get_active_bundle

DecState = custom.LongitudinalPlanSP.DynamicExperimentalControl.DynamicExperimentalControlState
LongitudinalPlanSource = custom.LongitudinalPlanSP.LongitudinalPlanSource

TMAP_DECEL_ACCEL_FLOOR = -2.5  # m/s^2, comfort floor for carrot-curve TMAP camera/bump deceleration


class LongitudinalPlannerSP:
  def __init__(self, CP: structs.CarParams, CP_SP: structs.CarParamsSP, mpc):
    self.events_sp = EventsSP()
    self.resolver = SpeedLimitResolver()
    self.dec = DynamicExperimentalController(CP, mpc)
    self.scc = SmartCruiseControl()
    self.resolver = SpeedLimitResolver()
    self.sla = SpeedLimitAssist(CP, CP_SP)
    self.generation = int(model_bundle.generation) if (model_bundle := get_active_bundle()) else None
    self.source = LongitudinalPlanSource.cruise
    self.e2e_alerts_helper = E2EAlertsHelper()

    self.output_v_target = 0.
    self.output_a_target = 0.

    # tjddyd: speed the driver reached by pressing the gas while we were slowing for a speed
    # bump. Once captured it becomes the bump pass speed for the rest of that bump event, so we
    # don't yank them back down after they release the pedal. Resets when the bump clears.
    self._bump_override_speed = 0.

  def is_e2e(self, sm: messaging.SubMaster) -> bool:
    experimental_mode = sm['selfdriveState'].experimentalMode
    if not self.dec.active():
      return experimental_mode

    return experimental_mode and self.dec.mode() == "blended"

  def update_targets(self, sm: messaging.SubMaster, v_ego: float, a_ego: float, v_cruise: float) -> tuple[float, float]:
    CS = sm['carState']
    v_cruise_cluster_kph = min(CS.vCruiseCluster, V_CRUISE_MAX)
    v_cruise_cluster = v_cruise_cluster_kph * CV.KPH_TO_MS

    long_enabled = sm['carControl'].enabled
    long_override = sm['carControl'].cruiseControl.override

    # Smart Cruise Control
    self.scc.update(sm, long_enabled, long_override, v_ego, a_ego, v_cruise)

    # Speed Limit Resolver
    self.resolver.update(v_ego, sm)

    # Speed Limit Assist
    has_speed_limit = self.resolver.speed_limit_valid or self.resolver.speed_limit_last_valid
    self.sla.update(long_enabled, long_override, v_ego, a_ego, v_cruise_cluster, self.resolver.speed_limit,
                    self.resolver.speed_limit_final_last, has_speed_limit, self.resolver.distance, self.events_sp)

    targets = {
      LongitudinalPlanSource.cruise: (v_cruise, a_ego),
      LongitudinalPlanSource.sccVision: (self.scc.vision.output_v_target, self.scc.vision.output_a_target),
      LongitudinalPlanSource.sccMap: (self.scc.map.output_v_target, self.scc.map.output_a_target),
      LongitudinalPlanSource.speedLimitAssist: (self.sla.output_v_target, self.sla.output_a_target),
    }

    # tjddyd TMAP fully-auto camera/bump deceleration (carrot-style, no stalk confirmation):
    # the resolver exposes the event limit + live distance while a camera/bump is ahead. Shape
    # the decel as a kinematic ramp so the car slows along AutoNaviSpeedDecelRate and reaches
    # the limit ~CtrlEnd (camera) / BumpTime (bump) seconds before the event. The ramp target is
    # high when far (no effect -- cruise wins the min) and falls to the limit as you approach;
    # it auto-releases once the event clears (resolver.speed_limit -> 0), restoring set speed.
    # Gated on EnableTmapSpeedLimit (off by default), so every other configuration is unaffected.
    if self.resolver.use_tmap:
      tmap_target = self.sla.output_v_target  # base: no tmap event -> assist's own (unset)
      # camera / section / bump (sign-bearing event)
      bump_active = self.resolver.speed_limit > 0. and self.resolver.tmap_ahead_is_bump
      # bump override-adopt: if the driver presses the gas while we slow for a bump, capture the
      # speed they reach and hold it as the bump pass speed (only rises) so there is no yank-down
      # after they lift off. Cameras are enforcement, so this is bump-only. Clears with the event.
      if bump_active:
        if long_override:
          self._bump_override_speed = max(self._bump_override_speed, v_ego)
      else:
        self._bump_override_speed = 0.
      if self.resolver.speed_limit > 0.:
        if bump_active:
          v_limit = max(self.resolver.speed_limit_final, self._bump_override_speed)
          end_s = self.resolver.tmap_bump_time
          decel_rate = self.resolver.tmap_bump_decel_rate
        else:
          v_limit = self.resolver.speed_limit_final
          end_s = self.resolver.tmap_ctrl_end
          decel_rate = self.resolver.tmap_decel_rate
        dd = max(0., self.resolver.distance - v_limit * end_s)
        tmap_target = min(tmap_target, max(v_limit, (v_limit ** 2 + 2.0 * decel_rate * dd) ** 0.5))
      # turn / intersection (separate TBT channel, so it never shows as a speed-limit sign).
      # Uses the resolver's odometry-smoothed turn speed/distance.
      if self.resolver.tmap_turn_speed > 0.:
        v_turn = self.resolver.tmap_turn_speed
        dd = max(0., self.resolver.tmap_turn_dist - v_turn * self.resolver.tmap_turn_end)
        tmap_target = min(tmap_target, max(v_turn, (v_turn ** 2 + 2.0 * self.resolver.tmap_turn_decel_rate * dd) ** 0.5))
      targets[LongitudinalPlanSource.speedLimitAssist] = (tmap_target, a_ego)

    self.source = min(targets, key=lambda k: targets[k][0])
    self.output_v_target, self.output_a_target = targets[self.source]
    return self.output_v_target, self.output_a_target

  def _tmap_event_accel(self, v_ego: float, v_target: float, distance: float, end_s: float, decel_rate: float) -> float:
    # carrot curve's implied (constant) deceleration to reach v_target at the carrot margin point.
    # It self-eases to 0 as v_ego -> v_target and steepens if we are behind the curve, but is
    # capped at the configured decel rate so the slowdown stays smooth (the rate setting controls
    # firmness instead of slamming to the comfort floor). TMAP_DECEL_ACCEL_FLOOR is a safety bound.
    if v_ego <= v_target + 0.1:
      return 0.0  # no decel needed
    decel_dist = max(1.0, distance - v_target * end_s)
    a_carrot = (v_target ** 2 - v_ego ** 2) / (2.0 * decel_dist)
    return max(a_carrot, -decel_rate, TMAP_DECEL_ACCEL_FLOOR)

  def tmap_decel_accel(self, v_ego: float, a_target: float) -> float:
    # Command the carrot-curve deceleration for whichever TMAP event is ahead so if2's MPC follows
    # it smoothly -- the v_target cap alone is chased too loosely (camera felt imprecise, turn felt
    # like a brake). Each event is capped at its own rate: camera (tmap_decel_rate), bump (firmer),
    # turn (gentler, so a turn eases in naturally). We take the most-binding decel, then min with
    # the MPC accel so a closer lead can still brake harder. Gated on use_tmap (base unaffected).
    if not self.resolver.use_tmap:
      return a_target

    accels = []
    # camera / section / bump (sign-bearing event)
    if self.resolver.speed_limit > 0.:
      if self.resolver.tmap_ahead_is_bump:
        v_limit = max(self.resolver.speed_limit_final, self._bump_override_speed)
        end_s = self.resolver.tmap_bump_time
        decel_rate = self.resolver.tmap_bump_decel_rate
      else:
        v_limit = self.resolver.speed_limit_final
        end_s = self.resolver.tmap_ctrl_end
        decel_rate = self.resolver.tmap_decel_rate
      accels.append(self._tmap_event_accel(v_ego, v_limit, self.resolver.distance, end_s, decel_rate))
    # turn / intersection (its own gentle rate so it eases in instead of feeling like a brake)
    if self.resolver.tmap_turn_speed > 0.:
      accels.append(self._tmap_event_accel(v_ego, self.resolver.tmap_turn_speed, self.resolver.tmap_turn_dist,
                                           self.resolver.tmap_turn_end, self.resolver.tmap_turn_decel_rate))

    accels = [a for a in accels if a < 0.0]
    if not accels:
      return a_target
    return min(a_target, min(accels))

  def update(self, sm: messaging.SubMaster) -> None:
    self.events_sp.clear()
    self.dec.update(sm)
    self.e2e_alerts_helper.update(sm, self.events_sp)

  def publish_longitudinal_plan_sp(self, sm: messaging.SubMaster, pm: messaging.PubMaster) -> None:
    plan_sp_send = messaging.new_message('longitudinalPlanSP')

    plan_sp_send.valid = sm.all_checks(service_list=['carState', 'controlsState'])

    longitudinalPlanSP = plan_sp_send.longitudinalPlanSP
    longitudinalPlanSP.longitudinalPlanSource = self.source
    longitudinalPlanSP.vTarget = float(self.output_v_target)
    longitudinalPlanSP.aTarget = float(self.output_a_target)
    longitudinalPlanSP.events = self.events_sp.to_msg()

    # Dynamic Experimental Control
    dec = longitudinalPlanSP.dec
    dec.state = DecState.blended if self.dec.mode() == 'blended' else DecState.acc
    dec.enabled = self.dec.enabled()
    dec.active = self.dec.active()

    # Smart Cruise Control
    smartCruiseControl = longitudinalPlanSP.smartCruiseControl
    # Vision Control
    sccVision = smartCruiseControl.vision
    sccVision.state = self.scc.vision.state
    sccVision.vTarget = float(self.scc.vision.output_v_target)
    sccVision.aTarget = float(self.scc.vision.output_a_target)
    sccVision.currentLateralAccel = float(self.scc.vision.current_lat_acc)
    sccVision.maxPredictedLateralAccel = float(self.scc.vision.max_pred_lat_acc)
    sccVision.enabled = self.scc.vision.is_enabled
    sccVision.active = self.scc.vision.is_active
    # Map Control
    sccMap = smartCruiseControl.map
    sccMap.state = self.scc.map.state
    sccMap.vTarget = float(self.scc.map.output_v_target)
    sccMap.aTarget = float(self.scc.map.output_a_target)
    sccMap.enabled = self.scc.map.is_enabled
    sccMap.active = self.scc.map.is_active

    # Speed Limit
    speedLimit = longitudinalPlanSP.speedLimit
    resolver = speedLimit.resolver
    resolver.speedLimit = float(self.resolver.speed_limit)
    resolver.speedLimitLast = float(self.resolver.speed_limit_last)
    resolver.speedLimitFinal = float(self.resolver.speed_limit_final)
    resolver.speedLimitFinalLast = float(self.resolver.speed_limit_final_last)
    resolver.speedLimitValid = self.resolver.speed_limit_valid
    resolver.speedLimitLastValid = self.resolver.speed_limit_last_valid
    resolver.speedLimitOffset = float(self.resolver.speed_limit_offset)
    resolver.distToSpeedLimit = float(self.resolver.distance)
    resolver.source = self.resolver.source
    assist = speedLimit.assist
    assist.state = self.sla.state
    assist.enabled = self.sla.is_enabled
    assist.active = self.sla.is_active
    assist.vTarget = float(self.sla.output_v_target)
    assist.aTarget = float(self.sla.output_a_target)

    # E2E Alerts
    e2eAlerts = longitudinalPlanSP.e2eAlerts
    e2eAlerts.greenLightAlert = self.e2e_alerts_helper.green_light_alert
    e2eAlerts.leadDepartAlert = self.e2e_alerts_helper.lead_depart_alert

    pm.send('longitudinalPlanSP', plan_sp_send)
