"""
tjddyd VW ID.4 (MEB) opt-in convenience features.

These toggles only expose params. The runtime behaviour is gated to
VW MEB (CP.brand == 'volkswagen' and CP.flags & VolkswagenFlags.MEB) in the
controls code, so enabling them has no effect on other platforms.

DisableDM is the exception: driver monitoring runs device-wide
and cannot be gated per car, so its description carries a safety warning.

All UI text is intentionally English: the device UI font does not render Hangul.
"""
from openpilot.common.params import Params, UnknownKeyName
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import toggle_item, text_item
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.selfdrive.ui.ui_state import ui_state

if gui_app.sunnypilot_ui():
  from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp as toggle_item

from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp

# TMAP (carrot AutoNavi) numeric options: (param, title, description, min, max, step)
# Ranges ported from carrot (selfdrive/carrot_settings.json).
TMAP_OPTIONS = [
  ("AutoNaviSpeedCtrlMode", "Nav deceleration mode",
   "What to slow down for. 0: off  1: speed cameras  2: + speed bumps  3: + mobile cameras", 0, 3, 1),
  ("AutoNaviSpeedSafetyFactor", "Camera limit factor (%)",
   "Slow to the camera limit x this percent (e.g. 105 = 5% over the posted limit).", 80, 120, 1),
  ("AutoNaviSpeedDecelRate", "Camera decel rate (x0.01 m/s2)",
   "Deceleration strength toward a camera. Lower = gentler and starts braking from farther away.", 50, 300, 10),
  ("AutoNaviSpeedCtrlEnd", "Camera finish margin (s)",
   "Reach the camera limit this many seconds before the camera.", 3, 20, 1),
  ("AutoNaviSpeedBumpSpeed", "Speed bump pass speed (km/h)",
   "Target speed to pass over a speed bump.", 10, 100, 5),
  ("AutoNaviSpeedBumpTime", "Bump finish margin (s)",
   "Reach the bump pass speed this many seconds before the bump.", 1, 50, 1),
  ("AutoNaviSpeedBumpDecelRate", "Bump decel rate (x0.01 m/s2)",
   "Separate from cameras. Higher = firmer braking that starts LATER / closer to the bump "
   "(lower = gentler, starts from farther away). Press the gas while it slows for a bump to "
   "take it at your speed; that speed is then kept until the bump passes.", 50, 350, 10),
  ("AutoNaviCountDownMode", "Nav alert countdown",
   "0: none  1: turn point + speed  2: turn point + speed + bumps", 0, 2, 1),
  ("AutoRoadSpeedLimitOffset", "Road limit offset",
   "Road speed limit + this value. -1 disables.", -1, 100, 1),
  ("AutoTurnControl", "Turn / intersection slowdown",
   "Slow down before turns from nav guidance (TBT). 0: off  1: on", 0, 1, 1),
  ("AutoTurnControlSpeedTurn", "Turn pass speed (km/h)",
   "Target speed through an actual left/right/u-turn.", 10, 60, 5),
  ("AutoTurnControlTurnEnd", "Turn finish margin (s)",
   "Reach the turn speed this many seconds before the turn.", 1, 20, 1),
  ("AutoTurnControlDecelRate", "Turn decel rate (x0.01 m/s2)",
   "How firmly to slow for a turn. Lower = gentler / eases in earlier (less like braking); "
   "higher = firmer and later. Separate from the camera rate.", 50, 200, 10),
  ("AutoTurnControlStartDist", "Turn slowdown start distance (m)",
   "How close to an actual turn before slowing begins (carrot atc_start_dist). Smaller = starts "
   "later / nearer the turn (no more braking from far away); larger = starts earlier. "
   "Forks/rotaries start farther out automatically, scaled by the road limit.", 30, 200, 10),
  ("BumpClusterEvent", "Bump cluster glyph (ACC_Events code)",
   "Which cluster event icon a speed bump uses (no speed-limit sign, just the icon + live decel "
   "km/h). The icon for each code is not documented, so try values on the road to find one that is "
   "not confusing. Known: 5=camera sign, 6=curve, 9=intersection. 0 = no bump display.", 0, 15, 1),
  ("AlertVolume", "openpilot alert volume (%)",
   "Overall openpilot alert sound volume. Lower if alerts are too loud. Floored at 30% so safety "
   "alerts (e.g. forward-collision warning) stay audible.", 30, 100, 5),
]

