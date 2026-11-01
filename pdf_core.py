"""Punto único de acceso a PyMuPDF.

PyMuPDF no es seguro para usarse desde varios hilos a la vez. Como la app
genera portadas y extrae texto desde hilos distintos, todo acceso a `fitz`
debe hacerse dentro de `PYMUPDF_LOCK`.
"""
import threading

import pymupdf as fitz

PYMUPDF_LOCK = threading.RLock()

# Evita que MuPDF escriba advertencias/errores de bajo nivel en la consola.
fitz.TOOLS.mupdf_display_errors(False)
fitz.TOOLS.mupdf_display_warnings(False)

__all__ = ["fitz", "PYMUPDF_LOCK"]
