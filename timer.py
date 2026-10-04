import datetime
from database import obtener_conexion

class CronometroEstudio:
    def __init__(self):
        self.activo = False
        self.en_pausa = False
        self.segundos_acumulados = 0
        self.materia_id = None
        self.semana_id = None
        self.fecha_inicio = None

    def clock_in(self, materia_id: int, semana_id: int = None):
        """Inicia el conteo de tiempo para una materia dada."""
        self.materia_id = materia_id
        self.semana_id = semana_id
        self.segundos_acumulados = 0
        self.activo = True
        self.en_pausa = False
        self.fecha_inicio = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def pausar_o_reanudar(self):
        """Alterna el estado de pausa."""
        if self.activo:
            self.en_pausa = not self.en_pausa

    def tick(self):
        """Aumenta un segundo si el cronómetro está activo y no pausado."""
        if self.activo and not self.en_pausa:
            self.segundos_acumulados += 1

    def clock_out(self, notas: str = "") -> int:
        """Detiene el cronómetro y guarda el registro de la sesión en SQLite."""
        if not self.activo:
            return 0

        fecha_fin = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duracion_final = self.segundos_acumulados

        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO sesiones_estudio (materia_id, semana_id, fecha_inicio, fecha_fin, duracion_segundos, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (self.materia_id, self.semana_id, self.fecha_inicio, fecha_fin, duracion_final, notas))
            conn.commit()

        # Resetear variables
        self.activo = False
        self.en_pausa = False
        self.segundos_acumulados = 0
        self.materia_id = None
        self.semana_id = None
        self.fecha_inicio = None

        return duracion_final

    def obtener_tiempo_formateado(self) -> str:
        """Retorna el tiempo transcurrido en formato HH:MM:SS."""
        horas = self.segundos_acumulados // 3600
        minutos = (self.segundos_acumulados % 3600) // 60
        segundos = self.segundos_acumulados % 60
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"