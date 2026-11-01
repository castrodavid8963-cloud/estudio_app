import datetime
import time

from database import obtener_conexion


class CronometroEstudio:
    """Cronómetro de sesiones de estudio.

    El tiempo se mide con `time.monotonic()` en lugar de contar "ticks" de la UI,
    así que no se desfasa si la interfaz se bloquea un momento y no depende de
    cambios del reloj del sistema.
    """

    def __init__(self):
        self.activo = False
        self.en_pausa = False
        self.materia_id = None
        self.semana_id = None
        self.fecha_inicio = None
        self._acumulado = 0.0          # segundos de tramos ya cerrados
        self._inicio_tramo = None      # monotonic() del tramo en curso (None si está en pausa)

    # ------------------------------------------------------------------ estado
    @property
    def segundos_acumulados(self) -> int:
        total = self._acumulado
        if self.activo and not self.en_pausa and self._inicio_tramo is not None:
            total += time.monotonic() - self._inicio_tramo
        return int(total)

    def _reiniciar_estado(self):
        self.activo = False
        self.en_pausa = False
        self.materia_id = None
        self.semana_id = None
        self.fecha_inicio = None
        self._acumulado = 0.0
        self._inicio_tramo = None

    # ----------------------------------------------------------------- acciones
    def clock_in(self, materia_id: int, semana_id: int = None) -> bool:
        """Inicia una sesión para la materia dada.

        - Si ya hay una sesión de ESA materia en curso, no hace nada (devuelve False).
        - Si hay una sesión de OTRA materia, la guarda primero (no se pierde su tiempo)
          y luego inicia la nueva.
        """
        if self.activo:
            if self.materia_id == materia_id:
                return False
            self.clock_out(notas="(cierre automático al cambiar de materia)")

        self.materia_id = materia_id
        self.semana_id = semana_id
        self._acumulado = 0.0
        self._inicio_tramo = time.monotonic()
        self.activo = True
        self.en_pausa = False
        self.fecha_inicio = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    def pausar_o_reanudar(self):
        """Alterna el estado de pausa."""
        if not self.activo:
            return
        if self.en_pausa:
            self._inicio_tramo = time.monotonic()
            self.en_pausa = False
        else:
            self._acumulado += time.monotonic() - self._inicio_tramo
            self._inicio_tramo = None
            self.en_pausa = True

    def clock_out(self, notas: str = "") -> int:
        """Detiene el cronómetro y guarda la sesión en SQLite. Devuelve la duración en segundos."""
        if not self.activo:
            return 0

        duracion_final = self.segundos_acumulados
        fecha_fin = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            if duracion_final > 0:
                with obtener_conexion() as conn:
                    conn.execute(
                        """
                        INSERT INTO sesiones_estudio
                            (materia_id, semana_id, fecha_inicio, fecha_fin, duracion_segundos, notas)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (self.materia_id, self.semana_id, self.fecha_inicio, fecha_fin,
                         duracion_final, notas),
                    )
        finally:
            self._reiniciar_estado()

        return duracion_final

    def obtener_tiempo_formateado(self) -> str:
        """Tiempo transcurrido en formato HH:MM:SS."""
        s = self.segundos_acumulados
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"