# Description constants (English)
DESCRIPTIONS = {
  "DisableDM": tr_noop(
    "WARNING: turns off driver monitoring (attention alerts and forced slowdown). Same as "
    "carrot's DisableDM - the DM model/daemon is not run and DM events are suppressed. This is "
    "a device-wide setting and cannot be limited to one car. You are always responsible for "
    "controlling the vehicle. Applied after reboot. Use at your own risk."
  ),
  "AutoGasSyncSpeed": tr_noop(
    "VW MEB only: if you press the accelerator (held ~0.4s+) and go faster than the set speed, "
    "the set speed auto-syncs up to your current speed. Works only with openpilot longitudinal "
    "(e.g. DEC on); has no effect on stock ACC."
  ),
  "EnableStalkBigStep": tr_noop(
    "VW MEB only: push the cruise stalk to the 2nd detent (GRA_Tip_Stufe_2) to change the set "
    "speed by a big step - the same amount as a long press (default x5, or your Custom ACC "
    "long-press increment). Requires openpilot longitudinal (e.g. DEC on)."
  ),
  "EnableWebTerminal": tr_noop(
    "WARNING: starts the carrot recovery web terminal on port 6999 (runs while driving and "
    "parked). Browse to http://<device-ip>:6999 for a terminal + git recovery UI. Anyone on the "
    "same network gets an unauthenticated root shell, so only enable on trusted networks. "
    "Applied after reboot."
  ),
  "Mads": tr_noop(
    "MADS (always-on steering) shortcut: keeps lateral/steering engaged independent of cruise. "
    "Same setting as Steering > MADS."
  ),
  "DynamicExperimentalControl": tr_noop(
    "DEC (Dynamic Experimental Control) shortcut: auto-switches between ACC and experimental "
    "longitudinal by situation. Same as Cruise > DEC. Gas-sync and big-step need this on."
  ),
  "EnableTmapSpeedLimit": tr_noop(
    "Use the T map / KakaoNavi phone nav as a speed-limit and speed-camera source (carrot SDI, "
    "HTTP :7713 / UDP :7706). Enabling turns on speed-limit control, routes it to map data and "
    "disables OSM map download. The phone app must broadcast data to the device. Applied after "
    "reboot."
  ),
  "MebStopDistance": tr_noop(
    "VW MEB only: how far behind a stopped lead the car comes to rest, in 0.1 m units "
    "(45 = 4.5 m; stock openpilot is 6.0 m = 60). This is a live solver parameter, so it takes "
    "effect without a rebuild once the new solver is built. Lower = stops closer; this is the "
    "rear-end safety margin, so keep it sensible (min 3.0 m). Requires openpilot longitudinal."
  ),
  "DisableClusterFcw": tr_noop(
    "VW MEB only: when the lead gets close, do not show the red collision warning on the "
    "instrument cluster (and its beep). openpilot still shows its own on-screen warning. "
    "Requires the opendbc cluster change."
  ),
}


class TjddydLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    # param, title, desc, icon
    self._toggle_defs = {
      "DisableDM": (
        lambda: tr("Driver monitoring OFF (own risk)"),
        DESCRIPTIONS["DisableDM"],
        "chffr_wheel.png",
      ),
      "AutoGasSyncSpeed": (
        lambda: tr("VW MEB: Gas sync (auto set speed)"),
        DESCRIPTIONS["AutoGasSyncSpeed"],
        "speed_limit.png",
      ),
      "EnableStalkBigStep": (
        lambda: tr("VW MEB: Stalk big step (2nd detent)"),
        DESCRIPTIONS["EnableStalkBigStep"],
        "speed_limit.png",
      ),
      "EnableWebTerminal": (
        lambda: tr("Web terminal :6999 (own risk)"),
        DESCRIPTIONS["EnableWebTerminal"],
        "chffr_wheel.png",
      ),
      "Mads": (
        lambda: tr("MADS - always-on steering (shortcut)"),
        DESCRIPTIONS["Mads"],
        "chffr_wheel.png",
      ),
      "DynamicExperimentalControl": (
        lambda: tr("DEC - dynamic experimental long (shortcut)"),
        DESCRIPTIONS["DynamicExperimentalControl"],
        "speed_limit.png",
      ),
      "EnableTmapSpeedLimit": (
        lambda: tr("T map / KakaoNavi speed limit (:7713)"),
        DESCRIPTIONS["EnableTmapSpeedLimit"],
        "speed_limit.png",
      ),
      "DisableClusterFcw": (
        lambda: tr("VW MEB: hide cluster collision warning"),
        DESCRIPTIONS["DisableClusterFcw"],
        "speed_limit.png",
      ),
    }

    self._toggles = {}
    for param, (title, desc, icon) in self._toggle_defs.items():
      toggle = toggle_item(
        title,
        desc,
        self._params.get_bool(param),
        callback=lambda state, p=param: self._toggle_callback(state, p),
        icon=icon,
      )
      toggle.set_description(lambda og_desc=toggle.description: tr(og_desc))
      self._toggles[param] = toggle

    # Live TMAP connection status row (updated ~2x/sec from the TmapStatus param)
    self._tmap_status_text = tr("Off (toggle disabled)")
    self._status_counter = 0
    self._tmap_status_item = text_item(
      lambda: tr("T map connection"),
      lambda: self._tmap_status_text,
    )

    # TMAP/KakaoNavi numeric options (carrot AutoNavi params), only active when TMAP is on
    items = list(self._toggles.values())
    items.append(self._tmap_status_item)
    self._option_items = []
    for opt_param, opt_title, opt_descr, opt_min, opt_max, opt_step in TMAP_OPTIONS:
      opt = option_item_sp(
        title=(lambda t=opt_title: tr(t)),
        param=opt_param,
        min_value=opt_min,
        max_value=opt_max,
        description=(lambda d=opt_descr: tr(d)),
        value_change_step=opt_step,
        enabled=lambda: ui_state.params.get_bool("EnableTmapSpeedLimit"),
      )
      self._option_items.append(opt)
      items.append(opt)

    # Standstill stopping distance behind a lead (runtime solver param, live-tunable on MEB)
    stop_opt = option_item_sp(
      title=(lambda: tr("VW MEB: Stop distance behind lead (x0.1 m)")),
      param="MebStopDistance",
      min_value=30,
      max_value=60,
      description=(lambda: tr(DESCRIPTIONS["MebStopDistance"])),
      value_change_step=1,
      enabled=lambda: True,
    )
    self._option_items.append(stop_opt)
    items.append(stop_opt)

    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _update_state(self):
    # Throttle the TMAP status param read to ~2x/sec (avoid per-frame IPC)
    self._status_counter += 1
    if self._status_counter % 30 == 0:
      if not self._params.get_bool("EnableTmapSpeedLimit"):
        self._tmap_status_text = tr("Off (toggle disabled)")
      else:
        s = self._params.get("TmapStatus")
        self._tmap_status_text = s if s else tr("Waiting - no phone data")

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
    # Always show the description under each item so it explains what the feature does.
    for toggle in self._toggles.values():
      toggle.show_description(True)
    for opt in getattr(self, "_option_items", []):
      opt.show_description(True)
    self._update_toggles()

  def _update_toggles(self):
    # Use ui_state's params cache (refreshed in own thread at 5Hz) to avoid extra IPC roundtrips
    ui_state.update_params()
    for param in self._toggle_defs:
      self._toggles[param].action_item.set_state(ui_state.params.get_bool(param))

  def _render(self, rect):
    self._scroller.render(rect)

  def _toggle_callback(self, state: bool, param: str):
    try:
      self._params.put_bool(param, state)
    except UnknownKeyName:
      pass

    # Enabling the TMAP source wires up the whole speed-limit pipeline so it "just
    # works": Speed Limit Control on, resolver routed to map data. The camera
    # deceleration itself is fully automatic and handled in the longitudinal planner
    # (caps the target at the live TMAP camera limit, no stalk confirmation), so we use
    # warning mode -- the onroad sign still shows but the Assist confirm/arrow state
    # machine stays disabled. RoadNameToggle shows the TMAP road name = connection cue.
    if param == "EnableTmapSpeedLimit" and state:
      try:
        self._params.put_bool("EnableSpeedLimitControl", True)
        self._params.put("SpeedLimitPolicy", 1)  # Policy.map_data_only
        self._params.put("SpeedLimitMode", 2)     # Mode.warning (sign shown; auto-decel via planner)
        self._params.put_bool("RoadNameToggle", True)  # show TMAP road name onroad = connection indicator
      except UnknownKeyName:
        pass
