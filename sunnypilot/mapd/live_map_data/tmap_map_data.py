"""
TMAP / KakaoNavi speed-limit + speed-camera adapter (tjddyd Phase 2).

A phone navigation app (modified T map / KakaoNavi) discovers this device via a
UDP "Carrot2" broadcast on :7705 and then delivers route-guidance JSON. Modern
apps POST it as {"rgdata": {...}} over HTTP to :7713; older ones send UDP to
:7706. Both paths feed the same parser, which extracts the speed-limit and
speed-camera fields (nRoadLimitSpeed and the nSdi* SDI block) and republishes
them as the standard sunnypilot ``liveMapDataSP`` message so the existing
speed-limit resolver consumes it with no further changes.

Only the speed-limit / camera subset of carrot's carrot_serv.py is ported here.
Turn-by-turn, ATC turns, curve speed, GPS path matching, FTP and the web server
are intentionally excluded.
"""
import fcntl
import json
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.sunnypilot.mapd.live_map_data.base_map_data import BaseMapData, MAX_SPEED_LIMIT

TMAP_UDP_PORT = 7706        # carrot carrot_man_port: legacy UDP SDI receiver
TMAP_BROADCAST_PORT = 7705  # carrot broadcast_port: announce the device here for discovery
TMAP_HTTP_PORT = 7713       # carrot navi_http_port: modern phone app POSTs rgdata here
DATA_TIMEOUT = 3.0          # seconds; navigation data is considered stale after this
MIN_VALID_SPEED_LIMIT = 20  # kph; below this the nav reports a sentinel (e.g. 10 = unknown)
DEBUG_DUMP = "/tmp/tmap_rgdata.json"  # last received rgdata, for inspection

SIOCGIFADDR = 0x8915        # get interface IP
SIOCGIFBRDADDR = 0x8919     # get interface broadcast address

# carrot nSdiType values that carry a speed limit / fixed camera
SDI_LIMIT_TYPES = (0, 1, 2, 3, 4, 7, 8, 75, 76)


