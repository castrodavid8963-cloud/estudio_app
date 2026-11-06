import os
import sqlite3
from contextlib import contextmanager

# La BD vive junto al código, sin importar desde dónde se lance la app.
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estudios.db")

# Carpetas de primer nivel que no entran al roadmap ni al tutor IA (se pueden cambiar en Ajustes).
AREAS_EXCLUIDAS_POR_DEFECTO = (
    "10_Literatura_y_Ocultismo",
    "11_Personal_y_Documentos",
    "12_Sin_Clasificar",
)

ESTADOS = ("Sin empezar", "En progreso", "Completado")
UMBRAL_COMPLETADO = 0.97   # al llegar a este % del libro se marca como Completado


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
        # Progreso de lectura (nuevo)
        _agregar_columna_si_falta(cursor, "recursos", "ultima_pagina", "INTEGER DEFAULT 0")
        _agregar_columna_si_falta(cursor, "recursos", "total_paginas", "INTEGER DEFAULT 0")
        _agregar_columna_si_falta(cursor, "recursos", "ultima_apertura", "TEXT")

        # Normalización de datos antiguos: la app siempre usó 'Completado'.
        cursor.execute("UPDATE recursos SET estado = 'Completado' WHERE estado = 'Terminado'")
        cursor.execute("UPDATE recursos SET estado = 'Sin empezar' WHERE estado IS NULL")
        cursor.execute("UPDATE recursos SET es_favorito = 0 WHERE es_favorito IS NULL")
        cursor.execute("UPDATE recursos SET disponible = 1 WHERE disponible IS NULL")
        cursor.execute("UPDATE recursos SET ultima_pagina = 0 WHERE ultima_pagina IS NULL")
        cursor.execute("UPDATE recursos SET total_paginas = 0 WHERE total_paginas IS NULL")

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
        _agregar_columna_si_falta(cursor, "sesiones_estudio", "recurso_id", "INTEGER")

        # ---------------- Configuración ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT
            )
        """)

        # ---------------- Ajustes manuales del roadmap ----------------
        # accion: 'ocultar' (quita un libro de la ruta) | 'agregar' (lo mete en una etapa)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roadmap_ajustes (
                objetivo TEXT NOT NULL,
                recurso_id INTEGER NOT NULL,
                accion TEXT NOT NULL,
                etapa INTEGER,
                PRIMARY KEY (objetivo, recurso_id)
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
            "CREATE INDEX IF NOT EXISTS idx_sesiones_inicio ON sesiones_estudio(fecha_inicio)",
            "CREATE INDEX IF NOT EXISTS idx_sesiones_recurso ON sesiones_estudio(recurso_id)",
        ):
            try:
                cursor.execute(sentencia)
            except sqlite3.DatabaseError as e:
                print(f"[BD] Índice omitido ({e}): {sentencia}")


# ============================================================================ configuración
def obtener_config(clave: str, defecto=None):
    try:
        with obtener_conexion() as conn:
            fila = conn.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
        return fila[0] if fila and fila[0] is not None else defecto
    except sqlite3.DatabaseError:
        return defecto


def guardar_config(clave: str, valor):
    with obtener_conexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)",
            (clave, None if valor is None else str(valor)),
        )


def obtener_ruta_biblioteca() -> str:
    return obtener_config("ruta_biblioteca", "") or ""


def areas_excluidas() -> tuple:
    """Carpetas de primer nivel fuera del roadmap/tutor (configurable, con valores por defecto)."""
    crudo = obtener_config("areas_excluidas")
    if crudo is None:
        return AREAS_EXCLUIDAS_POR_DEFECTO
    return tuple(a for a in crudo.split("|") if a)


def guardar_areas_excluidas(areas):
    guardar_config("areas_excluidas", "|".join(areas))


# ============================================================================ rutas -> área
def partes_relativas(ruta: str, raiz: str):
    """Lista de carpetas entre la raíz y el archivo ([] si está fuera de la raíz o suelto)."""
    if not ruta or not raiz:
        return []
    try:
        rel = os.path.relpath(os.path.dirname(os.path.abspath(ruta)), os.path.abspath(raiz))
    except ValueError:        # otra unidad en Windows
        return []
    if rel == "." or rel.startswith(".."):
        return []
    return [p for p in rel.replace("\\", "/").split("/") if p]


def area_y_subcarpeta(ruta: str, raiz: str):
    """('01_Programacion_y_Lenguajes', 'Python') o ('', '') si no se puede determinar."""
    partes = partes_relativas(ruta, raiz)
    area = partes[0] if partes else ""
    sub = partes[1] if len(partes) > 1 else ""
    return area, sub


def esta_excluido(ruta: str, raiz: str = None, excluidas=None) -> bool:
    raiz = raiz if raiz is not None else obtener_ruta_biblioteca()
    excluidas = areas_excluidas() if excluidas is None else excluidas
    area, _ = area_y_subcarpeta(ruta, raiz)
    return bool(area) and area.casefold() in {e.casefold() for e in excluidas}


# ============================================================================ libros
def _fila_a_libro(f, raiz: str) -> dict:
    area, sub = area_y_subcarpeta(f[4], raiz)
    paginas = f[8] or 0
    ultima = f[7] or 0
    estado = f[5] or "Sin empezar"
    if estado == "Completado":
        avance = 1.0
    elif paginas > 0:
        avance = min(1.0, ultima / paginas)
    else:
        avance = 0.0
    nombre = f[3] or ""
    titulo = nombre[:-4] if nombre.lower().endswith(".pdf") else nombre
    return {
        "id": f[0], "semana_id": f[1], "materia_id": f[2], "nombre_archivo": nombre,
        "titulo": titulo, "ruta": f[4], "estado": estado, "favorito": bool(f[6]),
        "ultima_pagina": ultima, "total_paginas": paginas, "ultima_apertura": f[9],
        "materia": f[10], "area": area, "subcarpeta": sub, "avance": avance,
    }


_SQL_LIBROS = """
    SELECT r.id, r.semana_id, s.materia_id, r.nombre_archivo, r.ruta_local, r.estado,
           r.es_favorito, r.ultima_pagina, r.total_paginas, r.ultima_apertura, m.nombre
    FROM recursos r
    JOIN semanas s ON s.id = r.semana_id
    JOIN materias m ON m.id = s.materia_id
