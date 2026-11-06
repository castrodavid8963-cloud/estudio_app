"""Detección y eliminación segura de libros duplicados.

Se detecta por tres vías, de más a menos fiable:
  1. identico   -> mismo contenido (misma huella: tamaño + inicio + final del archivo).
  2. metadatos  -> mismo título (y mismo autor o mismo nº de páginas) en los metadatos del PDF.
  3. titulo     -> nombre equivalente una vez limpio de edición/copia/signos; con las mismas páginas
                   es "probable", con distinto nº de páginas es solo "posible" (otra edición).
Nada se borra solo: el usuario elige, y por defecto los archivos van a una papelera dentro de la
biblioteca. El progreso de lectura del libro eliminado se fusiona con el que se conserva.
"""
import os
import re
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass, field

import database as db
import gestor_biblioteca as gb
from pdf_core import fitz, PYMUPDF_LOCK

CARPETA_PAPELERA = ".papelera_duplicados"
FUERZA = {"identico": 3, "metadatos": 2, "titulo_probable": 2, "titulo_posible": 1}
ETIQUETA = {
    "identico": "Idéntico (mismo contenido)",
    "metadatos": "Mismos metadatos",
    "titulo_probable": "Mismo título y páginas",
    "titulo_posible": "Título igual, distintas páginas",
}
_cache_meta = {}          # (ruta, tam, mtime) -> (titulo, autor, paginas)


@dataclass
class Miembro:
    id: int
    ruta: str
    nombre: str
    tam: int
    paginas: int
    meta_titulo: str
    meta_autor: str
    estado: str
    favorito: bool
    ultima_pagina: int
    area: str
    puntaje: float = 0.0


@dataclass
class Grupo:
    tipo: str
    miembros: list = field(default_factory=list)
    conservar_id: int = 0
    tipos: tuple = ()

    @property
    def etiqueta(self):
        orden = sorted(self.tipos or (self.tipo,), key=lambda t: -FUERZA[t])
        return " + ".join(ETIQUETA[t] for t in orden)

    @property
    def sobrantes(self):
        return [m for m in self.miembros if m.id != self.conservar_id]

    @property
    def bytes_sobrantes(self):
        return sum(m.tam for m in self.sobrantes)

    @property
    def sugerido(self):
        """¿Se preselecciona para eliminar? Solo las coincidencias fiables."""
        return FUERZA[self.tipo] >= 2


@dataclass
class Resultado:
    grupos: list
    revisados: int
    sin_archivo: int

    @property
    def total_sobrantes(self):
        return sum(len(g.sobrantes) for g in self.grupos)

    @property
    def bytes_sobrantes(self):
        return sum(g.bytes_sobrantes for g in self.grupos)

    def por_tipo(self):
        c = defaultdict(int)
        for g in self.grupos:
            c[g.tipo] += 1
        return dict(c)


# ----------------------------------------------------------------------------- claves de comparación
_RUIDO = re.compile(
    r"\b(\d+\s*(st|nd|rd|th|ra|da|a|era|ma)?\s*(edition|edicion|ed)|(first|second|third|fourth|fifth|segunda|tercera|primera|cuarta|quinta)"
    r"\s+(edition|edicion)|edition|edicion|ed|v\d+(\.\d+)*|copy|copia|final|pdf|ebook|libro|book|www\w*|com|free|download|"
    r"scribd|libgen|z lib|zlib|retail|ocr|scan|scanned|compressed|comprimido)\b")


def clave_titulo(nombre: str) -> str:
    """Nombre normalizado sin 'edición', 'copia', '(1)', extensiones, etc."""
    base = re.sub(r"\.pdf$", "", nombre or "", flags=re.IGNORECASE)
    base = re.sub(r"[\(\[]\s*\d+\s*[\)\]]\s*$", "", base)            # "Libro (1)"
    t = gb.normalizar(base)
    t = _RUIDO.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(clave: str) -> frozenset:
    """Palabras significativas (sin artículos/preposiciones ni palabras de 1-2 letras ni números)."""
    return frozenset(w for w in clave.split()
                     if len(w) > 2 and not w.isdigit() and w not in gb._PALABRAS_FINALES)


