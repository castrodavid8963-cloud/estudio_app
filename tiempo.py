"""Registro AUTOMÁTICO del tiempo de estudio (reemplaza al antiguo botón Clock-In).

Idea: el tiempo se acredita solo mientras hay actividad real en un libro (leer, cambiar de página,
preguntarle a la IA). Si no hay actividad durante `inactividad` segundos, el reloj se detiene sin
contar ese hueco; si pasa `cierre` segundos sin actividad, la sesión se cierra y la siguiente
actividad abre una nueva. Nadie tiene que acordarse de pulsar nada.

La lógica no depende de la interfaz: la UI solo llama a `actividad()` cuando el usuario hace algo y
a `revisar()` cada pocos segundos. Los relojes son inyectables para poder probarla.
"""
import time
from datetime import datetime, timedelta

from database import obtener_conexion, obtener_config

INACTIVIDAD_S = 90        # sin actividad más de esto: el reloj se pausa (no se cuenta el hueco)
CIERRE_S = 300            # sin actividad más de esto: la sesión se cierra
MIN_SESION_S = 5          # sesiones más cortas se descartan (ruido)
PERSISTIR_CADA_S = 15     # frecuencia máxima de escritura en BD durante una sesión
META_DIARIA_DEFECTO_MIN = 30
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


class RastreadorEstudio:
    def __init__(self, reloj=time.monotonic, ahora=datetime.now,
                 inactividad=INACTIVIDAD_S, cierre=CIERRE_S):
        self._reloj = reloj
        self._ahora = ahora
        self.inactividad = inactividad
        self.cierre = cierre
        self._contexto = None            # (recurso_id, materia_id)
        self._resetear()

    # ------------------------------------------------------------------ estado
    def _resetear(self):
        self._ultimo = None              # instante de la última actividad
        self._acreditado = 0.0           # segundos acreditados en la sesión actual
        self._inicio_dt = None
        self._sesion_id = None
        self._ultima_escritura = None

    @property
    def contexto(self):
        return self._contexto

    @property
    def segundos_sesion(self) -> int:
        return int(self._acreditado)

    @property
    def activo(self) -> bool:
        """True si ahora mismo se está acreditando tiempo."""
        return (self._contexto is not None and self._ultimo is not None
                and self._reloj() - self._ultimo <= self.inactividad)

    # ------------------------------------------------------------------ API
    def iniciar_contexto(self, recurso_id, materia_id=None):
        """Declara qué libro se está estudiando. Si cambia, cierra la sesión anterior."""
        nuevo = (recurso_id, materia_id)
        if self._contexto == nuevo:
            return
        self.cerrar()
        self._contexto = nuevo

    def sin_contexto(self):
        """El usuario salió del lector/chat: se cierra la sesión."""
        self.cerrar()
        self._contexto = None

    def actividad(self):
        """Llamar cuando el usuario hace algo con el libro (scroll, página, tecla, pregunta a la IA)."""
        if self._contexto is None:
            return
        t = self._reloj()
        if self._ultimo is None:
            self._inicio_dt = self._ahora()
        else:
            hueco = t - self._ultimo
            if hueco > self.cierre:
                self.cerrar()
                self._inicio_dt = self._ahora()
            elif hueco <= self.inactividad:
                self._acreditado += hueco
        self._ultimo = t
        self._persistir(forzar=False)

    def revisar(self):
        """Llamar periódicamente (p. ej. cada 5 s). Cierra la sesión si lleva demasiado inactiva."""
        if self._contexto is None or self._ultimo is None:
            return
        if self._reloj() - self._ultimo > self.cierre:
            self.cerrar()

    def cerrar(self):
        """Termina la sesión actual y la guarda (si duró lo suficiente)."""
        if self._ultimo is not None:
            self._persistir(forzar=True)
        self._resetear()

    # ------------------------------------------------------------------ persistencia
    def _persistir(self, forzar: bool):
        if self._acreditado < MIN_SESION_S or self._contexto is None or self._inicio_dt is None:
            return
        t = self._reloj()
        if not forzar and self._ultima_escritura is not None and t - self._ultima_escritura < PERSISTIR_CADA_S:
            return
        recurso_id, materia_id = self._contexto
        fin = self._inicio_dt + timedelta(seconds=int(self._acreditado))
        with obtener_conexion() as conn:
            if self._sesion_id is None:
                cur = conn.execute(
                    "INSERT INTO sesiones_estudio (materia_id, recurso_id, fecha_inicio, fecha_fin, duracion_segundos) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (materia_id, recurso_id, self._inicio_dt.strftime(FORMATO_FECHA),
                     fin.strftime(FORMATO_FECHA), int(self._acreditado)),
                )
                self._sesion_id = cur.lastrowid
            else:
                conn.execute(
                    "UPDATE sesiones_estudio SET fecha_fin = ?, duracion_segundos = ? WHERE id = ?",
                    (fin.strftime(FORMATO_FECHA), int(self._acreditado), self._sesion_id),
                )
        self._ultima_escritura = t


