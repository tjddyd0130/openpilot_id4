"""
한국어 UI 및 TMAP/OSM 동적 도로명용 Noto Sans KR 런타임 폰트.

unifont(16px 비트맵) 대신 벡터 폰트를 사용한다. 글리프는 문자열 단위로
점진적으로 로드하며, UI 시작 시 대량 preload는 하지 않는다(부팅 지연 방지).
"""
from __future__ import annotations

import os
from importlib.resources import as_file, files

import pyray as rl

from openpilot.common.basedir import BASEDIR
from openpilot.common.swaglog import cloudlog
from openpilot.system.ui.lib.multilang import multilang

# 온로드 표시 크기(40~90px)에 맞춘 베이스 로드 크기
BASE_FONT_SIZE = 72
_EXTRA_CHARS = "–‑✓×°§•X⚙✕◀▶✔⌫⇧␣○●↳çêüñ€£¥"
FONT_CANDIDATES = (
  "NotoSansKR-Regular.otf",
  "NotoSansKR-Regular.ttf",
  "NotoSansCJKkr-Regular.otf",
)


def has_hangul(text: str) -> bool:
  return any(
    "\uac00" <= c <= "\ud7a3"
    or "\u1100" <= c <= "\u11ff"
    or "\u3130" <= c <= "\u318f"
    for c in text
  )


def _resolve_font_path() -> str | None:
  font_dir = files("openpilot.selfdrive").joinpath("assets/fonts")
  for name in FONT_CANDIDATES:
    candidate = font_dir.joinpath(name)
    try:
      with as_file(candidate) as path:
        if path.exists():
          return path.as_posix()
    except FileNotFoundError:
      continue

  for name in FONT_CANDIDATES:
    path = os.path.join(BASEDIR, "selfdrive", "assets", "fonts", name)
    if os.path.isfile(path):
      return path
  return None


class KoreanFont:
  def __init__(self) -> None:
    self._codepoints: set[int] = set(range(32, 127)) | {ord(c) for c in _EXTRA_CHARS}
    self._font: rl.Font | None = None
    self._font_path = _resolve_font_path()

  def available(self) -> bool:
    return self._font_path is not None

  def ensure(self, text: str) -> rl.Font:
    if not self.available():
      raise FileNotFoundError("NotoSansKR font not found in selfdrive/assets/fonts")

    needed = {ord(c) for c in text}
    if self._font is not None and needed <= self._codepoints:
      return self._font

    self._codepoints |= needed
    return self._reload()

  def _reload(self) -> rl.Font:
    if self._font is not None and self._font.texture.id != 0:
      rl.unload_font(self._font)

    cps = tuple(sorted(self._codepoints))
    cp_buffer = rl.ffi.new("int[]", cps)
    cp_ptr = rl.ffi.cast("int *", cp_buffer)
    self._font = rl.load_font_ex(self._font_path, BASE_FONT_SIZE, cp_ptr, len(cps))

    if self._font.texture.id == 0:
      raise RuntimeError("Failed to load NotoSansKR font")

    rl.gen_texture_mipmaps(self._font.texture)
    rl.set_texture_filter(self._font.texture, rl.TextureFilter.TEXTURE_FILTER_TRILINEAR)
    return self._font


_manager: KoreanFont | None = None


def get_korean_font() -> KoreanFont:
  global _manager
  if _manager is None:
    _manager = KoreanFont()
  return _manager


def font_for_text(font: rl.Font, text: str) -> rl.Font:
  """문자열에 한글이 있을 때만 Noto Sans KR. 영어·숫자는 Inter 유지."""
  if has_hangul(text):
    try:
      return get_korean_font().ensure(text)
    except (FileNotFoundError, RuntimeError) as e:
      cloudlog.error(f"NotoSansKR render fallback: {e}")
      return font

  if multilang.requires_unifont():
    from openpilot.system.ui.lib.application import FontWeight, gui_app
    return gui_app.font(FontWeight.UNIFONT)
  return font
