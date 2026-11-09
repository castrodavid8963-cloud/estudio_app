"""Repaso espaciado: programación de tarjetas (variante simple de SM-2) y lectura de lo que genera el modelo.
Lógica pura, sin BD ni GUI, para poder probarla sola."""
import json
import re
from datetime import date, timedelta

OTRA_VEZ, DIFICIL, BIEN, FACIL = 0, 1, 2, 3
NOMBRES = {OTRA_VEZ: "Otra vez", DIFICIL: "Difícil", BIEN: "Bien", FACIL: "Fácil"}
FACILIDAD_INICIAL, FACILIDAD_MIN = 2.5, 1.3


def programar(tarjeta: dict, calidad: int, hoy: date = None) -> dict:
    """Devuelve los campos nuevos de la tarjeta tras responder con `calidad` (0-3).
    tarjeta: facilidad, intervalo (días), repeticiones, lapsos."""
    hoy = hoy or date.today()
    f = float(tarjeta.get("facilidad") or FACILIDAD_INICIAL)
    intervalo = int(tarjeta.get("intervalo") or 0)
    reps = int(tarjeta.get("repeticiones") or 0)
    lapsos = int(tarjeta.get("lapsos") or 0)

    if calidad == OTRA_VEZ:
        lapsos += 1
        reps = 0
        f = max(FACILIDAD_MIN, f - 0.2)
        intervalo = 0                              # se vuelve a ver hoy mismo
    else:
        if reps == 0:
            intervalo = {DIFICIL: 1, BIEN: 1, FACIL: 3}[calidad]
        elif reps == 1:
            intervalo = {DIFICIL: 2, BIEN: 4, FACIL: 7}[calidad]
        else:
            mult = {DIFICIL: 1.2, BIEN: f, FACIL: f * 1.3}[calidad]
            intervalo = max(intervalo + 1, round(intervalo * mult))
        f = max(FACILIDAD_MIN, f + {DIFICIL: -0.15, BIEN: 0.0, FACIL: 0.15}[calidad])
        reps += 1
    return {
        "facilidad": round(f, 3), "intervalo": intervalo, "repeticiones": reps, "lapsos": lapsos,
        "proxima": (hoy + timedelta(days=intervalo)).isoformat(),
        "ultima": hoy.isoformat(),
        "estado": "repaso" if reps > 0 else "aprendiendo",
    }


def etiqueta_intervalo(dias: int) -> str:
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "1 día"
    if dias < 30:
        return f"{dias} días"
    if dias < 365:
        meses = round(dias / 30)
        return f"{meses} mes" if meses == 1 else f"{meses} meses"
    return f"{dias / 365:.1f} años"


def vista_previa(tarjeta: dict, hoy: date = None) -> dict:
    """{calidad: «3 días»} para rotular los cuatro botones."""
    return {q: etiqueta_intervalo(programar(tarjeta, q, hoy)["intervalo"]) for q in (OTRA_VEZ, DIFICIL, BIEN, FACIL)}


# ------------------------------------------------------------------ lo que devuelve el modelo
def _extraer_json(texto: str):
    """Saca el primer objeto o lista JSON de la respuesta (con o sin ``` ni texto alrededor)."""
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE)
    for apertura, cierre in (("{", "}"), ("[", "]")):
        i, j = texto.find(apertura), texto.rfind(cierre)
        if i != -1 and j > i:
            try:
                return json.loads(texto[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


def _lista_de(dato, claves):
    if isinstance(dato, list):
        return dato
    if isinstance(dato, dict):
        for k in claves:
            if isinstance(dato.get(k), list):
                return dato[k]
        for v in dato.values():
            if isinstance(v, list):
                return v
    return []


def _txt(v) -> str:
    return " ".join(str(v).split()) if v is not None else ""


def parsear_tarjetas(texto: str, maximo: int = 12) -> list:
    """[{'pregunta', 'respuesta'}] válidas (ambas con contenido y no demasiado largas)."""
    out = []
    for item in _lista_de(_extraer_json(texto), ("tarjetas", "cards", "flashcards", "preguntas")):
        if not isinstance(item, dict):
            continue
        p = _txt(item.get("pregunta") or item.get("frente") or item.get("question") or item.get("front"))
        r = _txt(item.get("respuesta") or item.get("reverso") or item.get("answer") or item.get("back"))
        if len(p) >= 8 and len(r) >= 2:
            out.append({"pregunta": p[:400], "respuesta": r[:700]})
        if len(out) >= maximo:
            break
    return out


def parsear_quiz(texto: str, maximo: int = 10) -> list:
    """[{'pregunta', 'opciones': [4], 'correcta': 0-3, 'explicacion'}] válidas."""
    out = []
    for item in _lista_de(_extraer_json(texto), ("preguntas", "quiz", "questions")):
        if not isinstance(item, dict):
            continue
        p = _txt(item.get("pregunta") or item.get("question"))
        ops = item.get("opciones") or item.get("options") or item.get("respuestas")
        if isinstance(ops, dict):
            ops = list(ops.values())
        if not p or not isinstance(ops, list):
            continue
        ops = [re.sub(r"^\s*(?:[A-Da-d][\).:-]|\d[\).:-])\s*", "", _txt(o)) for o in ops if _txt(o)]
        if len(ops) < 3:
            continue
        ops = ops[:4]
        correcta = item.get("correcta", item.get("respuesta_correcta", item.get("correct", item.get("answer"))))
        idx = None
        if isinstance(correcta, int) and not isinstance(correcta, bool):
            idx = correcta if 0 <= correcta < len(ops) else (correcta - 1 if 1 <= correcta <= len(ops) else None)
        elif isinstance(correcta, str):
            c = correcta.strip()
            if len(c) == 1 and c.upper() in "ABCD":
                idx = "ABCD".index(c.upper())
            elif c.isdigit():
                n = int(c)                 # en texto se entiende «1…4» (1 = primera opción)
                idx = n - 1 if 1 <= n <= len(ops) else (0 if n == 0 else None)
            else:
                limpio = re.sub(r"^\s*(?:[A-Da-d][\).:-])\s*", "", _txt(c)).casefold()
                idx = next((i for i, o in enumerate(ops) if o.casefold() == limpio), None)
        if idx is None or idx >= len(ops):
            continue
        out.append({"pregunta": p[:400], "opciones": [o[:300] for o in ops], "correcta": idx,
                    "explicacion": _txt(item.get("explicacion") or item.get("explanation"))[:500]})
        if len(out) >= maximo:
            break
    return out


def normalizar_pregunta(p: str) -> str:
    return re.sub(r"[^\w]+", " ", (p or "").casefold()).strip()
