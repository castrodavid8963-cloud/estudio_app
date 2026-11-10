"""Búsqueda de texto completo en toda la biblioteca (SQLite FTS5).

El índice vive en su propio archivo (`busqueda.db`), separado de `estudios.db`, para poder moverlo a otro disco:
con ~800 libros puede ocupar varios GB. Cada página es una fila del índice; su rowid codifica libro y página
(recurso_id * 100000 + pagina), así borrar o reindexar un libro es un borrado por rango, no un barrido.

Indexar se hace en segundo plano, de a un libro y con pausas, para no saturar los discos mecánicos.
Los PDF escaneados (sin texto) se anotan como tales: necesitarán OCR (etapa 8).
"""
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager

import database as db
from pdf_core import fitz, PYMUPDF_LOCK

NOMBRE_ARCHIVO = "busqueda.db"
FACTOR_ID = 100_000
MIN_CARACTERES_PAGINA = 15          # páginas casi vacías (portadas, separadores) no se indexan
MIN_CARACTERES_POR_PAGINA = 25      # promedio por debajo del cual se considera un PDF escaneado
MARCA_INI, MARCA_FIN = "⁠[[", "]]⁠"


# ------------------------------------------------------------------ ubicación
def carpeta_indice() -> str:
    carpeta = os.environ.get("ESTUDIO_INDICE") or db.obtener_config("ruta_indice_busqueda")
    return carpeta if carpeta else os.path.dirname(db.DB_NAME)


def ruta_indice() -> str:
    return os.path.join(carpeta_indice(), NOMBRE_ARCHIVO)