class _NaviHandler(BaseHTTPRequestHandler):
  # The modern T map / KakaoNavi phone app POSTs route guidance to /api/navi/<version>
  # as {"rgdata": {...}}; rgdata carries the same fields the UDP path used.
  def do_POST(self):
    rgdata = None
    try:
      length = int(self.headers.get('Content-Length', 0))
      body = self.rfile.read(length) if length > 0 else b''
      obj = json.loads(body.decode('utf-8'))
      if isinstance(obj, dict) and isinstance(obj.get('rgdata'), dict):
        rgdata = obj['rgdata']
    except Exception:
      rgdata = None

    if rgdata is not None:
      try:
        self.server.tmap._handle(rgdata)
        self.server.tmap._remote_ip = self.client_address[0]
      except Exception:
        pass

    resp = json.dumps({"ok": rgdata is not None}).encode('utf-8')
    try:
      self.send_response(200)
      self.send_header('Content-Type', 'application/json')
      self.send_header('Content-Length', str(len(resp)))
      self.end_headers()
      self.wfile.write(resp)
    except Exception:
      pass

  def do_GET(self):
    try:
      self.send_response(200)
      self.send_header('Content-Length', '2')
      self.end_headers()
      self.wfile.write(b'ok')
    except Exception:
      pass

  def log_message(self, *args):
    pass  # silence access logging


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
    self._remote_ip = ""
    self._last_dump = 0.0

    # AutoNavi params (carrot semantics, read live)
    self.autoNaviSpeedSafetyFactor = 1.05
    self.autoNaviSpeedCtrlMode = 2
    self.autoNaviSpeedBumpSpeed = 35.0

    threading.Thread(target=self._udp_thread, daemon=True).start()
    threading.Thread(target=self._broadcast_thread, daemon=True).start()
    threading.Thread(target=self._http_thread, daemon=True).start()

  def _http_thread(self) -> None:
    # Modern phone app delivers rgdata via HTTP POST on :7713 (carrot navi_http_port).
    while True:
      try:
        httpd = ThreadingHTTPServer(('0.0.0.0', TMAP_HTTP_PORT), _NaviHandler)
        httpd.tmap = self
        httpd.serve_forever()
      except Exception:
        time.sleep(1)

  @staticmethod
  def _iface_addr(ioctl_code: int, ifname: str = "wlan0") -> str | None:
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(), ioctl_code,
                                            struct.pack('256s', ifname.encode()[:15]))[20:24])
    except Exception:
      return None

  def _broadcast_thread(self) -> None:
    # carrot device discovery: broadcast a "Carrot2" announcement on :7705 so the phone
    # nav app finds this device and starts sending SDI data to :7706.
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
      try:
        ip = self._iface_addr(SIOCGIFADDR) or ""
        bcast = self._iface_addr(SIOCGIFBRDADDR) or "255.255.255.255"
        msg = json.dumps({
          "Carrot2": self.params.get("Version") or "",
          "IsOnroad": self.params.get_bool("IsOnroad"),
          "CarrotRouteActive": False,
          "ip": ip,
          "port": TMAP_UDP_PORT,
          "navi_debug": 0,
          "navi_http_port": TMAP_HTTP_PORT,
          "log_carrot": "",
          "v_cruise_kph": 0,
          "carcruiseSpeed": 0,
          "v_ego_kph": 0,
          "tbt_dist": 0,
          "sdi_dist": 0,
          "active": False,
          "xState": 0,
          "trafficState": 0,
        }).encode("utf-8")
        for target in {bcast, "255.255.255.255"}:
          try:
            sock.sendto(msg, (target, TMAP_BROADCAST_PORT))
          except Exception:
            pass
      except Exception:
        pass
      time.sleep(1)

  def _read_params(self) -> None:
    self.autoNaviSpeedSafetyFactor = float(self.params.get("AutoNaviSpeedSafetyFactor", return_default=True)) * 0.01
    self.autoNaviSpeedCtrlMode = self.params.get("AutoNaviSpeedCtrlMode", return_default=True)
    self.autoNaviSpeedBumpSpeed = float(self.params.get("AutoNaviSpeedBumpSpeed", return_default=True))

  def _udp_thread(self) -> None:
    while True:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
          sock.settimeout(10)
          sock.bind(('0.0.0.0', TMAP_UDP_PORT))
          while True:
            try:
              data, addr = sock.recvfrom(4096)
            except socket.timeout:
              continue
            if not data:
              continue
            try:
              self._handle(json.loads(data.decode()))
              self._remote_ip = addr[0]
            except Exception:
              continue
      except Exception:
        time.sleep(1)

  def _handle(self, j: dict) -> None:
    if not isinstance(j, dict) or "nRoadLimitSpeed" not in j:
      return
    self._read_params()

    # debug: keep the last rgdata on disk (tmpfs) at ~1Hz for inspection
    now_dump = time.monotonic()
    if now_dump - self._last_dump > 1.0:
      self._last_dump = now_dump
      try:
        with open(DEBUG_DUMP, "w") as f:
          json.dump(j, f, ensure_ascii=False)
      except Exception:
        pass

    def _i(v, d=0):
      return d if v is None else int(v)

    # road limit speed (carrot decode)
    nrl = _i(j.get("nRoadLimitSpeed"), 0)
    if nrl > 200:
      nrl = int((nrl - 20) / 10)
    elif nrl == 120:
      nrl = 115  # carrot: 120 -> 115 bugfix
    if nrl < MIN_VALID_SPEED_LIMIT:
      nrl = 0  # sentinel / no posted limit -> treat as none

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
    # tjddyd (Korea, camera-centric): do NOT report the continuous road speed limit.
    # Returning 0 means the resolver applies no speed-limit cap normally; it only
    # switches to the camera/section limit (speedLimitAhead) when one is approaching,
    # so the sign appears and the car decelerates only at speed-camera zones.
    return 0.0

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

    # publish a human-readable status for the UI (tjddyd tab)
    with self._lock:
      if self._fresh():
        limit = f"{int(self.nRoadLimitSpeed)}km/h" if self.nRoadLimitSpeed >= MIN_VALID_SPEED_LIMIT else "없음"
        status = f"연결됨 · 제한 {limit} · {self._remote_ip}"
      else:
        status = "수신 없음 · 폰 앱/네트워크 확인"
    self.params.put("TmapStatus", status)