# ============================================================================ estadísticas
def _hoy() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def segundos_por_dia(dias: int = 14, hoy: datetime = None) -> dict:
    """{'YYYY-MM-DD': segundos} para los últimos `dias` días (incluye días en cero)."""
    hoy = hoy or datetime.now()
    desde = (hoy - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
    with obtener_conexion() as conn:
        filas = conn.execute(
            "SELECT substr(fecha_inicio, 1, 10) AS d, SUM(duracion_segundos) FROM sesiones_estudio "
            "WHERE fecha_inicio >= ? GROUP BY d",
            (desde,),
        ).fetchall()
    datos = {d: int(s or 0) for d, s in filas}
    resultado = {}
    for i in range(dias - 1, -1, -1):
        d = (hoy - timedelta(days=i)).strftime("%Y-%m-%d")
        resultado[d] = datos.get(d, 0)
    return resultado


def segundos_hoy(hoy: datetime = None) -> int:
    hoy = hoy or datetime.now()
    return segundos_por_dia(1, hoy)[hoy.strftime("%Y-%m-%d")]


def segundos_semana(hoy: datetime = None) -> int:
    return sum(segundos_por_dia(7, hoy).values())


def racha_dias(minimo_s: int = 60, hoy: datetime = None) -> int:
    """Días consecutivos con estudio. Si hoy aún no se estudia, la racha de ayer sigue viva."""
    hoy = hoy or datetime.now()
    dias = segundos_por_dia(366, hoy)
    fechas = sorted(dias.keys(), reverse=True)
    i = 0
    if dias[fechas[0]] < minimo_s:
        i = 1
    racha = 0
    while i < len(fechas) and dias[fechas[i]] >= minimo_s:
        racha += 1
        i += 1
    return racha


def total_segundos() -> int:
    with obtener_conexion() as conn:
        return int(conn.execute("SELECT COALESCE(SUM(duracion_segundos), 0) FROM sesiones_estudio").fetchone()[0])


def segundos_por_libro(recurso_id: int) -> int:
    with obtener_conexion() as conn:
        return int(conn.execute(
            "SELECT COALESCE(SUM(duracion_segundos), 0) FROM sesiones_estudio WHERE recurso_id = ?",
            (recurso_id,)).fetchone()[0])


def libros_mas_estudiados(limite: int = 5) -> list:
    """[(recurso_id, nombre_archivo, segundos)] de más a menos tiempo."""
    with obtener_conexion() as conn:
        filas = conn.execute(
            """SELECT r.id, r.nombre_archivo, SUM(s.duracion_segundos) AS t
               FROM sesiones_estudio s JOIN recursos r ON r.id = s.recurso_id
               GROUP BY r.id ORDER BY t DESC LIMIT ?""",
            (limite,),
        ).fetchall()
    return [(f[0], f[1], int(f[2] or 0)) for f in filas]


def meta_diaria_segundos() -> int:
    try:
        return max(60, int(float(obtener_config("meta_diaria_min", META_DIARIA_DEFECTO_MIN))) * 60)
    except (TypeError, ValueError):
        return META_DIARIA_DEFECTO_MIN * 60


def formatear(segundos: int) -> str:
    """'45 s', '12 min', '1 h 05 min'."""
    segundos = int(segundos or 0)
    if segundos < 60:
        return f"{segundos} s"
    minutos = segundos // 60
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60:02d} min"
