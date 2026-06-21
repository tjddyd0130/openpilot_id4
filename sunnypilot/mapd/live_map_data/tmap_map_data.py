"""
TMAP / KakaoNavi speed-limit + speed-camera adapter (tjddyd Phase 2).

A phone navigation app (T map / KakaoNavi with the carrot/SDI broadcast plugin)
broadcasts route-guidance JSON over UDP to port 7706. This adapter binds that
port, extracts only the speed-limit and speed-camera fields (nRoadLimitSpeed and
the nSdi* SDI block), and republishes them as the standard sunnypilot
``liveMapDataSP`` message so the existing speed-limit resolver and the instrument
cluster (ACC_Tempolimit) consume it with no further changes.

Only the speed-limit / camera subset of carrot's carrot_serv.py is ported here.
Turn-by-turn, ATC turns, curve speed, GPS path matching, FTP and the web server
are intentionally excluded.
"""
import json
import socket
import threading
import time

import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.sunnypilot.mapd.live_map_data.base_map_data import BaseMapData, MAX_SPEED_LIMIT

TMAP_UDP_PORT = 7706   # carrot carrot_man_port: bind here to receive the SDI broadcast
DATA_TIMEOUT = 3.0     # seconds; navigation data is considered stale after this

# carrot nSdiType values that carry a speed limit / fixed camera
SDI_LIMIT_TYPES = (0, 1, 2, 3, 4, 7, 8, 75, 76)


class TmapMapData(BaseMapData):
  def __init__(self):
    super().__init__()
    self._lock = threading.Lock()
    self._last_rx = 0.0

    # parsed navigation state (kph / metres)
    self.nRoadLimitSpeed = 0
    self.xSpdLimit = 0
    self.xSpdDist = 0
    self.xSpdType = -1
    self.roadName = ""
    self._nRoadLimitSpeed_counter = 0

    # AutoNavi params (carrot semantics, read live)
    self.autoNaviSpeedSafetyFactor = 1.05
    self.autoNaviSpeedCtrlMode = 2
    self.autoNaviSpeedBumpSpeed = 35.0

    threading.Thread(target=self._udp_thread, daemon=True).start()

  def _read_params(self) -> None:
    self.autoNaviSpeedSafetyFactor = float(self.params.get_int("AutoNaviSpeedSafetyFactor")) * 0.01
    self.autoNaviSpeedCtrlMode = self.params.get_int("AutoNaviSpeedCtrlMode")
    self.autoNaviSpeedBumpSpeed = float(self.params.get_int("AutoNaviSpeedBumpSpeed"))

  def _udp_thread(self) -> None:
    while True:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
          sock.settimeout(10)
          sock.bind(('0.0.0.0', TMAP_UDP_PORT))
          while True:
            try:
              data, _ = sock.recvfrom(4096)
            except socket.timeout:
              continue
            if not data:
              continue
            try:
              self._handle(json.loads(data.decode()))
            except Exception:
              continue
      except Exception:
        time.sleep(1)

  def _handle(self, j: dict) -> None:
    if not isinstance(j, dict) or "nRoadLimitSpeed" not in j:
      return
    self._read_params()

    def _i(v, d=0):
      return d if v is None else int(v)

    # road limit speed (carrot decode)
    nrl = int(j.get("nRoadLimitSpeed", 20))
    if nrl > 0:
      if nrl > 200:
        nrl = (nrl - 20) / 10
      elif nrl == 120:
        nrl = 115  # carrot: 120 -> 115 bugfix
    else:
      nrl = 30

    nSdiType = _i(j.get("nSdiType"), -1)
    nSdiSpeedLimit = _i(j.get("nSdiSpeedLimit"), 0)
    nSdiDist = _i(j.get("nSdiDist"), -1)
    nSdiBlockType = _i(j.get("nSdiBlockType"), -1)
    nSdiBlockDist = _i(j.get("nSdiBlockDist"), 0)
    nSdiPlusType = _i(j.get("nSdiPlusType"), -1)
    nSdiPlusDist = _i(j.get("nSdiPlusDist"), 0)
    roadcate = _i(j.get("roadcate"), 0)
    road_name = str(j.get("szPosRoadName") or "")
    if road_name == "null":
      road_name = ""

    with self._lock:
      # debounce road-limit changes (carrot: needs >5 stable updates)
      if self.nRoadLimitSpeed != nrl:
        self._nRoadLimitSpeed_counter += 1
        if self._nRoadLimitSpeed_counter > 5:
          self.nRoadLimitSpeed = nrl
          self._nRoadLimitSpeed_counter = 0
      else:
        self._nRoadLimitSpeed_counter = 0

      self.roadName = road_name

      # carrot _update_sdi: derive the upcoming camera/section limit
      if nSdiType in SDI_LIMIT_TYPES and nSdiSpeedLimit > 0 and self.autoNaviSpeedCtrlMode > 0:
        self.xSpdLimit = nSdiSpeedLimit * self.autoNaviSpeedSafetyFactor
        self.xSpdDist = nSdiDist
        self.xSpdType = nSdiType
        if nSdiBlockType in (2, 3):
          self.xSpdDist = nSdiBlockDist
          self.xSpdType = 4
        elif nSdiType == 7 and self.autoNaviSpeedCtrlMode < 3:  # mobile camera
          self.xSpdLimit = self.xSpdDist = 0
      elif (nSdiPlusType == 22 or nSdiType == 22) and roadcate > 1 and self.autoNaviSpeedCtrlMode >= 2:  # speed bump
        self.xSpdLimit = self.autoNaviSpeedBumpSpeed
        self.xSpdDist = nSdiPlusDist if nSdiPlusType == 22 else nSdiDist
        self.xSpdType = 22
      else:
        self.xSpdLimit = 0
        self.xSpdType = -1
        self.xSpdDist = 0

      self._last_rx = time.monotonic()

  def _fresh(self) -> bool:
    return (time.monotonic() - self._last_rx) < DATA_TIMEOUT

  def update_location(self) -> None:
    # TMAP provides the speed limit straight from the phone; no local GPS matching.
    return

  def get_current_speed_limit(self) -> float:
    with self._lock:
      if not self._fresh():
        return 0.0
      return float(self.nRoadLimitSpeed) * CV.KPH_TO_MS

  def get_next_speed_limit_and_distance(self) -> tuple[float, float]:
    with self._lock:
      if not self._fresh() or self.xSpdLimit <= 0:
        return 0.0, 0.0
      return float(self.xSpdLimit) * CV.KPH_TO_MS, float(max(self.xSpdDist, 0))

  def get_current_road_name(self) -> str:
    with self._lock:
      return self.roadName if self._fresh() else ""

  def publish(self) -> None:
    # Override BaseMapData.publish: validity follows fresh UDP data, not local GPS.
    speed_limit = self.get_current_speed_limit()
    next_speed_limit, next_speed_limit_distance = self.get_next_speed_limit_and_distance()

    mapd_sp_send = messaging.new_message('liveMapDataSP')
    mapd_sp_send.valid = self._fresh()
    live_map_data = mapd_sp_send.liveMapDataSP
    live_map_data.speedLimitValid = bool(MAX_SPEED_LIMIT > speed_limit > 0)
    live_map_data.speedLimit = speed_limit
    live_map_data.speedLimitAheadValid = bool(MAX_SPEED_LIMIT > next_speed_limit > 0)
    live_map_data.speedLimitAhead = next_speed_limit
    live_map_data.speedLimitAheadDistance = next_speed_limit_distance
    live_map_data.roadName = self.get_current_road_name()
    self.pm.send('liveMapDataSP', mapd_sp_send)
