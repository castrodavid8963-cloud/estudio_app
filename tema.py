"""Tema visual y piezas de interfaz reutilizables (colores, fuentes, tarjetas, barras, chips)."""
import customtkinter as ctk

import json
import os

from datos import ruta_datos

# ---------------------------------------------------------------- temas
# Cada tema define TODOS los colores. `modo` indica a CustomTkinter si es claro u oscuro (menús, barras, etc.).
TEMAS = {
    "Medianoche": dict(modo="Dark", fondo="#0e1016", lateral="#12141c", panel="#171a24", tarjeta="#1d2130",
                       tarjeta_hover="#252a3d", borde="#2b3047", texto="#e9ebf5", texto2="#9aa2bf", texto3="#656d8c",
                       acento="#7c83ff", acento_hover="#6a71ee", acento_suave="#2a2f5c", sobre_acento="#ffffff",
                       ok="#34d399", aviso="#fbbf24", error="#f87171", pista="#2a2f45"),
    "Onyx": dict(modo="Dark", fondo="#0b0b0c", lateral="#101012", panel="#151517", tarjeta="#1b1b1e",
                 tarjeta_hover="#242428", borde="#2e2e33", texto="#ececef", texto2="#a0a0a8", texto3="#6c6c75",
                 acento="#e4e4e7", acento_hover="#c9c9ce", acento_suave="#2c2c31", sobre_acento="#0b0b0c",
                 ok="#4ade80", aviso="#fbbf24", error="#f87171", pista="#2a2a2f"),
    "Negro": dict(modo="Dark", fondo="#000000", lateral="#050505", panel="#0a0a0a", tarjeta="#111111",
                  tarjeta_hover="#1a1a1a", borde="#262626", texto="#f2f2f2", texto2="#a3a3a3", texto3="#6b6b6b",
                  acento="#38bdf8", acento_hover="#0ea5e9", acento_suave="#0c2a3a", sobre_acento="#03121c",
                  ok="#34d399", aviso="#fbbf24", error="#f87171", pista="#232323"),
    "Verde bosque": dict(modo="Dark", fondo="#0a120e", lateral="#0d1712", panel="#111d17", tarjeta="#16251d",
                         tarjeta_hover="#1e3128", borde="#274035", texto="#e6f0ea", texto2="#96ae9f", texto3="#61776a",
                         acento="#4ade80", acento_hover="#22c55e", acento_suave="#1b3d2b", sobre_acento="#052e16",
                         ok="#bef264", aviso="#fbbf24", error="#f87171", pista="#22372c"),
    "Océano": dict(modo="Dark", fondo="#08111c", lateral="#0b1624", panel="#0f1c2e", tarjeta="#14253b",
                   tarjeta_hover="#1b3050", borde="#25395a", texto="#e6eefb", texto2="#94a8c8", texto3="#5f7498",
                   acento="#4f9cff", acento_hover="#3b82f6", acento_suave="#173a6b", sobre_acento="#04122a",
                   ok="#34d399", aviso="#fbbf24", error="#f87171", pista="#203350"),
    "Vino": dict(modo="Dark", fondo="#140a0e", lateral="#190d12", panel="#1f1117", tarjeta="#28161d",
                 tarjeta_hover="#331d26", borde="#46262f", texto="#f4e8ec", texto2="#bf9aa8", texto3="#86606d",
                 acento="#fb7185", acento_hover="#f43f5e", acento_suave="#4a1f2c", sobre_acento="#2a050f",
                 ok="#34d399", aviso="#fbbf24", error="#fda4af", pista="#3a2029"),
    "Blanco": dict(modo="Light", fondo="#f3f4f8", lateral="#ffffff", panel="#ffffff", tarjeta="#ffffff",
                   tarjeta_hover="#eceef5", borde="#dcdfe9", texto="#1b1f2e", texto2="#565e78", texto3="#8a91a8",
                   acento="#5b61f0", acento_hover="#484ed8", acento_suave="#e4e5ff", sobre_acento="#ffffff",
                   ok="#059669", aviso="#b45309", error="#dc2626", pista="#e3e6ef"),
    "Papel": dict(modo="Light", fondo="#f6f1e7", lateral="#efe8da", panel="#fbf8f1", tarjeta="#fffdf8",
                  tarjeta_hover="#f1ead9", borde="#ded4be", texto="#2b2620", texto2="#6b6254", texto3="#9a907d",
                  acento="#b45f06", acento_hover="#964d04", acento_suave="#f3e2c4", sobre_acento="#ffffff",
                  ok="#3f7d46", aviso="#a16207", error="#b91c1c", pista="#e6dcc6"),
}
TEMA_POR_DEFECTO = "Medianoche"
_ARCHIVO_TEMA = "tema.json"

