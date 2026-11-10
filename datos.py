"""Dónde guarda la app sus datos (base de datos, portadas, historiales, respaldos).

- Normal (código fuente): junto al código, como siempre.
- Ejecutable (PyInstaller): junto al .exe si se puede escribir ahí; si no, en %APPDATA%/HubEstudio.
- Variable de entorno ESTUDIO_DATOS: manda sobre todo lo anterior (útil para moverlos a otro disco).
"""
import os
import sys


def _escribible(carpeta: str) -> bool:
    try:
        os.makedirs(carpeta, exist_ok=True)
        prueba = os.path.join(carpeta, ".escritura")
        with open(prueba, "w") as f:
            f.write("ok")
        os.remove(prueba)
        return True
    except OSError:
        return False


def carpeta_datos() -> str:
    forzada = os.environ.get("ESTUDIO_DATOS")
    if forzada:
        os.makedirs(forzada, exist_ok=True)
        return forzada
    if getattr(sys, "frozen", False):
        junto_al_exe = os.path.dirname(os.path.abspath(sys.executable))
        if _escribible(junto_al_exe):
            return junto_al_exe
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        carpeta = os.path.join(base, "HubEstudio")
        os.makedirs(carpeta, exist_ok=True)
        return carpeta
    return os.path.dirname(os.path.abspath(__file__))


def ruta_datos(*partes) -> str:
    return os.path.join(carpeta_datos(), *partes)
