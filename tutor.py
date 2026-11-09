"""Piezas puras del tutor: citas de página en las respuestas y modo socrático. Sin GUI ni Ollama, para poder probarlas."""
import re

# «(p. 12)», «p. 12», «pág. 12-14», «págs. 3, 5 y 9», «página 7», «pp. 4–6», «(pp. 4 y 6)»
_CITA = re.compile(
    r"\b(?:p(?:p|[aá]gs?|[aá]ginas?)?)\.?\s*(\d{1,5})(?:\s*(?:[-–—]|a)\s*(\d{1,5}))?"
    r"((?:\s*(?:,|y|e)\s*\d{1,5})*)",
    re.IGNORECASE)
_NUM = re.compile(r"\d{1,5}")


def citas_en_texto(texto: str, total_paginas: int = 0) -> list:
    """[(inicio, fin, pagina)] de cada número de página citado, con su posición exacta en el texto.
    Descarta páginas fuera del libro (si se conoce el total). Un rango «12-14» enlaza a la primera."""
    out = []
    for m in _CITA.finditer(texto or ""):
        if not re.match(r"p", m.group(0), re.IGNORECASE):
            continue
        # el prefijo debe ser una abreviatura real, no «porque 12»
        prefijo = re.match(r"[A-Za-zÁáÉéÍíÓóÚú]+", m.group(0)).group(0).lower()
        if prefijo not in ("p", "pp", "pag", "pág", "pags", "págs", "pagina", "página", "paginas", "páginas"):
            continue
        for n in _NUM.finditer(m.group(0)[len(prefijo):]):
            pag = int(n.group(0))
            if pag < 1 or (total_paginas and pag > total_paginas):
                continue
            ini = m.start() + len(prefijo) + n.start()
            out.append((ini, ini + len(n.group(0)), pag))
            if n.start() < len(m.group(0)) and re.match(r"\s*(?:[-–—]|a)\s*\d", m.group(0)[len(prefijo) + n.end():]):
                break      # solo el inicio del rango es enlace
    return out


def partir_con_citas(texto: str, total_paginas: int = 0) -> list:
    """[(trozo, pagina_o_None)] para pintar el texto con las citas como enlaces."""
    trozos, pos = [], 0
    for ini, fin, pag in citas_en_texto(texto, total_paginas):
        if ini < pos:
            continue
        if ini > pos:
            trozos.append((texto[pos:ini], None))
        trozos.append((texto[ini:fin], pag))
        pos = fin
    if pos < len(texto):
        trozos.append((texto[pos:], None))
    return trozos


def etiqueta_fuentes(paginas: list, maximo: int = 8) -> str:
    """«Fuentes: p. 12, 15, 40» para las páginas realmente usadas como contexto (ordenadas, sin repetir)."""
    unicas = sorted({int(p) for p in paginas})
    if not unicas:
        return ""
    extra = f" y {len(unicas) - maximo} más" if len(unicas) > maximo else ""
    return "Fuentes: p. " + ", ".join(str(p) for p in unicas[:maximo]) + extra


SOCRATICO = (
    "MODO SOCRÁTICO: tu objetivo es que el estudiante llegue a la respuesta por sí mismo. "
    "No des la solución completa de entrada. Responde con UNA sola pregunta guía (máximo dos frases antes de ella) "
    "que apunte al siguiente paso del razonamiento, apoyándote en el libro. "
    "Si el estudiante responde, dile con claridad qué acertó y qué le falta, y haz la siguiente pregunta. "
    "Si dice que no sabe o pide la respuesta, da una pista concreta; si insiste, explícalo completo y termina con "
    "una pregunta para comprobar que lo entendió."
)
