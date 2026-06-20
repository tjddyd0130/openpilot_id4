"""
tjddyd VW ID.4 (MEB) opt-in convenience features (Phase 1).

These toggles only expose params. The runtime behaviour is gated to
VW MEB (CP.brand == 'volkswagen' and CP.flags & VolkswagenFlags.MEB) in the
controls code, so enabling them has no effect on other platforms.

DisableDriverMonitoring is the exception: driver monitoring runs device-wide
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

# Description constants
DESCRIPTIONS = {
  "DisableDriverMonitoring": tr_noop(
    "WARNING: Disables the driver monitoring system (attention alerts and forced "
    "deceleration). This is device-wide and cannot be limited to a single car. "
    "You remain fully responsible for the vehicle at all times. Use at your own risk."
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
}


class TjddydLayout(Widget):
  def __init__(self):
    super().__init__()
    self._params = Params()

    # param, title, desc, icon
    self._toggle_defs = {
      "DisableDriverMonitoring": (
        lambda: tr("VW MEB: Disable Driver Monitoring (USE AT OWN RISK)"),
        DESCRIPTIONS["DisableDriverMonitoring"],
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

    self._scroller = Scroller(list(self._toggles.values()), line_separator=True, spacing=0)

  def _update_state(self):
    return

  def show_event(self):
    super().show_event()
    self._scroller.show_event()
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