C = dict(TEMAS[TEMA_POR_DEFECTO])        # paleta activa: las vistas leen C["..."] al crear sus widgets
ESTADO_COLOR = {}
ESTADO_ICONO = {"Sin empezar": "○", "En progreso": "◐", "Completado": "●"}


def tema_guardado() -> str:
    """Nombre del tema elegido (se guarda en un archivito, sin depender de la base de datos)."""
    try:
        with open(ruta_datos(_ARCHIVO_TEMA), encoding="utf-8") as f:
            nombre = json.load(f).get("tema")
        return nombre if nombre in TEMAS else TEMA_POR_DEFECTO
    except (OSError, ValueError):
        return TEMA_POR_DEFECTO


def guardar_tema(nombre: str):
    if nombre in TEMAS:
        with open(ruta_datos(_ARCHIVO_TEMA), "w", encoding="utf-8") as f:
            json.dump({"tema": nombre}, f)


def aplicar(nombre: str):
    """Pone la paleta `nombre` en C (en el sitio, para que todos los módulos la vean)."""
    global TEMA_ACTUAL
    nombre = nombre if nombre in TEMAS else TEMA_POR_DEFECTO
    C.clear()
    C.update(TEMAS[nombre])
    ESTADO_COLOR.clear()
    ESTADO_COLOR.update({"Sin empezar": C["texto3"], "En progreso": C["aviso"], "Completado": C["ok"]})
    TEMA_ACTUAL = nombre


def es_claro() -> bool:
    return C.get("modo") == "Light"


def mezclar(c1: str, c2: str, t: float) -> str:
    """Color intermedio entre c1 y c2 (t=0 → c1, t=1 → c2). Sirve para escalas derivadas del tema."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def texto_sobre(color: str) -> str:
    """Texto oscuro o claro, el que mejor se lea sobre `color` (para casillas verdes, chips, botones de color…)."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#0e1016" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


TEMA_ACTUAL = TEMA_POR_DEFECTO
aplicar(tema_guardado())

NIVEL_COLOR = {1: "#34d399", 2: "#60a5fa", 3: "#f472b6", 4: "#9aa2bf"}

_fuentes = {}


def fuente(tam=13, peso="normal"):
    """CTkFont cacheada (hay que pedirla cuando ya existe la ventana raíz)."""
    clave = (tam, peso)
    if clave not in _fuentes:
        _fuentes[clave] = ctk.CTkFont(size=tam, weight=peso)
    return _fuentes[clave]


_segmentados_parcheados = False


def _parchear_segmentados():
    """Los botones segmentados (pestañas y selectores) usan un solo color de texto para todos los segmentos; con acentos
    claros (Onyx, Verde, Negro…) el texto del segmento activo quedaría ilegible. Aquí el activo usa `sobre_acento`."""
    global _segmentados_parcheados
    if _segmentados_parcheados:
        return
    _segmentados_parcheados = True
    clase = ctk.CTkSegmentedButton
    sel, desel = clase._select_button_by_value, clase._unselect_button_by_value

    def seleccionar(self, value):
        sel(self, value)
        try:
            self._buttons_dict[value].configure(text_color=C["sobre_acento"])
        except (KeyError, Exception):
            pass

    def deseleccionar(self, value):
        desel(self, value)
        try:
            self._buttons_dict[value].configure(text_color=self._sb_text_color)
        except (KeyError, Exception):
            pass

    clase._select_button_by_value, clase._unselect_button_by_value = seleccionar, deseleccionar


