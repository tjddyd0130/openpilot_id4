#!/usr/bin/env python3
# tjddyd: reorder MEB cluster ACC_Events priority to camera > bump > curve/turn > ACC-standby.
# Run from the opendbc repo root, then commit. Idempotent (skips if already applied).
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


# 1) mebcan: move the standstill (event 3) check from FIRST to LAST so camera/bump/curve win.
edit(D + "mebcan.py", [
  ("  if esp_hold and acc_hud_control == ACC_HUD_ACTIVE:\n"
   "    acc_event = 3 # acc ready message at standstill\n"
   "  elif acc_hud_control in (ACC_HUD_ACTIVE, ACC_HUD_OVERRIDE) and speed_limit_predicative:",
   "  if acc_hud_control in (ACC_HUD_ACTIVE, ACC_HUD_OVERRIDE) and speed_limit_predicative:",
   "  if acc_hud_control in (ACC_HUD_ACTIVE, ACC_HUD_OVERRIDE) and speed_limit_predicative:"),
  ("  elif acc_hud_control in (ACC_HUD_ACTIVE, ACC_HUD_OVERRIDE) and speed_limit:\n"
   "    acc_event = 5 # acc limited by speed limit by camera (recently detected)\n"
   "\n"
   "  return acc_event",
   "  elif acc_hud_control in (ACC_HUD_ACTIVE, ACC_HUD_OVERRIDE) and speed_limit:\n"
   "    acc_event = 5 # acc limited by speed limit by camera (recently detected)\n"
   "  elif esp_hold and acc_hud_control == ACC_HUD_ACTIVE:\n"
   "    acc_event = 3 # tjddyd: acc ready at standstill -- lowest priority (camera/bump/curve win)\n"
   "\n"
   "  return acc_event",
   "tjddyd: acc ready at standstill -- lowest priority"),
])

# 2) carcontroller: drop the camera live-speed (the camera glyph ignores the number) and let a speed
#    bump override a curve/turn -> net priority camera > bump > curve/turn > ACC-standby.
edit(D + "carcontroller.py", [
  ("        # tjddyd: live event speed shown in ACC_Event_Wunschgeschw, separate from the speed-limit\n"
   "        # sign (ACC_Tempolimit). Camera: keep the sign at the recognised limit, show the live ramp\n"
   "        # km/h by the glyph. Speed bump: no sign, use the configurable BumpClusterEvent glyph + the\n"
   "        # live bump decel km/h. carcontroller display only; never caps speed.\n"
   "        event_speed = None\n"
   "        if sl_active and not sl_predicative_active and CS._tmap_camera_speed > 0.:\n"
   "          event_speed = CS._tmap_camera_speed\n"
   "        elif not sl_active and not sl_predicative_active and CS._tmap_bump_speed > 0. and CS._bump_cluster_event > 0:\n"
   "          acc_hud_event = CS._bump_cluster_event\n"
   "          event_speed = CS._tmap_bump_speed\n"
   "          speed_limit = 0\n",
   "        # tjddyd: cluster event priority camera > bump > curve/turn > ACC-standby. The camera\n"
   "        # glyph ignores the speed number, so only the bump shows a live km/h. A speed bump (no\n"
   "        # sign) overrides a curve/turn via the configurable BumpClusterEvent glyph + decel km/h.\n"
   "        event_speed = None\n"
   "        if not sl_active and CS._tmap_bump_speed > 0. and CS._bump_cluster_event > 0:\n"
   "          acc_hud_event = CS._bump_cluster_event\n"
   "          event_speed = CS._tmap_bump_speed\n"
   "          speed_limit = 0\n",
   "cluster event priority camera > bump > curve/turn > ACC-standby"),
])

print("done")
