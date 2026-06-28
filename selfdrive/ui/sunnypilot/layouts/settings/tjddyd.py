"""
Korea (tjddyd) VW ID.4 (MEB) opt-in convenience features.

These toggles only expose params. The runtime behaviour is gated to
VW MEB (CP.brand == 'volkswagen' and CP.flags & VolkswagenFlags.MEB) in the
controls code, so enabling them has no effect on other platforms.

DisableDM is the exception: driver monitoring runs device-wide
and cannot be gated per car, so its description carries a safety warning.

Text is bilingual: Korean is shown when the device language is Korean
(LanguageSetting == ko), English otherwise. Hangul renders via unifont
(the full Hangul block is baked into unifont.fnt, see assets/fonts/process.py).
The items are split into sub-tabs (Navi / Safety / Convenience) shown as a
button row at the top of the panel.
"""
import pyray as rl

from openpilot.common.params import Params, UnknownKeyName
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.button import Button, ButtonStyle
from openpilot.system.ui.widgets.list_view import toggle_item, text_item
from openpilot.system.ui.widgets.scroller_tici import Scroller
from openpilot.system.ui.lib.application import gui_app
from openpilot.system.ui.lib.multilang import multilang
from openpilot.selfdrive.ui.ui_state import ui_state

if gui_app.sunnypilot_ui():
  from openpilot.system.ui.sunnypilot.widgets.list_view import toggle_item_sp as toggle_item

from openpilot.system.ui.sunnypilot.widgets.list_view import option_item_sp


def L(en: str, ko: str) -> str:
  """Pick Korean when the device language is Korean, else English."""
  return ko if multilang.language == "ko" else en


# Sub-tab categories
CAT_NAV = "nav"
CAT_SAFETY = "safety"
CAT_CONV = "conv"

CATEGORIES = [
  (CAT_NAV, lambda: L("Navi", "내비")),
  (CAT_SAFETY, lambda: L("Safety", "안전")),
  (CAT_CONV, lambda: L("Convenience", "편의")),
]