def configurar():
    import iconos
    iconos.instalar()
    _parchear_segmentados()
    ctk.set_appearance_mode(C.get("modo", "Dark"))
    ctk.set_default_color_theme("blue")


def recortar(texto: str, maximo: int) -> str:
    texto = texto or ""
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def nombre_area(carpeta: str) -> str:
    """'01_Programacion_y_Lenguajes' -> 'Programacion y Lenguajes'."""
    if not carpeta:
        return "Sin carpeta"
    partes = carpeta.split("_", 1)
    if len(partes) == 2 and partes[0].isdigit():
        carpeta = partes[1]
    return carpeta.replace("_", " ")


def tarjeta(padre, **kw):
    kw.setdefault("fg_color", C["tarjeta"])
    kw.setdefault("corner_radius", 14)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", C["borde"])
    return ctk.CTkFrame(padre, **kw)


def titulo(padre, texto, tam=22, **kw):
    kw.setdefault("text_color", C["texto"])
    return ctk.CTkLabel(padre, text=texto, font=fuente(tam, "bold"), anchor="w", **kw)


def subtitulo(padre, texto, tam=13, **kw):
    kw.setdefault("text_color", C["texto2"])
    return ctk.CTkLabel(padre, text=texto, font=fuente(tam), anchor="w", justify="left", **kw)


def chip(padre, texto, color=None, fondo=None, tam=11):
    color = color or C["texto2"]
    return ctk.CTkLabel(padre, text=texto, font=fuente(tam, "bold"), text_color=color,
                        fg_color=fondo or C["pista"], corner_radius=8, height=20, padx=8)


def barra(padre, valor=0.0, color=None, alto=6, **kw):
    b = ctk.CTkProgressBar(padre, height=alto, corner_radius=alto, fg_color=C["pista"],
                           progress_color=color or C["acento"], **kw)
    b.set(max(0.0, min(1.0, valor)))
    return b


def boton(padre, texto, comando=None, tipo="primario", **kw):
    """tipo: primario | suave | fantasma | peligro"""
    estilos = {
        "primario": dict(fg_color=C["acento"], hover_color=C["acento_hover"], text_color=C["sobre_acento"]),
        "suave": dict(fg_color=C["tarjeta_hover"], hover_color=C["borde"], text_color=C["texto"]),
        "fantasma": dict(fg_color="transparent", hover_color=C["tarjeta_hover"], text_color=C["texto2"]),
        "peligro": dict(fg_color=mezclar(C["fondo"], C["error"], 0.35), hover_color=mezclar(C["fondo"], C["error"], 0.5),
                        text_color="#ffffff" if not es_claro() else "#7f1d1d"),
    }[tipo]
    kw.setdefault("corner_radius", 10)
    kw.setdefault("height", 34)
    kw.setdefault("font", fuente(13, "bold" if tipo == "primario" else "normal"))
    return ctk.CTkButton(padre, text=texto, command=comando, **estilos, **kw)


def estado_vacio(padre, icono, titulo_txt, detalle, texto_boton=None, comando=None):
    marco = ctk.CTkFrame(padre, fg_color="transparent")
    ctk.CTkLabel(marco, text=icono, font=fuente(48)).pack(pady=(40, 6))
    ctk.CTkLabel(marco, text=titulo_txt, font=fuente(18, "bold"), text_color=C["texto"]).pack()
    ctk.CTkLabel(marco, text=detalle, font=fuente(13), text_color=C["texto2"], wraplength=420,
                 justify="center").pack(pady=(4, 14))
    if texto_boton:
        boton(marco, texto_boton, comando).pack()
    return marco


def fecha_relativa(texto_sqlite: str) -> str:
    """'2026-11-03 10:20:00' -> 'hoy', 'ayer', 'hace 3 días'... (cadena vacía si no hay fecha)."""
    from datetime import datetime
    if not texto_sqlite:
        return ""
    try:
        f = datetime.strptime(texto_sqlite[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""
    # CURRENT_TIMESTAMP de SQLite está en UTC; las sesiones del rastreador, en hora local.
    dias = (datetime.now().date() - f.date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    if dias < 30:
        return f"hace {dias} días"
    return f"hace {dias // 30} mes(es)"
