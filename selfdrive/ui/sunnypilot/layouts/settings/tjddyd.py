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
    "경고: 운전자 감시(주의 경고·강제감속)를 끕니다. 당근 DisableDM 방식 그대로 — DM "
    "모델/데몬을 아예 실행하지 않고 DM 이벤트를 억제합니다. 디바이스 전역 설정이라 특정 "
    "차종만 가릴 수 없습니다. 차량 통제 책임은 항상 운전자에게 있습니다. 재부팅 후 적용. "
    "본인 책임 하에 사용하세요."
  ),
  "AutoGasSyncSpeed": tr_noop(
    "VW MEB 전용: 가속 페달을 밟아(약 0.4초 이상 유지) 속도가 설정속도보다 빨라지면, "
    "설정속도를 현재 속도로 자동 동기화합니다. openpilot 롱컨(예: DEC 켜짐)에서만 작동하며, "
    "순정 ACC에서는 무효입니다."
  ),
  "EnableStalkBigStep": tr_noop(
    "VW MEB 전용: 크루즈 스토크 2단(GRA_Tip_Stufe_2)으로 설정속도를 크게(5단위) 조절합니다. "
    "openpilot 롱컨(예: DEC 켜짐) 필요. ※현재는 opendbc 미반영으로 동작하지 않습니다(켜도 무해)."
  ),
  "EnableWebTerminal": tr_noop(
    "경고: 6999 포트에 carrot 복구 웹 터미널을 띄웁니다(주행/주차 모두 실행). 브라우저로 "
    "http://<디바이스IP>:6999 접속 시 터미널 + git 복구 UI를 사용할 수 있습니다. 같은 "
    "네트워크의 누구나 인증 없이 root 셸에 접근할 수 있으니 신뢰된 네트워크에서만 켜세요. 재부팅 후 적용."
  ),
  "Mads": tr_noop(
    "MADS(상시 조향) 바로가기: 크루즈와 무관하게 조향(횡방향)을 유지합니다. "
    "Steering > MADS와 동일한 설정입니다."
  ),
  "DynamicExperimentalControl": tr_noop(
    "DEC(동적 실험 롱컨) 바로가기: 상황에 따라 일반/실험 롱컨을 자동으로 전환합니다. "
    "Cruise > DEC와 동일한 설정. 가스싱크·빅스텝을 쓰려면 이 항목을 켜야 합니다."
  ),
  "EnableTmapSpeedLimit": tr_noop(
    "T맵/카카오내비 폰 내비를 제한속도·과속카메라 소스로 사용합니다(carrot SDI, UDP :7706). "
    "켜면 속도제한 제어가 켜지고 정책이 map-data로 설정되며, OSM 지도 다운로드는 꺼집니다. "
    "폰 앱이 디바이스로 데이터를 브로드캐스트해야 작동합니다. 재부팅 후 적용."
  ),
}


class TjddydLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    # param, title, desc, icon
    self._toggle_defs = {
      "DisableDM": (
        lambda: tr("운전자 감시 끄기 (본인 책임)"),
        DESCRIPTIONS["DisableDM"],
        "chffr_wheel.png",
      ),
      "AutoGasSyncSpeed": (
        lambda: tr("VW MEB: 가스 싱크 (설정속도 자동맞춤)"),
        DESCRIPTIONS["AutoGasSyncSpeed"],
        "speed_limit.png",
      ),
      "EnableStalkBigStep": (
        lambda: tr("VW MEB: 스토크 빅스텝 (2단)"),
        DESCRIPTIONS["EnableStalkBigStep"],
        "speed_limit.png",
      ),
      "EnableWebTerminal": (
        lambda: tr("웹 터미널 :6999 (본인 책임)"),
        DESCRIPTIONS["EnableWebTerminal"],
        "chffr_wheel.png",
      ),
      "Mads": (
        lambda: tr("MADS - 상시 조향 (바로가기)"),
        DESCRIPTIONS["Mads"],
        "chffr_wheel.png",
      ),
      "DynamicExperimentalControl": (
        lambda: tr("DEC - 동적 실험 롱컨 (바로가기)"),
        DESCRIPTIONS["DynamicExperimentalControl"],
        "speed_limit.png",
      ),
      "EnableTmapSpeedLimit": (
        lambda: tr("T맵/카카오내비 제한속도 (:7706)"),
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
