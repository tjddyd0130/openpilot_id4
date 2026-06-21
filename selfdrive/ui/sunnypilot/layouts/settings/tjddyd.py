"""
tjddyd VW ID.4 (MEB) opt-in convenience features (Phase 1).

These toggles only expose params. The runtime behaviour is gated to
VW MEB (CP.brand == 'volkswagen' and CP.flags & VolkswagenFlags.MEB) in the
controls code, so enabling them has no effect on other platforms.

DisableDM is the exception: driver monitoring runs device-wide
and cannot be gated per car, so its description carries a safety warning.
"""
from openpilot.common.params import Params, UnknownKeyName
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.list_view import toggle_item
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import tr, tr_noop
from openpilot.selfdrive.ui.ui_state import ui_state

if gui_app.sunnypilot_ui():
  from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp as toggle_item

from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp

# TMAP (carrot AutoNavi) numeric options: (param, title, description, min, max, step)
# Titles/descriptions and ranges ported from carrot (selfdrive/carrot_settings.json).
TMAP_OPTIONS = [
  ("AutoNaviSpeedCtrlMode", "네비게이션 감속모드",
   "0: 감속안함  1: 과속카메라  2: +과속방지턱  3: +이동식카메라", 0, 3, 1),
  ("AutoNaviSpeedSafetyFactor", "과속카메라 제한속도 적용율(%)",
   "과속카메라에서 도로제한속도 × 설정값(%)으로 감속합니다", 80, 120, 1),
  ("AutoNaviSpeedDecelRate", "과속카메라 감속율(×0.01 m/s²)",
   "낮을수록 더 멀리서부터 천천히 감속합니다", 50, 300, 10),
  ("AutoNaviSpeedCtrlEnd", "과속카메라 감속 완료시간(초)",
   "감속 종료 시점을 설정합니다", 3, 20, 1),
  ("AutoNaviSpeedBumpSpeed", "과속방지턱 통과속도(km/h)",
   "과속방지턱을 통과할 목표 속도", 10, 100, 5),
  ("AutoNaviSpeedBumpTime", "사고방지턱 감속완료 시점(초)",
   "사고방지턱 감속을 끝낼 시점", 1, 50, 1),
  ("AutoNaviCountDownMode", "네비 알림 카운트다운",
   "0: 알림없음  1: 턴지점+속도  2: 턴지점+속도+방지턱", 0, 2, 1),
  ("AutoRoadSpeedLimitOffset", "도로제한속도 맞춤(offset)",
   "도로제한속도 + 설정값. -1이면 미적용", -1, 100, 1),
]

# Description constants
DESCRIPTIONS = {
  "DisableDM": tr_noop(
    "WARNING: Disables the driver monitoring system (attention alerts and forced "
    "deceleration) using carrot's DisableDM mechanism: the DM model/daemon are not "
    "started and DM events are suppressed. This is device-wide and cannot be limited "
    "to a single car. You remain fully responsible for the vehicle at all times. "
    "Takes effect after a reboot. Use at your own risk."
  ),
  "AutoGasSyncSpeed": tr_noop(
    "VW MEB only: When you press the accelerator above the set cruise speed, the set "
    "speed is automatically synced up to your current speed when you release. "
    "Requires openpilot longitudinal control (e.g. DEC enabled); has no effect with stock ACC."
  ),
  "EnableStalkBigStep": tr_noop(
    "VW MEB only: Use the cruise stalk's second detent (GRA_Tip_Stufe_2) for a big "
    "set-speed step (rounded to 5). Requires openpilot longitudinal control "
    "(e.g. DEC enabled); has no effect with stock ACC."
  ),
  "EnableWebTerminal": tr_noop(
    "WARNING: Starts the carrot recovery web terminal on port 6999 (runs both while "
    "driving and parked). Open http://<device-ip>:6999 in a browser for a terminal "
    "and git recovery UI. This exposes an UNAUTHENTICATED root shell to anyone on the "
    "same network - only enable on trusted networks. Takes effect after a reboot."
  ),
  "Mads": tr_noop(
    "Shortcut to MADS (Modular Assistive Driving System): keep steering (lateral) "
    "engaged independently of cruise. Same setting as Steering > MADS."
  ),
  "DynamicExperimentalControl": tr_noop(
    "Shortcut to Dynamic Experimental Control (DEC): automatically switch between "
    "chill and experimental longitudinal as the scene requires. Same setting as Cruise > DEC."
  ),
  "EnableTmapSpeedLimit": tr_noop(
    "Use the T map / KakaoNavi phone navigation as the speed-limit and speed-camera "
    "source (carrot SDI broadcast over UDP :7706). Enabling this also turns on Speed "
    "Limit Control and sets the speed-limit policy to map-data, and disables the OSM "
    "map download. The phone app must broadcast to the device. Takes effect after a reboot."
  ),
}


class TjddydLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    # param, title, desc, icon
    self._toggle_defs = {
      "DisableDM": (
        lambda: tr("Disable Driver Monitoring (USE AT OWN RISK)"),
        DESCRIPTIONS["DisableDM"],
        "chffr_wheel.png",
      ),
      "AutoGasSyncSpeed": (
        lambda: tr("VW MEB: Auto Gas Sync Set Speed"),
        DESCRIPTIONS["AutoGasSyncSpeed"],
        "speed_limit.png",
      ),
      "EnableStalkBigStep": (
        lambda: tr("VW MEB: Stalk Big Step (2nd detent)"),
        DESCRIPTIONS["EnableStalkBigStep"],
        "speed_limit.png",
      ),
      "EnableWebTerminal": (
        lambda: tr("Web Terminal on :6999 (USE AT OWN RISK)"),
        DESCRIPTIONS["EnableWebTerminal"],
        "chffr_wheel.png",
      ),
      "Mads": (
        lambda: tr("MADS - Always-on Steering (shortcut)"),
        DESCRIPTIONS["Mads"],
        "chffr_wheel.png",
      ),
      "DynamicExperimentalControl": (
        lambda: tr("Dynamic Experimental Control (shortcut)"),
        DESCRIPTIONS["DynamicExperimentalControl"],
        "speed_limit.png",
      ),
      "EnableTmapSpeedLimit": (
        lambda: tr("TMAP/KakaoNavi Speed Limit (:7706)"),
        DESCRIPTIONS["EnableTmapSpeedLimit"],
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

    # TMAP/KakaoNavi numeric options (carrot AutoNavi params), only active when TMAP is on
    items = list(self._toggles.values())
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

    self._scroller = Scroller(items, line_separator=True, spacing=0)

  def _update_state(self):
    return

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
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

    # Enabling the TMAP source wires up the rest of the speed-limit pipeline so it
    # "just works": turn on Speed Limit Control and route the resolver to map data.
    if param == "EnableTmapSpeedLimit" and state:
      try:
        self._params.put_bool("EnableSpeedLimitControl", True)
        self._params.put("SpeedLimitPolicy", "1")  # Policy.map_data_only
      except UnknownKeyName:
        pass