"""


def listar_libros(solo_disponibles: bool = True, incluir_excluidos: bool = True) -> list:
    """Todos los libros con su área/subcarpeta (derivadas de la ruta y la raíz guardada)."""
    raiz = obtener_ruta_biblioteca()
    excluidas = {e.casefold() for e in areas_excluidas()}
    sql = _SQL_LIBROS + (" WHERE r.disponible = 1" if solo_disponibles else "") + " ORDER BY r.nombre_archivo COLLATE NOCASE"
    with obtener_conexion() as conn:
        filas = conn.execute(sql).fetchall()
    libros = []
    for f in filas:
        libro = _fila_a_libro(f, raiz)
        libro["excluido"] = bool(libro["area"]) and libro["area"].casefold() in excluidas
        if libro["excluido"] and not incluir_excluidos:
            continue
        libros.append(libro)
    return libros


def obtener_libro(recurso_id: int):
    with obtener_conexion() as conn:
        f = conn.execute(_SQL_LIBROS + " WHERE r.id = ?", (recurso_id,)).fetchone()
    if not f:
        return None
    libro = _fila_a_libro(f, obtener_ruta_biblioteca())
    libro["excluido"] = esta_excluido(libro["ruta"])
    return libro


def actualizar_estado_libro(recurso_id: int, estado: str):
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: {estado}")
    with obtener_conexion() as conn:
        conn.execute("UPDATE recursos SET estado = ? WHERE id = ?", (estado, recurso_id))


def alternar_favorito(recurso_id: int) -> bool:
    with obtener_conexion() as conn:
        fila = conn.execute("SELECT es_favorito FROM recursos WHERE id = ?", (recurso_id,)).fetchone()
        nuevo = 0 if (fila and fila[0]) else 1
        conn.execute("UPDATE recursos SET es_favorito = ? WHERE id = ?", (nuevo, recurso_id))
    return bool(nuevo)


def marcar_apertura(recurso_id: int):
    """Registra que el libro se abrió: pasa a 'En progreso' si estaba sin empezar y actualiza actividad."""
    with obtener_conexion() as conn:
        conn.execute(
            """UPDATE recursos SET ultima_apertura = datetime('now','localtime'),
               estado = CASE WHEN estado = 'Sin empezar' OR estado IS NULL THEN 'En progreso' ELSE estado END
               WHERE id = ?""",
            (recurso_id,),
        )
        conn.execute(
            """UPDATE materias SET ultima_actividad = datetime('now','localtime') WHERE id =
               (SELECT s.materia_id FROM recursos r JOIN semanas s ON s.id = r.semana_id WHERE r.id = ?)""",
            (recurso_id,),
        )


def guardar_progreso_lectura(recurso_id: int, pagina: int, total: int) -> str:
    """Guarda la página (1-based) donde va el lector. Devuelve el estado resultante.

    Pasa a 'En progreso' al leer y a 'Completado' al alcanzar el umbral. Nunca degrada un
    'Completado' marcado a mano.
    """
    pagina = max(0, int(pagina))
    total = max(0, int(total))
    with obtener_conexion() as conn:
        fila = conn.execute("SELECT estado FROM recursos WHERE id = ?", (recurso_id,)).fetchone()
        if not fila:
            return "Sin empezar"
        estado = fila[0] or "Sin empezar"
        if estado != "Completado":
            if total and pagina / total >= UMBRAL_COMPLETADO:
                estado = "Completado"
            else:
                estado = "En progreso"
        conn.execute(
            "UPDATE recursos SET ultima_pagina = ?, total_paginas = ?, estado = ?, "
            "ultima_apertura = datetime('now','localtime') WHERE id = ?",
            (pagina, total, estado, recurso_id),
        )
    return estado


def cargar_historial_chat(recurso_id: int) -> list:
    import json
    with obtener_conexion() as conn:
        fila = conn.execute("SELECT historial_chat FROM recursos WHERE id = ?", (recurso_id,)).fetchone()
    if not fila or not fila[0]:
        return []
    try:
        datos = json.loads(fila[0])
        return datos if isinstance(datos, list) else []
    except ValueError:
        return []


def guardar_historial_chat(recurso_id: int, historial: list):
    import json
    with obtener_conexion() as conn:
        conn.execute("UPDATE recursos SET historial_chat = ? WHERE id = ?",
                     (json.dumps(historial, ensure_ascii=False), recurso_id))


# ============================================================================ materias
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
            "UPDATE materias SET ultima_actividad = datetime('now','localtime') WHERE id = ?",
            (materia_id,),
        )


# ============================================================================ ajustes del roadmap
def obtener_ajustes_roadmap(objetivo: str) -> list:
    with obtener_conexion() as conn:
        filas = conn.execute(
            "SELECT recurso_id, accion, etapa FROM roadmap_ajustes WHERE objetivo = ?", (objetivo,)
        ).fetchall()
    return [{"recurso_id": f[0], "accion": f[1], "etapa": f[2]} for f in filas]


def ocultar_en_roadmap(objetivo: str, recurso_id: int):
    with obtener_conexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO roadmap_ajustes (objetivo, recurso_id, accion, etapa) VALUES (?, ?, 'ocultar', NULL)",
            (objetivo, recurso_id),
        )


def agregar_a_roadmap(objetivo: str, recurso_id: int, etapa: int):
    with obtener_conexion() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO roadmap_ajustes (objetivo, recurso_id, accion, etapa) VALUES (?, ?, 'agregar', ?)",
            (objetivo, recurso_id, etapa),
        )


def quitar_ajuste_roadmap(objetivo: str, recurso_id: int):
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM roadmap_ajustes WHERE objetivo = ? AND recurso_id = ?", (objetivo, recurso_id))


def reiniciar_ajustes_roadmap(objetivo: str):
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM roadmap_ajustes WHERE objetivo = ?", (objetivo,))


# ============================================================================ consultas para el inicio
def libro_para_continuar():
    """El libro abierto más recientemente que aún no está completado (o None)."""
    raiz = obtener_ruta_biblioteca()
    with obtener_conexion() as conn:
        f = conn.execute(
            _SQL_LIBROS + " WHERE r.disponible = 1 AND r.ultima_apertura IS NOT NULL AND r.estado != 'Completado' "
            "ORDER BY r.ultima_apertura DESC LIMIT 1").fetchone()
    if not f:
        return None
    libro = _fila_a_libro(f, raiz)
    libro["excluido"] = esta_excluido(libro["ruta"], raiz)
    return libro


def contar_por_estado() -> dict:
    cuentas = {e: 0 for e in ESTADOS}
    for l in listar_libros(incluir_excluidos=False):
        cuentas[l["estado"]] = cuentas.get(l["estado"], 0) + 1
    return cuentas


# ============================================================================ duplicados
_RANGO_ESTADO = {"Sin empezar": 0, "En progreso": 1, "Completado": 2}


def obtener_huellas() -> dict:
    """{recurso_id: huella} de los libros disponibles (la huella se calcula al indexar)."""
    with obtener_conexion() as conn:
        filas = conn.execute("SELECT id, huella FROM recursos WHERE disponible = 1 AND huella IS NOT NULL").fetchall()
    return {i: h for i, h in filas}


def fusionar_progreso(origen_id: int, destino_id: int):
    """Pasa el progreso del libro que se va a eliminar al que se conserva (sin perder nada:
    el estado más avanzado, favorito, tiempo estudiado, chat y ajustes de rutas)."""
    if origen_id == destino_id:
        return
    with obtener_conexion() as conn:
        o = conn.execute("SELECT estado, es_favorito, ultima_pagina, total_paginas, ultima_apertura, historial_chat "
                         "FROM recursos WHERE id = ?", (origen_id,)).fetchone()
        d = conn.execute("SELECT estado, es_favorito, ultima_pagina, total_paginas, ultima_apertura, historial_chat "
                         "FROM recursos WHERE id = ?", (destino_id,)).fetchone()
        if not o or not d:
            return
        estado = max((o[0] or "Sin empezar", d[0] or "Sin empezar"), key=lambda e: _RANGO_ESTADO.get(e, 0))
        favorito = 1 if (o[1] or d[1]) else 0
        # Páginas: se conserva el avance mayor solo si ambos PDF tienen el mismo número de páginas
        pagina, total = d[2] or 0, d[3] or 0
        if (o[3] or 0) == total and (o[2] or 0) > pagina:
            pagina = o[2]
        apertura = max(filter(None, (o[4], d[4])), default=None)
        chat = d[5] if d[5] else o[5]
        conn.execute("UPDATE recursos SET estado=?, es_favorito=?, ultima_pagina=?, ultima_apertura=?, historial_chat=? "
                     "WHERE id=?", (estado, favorito, pagina, apertura, chat, destino_id))
        conn.execute("UPDATE sesiones_estudio SET recurso_id = ? WHERE recurso_id = ?", (destino_id, origen_id))
        conn.execute("UPDATE OR IGNORE roadmap_ajustes SET recurso_id = ? WHERE recurso_id = ?", (destino_id, origen_id))
        conn.execute("DELETE FROM roadmap_ajustes WHERE recurso_id = ?", (origen_id,))


def marcar_no_disponible(recurso_id: int):
    with obtener_conexion() as conn:
        conn.execute("UPDATE recursos SET disponible = 0 WHERE id = ?", (recurso_id,))
