"""Tema visual y piezas de interfaz reutilizables (colores, fuentes, tarjetas, barras, chips)."""
import customtkinter as ctk

C = {
    "fondo": "#0e1016",        # ventana
    "lateral": "#12141c",      # barra lateral
    "panel": "#171a24",        # paneles grandes
    "tarjeta": "#1d2130",      # tarjetas
    "tarjeta_hover": "#252a3d",
    "borde": "#2b3047",
    "texto": "#e9ebf5",
    "texto2": "#9aa2bf",
    "texto3": "#656d8c",
    "acento": "#7c83ff",
    "acento_hover": "#6a71ee",
    "acento_suave": "#2a2f5c",
    "ok": "#34d399",
    "aviso": "#fbbf24",
    "error": "#f87171",
    "pista": "#2a2f45",        # fondo de barras de progreso
}

ESTADO_COLOR = {"Sin empezar": "#656d8c", "En progreso": "#fbbf24", "Completado": "#34d399"}
ESTADO_ICONO = {"Sin empezar": "○", "En progreso": "◐", "Completado": "●"}

NIVEL_COLOR = {1: "#34d399", 2: "#60a5fa", 3: "#f472b6", 4: "#9aa2bf"}

_fuentes = {}


def fuente(tam=13, peso="normal"):
    """CTkFont cacheada (hay que pedirla cuando ya existe la ventana raíz)."""
    clave = (tam, peso)
    if clave not in _fuentes:
        _fuentes[clave] = ctk.CTkFont(size=tam, weight=peso)
    return _fuentes[clave]


def configurar():
    ctk.set_appearance_mode("Dark")
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
        "primario": dict(fg_color=C["acento"], hover_color=C["acento_hover"], text_color="#ffffff"),
        "suave": dict(fg_color=C["tarjeta_hover"], hover_color=C["borde"], text_color=C["texto"]),
        "fantasma": dict(fg_color="transparent", hover_color=C["tarjeta_hover"], text_color=C["texto2"]),
        "peligro": dict(fg_color="#5b2330", hover_color="#7a2d3e", text_color="#ffd9df"),
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