@contextmanager
def conexion(ruta: str = None):
    conn = sqlite3.connect(ruta or ruta_indice(), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def inicializar(ruta: str = None):
    with conexion(ruta) as conn:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS paginas USING fts5(texto, tokenize = 'unicode61 remove_diacritics 2')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS libros_indexados (
                recurso_id INTEGER PRIMARY KEY,
                firma TEXT,
                paginas INTEGER,
                caracteres INTEGER,
                sin_texto INTEGER DEFAULT 0,
                indexado TEXT
            )
        """)
        _asegurar_tabla_ocr(conn)


def _asegurar_tabla_ocr(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_paginas (rowid_pag INTEGER PRIMARY KEY, texto TEXT)")


def tamano_bytes() -> int:
    ruta, total = ruta_indice(), 0
    for sufijo in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(ruta + sufijo)
        except OSError:
            pass
    return total


def estado_indice() -> dict:
    """{recurso_id: (firma, paginas, sin_texto)} de lo ya indexado."""
    if not os.path.exists(ruta_indice()):
        return {}
    with conexion() as conn:
        return {r[0]: (r[1], r[2], bool(r[3])) for r in
                conn.execute("SELECT recurso_id, firma, paginas, sin_texto FROM libros_indexados")}


def borrar_indice():
    for sufijo in ("", "-wal", "-shm"):
        try:
            os.remove(ruta_indice() + sufijo)
        except OSError:
            pass


def firma_archivo(ruta: str):
    try:
        st = os.stat(ruta)
        return f"{st.st_size}-{int(st.st_mtime)}"
    except OSError:
        return None


# ------------------------------------------------------------------ consulta
def construir_consulta(texto: str):
    """Convierte lo que escribe el usuario en una consulta FTS5 segura.
    Palabras sueltas se combinan con Y; «frases entre comillas» se buscan juntas; las palabras de 3 o más
    letras admiten prefijo (escribir «punte» encuentra «punteros»)."""
    piezas = []
    for m in re.finditer(r'"([^"]+)"|(\S+)', texto or ""):
        crudo, es_frase = (m.group(1), True) if m.group(1) else (m.group(2), False)
        partes = re.findall(r"[^\W_]+", crudo, re.UNICODE)
        if not partes:
            continue
        if es_frase or len(partes) > 1:
            piezas.append(('"' + " ".join(partes) + '"', False))
        else:
            palabra = partes[0]
            piezas.append((f'"{palabra}"*' if len(palabra) >= 3 else f'"{palabra}"', True))
    if not piezas:
        return None
    return " AND ".join(p for p, _ in piezas)


def buscar(texto: str, limite: int = 400) -> list:
    """[(recurso_id, pagina, fragmento_con_marcas, puntuacion)] mejores primero."""
    consulta = construir_consulta(texto)
    if not consulta or not os.path.exists(ruta_indice()):
        return []
    try:
        with conexion() as conn:
            filas = conn.execute(
                "SELECT rowid, snippet(paginas, 0, ?, ?, ' … ', 22), bm25(paginas) FROM paginas "
                "WHERE paginas MATCH ? ORDER BY bm25(paginas) LIMIT ?",
                (MARCA_INI, MARCA_FIN, consulta, limite)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r[0] // FACTOR_ID, r[0] % FACTOR_ID, r[1], r[2]) for r in filas]


def partir_fragmento(fragmento: str) -> list:
    """Divide un fragmento con marcas en [(texto, es_coincidencia)]."""
    partes, resto = [], fragmento or ""
    while resto:
        i = resto.find(MARCA_INI)
        if i < 0:
            partes.append((resto, False))
            break
        if i:
            partes.append((resto[:i], False))
        resto = resto[i + len(MARCA_INI):]
        j = resto.find(MARCA_FIN)
        if j < 0:
            partes.append((resto, True))
            break
        partes.append((resto[:j], True))
        resto = resto[j + len(MARCA_FIN):]
    return [(re.sub(r"\s+", " ", t), hit) for t, hit in partes if t]


# ------------------------------------------------------------------ indexado
def indexar_libro(recurso_id: int, ruta: str, firma: str, debe_parar=lambda: False, esperar=lambda: None):
    """Extrae el texto de cada página y lo guarda. Devuelve (paginas, caracteres) o None si se interrumpió."""
    with PYMUPDF_LOCK:
        doc = fitz.open(ruta)
        total = len(doc)
    filas, caracteres = [], 0
    try:
        for n in range(total):
            if n % 25 == 0:
                esperar()
                if debe_parar():
                    return None
            with PYMUPDF_LOCK:
                try:
                    texto = doc[n].get_text("text")
                except Exception:
                    texto = ""
            texto = " ".join(texto.split())
            if len(texto) >= MIN_CARACTERES_PAGINA:
                filas.append((recurso_id * FACTOR_ID + n + 1, texto))
                caracteres += len(texto)
            time.sleep(0.002)                 # deja respirar al lector y al disco
    finally:
        with PYMUPDF_LOCK:
            doc.close()
    sin_texto = total > 0 and caracteres / total < MIN_CARACTERES_POR_PAGINA
    with conexion() as conn:
        _asegurar_tabla_ocr(conn)
        conn.execute("DELETE FROM ocr_paginas WHERE rowid_pag BETWEEN ? AND ?",
                     (recurso_id * FACTOR_ID, recurso_id * FACTOR_ID + FACTOR_ID - 1))
        conn.execute("DELETE FROM paginas WHERE rowid BETWEEN ? AND ?",
                     (recurso_id * FACTOR_ID, recurso_id * FACTOR_ID + FACTOR_ID - 1))
        conn.executemany("INSERT INTO paginas(rowid, texto) VALUES (?, ?)", filas)
        conn.execute("INSERT OR REPLACE INTO libros_indexados(recurso_id, firma, paginas, caracteres, sin_texto, indexado) "
                     "VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))",
                     (recurso_id, firma, total, caracteres, 1 if sin_texto else 0))
    return total, caracteres


def quitar_libro(recurso_id: int):
    if not os.path.exists(ruta_indice()):
        return
    with conexion() as conn:
        conn.execute("DELETE FROM paginas WHERE rowid BETWEEN ? AND ?",
                     (recurso_id * FACTOR_ID, recurso_id * FACTOR_ID + FACTOR_ID - 1))
        conn.execute("DELETE FROM libros_indexados WHERE recurso_id = ?", (recurso_id,))
        _asegurar_tabla_ocr(conn)
        conn.execute("DELETE FROM ocr_paginas WHERE rowid_pag BETWEEN ? AND ?",
                     (recurso_id * FACTOR_ID, recurso_id * FACTOR_ID + FACTOR_ID - 1))


def pendientes(con_total: bool = False):
    """[(id, ruta, firma)] de libros disponibles (fuera de áreas excluidas) sin indexar o que cambiaron.
    Con con_total=True devuelve (lista, total_de_libros_indexables)."""
    hechos = estado_indice()
    excluidas, raiz = db.areas_excluidas(), db.obtener_ruta_biblioteca()
    resultado, total = [], 0
    with db.obtener_conexion() as conn:
        filas = conn.execute("SELECT id, ruta_local FROM recursos WHERE disponible = 1 ORDER BY nombre_archivo").fetchall()
    for rid, ruta in filas:
        if db.esta_excluido(ruta, raiz, excluidas):
            continue
        firma = firma_archivo(ruta)
        if firma is None:
            continue
        total += 1
        previo = hechos.get(rid)
        if previo is None or previo[0] != firma:
            resultado.append((rid, ruta, firma))
    return (resultado, total) if con_total else resultado


class Indexador:
    """Hilo de fondo que indexa los libros pendientes. Pausable, detenible y reanudable (lo hecho se conserva)."""

    def __init__(self, al_progreso=None, debe_ceder=None):
        self.al_progreso = al_progreso or (lambda *a: None)     # (hechos, total, titulo, terminado)
        self.debe_ceder = debe_ceder or (lambda: False)         # True mientras hay que dejar libre el disco
        self._hilo = None
        self._parar = threading.Event()
        self._pausa = threading.Event()
        self.hechos = self.total = 0
        self.errores = 0
        self.finalizado = True

    @property
    def activo(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    @property
    def en_pausa(self) -> bool:
        return self._pausa.is_set()

    def iniciar(self):
        if self.activo:
            return
        inicializar()
        self._parar.clear()
        self._pausa.clear()
        self.finalizado = False
        self._hilo = threading.Thread(target=self._trabajo, daemon=True)
        self._hilo.start()

    def pausar(self, valor: bool = True):
        (self._pausa.set if valor else self._pausa.clear)()

    def detener(self):
        self._parar.set()

    def _esperar(self):
        while (self._pausa.is_set() or self.debe_ceder()) and not self._parar.is_set():
            time.sleep(0.5)

    def _trabajo(self):
        try:
            lista = pendientes()
            self.total, self.hechos, self.errores = len(lista), 0, 0
            self.al_progreso(0, self.total, "", False)
            for rid, ruta, firma in lista:
                self._esperar()
                if self._parar.is_set():
                    break
                nombre = os.path.basename(ruta)
                try:
                    r = indexar_libro(rid, ruta, firma, self._parar.is_set, self._esperar)
                    if r is None:
                        break
                except Exception:
                    self.errores += 1
                    try:    # se marca como visto para no reintentarlo en cada pasada
                        with conexion() as conn:
                            conn.execute("INSERT OR REPLACE INTO libros_indexados VALUES (?, ?, 0, 0, 1, datetime('now','localtime'))",
                                         (rid, firma))
                    except Exception:
                        pass
                self.hechos += 1
                self.al_progreso(self.hechos, self.total, nombre, False)
                time.sleep(0.05)
        finally:
            self.finalizado = True
            self.al_progreso(self.hechos, self.total, "", True)


# ------------------------------------------------------------------ OCR de libros escaneados
def libros_escaneados() -> list:
    """[(id, ruta, firma)] de libros disponibles ya indexados que resultaron sin texto (necesitan OCR)."""
    hechos = estado_indice()
    ids = [rid for rid, v in hechos.items() if v[2]]
    if not ids:
        return []
    with db.obtener_conexion() as conn:
        filas = conn.execute(
            f"SELECT id, ruta_local FROM recursos WHERE disponible = 1 AND id IN ({','.join('?' * len(ids))}) "
            "ORDER BY nombre_archivo", ids).fetchall()
    out = []
    excluidas, raiz = db.areas_excluidas(), db.obtener_ruta_biblioteca()
    for rid, ruta in filas:
        if db.esta_excluido(ruta, raiz, excluidas):
            continue
        firma = firma_archivo(ruta)
        if firma:
            out.append((rid, ruta, firma))
    return out


def ocr_libro(recurso_id: int, ruta: str, firma: str, idioma: str, exe: str, debe_parar=lambda: False,
              esperar=lambda: None, progreso=lambda pagina, total: None) -> bool:
    """Reconoce con OCR las páginas sin texto de un libro y las añade al índice. Guarda cada página al terminarla,
    así que si se interrumpe se retoma donde quedó. Devuelve True si el libro quedó completo."""
    import ocr
    inicializar()
    with PYMUPDF_LOCK:
        doc = fitz.open(ruta)
        total = len(doc)
    base = recurso_id * FACTOR_ID
    try:
        with conexion() as conn:
            _asegurar_tabla_ocr(conn)
            hechas = {r[0] - base for r in conn.execute(
                "SELECT rowid_pag FROM ocr_paginas WHERE rowid_pag BETWEEN ? AND ?", (base, base + FACTOR_ID - 1))}
        for n in range(1, total + 1):
            esperar()
            if debe_parar():
                return False
            progreso(n, total)
            if n in hechas:
                continue
            with PYMUPDF_LOCK:
                nativo = " ".join((doc[n - 1].get_text("text") or "").split())
            if len(nativo) >= MIN_CARACTERES_PAGINA:
                continue                                   # ya tiene texto: no se toca
            with PYMUPDF_LOCK:
                png = doc[n - 1].get_pixmap(dpi=ocr.DPI, colorspace=fitz.csGRAY).tobytes("png")
            texto = ocr.reconocer_png(png, idioma, exe)
            with conexion() as conn:
                conn.execute("INSERT OR REPLACE INTO ocr_paginas (rowid_pag, texto) VALUES (?, ?)", (base + n, texto))
    finally:
        with PYMUPDF_LOCK:
            doc.close()
    # Libro completo: se vuelca el texto reconocido al índice de búsqueda
    with conexion() as conn:
        filas = conn.execute("SELECT rowid_pag, texto FROM ocr_paginas WHERE rowid_pag BETWEEN ? AND ?",
                             (base, base + FACTOR_ID - 1)).fetchall()
        validas = [(r, t) for r, t in filas if len(t) >= MIN_CARACTERES_PAGINA]
        for r, _ in validas:
            conn.execute("DELETE FROM paginas WHERE rowid = ?", (r,))
        conn.executemany("INSERT INTO paginas(rowid, texto) VALUES (?, ?)", validas)
        extra = sum(len(t) for _, t in validas)
        conn.execute("UPDATE libros_indexados SET sin_texto = 0, caracteres = caracteres + ?, firma = ? WHERE recurso_id = ?",
                     (extra, firma, recurso_id))
    return True


def textos_ocr(recurso_id: int) -> list:
    """[(pagina, texto)] reconocidos con OCR para el tutor. [] si no hay."""
    if not os.path.exists(ruta_indice()):
        return []
    base = recurso_id * FACTOR_ID
    try:
        with conexion() as conn:
            filas = conn.execute("SELECT rowid_pag, texto FROM ocr_paginas WHERE rowid_pag BETWEEN ? AND ? ORDER BY rowid_pag",
                                 (base, base + FACTOR_ID - 1)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(r - base, t) for r, t in filas if t and len(t) >= MIN_CARACTERES_PAGINA]