# TMAP (carrot AutoNavi) numeric options. Ranges ported from carrot
# (selfdrive/carrot_settings.json). Fields: param, en_title, ko_title, en_desc, ko_desc,
# min, max, step, category.
OPTIONS = [
  ("AutoNaviSpeedCtrlMode",
   "Nav deceleration mode", "내비 감속 모드",
   "What to slow down for. 0: off  1: speed cameras  2: + speed bumps  3: + mobile cameras",
   "무엇에 대해 감속할지. 0: 끔  1: 과속카메라  2: + 방지턱  3: + 이동식 카메라",
   0, 3, 1, CAT_NAV),
  ("AutoNaviSpeedSafetyFactor",
   "Camera limit factor (%)", "카메라 제한 배율 (%)",
   "Slow to the camera limit x this percent (e.g. 105 = 5% over the posted limit).",
   "카메라 제한속도 × 이 비율로 감속(예: 105 = 제한속도보다 5% 높게).",
   80, 120, 1, CAT_NAV),
  ("AutoNaviSpeedDecelRate",
   "Camera decel rate (x0.01 m/s2)", "카메라 감속 강도 (x0.01 m/s²)",
   "Deceleration strength toward a camera. Lower = gentler and starts braking from farther away.",
   "카메라를 향한 감속 강도. 낮을수록 부드럽고 더 먼 곳에서부터 제동을 시작합니다.",
   50, 300, 10, CAT_NAV),
  ("AutoNaviSpeedCtrlEnd",
   "Camera finish margin (s)", "카메라 도달 여유 (초)",
   "Reach the camera limit this many seconds before the camera.",
   "카메라보다 이 초만큼 앞서 제한속도에 도달합니다.",
   3, 20, 1, CAT_NAV),
  ("AutoNaviSpeedBumpSpeed",
   "Speed bump pass speed (km/h)", "방지턱 통과 속도 (km/h)",
   "Target speed to pass over a speed bump.",
   "방지턱을 넘는 목표 속도.",
   10, 100, 5, CAT_NAV),
  ("AutoNaviSpeedBumpTime",
   "Bump finish margin (s)", "방지턱 도달 여유 (초)",
   "Reach the bump pass speed this many seconds before the bump.",
   "방지턱보다 이 초만큼 앞서 통과 속도에 도달합니다.",
   1, 50, 1, CAT_NAV),
  ("AutoNaviSpeedBumpDecelRate",
   "Bump decel rate (x0.01 m/s2)", "방지턱 감속 강도 (x0.01 m/s²)",
   "Separate from cameras. Higher = firmer braking that starts LATER / closer to the bump "
   "(lower = gentler, starts from farther away). Press the gas while it slows for a bump to "
   "take it at your speed; that speed is then kept until the bump passes.",
   "카메라와 별개. 높을수록 더 늦게/방지턱에 가까이서 단단하게 제동(낮을수록 부드럽고 더 먼 곳에서 시작). "
   "방지턱 감속 중 가속 페달을 밟으면 그 속도로 넘어가며, 그 속도는 방지턱을 지날 때까지 유지됩니다.",
   50, 350, 10, CAT_NAV),
  ("AutoNaviCountDownMode",
   "Nav alert countdown", "내비 알림 카운트다운",
   "0: none  1: turn point + speed  2: turn point + speed + bumps",
   "0: 없음  1: 회전 지점 + 속도  2: 회전 지점 + 속도 + 방지턱",
   0, 2, 1, CAT_NAV),
  ("AutoRoadSpeedLimitOffset",
   "Road limit offset", "도로 제한속도 보정",
   "Road speed limit + this value. -1 disables.",
   "도로 제한속도 + 이 값. -1이면 비활성화.",
   -1, 100, 1, CAT_NAV),
  ("AutoTurnControl",
   "Turn / intersection slowdown", "회전 / 교차로 감속",
   "Slow down before turns from nav guidance (TBT). 0: off  1: on",
   "내비 안내(TBT)에 따라 회전 전에 감속합니다. 0: 끔  1: 켬",
   0, 1, 1, CAT_NAV),
  ("AutoTurnControlSpeedTurn",
   "Turn pass speed (km/h)", "회전 통과 속도 (km/h)",
   "Target speed through an actual left/right/u-turn.",
   "실제 좌/우회전·유턴을 통과하는 목표 속도.",
   10, 60, 5, CAT_NAV),
  ("AutoTurnControlTurnEnd",
   "Turn finish margin (s)", "회전 도달 여유 (초)",
   "Reach the turn speed this many seconds before the turn.",
   "회전보다 이 초만큼 앞서 회전 속도에 도달합니다.",
   1, 20, 1, CAT_NAV),
  ("AutoTurnControlDecelRate",
   "Turn decel rate (x0.01 m/s2)", "회전 감속 강도 (x0.01 m/s²)",
   "How firmly to slow for a turn. Lower = gentler / eases in earlier (less like braking); "
   "higher = firmer and later. Separate from the camera rate.",
   "회전 시 제동 강도. 낮을수록 부드럽고 더 일찍 천천히 들어감(제동 느낌 덜함); 높을수록 단단하고 늦게. "
   "카메라 감속과 별개.",
   50, 200, 10, CAT_NAV),
  ("AutoTurnControlStartDist",
   "Turn slowdown start distance (m)", "회전 감속 시작 거리 (m)",
   "How close to an actual turn before slowing begins (carrot atc_start_dist). Smaller = starts "
   "later / nearer the turn (no more braking from far away); larger = starts earlier. "
   "Forks/rotaries start farther out automatically, scaled by the road limit.",
   "실제 회전까지 얼마나 가까워졌을 때 감속을 시작할지(carrot atc_start_dist). 작을수록 더 늦게/회전에 "
   "가까이서 시작(먼 곳에서 미리 제동 안 함); 클수록 더 일찍 시작. 분기/회전교차로는 도로 제한속도에 "
   "따라 자동으로 더 먼 곳에서 시작합니다.",
   30, 200, 10, CAT_NAV),
  ("BumpClusterEvent",
   "Bump cluster glyph (ACC_Events code)", "방지턱 계기판 아이콘 (ACC_Events 코드)",
   "Which cluster event icon a speed bump uses (no speed-limit sign, just the icon + live decel "
   "km/h). The icon for each code is not documented, so try values on the road to find one that is "
   "not confusing. Known: 5=camera sign, 6=curve, 9=intersection. 0 = no bump display.",
   "방지턱이 사용할 계기판 이벤트 아이콘(제한속도 표지 없이 아이콘 + 실시간 감속 km/h만). 각 코드의 "
   "아이콘은 문서화되어 있지 않으니 도로에서 값을 바꿔보며 헷갈리지 않는 것을 찾으세요. 알려진 값: "
   "5=카메라 표지, 6=커브, 9=교차로. 0 = 방지턱 표시 안 함.",
   0, 15, 1, CAT_NAV),
  ("AlertVolume",
   "openpilot alert volume (%)", "openpilot 경고음 볼륨 (%)",
   "Overall openpilot alert sound volume. Lower if alerts are too loud. Floored at 30% so safety "
   "alerts (e.g. forward-collision warning) stay audible.",
   "openpilot 경고음 전체 볼륨. 경고음이 너무 크면 낮추세요. 안전 경고(예: 전방 충돌 경고)가 들리도록 "
   "최소 30%로 제한됩니다.",
   30, 100, 5, CAT_SAFETY),
  ("MebStopDistance",
   "VW MEB: Stop distance behind lead (x0.1 m)", "VW MEB: 앞차 뒤 정지 거리 (x0.1 m)",
   "VW MEB only: how far behind a stopped lead the car comes to rest, in 0.1 m units "
   "(45 = 4.5 m; stock openpilot is 6.0 m = 60). This is a live solver parameter, so it takes "
   "effect without a rebuild once the new solver is built. Lower = stops closer; this is the "
   "rear-end safety margin, so keep it sensible (min 3.0 m). Requires openpilot longitudinal.",
   "VW MEB 전용: 정지한 앞차 뒤로 몇 m 떨어져 정지할지, 0.1m 단위(45 = 4.5m; 순정 openpilot은 "
   "6.0m = 60). 실시간 솔버 파라미터라 새 솔버가 빌드되면 재빌드 없이 적용됩니다. 낮을수록 더 가까이 "
   "정지; 추돌 안전 여유이니 적정하게 유지하세요(최소 3.0m). openpilot 종방향 제어가 필요합니다.",
   30, 60, 1, CAT_SAFETY),
]

