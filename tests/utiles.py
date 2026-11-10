"""Ayudas comunes de las pruebas: BD temporal y PDF de mentira."""
import os

import database as db
from pdf_core import fitz

db.inicializar_db()
CARPETA = os.path.join(os.environ["ESTUDIO_DATOS"], "pdfs")
os.makedirs(CARPETA, exist_ok=True)


def crear_pdf(nombre: str, textos: list) -> str:
    """PDF con una página por cada texto."""
    ruta = os.path.join(CARPETA, nombre)
    d = fitz.open()
    for t in textos:
        d.new_page().insert_text((72, 100), t)
    d.save(ruta)
    d.close()
    return ruta


def crear_pdf_escaneado(nombre: str, textos: list) -> str:
    """PDF cuyas páginas son solo imágenes (como un escaneo): sin texto extraíble."""
    ruta = os.path.join(CARPETA, nombre)
    d = fitz.open()
    for t in textos:
        origen = fitz.open()
        origen.new_page().insert_text((72, 120), t, fontsize=28)
        png = origen.load_page(0).get_pixmap(dpi=150).tobytes("png")
        origen.close()
        p = d.new_page()
        p.insert_image(p.rect, stream=png)
    d.save(ruta)
    d.close()
    return ruta


def registrar_libro(ruta: str) -> int:
    with db.obtener_conexion() as c:
        if not c.execute("SELECT 1 FROM semanas WHERE id = 1").fetchone():
            c.execute("INSERT OR IGNORE INTO materias (id, nombre) VALUES (1, 'Pruebas')")
            c.execute("INSERT OR IGNORE INTO semanas (id, materia_id, numero_semana) VALUES (1, 1, 1)")
        cur = c.execute("INSERT INTO recursos (semana_id, nombre_archivo, ruta_local, total_paginas) VALUES (1, ?, ?, 0)",
                        (os.path.basename(ruta), ruta))
        return cur.lastrowid
