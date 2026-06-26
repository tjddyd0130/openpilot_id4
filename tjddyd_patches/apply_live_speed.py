#!/usr/bin/env python3
# tjddyd: apply the "live camera/bump target km/h on the cluster" change directly (string
# replacement) instead of a git patch -- the carcontroller has whitespace-only blank lines that
# break `git am`. Run from the opendbc repo root, then commit. Idempotent (skips if already done).
import sys

D = "opendbc/car/volkswagen/"


def edit(path, repls):
  s = open(path).read()
  for old, new, tag in repls:
    if tag in s:
      print(f"  - {path}: '{tag}' already present, skipping")
      continue
    if old not in s:
      print(f"  ! {path}: anchor not found: {old[:60]!r}")
      sys.exit(1)
    s = s.replace(old, new, 1)
    print(f"  + {path}: applied '{tag}'")
  open(path, "w").write(s)


CC_INS = (
  "        # tjddyd: live event speed shown in ACC_Event_Wunschgeschw, separate from the speed-limit\n"
  "        # sign (ACC_Tempolimit). Camera: keep the sign at the recognised limit, show the live ramp\n"
  "        # km/h by the glyph. Speed bump: no sign, use the configurable BumpClusterEvent glyph + the\n"
  "        # live bump decel km/h. carcontroller display only; never caps speed.\n"
  "        event_speed = None\n"
  "        if sl_active and not sl_predicative_active and CS._tmap_camera_speed > 0.:\n"
  "          event_speed = CS._tmap_camera_speed\n"
  "        elif not sl_active and not sl_predicative_active and CS._tmap_bump_speed > 0. and CS._bump_cluster_event > 0:\n"
  "          acc_hud_event = CS._bump_cluster_event\n"
  "          event_speed = CS._tmap_bump_speed\n"
  "          speed_limit = 0\n"
)
CC_ANCHOR = "        can_sends.append(self.CCS.create_acc_hud_control("

edit(D + "carcontroller.py", [
  (CC_ANCHOR, CC_INS + CC_ANCHOR, "event_speed = None"),
  ("fcw_alert, acc_hud_event, speed_limit))",
   "fcw_alert, acc_hud_event, speed_limit, event_speed))",
   "speed_limit, event_speed))"),
])

edit(D + "carstate.py", [
  ("    self._tmap_turn_speed = 0.\n    self.force_rhd_for_bsm = False",
   "    self._tmap_turn_speed = 0.\n"
   "    # tjddyd: live camera / speed-bump target speeds (m/s) + bump cluster glyph code, shown by\n"
   "    # carcontroller in ACC_Event_Wunschgeschw (camera keeps its sign; bump has no sign)\n"
   "    self._tmap_camera_speed = 0.\n    self._tmap_bump_speed = 0.\n    self._bump_cluster_event = 0\n"
   "    self.force_rhd_for_bsm = False",
   "self._tmap_camera_speed = 0."),
  ('          self._tmap_turn_speed = int(self._tmap_params.get("TmapTurnSpeed", return_default=True)) * CV.KPH_TO_MS\n',
   '          self._tmap_turn_speed = int(self._tmap_params.get("TmapTurnSpeed", return_default=True)) * CV.KPH_TO_MS\n'
   '          self._tmap_camera_speed = int(self._tmap_params.get("TmapCameraSpeed", return_default=True)) * CV.KPH_TO_MS\n'
   '          self._tmap_bump_speed = int(self._tmap_params.get("TmapBumpSpeed", return_default=True)) * CV.KPH_TO_MS\n'
   '          self._bump_cluster_event = int(self._tmap_params.get("BumpClusterEvent", return_default=True))\n',
   'self._tmap_params.get("TmapCameraSpeed"'),
  ("          self._tmap_turn_speed = 0.\n",
   "          self._tmap_turn_speed = 0.\n          self._tmap_camera_speed = 0.\n"
   "          self._tmap_bump_speed = 0.\n          self._bump_cluster_event = 0\n",
   "self._tmap_camera_speed = 0."),
])

edit(D + "mebcan.py", [
  ("fcw_alert, acc_event, speed_limit):",
   "fcw_alert, acc_event, speed_limit, event_speed=None):",
   "speed_limit, event_speed=None):"),
  ('    "ACC_Event_Wunschgeschw":        speed_limit * CV.MS_TO_KPH,',
   '    "ACC_Event_Wunschgeschw":        (speed_limit if event_speed is None else event_speed) * CV.MS_TO_KPH,',
   "if event_speed is None else event_speed"),
])

print("done")
