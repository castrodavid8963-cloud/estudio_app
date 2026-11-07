"""Capítulos de un PDF y modo de lectura (completo / por capítulos). Lógica pura: no toca la BD ni la GUI."""
import re
import unicodedata

UMBRAL_PAGINAS_LARGO = 350
PALABRAS_CONSULTA = ("manual", "reference", "referencia", "cookbook", "handbook", "encyclopedia", "enciclopedia",
                     "cheat sheet", "cheatsheet", "recetario", "compendio")
MODOS = ("auto", "completo", "capitulos")
NOMBRE_MODO = {"auto": "Automático", "completo": "Completo", "capitulos": "Por capítulos"}

# Entradas del índice que no son contenido de estudio: empiezan sin contar para el progreso.
_NO_CAPITULO = re.compile(
    r"^(portada|cover|front\s*cover|back\s*cover|title\s*page|half\s*title|copyright|colophon|dedication|dedicatoria|"
    r"table\s+of\s+contents|contents|contenido|indice|index|preface|prefacio|foreword|prologo|acknowledg|"
    r"agradecimientos|about\s+the|sobre\s+el\s+autor|acerca\s+del|bibliograf|references|referencias|glosario|glossary|"
    r"list\s+of\s+(figures|tables)|lista\s+de\s+(figuras|tablas)|errata|credits|creditos)\b")


def _normalizar(texto: str) -> str:
    sin = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin if not unicodedata.combining(c)).casefold().strip()


def es_no_capitulo(titulo: str) -> bool:
    return bool(_NO_CAPITULO.match(_normalizar(titulo)))


def extraer_capitulos(toc: list, total_paginas: int) -> list:
    """De `doc.get_toc(simple=True)` ([nivel, título, página]) saca la lista de capítulos:
    [{"titulo", "nivel", "pagina_ini", "pagina_fin", "incluido"}], ordenados por página.

    Elige el nivel del índice que mejor sirve como «capítulo»: el primero con al menos 3 entradas
    (si el nivel 1 es solo el título del libro, usa el 2)."""
    entradas = []
    for fila in toc or []:
        try:
            nivel, titulo, pagina = int(fila[0]), str(fila[1]).strip(), int(fila[2])
        except (TypeError, ValueError, IndexError):
            continue
        if titulo and 1 <= pagina <= total_paginas:
            entradas.append((nivel, titulo, pagina))
    if not entradas:
        return []
    niveles = sorted({n for n, _, _ in entradas})
    elegido = next((n for n in niveles if sum(1 for e in entradas if e[0] == n) >= 3), niveles[0])
    base = sorted(((p, t) for n, t, p in entradas if n == elegido), key=lambda x: x[0])
    unicos, vistos = [], set()
    for pagina, titulo in base:
        if pagina in vistos:            # dos entradas en la misma página: se conserva la primera
            continue
        vistos.add(pagina)
        unicos.append((pagina, titulo))
    unicos = unicos[:250]
    caps = []
    for i, (pagina, titulo) in enumerate(unicos):
        fin = unicos[i + 1][0] - 1 if i + 1 < len(unicos) else total_paginas
        caps.append({"titulo": titulo, "nivel": elegido, "pagina_ini": pagina, "pagina_fin": max(pagina, fin),
                     "incluido": 0 if es_no_capitulo(titulo) else 1})
    return caps


def sugerir_modo(titulo: str, paginas: int, n_capitulos: int, indice_leido: bool = True) -> tuple:
    """Sugerencia automática: («completo» | «capitulos», motivo en español)."""
    if n_capitulos < 2:
        return "completo", ("el PDF no trae índice interno" if indice_leido else "índice aún sin leer")
    t = _normalizar(titulo)
    if any(p in t for p in PALABRAS_CONSULTA):
        return "capitulos", "parece un libro de consulta"
    if paginas > UMBRAL_PAGINAS_LARGO:
        return "capitulos", f"libro largo ({paginas} páginas)"
    return "completo", "libro corto o de teoría"


def modo_efectivo(modo: str, titulo: str, paginas: int, n_capitulos: int, indice_leido: bool = True) -> tuple:
    """Modo con el que se mide el libro: (modo, motivo). El elegido por el usuario manda sobre la sugerencia."""
    if modo == "completo":
        return "completo", "elegido por ti"
    if modo == "capitulos":
        if n_capitulos < 2:
            return "completo", "pediste capítulos, pero el PDF no trae índice"
        return "capitulos", "elegido por ti"
    return sugerir_modo(titulo, paginas, n_capitulos, indice_leido)


def capitulo_de(caps: list, pagina: int):
    """Capítulo que contiene la página (o None)."""
    for c in caps:
        if c["pagina_ini"] <= pagina <= c["pagina_fin"]:
            return c
    return None
