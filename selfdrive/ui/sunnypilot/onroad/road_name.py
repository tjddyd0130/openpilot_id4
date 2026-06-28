"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget


class RoadNameRenderer(Widget):
  def __init__(self):
    super().__init__()
    self.road_name = ""
    self.is_metric = False
    self.font_demi = gui_app.font(FontWeight.SEMI_BOLD)
    # tjddyd: road names from TMAP are Korean. draw_text_ex only falls back to unifont
    # when the UI *language* is Korean, so pick unifont ourselves whenever the name has
    # any non-ASCII (Hangul) char -- otherwise Inter has no glyph and it breaks into boxes.
    self.font_unifont = gui_app.font(FontWeight.UNIFONT)

  def update(self):
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      return

    self.is_metric = ui_state.is_metric

    if sm.updated["liveMapDataSP"]:
      lmd = sm["liveMapDataSP"]
      self.road_name = lmd.roadName

  def _render(self, rect: rl.Rectangle):
    if not self.road_name or not ui_state.road_name_toggle:
      return

    text = self.road_name
    font = self.font_unifont if any(ord(c) > 0x7F for c in text) else self.font_demi
    text_size = measure_text_cached(font, text, 46)

    padding = 40
    rect_width = max(200, min(text_size.x + padding, rect.width - 40))

    road_rect = rl.Rectangle(rect.x + rect.width / 2 - rect_width / 2, rect.y - 4, rect_width, 60)

    rl.draw_rectangle_rounded(road_rect, 0.2, 10, rl.Color(0, 0, 0, 120))

    max_text_width = road_rect.width - 20
    if text_size.x > max_text_width:
      while text_size.x > max_text_width and len(text) > 3:
        text = text[:-1]
        text_size = measure_text_cached(font, text + "...", 46)
      text = text + "..."

    sz = measure_text_cached(font, text, 46)
    origin = rl.Vector2(road_rect.x + road_rect.width / 2 - sz.x / 2, road_rect.y + road_rect.height / 2 - sz.y / 2)
    rl.draw_text_ex(font, text, origin, 46, 0, rl.Color(255, 255, 255, 200))
