"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from cereal import car

from openpilot.common.params import Params

AudibleAlert = car.CarControl.HUDControl.AudibleAlert

ALERTS_ALWAYS_PLAY = {
  AudibleAlert.warningSoft,
  AudibleAlert.warningImmediate,
  AudibleAlert.promptDistracted,
  AudibleAlert.promptRepeat,
}


class QuietMode:
  def __init__(self):
    self.params = Params()
    self.enabled: bool = self.params.get_bool("QuietMode")
    # tjddyd: overall alert-volume scale (0.3 - 1.0); user lowers it when alerts are too loud.
    # Floored at 0.3 so safety alerts (e.g. FCW) stay audible.
    self.volume_scale: float = self._read_volume_scale()
    self._frame = 0

  def _read_volume_scale(self) -> float:
    try:
      return min(1.0, max(0.3, self.params.get("AlertVolume", return_default=True) * 0.01))
    except Exception:
      return 1.0

  def load_param(self) -> None:
    self._frame += 1
    if self._frame % 50 == 0:  # 2.5 seconds
      self.enabled = self.params.get_bool("QuietMode")
      self.volume_scale = self._read_volume_scale()

  def should_play_sound(self, current_alert: int) -> bool:
    """
    Check if a sound should be played based on the Quiet Mode setting
    and the current alert.
    """
    if not self.enabled:
      return bool(current_alert != AudibleAlert.none)

    return current_alert in ALERTS_ALWAYS_PLAY
