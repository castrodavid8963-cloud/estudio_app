import math
import os
import re
import unicodedata
from collections import Counter

import ollama

from pdf_core import fitz, PYMUPDF_LOCK

# ----------------------------------------------------------------- configuración
# Se pueden cambiar sin tocar código:  ESTUDIO_MODELO=llama3.2:3b  ESTUDIO_NUM_CTX=4096
MODELO_POR_DEFECTO = os.environ.get("ESTUDIO_MODELO", "qwen2.5-coder:3b")
NUM_CTX = int(os.environ.get("ESTUDIO_NUM_CTX", "8192"))

MAX_PAGINAS = 600                  # tope de páginas a leer por libro
MAX_CHARS_FRAGMENTO = 1200         # tamaño de cada fragmento indexado
MAX_CHARS_CONTEXTO = 7000          # texto del libro que se envía por consulta (~2k tokens)
MAX_MENSAJES_HISTORIAL = 8         # últimos mensajes del chat que se reenvían al modelo
MAX_CHARS_MENSAJE_HISTORIAL = 900

# Mensajes guardados que no deben reenviarse al modelo (saludos, errores y reportes)
_PREFIJOS_IGNORADOS = ("¡Hola! He cargado el libro", "¡Hola de nuevo!", "⚠️", "📊 REPORTE")

_cliente = ollama.Client(timeout=180)


class ErrorOllama(Exception):
    """No se pudo obtener una respuesta de Ollama. El mensaje es apto para mostrar al usuario."""


# ----------------------------------------------------------------- extracción
def extraer_fragmentos_pdf(ruta_pdf: str, max_paginas: int = MAX_PAGINAS) -> list:
    """Lee el PDF y lo parte en fragmentos [{'pagina': n, 'texto': str}, ...].

    Es lento en libros grandes: llamar desde un hilo, no desde la UI.
    """
    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return []

    fragmentos = []
    doc = None
    try:
        with PYMUPDF_LOCK:
            doc = fitz.open(ruta_pdf)
            total = min(len(doc), max_paginas)

        for i in range(total):
            # El lock se libera entre páginas para no bloquear la generación de portadas.
            with PYMUPDF_LOCK:
                texto = doc[i].get_text("text") or ""
            for trozo in _partir_texto(texto, MAX_CHARS_FRAGMENTO):
                fragmentos.append({"pagina": i + 1, "texto": trozo})
    except Exception as e:
        print(f"[PDF] Error extrayendo texto de {ruta_pdf}: {e}")
    finally:
        if doc is not None:
            with PYMUPDF_LOCK:
                doc.close()
    return fragmentos