def _leer_meta(ruta: str):
    try:
        st = os.stat(ruta)
    except OSError:
        return None
    k = (ruta, st.st_size, int(st.st_mtime))
    if k in _cache_meta:
        return st.st_size, *_cache_meta[k]
    titulo = autor = ""
    paginas = 0
    try:
        with PYMUPDF_LOCK:
            doc = fitz.open(ruta)
            try:
                if not doc.needs_pass:
                    md = doc.metadata or {}
                    titulo = (md.get("title") or "").strip()
                    autor = (md.get("author") or "").strip()
                paginas = len(doc)
            finally:
                doc.close()
    except Exception:
        pass
    _cache_meta[k] = (titulo, autor, paginas)
    return st.st_size, titulo, autor, paginas


# ----------------------------------------------------------------------------- unión de grupos
class _Union:
    def __init__(self, n):
        self.p = list(range(n))
        self.fuerza = {}          # raíz -> (fuerza, tipo)
        self.tipos = defaultdict(set)   # raíz -> todos los tipos de coincidencia del grupo

    def buscar(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def unir(self, a, b, tipo):
        ra, rb = self.buscar(a), self.buscar(b)
        f = FUERZA[tipo]
        mejor = max(((f, tipo), self.fuerza.get(ra, (0, "")), self.fuerza.get(rb, (0, ""))), key=lambda x: x[0])
        if ra != rb:
            self.p[rb] = ra
            self.tipos[ra] |= self.tipos.pop(rb, set())
        self.fuerza[ra] = mejor
        self.tipos[ra].add(tipo)


def _puntaje(m: Miembro) -> float:
    """Cuál conservar: el que ya tiene progreso/favorito, nombre legible, área real y mejor archivo."""
    p = 0.0
    p += 1000 if m.favorito else 0
    p += {"Completado": 400, "En progreso": 300}.get(m.estado, 0)
    p += min(m.ultima_pagina, 200)
    p += 60 if not gb.nombre_deficiente(re.sub(r"\.pdf$", "", m.nombre, flags=re.IGNORECASE)) else 0
    p += 0 if m.area.startswith("12_") else 40
    nombre = re.sub(r"\.pdf$", "", m.nombre, flags=re.IGNORECASE)
    p += min(len(nombre.split()), 8) * 3                         # nombre más descriptivo
    p -= 25 if re.search(r"\(\d+\)|\bcopia\b|\bcopy\b|_final|_old", nombre, re.IGNORECASE) else 0
    p += min(m.tam / (1024 * 1024), 50) * 0.5
    p -= len(m.ruta) * 0.01
    return p


# ----------------------------------------------------------------------------- búsqueda
def buscar(progreso_cb=None, cancelar=None) -> Resultado:
    """Analiza los libros disponibles. `progreso_cb(i, total, nombre)`; `cancelar()` -> bool."""
    libros = db.listar_libros()
    huellas = db.obtener_huellas()
    miembros, sin_archivo = [], 0
    total = len(libros)
    for i, l in enumerate(libros, 1):
        if cancelar and cancelar():
            return Resultado([], i, sin_archivo)
        if progreso_cb and (i % 5 == 0 or i == total):
            progreso_cb(i, total, l["nombre_archivo"])
        meta = _leer_meta(l["ruta"])
        if meta is None:
            sin_archivo += 1
            continue
        tam, mt, ma, pag = meta
        miembros.append(Miembro(l["id"], l["ruta"], l["nombre_archivo"], tam, pag or l["total_paginas"], mt, ma,
                                l["estado"], l["favorito"], l["ultima_pagina"], l["area"]))

    n = len(miembros)
    u = _Union(n)

    # 1) idénticos por huella
    por_huella = defaultdict(list)
    for idx, m in enumerate(miembros):
        h = huellas.get(m.id)
        if h:
            por_huella[h].append(idx)
    for idxs in por_huella.values():
        for j in idxs[1:]:
            u.unir(idxs[0], j, "identico")

    # 2) metadatos: título válido, no compartido por muchos (metadato basura) y coincide autor o páginas
    por_meta = defaultdict(list)
    for idx, m in enumerate(miembros):
        if m.meta_titulo and gb.titulo_valido(m.meta_titulo):
            por_meta[gb.normalizar(m.meta_titulo)].append(idx)
    for idxs in por_meta.values():
        if len(idxs) < 2 or len(idxs) > 5:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ma, mb = miembros[idxs[a]], miembros[idxs[b]]
                mismo_autor = ma.meta_autor and gb.normalizar(ma.meta_autor) == gb.normalizar(mb.meta_autor)
                if mismo_autor or (ma.paginas and ma.paginas == mb.paginas):
                    u.unir(idxs[a], idxs[b], "metadatos")

    # 3) título del nombre de archivo
    por_clave = defaultdict(list)
    for idx, m in enumerate(miembros):
        k = clave_titulo(m.nombre)
        if len(k) >= 6:
            por_clave[k].append(idx)
    for idxs in por_clave.values():
        for j in idxs[1:]:
            ma, mb = miembros[idxs[0]], miembros[j]
            tipo = "titulo_probable" if (ma.paginas and abs(ma.paginas - mb.paginas) <= max(1, ma.paginas // 50)) else "titulo_posible"
            u.unir(idxs[0], j, tipo)

    #    título parecido (uno contiene al otro) con exactamente las mismas páginas
    por_paginas = defaultdict(list)
    for idx, m in enumerate(miembros):
        if m.paginas > 8:
            por_paginas[m.paginas].append(idx)
    for idxs in por_paginas.values():
        if len(idxs) < 2 or len(idxs) > 60:
            continue
        toks = {i: _tokens(clave_titulo(miembros[i].nombre)) for i in idxs}
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                ta, tb = toks[idxs[a]], toks[idxs[b]]
                if len(ta) >= 2 and len(tb) >= 2 and (ta <= tb or tb <= ta):
                    u.unir(idxs[a], idxs[b], "titulo_probable")

    grupos_idx = defaultdict(list)
    for idx in range(n):
        grupos_idx[u.buscar(idx)].append(idx)
    grupos = []
    for raiz, idxs in grupos_idx.items():
        if len(idxs) < 2:
            continue
        ms = [miembros[i] for i in idxs]
        for m in ms:
            m.puntaje = _puntaje(m)
        ms.sort(key=lambda m: -m.puntaje)
        tipo = u.fuerza.get(raiz, (0, "titulo_posible"))[1] or "titulo_posible"
        grupos.append(Grupo(tipo, ms, ms[0].id, tuple(u.tipos.get(raiz, {tipo}))))
    grupos.sort(key=lambda g: (-FUERZA[g.tipo], -g.bytes_sobrantes))
    return Resultado(grupos, n, sin_archivo)


# ----------------------------------------------------------------------------- eliminación
def eliminar(raiz: str, grupos: list, ids_eliminar: set, definitivo: bool = False, progreso_cb=None) -> dict:
    """Elimina los libros `ids_eliminar` de sus grupos. Garantiza que en cada grupo quede al menos uno.

    Por defecto mueve a `<raiz>/.papelera_duplicados/<fecha>/<ruta relativa>` (recuperable);
    con definitivo=True borra el archivo. El progreso se fusiona con el libro que se conserva.
    """
    res = {"eliminados": 0, "bytes": 0, "errores": [], "carpeta": ""}
    destino_base = os.path.join(raiz, CARPETA_PAPELERA, time.strftime("%Y%m%d-%H%M%S"))
    pendientes = []
    for g in grupos:
        fuera = [m for m in g.miembros if m.id in ids_eliminar]
        quedan = [m for m in g.miembros if m.id not in ids_eliminar and os.path.exists(m.ruta)]
        if not fuera:
            continue
        if not quedan:
            res["errores"].append(f"Grupo «{g.miembros[0].nombre}»: no se puede eliminar todo; se omitió.")
            continue
        conservar = next((m for m in quedan if m.id == g.conservar_id), quedan[0])
        pendientes += [(m, conservar) for m in fuera]
    total = len(pendientes)
    for i, (m, conservar) in enumerate(pendientes, 1):
        if progreso_cb:
            progreso_cb(i, total, m.nombre)
        try:
            if not os.path.exists(m.ruta):
                db.marcar_no_disponible(m.id)
                continue
            db.fusionar_progreso(m.id, conservar.id)
            if definitivo:
                os.remove(m.ruta)
            else:
                try:
                    rel = os.path.relpath(m.ruta, raiz)
                    if rel.startswith(".."):
                        rel = os.path.basename(m.ruta)
                except ValueError:
                    rel = os.path.basename(m.ruta)
                destino = os.path.join(destino_base, rel)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                base, ext = os.path.splitext(destino)
                k = 1
                while os.path.exists(destino):
                    destino, k = f"{base} ({k}){ext}", k + 1
                shutil.move(m.ruta, destino)
                res["carpeta"] = destino_base
            db.marcar_no_disponible(m.id)
            res["eliminados"] += 1
            res["bytes"] += m.tam
        except OSError as e:
            res["errores"].append(f"{m.nombre}: {e}")
    return res


def formatear_bytes(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024
