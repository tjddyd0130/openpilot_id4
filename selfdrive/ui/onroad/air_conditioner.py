import time

import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.ui import UI_BORDER_SIZE
from openpilot.selfdrive.ui.onroad.driver_state import BTN_SIZE
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

_DM_OFFSET = UI_BORDER_SIZE + BTN_SIZE // 2
_DM_RADIUS = BTN_SIZE // 2


class AirConditioner(Widget):
  def __init__(self) -> None:
    super().__init__()
    self._params = Params()
    self._outlet_temperature: float = 0.0
    self._pressure: float = 0.0
    self._font: rl.Font = gui_app.font(FontWeight.SEMI_BOLD)
    self._panel_bg: rl.Color = rl.Color(0, 0, 0, 128)
    self._label_color: rl.Color = rl.Color(200, 200, 200, 255)
    self._value_color: rl.Color = rl.Color(255, 255, 255, 255)
    self._font_size: int = 38
    self._is_rhd: bool = False
    self._display_enabled: bool = False
    self._param_update_time: float = 0.0
    self._update_params()

  def _update_params(self) -> None:
    self._param_update_time = time.monotonic()
    self._display_enabled = self._params.get_bool("AirConditioner")

  def _update_state(self) -> None:
    if time.monotonic() - self._param_update_time > 2.0:
      self._update_params()
    if not self._display_enabled:
      return
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self._outlet_temperature = 0.0
      self._pressure = 0.0
      return
    ac = sm["carState"].airConditionerDetails
    self._outlet_temperature = float(ac.outletTemperature)
    self._pressure = float(ac.pressure)
    if sm.recv_frame["driverMonitoringState"] > 0:
      self._is_rhd = bool(sm["driverMonitoringState"].isRHD)

  def _render(self, rect: rl.Rectangle) -> None:
    if not self._display_enabled:
      return
    rows = [("A/C Temp", f"{self._outlet_temperature:.1f} °C"), ("A/C Press", f"{self._pressure:.2f} bar")]
    padding, line_spacing, row_height = 20, 12, self._font_size + 12
    gap = 24
    content_width = max(measure_text_cached(self._font, l, self._font_size).x + gap + measure_text_cached(self._font, v, self._font_size).x for l, v in rows)
    panel_width = int(content_width + padding * 2)
    panel_height = int(row_height * len(rows) - line_spacing + padding * 2)
    dm_top = rect.y + rect.height - _DM_OFFSET - _DM_RADIUS
    y_start = int(dm_top - panel_height - 20)
    x_start = int(rect.x + rect.width - UI_BORDER_SIZE - panel_width if self._is_rhd else rect.x + UI_BORDER_SIZE)
    rl.draw_rectangle_rounded(rl.Rectangle(x_start, y_start, panel_width, panel_height), 0.15, 8, self._panel_bg)
    for i, (label, value) in enumerate(rows):
      base_y = float(y_start + padding + i * row_height)
      rl.draw_text_ex(self._font, label, rl.Vector2(float(x_start + padding), base_y), self._font_size, 0, self._label_color)
      value_w = measure_text_cached(self._font, value, self._font_size).x
      rl.draw_text_ex(self._font, value, rl.Vector2(float(x_start + panel_width - padding - value_w), base_y), self._font_size, 0, self._value_color)