def _partir_texto(texto: str, max_chars: int) -> list:
    """Divide el texto de una página en trozos <= max_chars respetando párrafos cuando se puede."""
    texto = re.sub(r"[ \t]+", " ", texto).strip()
    if not texto:
        return []

    trozos, actual = [], ""
    for parrafo in re.split(r"\n\s*\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        while len(parrafo) > max_chars:  # párrafo gigante: corte duro
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.append(parrafo[:max_chars])
            parrafo = parrafo[max_chars:]
        if len(actual) + len(parrafo) + 2 > max_chars and actual:
            trozos.append(actual)
            actual = parrafo
        else:
            actual = f"{actual}\n\n{parrafo}" if actual else parrafo
    if actual:
        trozos.append(actual)
    return trozos


# ----------------------------------------------------------------- búsqueda (BM25 simple)
_STOPWORDS = {
    "que", "los", "las", "del", "con", "una", "uno", "por", "para", "como", "mas", "pero", "sus",
    "este", "esta", "esto", "son", "les", "hay", "muy", "sin", "sobre", "entre", "cuando", "donde",
    "quien", "cual", "cuales", "tiene", "tienen", "puede", "pueden", "ser", "est", "fue", "han",
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "have", "has",
}


def _tokens(texto: str) -> list:
    """Minúsculas, sin acentos, sin stopwords y con raíz aproximada (primeros 6 caracteres)."""
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return [
        p[:6] for p in re.findall(r"[a-z0-9]{3,}", texto)
        if p not in _STOPWORDS
    ]


class IndiceLibro:
    """Índice en memoria de un libro para recuperar los fragmentos relevantes a una pregunta."""

    K1 = 1.5
    B = 0.75

    def __init__(self, fragmentos: list):
        self.fragmentos = fragmentos
        self._tf = [Counter(_tokens(f["texto"])) for f in fragmentos]
        self._largos = [sum(tf.values()) for tf in self._tf]
        n = len(fragmentos)
        self._prom = (sum(self._largos) / n) if n else 0.0

        df = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def __bool__(self):
        return bool(self.fragmentos)

    def _puntaje(self, i: int, terminos: set) -> float:
        tf, largo = self._tf[i], self._largos[i]
        norm = self.K1 * (1 - self.B + self.B * (largo / self._prom if self._prom else 1))
        total = 0.0
        for t in terminos:
            f = tf.get(t)
            if f:
                total += self._idf.get(t, 0.0) * (f * (self.K1 + 1)) / (f + norm)
        return total

    def contexto_para(self, pregunta: str, max_chars: int = MAX_CHARS_CONTEXTO) -> str:
        """Devuelve los fragmentos más relevantes a `pregunta`, en orden de lectura y con su página.

        Si la pregunta no comparte términos con el libro (p. ej. "haz un resumen"), se muestrea el
        libro de forma uniforme para dar una visión general.
        """
        if not self.fragmentos:
            return ""

        terminos = set(_tokens(pregunta))
        puntajes = [(self._puntaje(i, terminos), i) for i in range(len(self.fragmentos))] if terminos else []
        puntajes = [p for p in puntajes if p[0] > 0]
        puntajes.sort(reverse=True)

        elegidos, usados = [], 0
        for _, i in puntajes:
            largo = len(self.fragmentos[i]["texto"])
            if usados + largo > max_chars and elegidos:
                continue
            elegidos.append(i)
            usados += largo
            if usados >= max_chars:
                break

        if not elegidos:
            # Muestreo uniforme: un fragmento cada cierto paso a lo largo del libro.
            prom = max(1, sum(len(f["texto"]) for f in self.fragmentos) // len(self.fragmentos))
            cuantos = max(1, min(len(self.fragmentos), max_chars // prom))
            paso = len(self.fragmentos) / cuantos
            elegidos = sorted({int(k * paso) for k in range(cuantos)})

        partes = []
        for i in sorted(elegidos):
            f = self.fragmentos[i]
            partes.append(f"[Página {f['pagina']}]\n{f['texto']}")
        return "\n\n".join(partes)[:max_chars + 200]


# ----------------------------------------------------------------- chat
def historial_a_mensajes(historial) -> list:
    """Convierte el historial guardado [{'emisor','texto'}] a mensajes de chat de Ollama."""
    mensajes = []
    for m in (historial or []):
        texto = (m.get("texto") or "").strip()
        if not texto or texto.startswith(_PREFIJOS_IGNORADOS):
            continue
        rol = "user" if m.get("emisor") == "USUARIO" else "assistant" if m.get("emisor") == "IA" else None
        if rol:
            mensajes.append({"role": rol, "content": texto[:MAX_CHARS_MENSAJE_HISTORIAL]})
    return mensajes[-MAX_MENSAJES_HISTORIAL:]


def consultar_ollama_con_contexto(
    pregunta: str,
    contexto_pdf: str = "",
    nombre_pdf: str = "",
    historial=None,
    modelo: str = None,
) -> str:
    """Consulta a Ollama con el libro activo, el historial reciente y la pregunta.

    Lanza `ErrorOllama` si algo falla (así el error nunca se confunde con una respuesta de la IA).
    """
    modelo = modelo or MODELO_POR_DEFECTO
    hay_libro = bool(nombre_pdf) and nombre_pdf != "Ninguno"

    if hay_libro:
        sistema = (
            f"Eres un tutor de estudio experto. El estudiante está estudiando el libro '{nombre_pdf}'. "
            "Explica conceptos, haz resúmenes, resuelve dudas y sugiere guías de estudio. "
            "Responde siempre en español, de forma clara y estructurada. "
            "Cuando uses los fragmentos del libro, indica la página entre paréntesis, por ejemplo (p. 12). "
            "Si la respuesta no está en los fragmentos, dilo y responde con tu conocimiento general "
            "dejando claro que no proviene del libro. No inventes citas."
        )
        if contexto_pdf.strip():
            sistema += f"\n\nFRAGMENTOS RELEVANTES DEL LIBRO:\n{contexto_pdf[:MAX_CHARS_CONTEXTO + 200]}"
        else:
            sistema += (
                "\n\n(No se pudo extraer texto legible del PDF; puede ser un documento escaneado. "
                "Usa el título como guía y avisa al estudiante de esta limitación.)"
            )
    else:
        sistema = (
            "Eres un tutor de estudio personal experto y didáctico. "
            "Responde en español, de forma clara, estructurada y concisa."
        )

    mensajes = [{"role": "system", "content": sistema}]
    mensajes += historial_a_mensajes(historial)
    mensajes.append({"role": "user", "content": pregunta})

    try:
        respuesta = _cliente.chat(
            model=modelo,
            messages=mensajes,
            options={"num_ctx": NUM_CTX, "temperature": 0.3},
        )
        contenido = (respuesta["message"]["content"] or "").strip()
    except Exception as e:
        raise ErrorOllama(f"No se pudo obtener respuesta de Ollama (modelo '{modelo}'): {e}") from e

    if not contenido:
        raise ErrorOllama("Ollama devolvió una respuesta vacía.")
    return contenido


# ============================================================================ tarjetas y quizzes
_SISTEMA_ESTUDIO = (
    "Eres un profesor que prepara material de estudio a partir de un texto de un libro. "
    "Escribes siempre en español, con preguntas claras y autocontenidas (que se entiendan sin ver el texto), "
    "basadas únicamente en lo que dice el texto. Respondes SOLO con JSON válido, sin comentarios."
)


def _generar_json(instruccion: str, texto: str, nombre_pdf: str, modelo: str = None) -> str:
    modelo = modelo or MODELO_POR_DEFECTO
    if len((texto or "").strip()) < 200:
        raise ErrorOllama("Ese fragmento casi no tiene texto (¿es una página escaneada o de imágenes?).")
    mensajes = [
        {"role": "system", "content": _SISTEMA_ESTUDIO},
        {"role": "user", "content": f"Libro: {nombre_pdf}\n\nTEXTO:\n{texto[:MAX_CHARS_CONTEXTO + 2500]}\n\n{instruccion}"},
    ]
    try:
        r = _cliente.chat(model=modelo, messages=mensajes, format="json",
                          options={"num_ctx": NUM_CTX, "temperature": 0.4})
        contenido = (r["message"]["content"] or "").strip()
    except Exception as e:
        raise ErrorOllama(f"No se pudo obtener respuesta de Ollama (modelo '{modelo}'): {e}") from e
    if not contenido:
        raise ErrorOllama("Ollama devolvió una respuesta vacía.")
    return contenido


def generar_tarjetas_ia(texto: str, nombre_pdf: str, cantidad: int = 6, modelo: str = None) -> list:
    """Tarjetas [{'pregunta','respuesta'}] para repasar el texto dado."""
    import repaso
    crudo = _generar_json(
        f"Crea {cantidad} tarjetas de repaso (pregunta y respuesta corta) con los conceptos, definiciones o "
        "procedimientos más importantes del texto. Evita preguntas triviales o de sí/no. Formato exacto: "
        '{"tarjetas": [{"pregunta": "...", "respuesta": "..."}]}', texto, nombre_pdf, modelo)
    tarjetas = repaso.parsear_tarjetas(crudo, cantidad + 3)
    if not tarjetas:
        raise ErrorOllama("El modelo no devolvió tarjetas utilizables. Prueba de nuevo o con otro modelo.")
    return tarjetas


def generar_quiz_ia(texto: str, nombre_pdf: str, cantidad: int = 5, modelo: str = None) -> list:
    """Preguntas de opción múltiple [{'pregunta','opciones','correcta','explicacion'}]."""
    import repaso
    crudo = _generar_json(
        f"Crea {cantidad} preguntas de opción múltiple con exactamente 4 opciones cada una, una sola correcta y "
        "distractores plausibles. Indica la correcta con la letra A, B, C o D y una explicación de una frase. "
        'Formato exacto: {"preguntas": [{"pregunta": "...", "opciones": ["...", "...", "...", "..."], '
        '"correcta": "B", "explicacion": "..."}]}', texto, nombre_pdf, modelo)
    quiz = repaso.parsear_quiz(crudo, cantidad + 2)
    if not quiz:
        raise ErrorOllama("El modelo no devolvió preguntas utilizables. Prueba de nuevo o con otro modelo.")
    return quiz
