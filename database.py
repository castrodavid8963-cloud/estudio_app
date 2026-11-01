import os
import sqlite3
from contextlib import contextmanager

# La BD vive junto al código, sin importar desde dónde se lance la app.
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estudios.db")


@contextmanager
def obtener_conexion():
    """Abre una conexión SQLite, confirma al salir sin errores y SIEMPRE la cierra.

    `with sqlite3.connect(...)` por sí solo hace commit/rollback pero no cierra
    la conexión; este contexto sí lo hace. Es compatible con el uso anterior:
    `with obtener_conexion() as conn: ...`.
    """
    conn = sqlite3.connect(DB_NAME, timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columnas(cursor, tabla: str) -> set:
    cursor.execute(f"PRAGMA table_info({tabla})")
    return {fila[1] for fila in cursor.fetchall()}


def _agregar_columna_si_falta(cursor, tabla: str, columna: str, definicion: str):
    if columna not in _columnas(cursor, tabla):
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def inicializar_db():
    """Crea el esquema completo y aplica migraciones sobre BDs ya existentes."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()

        # ---------------- Materias ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS materias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                tipo TEXT DEFAULT 'Personal',
                descripcion TEXT,
                icono TEXT DEFAULT '📚',
                color_tag TEXT DEFAULT '#1f538d',
                ultima_actividad TEXT,
                estado_materia TEXT DEFAULT 'Activa'
            )
        """)
        _agregar_columna_si_falta(cursor, "materias", "icono", "TEXT DEFAULT '📚'")
        _agregar_columna_si_falta(cursor, "materias", "color_tag", "TEXT DEFAULT '#1f538d'")
        _agregar_columna_si_falta(cursor, "materias", "ultima_actividad", "TEXT")
        _agregar_columna_si_falta(cursor, "materias", "estado_materia", "TEXT DEFAULT 'Activa'")

        # ---------------- Semanas ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS semanas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_id INTEGER NOT NULL,
                numero_semana INTEGER NOT NULL DEFAULT 1,
                titulo_tema TEXT,
                FOREIGN KEY (materia_id) REFERENCES materias(id)
            )
        """)

        # ---------------- Recursos (PDFs) ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recursos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                semana_id INTEGER NOT NULL,
                tipo TEXT DEFAULT 'PDF',
                nombre_archivo TEXT NOT NULL,
                ruta_local TEXT NOT NULL,
                estado TEXT DEFAULT 'Sin empezar',
                es_favorito INTEGER DEFAULT 0,
                historial_chat TEXT,
                huella TEXT,
                disponible INTEGER DEFAULT 1,
                FOREIGN KEY (semana_id) REFERENCES semanas(id)
            )
        """)
        _agregar_columna_si_falta(cursor, "recursos", "estado", "TEXT DEFAULT 'Sin empezar'")
        _agregar_columna_si_falta(cursor, "recursos", "es_favorito", "INTEGER DEFAULT 0")
        _agregar_columna_si_falta(cursor, "recursos", "historial_chat", "TEXT")
        _agregar_columna_si_falta(cursor, "recursos", "huella", "TEXT")
        _agregar_columna_si_falta(cursor, "recursos", "disponible", "INTEGER DEFAULT 1")

        # Normalización de datos antiguos: la app siempre usó 'Completado'.
        cursor.execute("UPDATE recursos SET estado = 'Completado' WHERE estado = 'Terminado'")
        cursor.execute("UPDATE recursos SET estado = 'Sin empezar' WHERE estado IS NULL")
        cursor.execute("UPDATE recursos SET es_favorito = 0 WHERE es_favorito IS NULL")
        cursor.execute("UPDATE recursos SET disponible = 1 WHERE disponible IS NULL")

        # ---------------- Sesiones de estudio ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sesiones_estudio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                materia_id INTEGER,
                semana_id INTEGER,
                fecha_inicio TEXT,
                fecha_fin TEXT,
                duracion_segundos INTEGER DEFAULT 0,
                notas TEXT
            )
        """)

        # ---------------- Configuración ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)

        # ---------------- Índices ----------------
        # Estos pueden fallar si la BD antigua ya contiene duplicados; en ese
        # caso la app sigue funcionando y solo se omite la restricción.
        for sentencia in (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_materias_nombre ON materias(nombre)",
            "CREATE INDEX IF NOT EXISTS idx_recursos_ruta ON recursos(ruta_local)",
            "CREATE INDEX IF NOT EXISTS idx_recursos_huella ON recursos(huella)",
            "CREATE INDEX IF NOT EXISTS idx_semanas_materia ON semanas(materia_id)",
            "CREATE INDEX IF NOT EXISTS idx_recursos_semana ON recursos(semana_id)",
        ):
            try:
                cursor.execute(sentencia)
            except sqlite3.DatabaseError as e:
                print(f"[BD] Índice omitido ({e}): {sentencia}")


def obtener_materias_con_estadisticas():
    """Recupera cada materia junto con su total de PDFs y porcentaje de avance."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                m.id,
                m.nombre,
                m.tipo,
                m.icono,
                m.ultima_actividad,
                COUNT(r.id) AS total_recursos,
                SUM(CASE WHEN r.estado = 'Completado' THEN 1 ELSE 0 END) AS completados
            FROM materias m
            LEFT JOIN semanas s ON s.materia_id = m.id
            LEFT JOIN recursos r ON r.semana_id = s.id AND r.disponible = 1
            GROUP BY m.id
            ORDER BY
                CASE WHEN m.ultima_actividad IS NULL THEN 1 ELSE 0 END,
                m.ultima_actividad DESC,
                m.nombre ASC
        """
        cursor.execute(query)
        filas = cursor.fetchall()

    resultado = []
    for f in filas:
        total = f[5] or 0
        completados = f[6] or 0
        progreso = (completados / total) if total > 0 else 0.0

        resultado.append({
            "id": f[0],
            "nombre": f[1],
            "tipo": f[2],
            "icono": f[3] or "📚",
            "ultima_actividad": f[4] or "Sin actividad",
            "total_recursos": total,
            "completados": completados,
            "progreso": progreso,
        })
    return resultado


def registrar_actividad_materia(materia_id):
    """Actualiza la fecha de última actividad al abrir/estudiar un recurso de la materia."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE materias SET ultima_actividad = CURRENT_TIMESTAMP WHERE id = ?",
            (materia_id,),
        )
