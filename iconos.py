"""Iconos vectoriales (Lucide, licencia ISC) dibujados desde `assets/lucide.ttf` y teñidos con el color del tema.

Uso directo:    iconos.imagen("target", 18, color)     → CTkImage
Automático:     iconos.instalar()  hace que los botones y etiquetas cuyo texto EMPIEZA con un emoji conocido
                («🎯 Plan y meta») muestren en su lugar el icono equivalente. Lo que no esté en la tabla queda igual.
"""
import os
import sys

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from iconos_codigos import CODIGOS
from tema import C

ESCALA = 4                                   # se dibuja a 4× y se reduce: bordes suaves en pantallas con DPI alto
_TTF = None
_cache = {}

# emoji inicial → icono Lucide
EMOJI_A_ICONO = {
    "🏠": "house", "📚": "library", "🧭": "compass", "🧠": "brain", "🔎": "search", "🔍": "search", "🛠": "wrench",
    "📖": "book-open", "📕": "book", "📄": "file-text", "📑": "file-text", "🎯": "target", "💾": "save",
    "📤": "upload", "📁": "folder", "📂": "folder-open", "🃏": "layers", "✅": "circle-check", "☑": "square-check",
    "☐": "square", "📝": "notebook-pen", "✨": "sparkles", "🎓": "graduation-cap", "📌": "pin", "⏳": "hourglass",
    "⚙": "settings", "★": "star", "☆": "star", "🗑": "trash-2", "＋": "plus", "🔄": "refresh-cw", "▶": "play",
    "🌙": "moon", "💡": "lightbulb", "🎉": "party-popper", "📊": "chart-bar", "🤖": "bot", "🖍": "highlighter",
    "🏁": "flag", "🔔": "bell", "🔒": "lock", "🛡": "shield-check", "🗄": "database", "☁": "cloud",
    "🌐": "globe", "🔌": "plug", "🖧": "server", "📐": "ruler", "🏗": "hammer", "☕": "coffee", "🐍": "code-xml",
    "⚠": "triangle-alert", "✕": "x", "👋": "hand", "✎": "pencil", "✓": "check",
}
_VARIANTES = "️"                       # selector de emoji que acompaña a algunos caracteres


def _ruta_asset(nombre: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", nombre)


def _fuente(px: int):
    global _TTF
    if _TTF is None:
        _TTF = _ruta_asset("lucide.ttf")
    return ImageFont.truetype(_TTF, px)


def existe(nombre: str) -> bool:
    return nombre in CODIGOS


def imagen(nombre: str, tam: int = 18, color: str = None):
    """CTkImage cuadrada de `tam` px (lógicos) con el icono `nombre` del color pedido."""
    color = color or C["texto"]
    clave = (nombre, tam, color)
    if clave in _cache:
        return _cache[clave]
    px = tam * ESCALA
    lienzo = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    glifo = chr(CODIGOS[nombre])
    f = _fuente(int(px * 0.9))
    caja = f.getbbox(glifo)
    x = (px - (caja[2] - caja[0])) / 2 - caja[0]
    y = (px - (caja[3] - caja[1])) / 2 - caja[1]
    ImageDraw.Draw(lienzo).text((x, y), glifo, font=f, fill=color)
    img = ctk.CTkImage(light_image=lienzo, dark_image=lienzo, size=(tam, tam))
    _cache[clave] = img
    return img


def separar(texto: str):
    """('🎯 Plan y meta') → ('target', 'Plan y meta'); si no empieza con un emoji conocido → (None, texto)."""
    if not isinstance(texto, str):
        return None, texto
    corto = texto.lstrip()
    if not corto:
        return None, texto
    primero = corto[0]
    nombre = EMOJI_A_ICONO.get(primero)
    if not nombre or not existe(nombre):
        return None, texto
    resto = corto[1:].lstrip(_VARIANTES).strip()
    return nombre, resto


def _color_de(kw: dict, actual=None):
    c = kw.get("text_color") or actual
    if isinstance(c, (tuple, list)):
        c = c[-1]
    return c if isinstance(c, str) and c.startswith("#") else C["texto"]


def _tam_para(fuente) -> int:
    try:
        return min(max(int(abs(fuente.cget("size")) * 1.2), 14), 44)
    except Exception:
        return 17


def convertir(kw: dict, color_actual=None, fuente_actual=None) -> dict:
    """Si kw['text'] empieza con un emoji conocido, devuelve kw con image/compound/text ajustados."""
    if "text" not in kw or kw.get("image") is not None:
        return kw, None
    nombre, resto = separar(kw["text"])
    if not nombre:
        return kw, None
    kw = dict(kw)
    tam = _tam_para(kw.get("font") or fuente_actual)
    kw["image"] = imagen(nombre, tam, _color_de(kw, color_actual))
    kw["compound"] = "left"
    kw["text"] = resto
    return kw, (nombre, tam)


_instalado = False


def instalar():
    """Parchea CTkButton y CTkLabel para que conviertan el emoji inicial de su texto en un icono."""
    global _instalado
    if _instalado:
        return
    _instalado = True

    def envolver(clase, separacion):
        init, conf = clase.__init__, clase.configure

        def con_espacio(kw):
            if kw.get("image") is not None and kw.get("text"):
                kw["text"] = separacion + kw["text"]
            return kw

        def nuevo_init(self, *a, **kw):
            kw, icono = convertir(kw)
            init(self, *a, **con_espacio(kw))
            self._icono = icono

        def nuevo_conf(self, require_redraw=False, **kw):
            if "text" in kw and kw.get("image") is None:
                kw, icono = convertir(kw, getattr(self, "_text_color", None), getattr(self, "_font", None))
                if icono:
                    self._icono = icono
                elif "text" in kw:
                    self._icono = None
                kw = con_espacio(kw)
            elif "text_color" in kw and getattr(self, "_icono", None) and kw.get("image") is None:
                nombre, tam = self._icono                       # al cambiar el color del texto, el icono lo acompaña
                kw["image"] = imagen(nombre, tam, _color_de(kw))
            return conf(self, require_redraw=require_redraw, **kw)

        clase.__init__, clase.configure = nuevo_init, nuevo_conf

    envolver(ctk.CTkButton, "  ")
    envolver(ctk.CTkLabel, "  ")
