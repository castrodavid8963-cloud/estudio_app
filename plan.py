"""Planificación: tiempo restante de una ruta, proyección contra una fecha meta y rejilla del mapa de calor.
Lógica pura (sin BD ni GUI) para poder probarla sola."""
import statistics
from datetime import date, datetime, timedelta

PAGINAS_HORA_DEFECTO = 20            # ritmo de lectura técnica si aún no hay datos propios
PAGINAS_HORA_MIN, PAGINAS_HORA_MAX = 6, 90
SEG_MIN_PARA_RITMO = 900             # un libro cuenta para medir tu ritmo desde 15 min de estudio
PAGINAS_MIN_PARA_RITMO = 5


def ritmo_paginas_hora(muestras) -> tuple:
    """muestras: [(paginas_leidas, segundos)] de libros ya trabajados. Devuelve (páginas/hora, 'medido'|'estimado').
    Usa la mediana (un libro raro no distorsiona) y la acota a valores razonables."""
    valores = []
    for paginas, segundos in muestras:
        if segundos >= SEG_MIN_PARA_RITMO and paginas >= PAGINAS_MIN_PARA_RITMO:
            valores.append(paginas / (segundos / 3600))
    if not valores:
        return float(PAGINAS_HORA_DEFECTO), "estimado"
    pph = statistics.median(valores)
    return float(min(PAGINAS_HORA_MAX, max(PAGINAS_HORA_MIN, pph))), "medido"


def paginas_restantes(libro: dict) -> float:
    """Páginas que faltan para dar el libro por terminado (según su avance, que ya respeta el modo por capítulos)."""
    if libro.get("estado") == "Completado":
        return 0.0
    paginas = libro.get("total_paginas") or 0
    if paginas <= 0:
        return 0.0
    return max(0.0, paginas * (1.0 - min(1.0, max(0.0, libro.get("avance") or 0.0))))


def segundos_restantes(libros, pph: float) -> int:
    """Tiempo de lectura que falta para `libros` a `pph` páginas por hora."""
    if pph <= 0:
        return 0
    return int(sum(paginas_restantes(l) for l in libros) / pph * 3600)


def ritmo_diario(seg_por_dia: dict, meta_diaria_s: int) -> tuple:
    """(segundos/día, 'real'|'meta'): promedio de los últimos días (con ceros); sin historial usa tu meta diaria."""
    if seg_por_dia and sum(seg_por_dia.values()) >= 600:
        return sum(seg_por_dia.values()) / len(seg_por_dia), "real"
    return float(meta_diaria_s), "meta"


def parsear_fecha(texto) -> date:
    try:
        return datetime.strptime(str(texto).strip()[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def proyeccion(restante_s: int, diario_s: float, fecha_meta=None, hoy: date = None) -> dict:
    """Cuánto falta y si se llega a la meta.
    estado: 'completa' | 'sin_meta' | 'a_tiempo' | 'justo' | 'atrasado' | 'vencida'."""
    hoy = hoy or date.today()
    out = {"restante_s": int(restante_s), "dias_necesarios": None, "fecha_estimada": None,
           "dias_hasta_meta": None, "necesario_por_dia_s": None, "estado": "sin_meta"}
    if restante_s <= 0:
        out["estado"] = "completa"
        return out
    if diario_s > 0:
        dias = max(1, -(-int(restante_s) // int(diario_s)))          # techo
        out["dias_necesarios"] = dias
        out["fecha_estimada"] = hoy + timedelta(days=dias)
    meta = parsear_fecha(fecha_meta) if not isinstance(fecha_meta, date) else fecha_meta
    if not meta:
        return out
    restan = (meta - hoy).days
    out["dias_hasta_meta"] = restan
    if restan < 0:
        out["estado"] = "vencida"
        return out
    out["necesario_por_dia_s"] = int(restante_s / max(1, restan))
    if out["dias_necesarios"] is None or out["dias_necesarios"] > restan * 1.15:
        out["estado"] = "atrasado"
    elif out["dias_necesarios"] > restan * 0.85:
        out["estado"] = "justo"
    else:
        out["estado"] = "a_tiempo"
    return out


# ------------------------------------------------------------------ mapa de calor
def nivel_calor(segundos: int, meta_s: int) -> int:
    """0 = nada, 1..4 según qué parte de tu meta diaria cubriste."""
    if segundos <= 0:
        return 0
    if segundos >= meta_s:
        return 4
    if segundos >= meta_s * 0.5:
        return 3
    if segundos >= meta_s * 0.2:
        return 2
    return 1


def rejilla_calor(seg_por_dia: dict, meta_s: int, semanas: int, hoy: date = None) -> list:
    """Columnas de semanas (lunes→domingo), la última es la actual. Cada celda: (fecha_iso, segundos, nivel) o None
    si es un día futuro. Devuelve `semanas` columnas de 7 celdas."""
    hoy = hoy or date.today()
    lunes_actual = hoy - timedelta(days=hoy.weekday())
    columnas = []
    for s in range(semanas - 1, -1, -1):
        lunes = lunes_actual - timedelta(weeks=s)
        col = []
        for d in range(7):
            dia = lunes + timedelta(days=d)
            if dia > hoy:
                col.append(None)
                continue
            iso = dia.isoformat()
            seg = int(seg_por_dia.get(iso, 0))
            col.append((iso, seg, nivel_calor(seg, meta_s)))
        columnas.append(col)
    return columnas


def etiquetas_meses(columnas: list) -> list:
    """[(indice_columna, 'ene')] en la primera semana de cada mes visible."""
    nombres = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    out, ultimo = [], None
    for i, col in enumerate(columnas):
        primero = next((c for c in col if c), None)
        if not primero:
            continue
        mes = int(primero[0][5:7])
        if mes != ultimo:
            if ultimo is not None or i == 0:
                out.append((i, nombres[mes - 1]))
            ultimo = mes
    return out


# ------------------------------------------------------------------ mini-proyectos sugeridos por el modelo
def parsear_proyectos(texto: str, maximo: int = 5) -> list:
    """[{'titulo','descripcion'}] a partir de la respuesta JSON del modelo (tolerante a variantes)."""
    import repaso
    out = []
    for item in repaso._lista_de(repaso._extraer_json(texto), ("proyectos", "mini_proyectos", "projects", "ideas")):
        if not isinstance(item, dict):
            continue
        t = repaso._txt(item.get("titulo") or item.get("nombre") or item.get("title"))
        d = repaso._txt(item.get("descripcion") or item.get("description") or item.get("detalle"))
        if len(t) >= 6:
            out.append({"titulo": t[:160], "descripcion": d[:600]})
        if len(out) >= maximo:
            break
    return out