# Toggles. Fields: param -> (en_title, ko_title, en_desc, ko_desc, icon, category).
TOGGLES = {
  "AirConditioner": (
    "VW MEB: A/C temp & pressure (onroad)", "VW MEB: 에어컨 온도·압력 (주행화면)",
    "VW MEB only: show A/C refrigerant pressure (bar) and DC-DC temperature "
    "(used as outlet temp) above the driver monitor while driving.",
    "VW MEB 전용: 주행 중 운전자 감시 카메라 위에 에어컨 냉매 압력(bar)과 DC-DC 온도"
    "(토출 온도로 사용)를 표시합니다.",
    "speed_limit.png", CAT_CONV,
  ),
  "AutoGasSyncSpeed": (
    "VW MEB: Gas sync (auto set speed)", "VW MEB: 가속 동기화 (설정속도 자동)",
    "VW MEB only: if you press the accelerator (held ~0.4s+) and go faster than the set speed, "
    "the set speed auto-syncs up to your current speed. Works only with openpilot longitudinal "
    "(e.g. DEC on); has no effect on stock ACC.",
    "VW MEB 전용: 가속 페달을 약 0.4초 이상 밟아 설정 속도보다 빠르게 주행하면 설정 속도가 현재 "
    "속도까지 자동으로 올라갑니다. openpilot 종방향 제어(예: DEC 켜짐)에서만 동작하며 순정 ACC에는 "
    "영향이 없습니다.",
    "speed_limit.png", CAT_CONV,
  ),
  "EnableStalkBigStep": (
    "VW MEB: Stalk big step (2nd detent)", "VW MEB: 스토크 큰 단계 (2단)",
    "VW MEB only: push the cruise stalk to the 2nd detent (GRA_Tip_Stufe_2) to change the set "
    "speed by a big step - the same amount as a long press (default x5, or your Custom ACC "
    "long-press increment). Requires openpilot longitudinal (e.g. DEC on).",
    "VW MEB 전용: 크루즈 스토크를 2단(GRA_Tip_Stufe_2)까지 밀면 설정 속도가 큰 단위로 바뀝니다 — "
    "길게 누른 것과 동일(기본 x5, 또는 사용자 지정 ACC 길게누름 증가량). openpilot 종방향 제어"
    "(예: DEC 켜짐)가 필요합니다.",
    "speed_limit.png", CAT_CONV,
  ),
  "Mads": (
    "MADS - always-on steering (shortcut)", "MADS - 상시 조향 (바로가기)",
    "MADS (always-on steering) shortcut: keeps lateral/steering engaged independent of cruise. "
    "Same setting as Steering > MADS.",
    "MADS(상시 조향) 바로가기: 크루즈와 무관하게 횡방향/조향을 계속 작동시킵니다. 조향 > MADS "
    "설정과 동일합니다.",
    "chffr_wheel.png", CAT_CONV,
  ),
  "DynamicExperimentalControl": (
    "DEC - dynamic experimental long (shortcut)", "DEC - 동적 실험 종방향 (바로가기)",
    "DEC (Dynamic Experimental Control) shortcut: auto-switches between ACC and experimental "
    "longitudinal by situation. Same as Cruise > DEC. Gas-sync and big-step need this on.",
    "DEC(동적 실험 제어) 바로가기: 상황에 따라 ACC와 실험적 종방향 제어를 자동 전환합니다. "
    "크루즈 > DEC와 동일. 가속 동기화와 큰 단계 기능은 이 설정이 켜져 있어야 합니다.",
    "speed_limit.png", CAT_CONV,
  ),
  "EnableWebTerminal": (
    "Web terminal :6999 (own risk)", "웹 터미널 :6999 (본인 책임)",
    "WARNING: starts the carrot recovery web terminal on port 6999 (runs while driving and "
    "parked). Browse to http://<device-ip>:6999 for a terminal + git recovery UI. Anyone on the "
    "same network gets an unauthenticated root shell, so only enable on trusted networks. "
    "Applied after reboot.",
    "경고: carrot 복구용 웹 터미널을 6999 포트에서 실행합니다(주행/주차 중 모두 동작). "
    "http://<기기-IP>:6999 로 접속하면 터미널과 git 복구 UI를 사용할 수 있습니다. 같은 네트워크의 "
    "누구나 인증 없이 root 셸을 얻을 수 있으니 신뢰할 수 있는 네트워크에서만 켜세요. 재부팅 후 "
    "적용됩니다.",
    "chffr_wheel.png", CAT_CONV,
  ),
  "EnableTmapSpeedLimit": (
    "T map / KakaoNavi speed limit (:7713)", "T맵 / 카카오내비 제한속도 (:7713)",
    "Use the T map / KakaoNavi phone nav as a speed-limit and speed-camera source (carrot SDI, "
    "HTTP :7713 / UDP :7706). Enabling turns on speed-limit control, routes it to map data and "
    "disables OSM map download. The phone app must broadcast data to the device. Applied after "
    "reboot.",
    "T맵/카카오내비 휴대폰 내비를 제한속도·과속카메라 정보원으로 사용합니다(carrot SDI, "
    "HTTP :7713 / UDP :7706). 켜면 제한속도 제어가 활성화되고 지도 데이터로 연결되며 OSM 지도 "
    "다운로드가 꺼집니다. 휴대폰 앱이 기기로 데이터를 송출해야 합니다. 재부팅 후 적용됩니다.",
    "speed_limit.png", CAT_NAV,
  ),
  "DisableDM": (
    "Driver monitoring OFF (own risk)", "운전자 감시 끄기 (본인 책임)",
    "WARNING: turns off driver monitoring (attention alerts and forced slowdown). Same as "
    "carrot's DisableDM - the DM model/daemon is not run and DM events are suppressed. This is "
    "a device-wide setting and cannot be limited to one car. You are always responsible for "
    "controlling the vehicle. Applied after reboot. Use at your own risk.",
    "경고: 운전자 감시(주의 경고 및 강제 감속)를 끕니다. carrot의 DisableDM과 동일 — DM 모델/데몬을 "
    "실행하지 않고 DM 이벤트를 억제합니다. 이 설정은 기기 전체에 적용되며 특정 차량에만 제한할 수 "
    "없습니다. 차량 제어 책임은 항상 운전자에게 있습니다. 재부팅 후 적용됩니다. 본인 책임 하에 "
    "사용하세요.",
    "chffr_wheel.png", CAT_SAFETY,
  ),
  "DisableClusterFcw": (
    "VW MEB: hide cluster collision warning", "VW MEB: 계기판 충돌 경고 숨기기",
    "VW MEB only: when the lead gets close, do not show the red collision warning on the "
    "instrument cluster (and its beep). openpilot still shows its own on-screen warning. "
    "Requires the opendbc cluster change.",
    "VW MEB 전용: 앞차가 가까워져도 계기판에 빨간 충돌 경고(및 경고음)를 표시하지 않습니다. "
    "openpilot은 화면에 자체 경고를 계속 표시합니다. opendbc 계기판 변경이 필요합니다.",
    "speed_limit.png", CAT_SAFETY,
  ),
}


class TjddydLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    self._active_category = CAT_NAV
    self._tab_buttons = {
      cat: Button(title_fn, click_callback=(lambda c=cat: self._select_category(c)),
                  button_style=ButtonStyle.NORMAL, font_size=44)
      for cat, title_fn in CATEGORIES
    }

    # Build toggles (split per category below)
    self._toggles = {}
    cat_items: dict[str, list[Widget]] = {CAT_NAV: [], CAT_SAFETY: [], CAT_CONV: []}
    for param, (en_t, ko_t, en_d, ko_d, icon, cat) in TOGGLES.items():
      toggle = toggle_item(
        (lambda e=en_t, k=ko_t: L(e, k)),
        (lambda e=en_d, k=ko_d: L(e, k)),
        self._params.get_bool(param),
        callback=lambda state, p=param: self._toggle_callback(state, p),
        icon=icon,
      )
      self._toggles[param] = toggle
      cat_items[cat].append(toggle)

    # Live TMAP connection status row (updated ~2x/sec from the TmapStatus param)
    self._tmap_status_text = L("Off (toggle disabled)", "꺼짐 (토글 비활성)")
    self._status_counter = 0
    self._tmap_status_item = text_item(
      lambda: L("T map connection", "T맵 연결"),
      lambda: self._tmap_status_text,
    )
    cat_items[CAT_NAV].append(self._tmap_status_item)

    # Numeric options
    self._option_items = []
    for param, en_t, ko_t, en_d, ko_d, vmin, vmax, step, cat in OPTIONS:
      # MebStopDistance is a live solver param available regardless of the TMAP toggle;
      # the AutoNavi/TBT options only take effect when the TMAP source is enabled.
      enabled = (lambda: True) if param == "MebStopDistance" else \
                (lambda: ui_state.params.get_bool("EnableTmapSpeedLimit"))
      opt = option_item_sp(
        title=(lambda e=en_t, k=ko_t: L(e, k)),
        param=param,
        min_value=vmin,
        max_value=vmax,
        description=(lambda e=en_d, k=ko_d: L(e, k)),
        value_change_step=step,
        enabled=enabled,
      )
      self._option_items.append(opt)
      cat_items[cat].append(opt)

    self._scrollers = {
      cat: Scroller(cat_items[cat], line_separator=True, spacing=0)
      for cat in cat_items
    }

  def _select_category(self, cat: str):
    self._active_category = cat

  def _update_state(self):
    # Throttle the TMAP status param read to ~2x/sec (avoid per-frame IPC)
    self._status_counter += 1
    if self._status_counter % 30 == 0:
      if not self._params.get_bool("EnableTmapSpeedLimit"):
        self._tmap_status_text = L("Off (toggle disabled)", "꺼짐 (토글 비활성)")
      else:
        s = self._params.get("TmapStatus")
        self._tmap_status_text = s if s else L("Waiting - no phone data", "대기 중 - 휴대폰 데이터 없음")

  def show_event(self):
    super().show_event()
    for scroller in self._scrollers.values():
      scroller.show_event()
    # Always show the description under each item so it explains what the feature does.
    for toggle in self._toggles.values():
      toggle.show_description(True)
    for opt in self._option_items:
      opt.show_description(True)
    self._update_toggles()

  def _update_toggles(self):
    # Use ui_state's params cache (refreshed in own thread at 5Hz) to avoid extra IPC roundtrips
    ui_state.update_params()
    for param in self._toggles:
      self._toggles[param].action_item.set_state(ui_state.params.get_bool(param))

  def _render(self, rect):
    # Sub-tab button row at the top, active category highlighted
    tab_h = 90
    gap = 16
    n = len(self._tab_buttons)
    tab_w = (rect.width - gap * (n - 1)) / n
    for i, (cat, _title) in enumerate(CATEGORIES):
      btn = self._tab_buttons[cat]
      btn.set_button_style(ButtonStyle.PRIMARY if cat == self._active_category else ButtonStyle.NORMAL)
      btn.render(rl.Rectangle(rect.x + i * (tab_w + gap), rect.y, tab_w, tab_h))

    content = rl.Rectangle(rect.x, rect.y + tab_h + gap, rect.width, rect.height - tab_h - gap)
    self._scrollers[self._active_category].render(content)

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
