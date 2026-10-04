import sqlite3
import json

DB_NAME = "estudios.db"

def obtener_conexion():
    return sqlite3.connect(DB_NAME)

def inicializar_db():
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        
        # Tabla de Materias con campos visuales y de seguimiento
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

        # Migraciones automáticas por si las tablas ya existían
        cursor.execute("PRAGMA table_info(materias)")
        cols = [col[1] for col in cursor.fetchall()]
        
        if "icono" not in cols:
            cursor.execute("ALTER TABLE materias ADD COLUMN icono TEXT DEFAULT '📚'")
        if "color_tag" not in cols:
            cursor.execute("ALTER TABLE materias ADD COLUMN color_tag TEXT DEFAULT '#1f538d'")
        if "ultima_actividad" not in cols:
            cursor.execute("ALTER TABLE materias ADD COLUMN ultima_actividad TEXT")
        if "estado_materia" not in cols:
            cursor.execute("ALTER TABLE materias ADD COLUMN estado_materia TEXT DEFAULT 'Activa'")

        conn.commit()

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
                SUM(CASE WHEN r.estado = 'Terminado' THEN 1 ELSE 0 END) AS completados
            FROM materias m
            LEFT JOIN semanas s ON s.materia_id = m.id
            LEFT JOIN recursos r ON r.semana_id = s.id
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
                "progreso": progreso
            })
        return resultado

def registrar_actividad_materia(materia_id):
    """Actualiza la fecha de última actividad al abrir/estudiar un recurso de la materia."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE materias SET ultima_actividad = CURRENT_TIMESTAMP WHERE id = ?",
            (materia_id,)
        )
        conn.commit()