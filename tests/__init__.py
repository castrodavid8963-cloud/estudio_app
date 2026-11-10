"""Pruebas automáticas. Se ejecutan con:  python -m unittest discover -s tests -t .

Usan una carpeta temporal para la base de datos y el índice: tus datos reales nunca se tocan.
"""
import atexit
import os
import shutil
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

TMP = tempfile.mkdtemp(prefix="estudio_tests_")
os.environ["ESTUDIO_DATOS"] = os.path.join(TMP, "datos")
os.environ["ESTUDIO_INDICE"] = os.path.join(TMP, "indice")
os.makedirs(os.environ["ESTUDIO_INDICE"], exist_ok=True)
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
