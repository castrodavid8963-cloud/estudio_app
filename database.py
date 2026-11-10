from __future__ import annotations
from datetime import date, datetime, timedelta
import json
import os
import sqlite3

import capitulos as cap
import repaso as rp
from contextlib import contextmanager

# La BD vive en la carpeta de datos (junto al código o al .exe; ver datos.py).
from datos import ruta_datos
DB_NAME = ruta_datos("estudios.db")

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

        # ---------------- Capítulos y modo de lectura ----------------
        # modo_lectura: 'auto' | 'completo' | 'capitulos'. toc_leido: 1 cuando ya se leyó el índice del PDF.
        _agregar_columna_si_falta(cursor, "recursos", "modo_lectura", "TEXT DEFAULT 'auto'")
        _agregar_columna_si_falta(cursor, "recursos", "toc_leido", "INTEGER DEFAULT 0")
        cursor.execute("UPDATE recursos SET modo_lectura = 'auto' WHERE modo_lectura IS NULL")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS capitulos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurso_id INTEGER NOT NULL,
                orden INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                nivel INTEGER DEFAULT 1,
                pagina_ini INTEGER NOT NULL,
                pagina_fin INTEGER NOT NULL,
                incluido INTEGER DEFAULT 1,
                hecho INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_capitulos_recurso ON capitulos(recurso_id)")

        # ---------------- Repaso espaciado y quizzes ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tarjetas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurso_id INTEGER DEFAULT 0,
                pagina INTEGER DEFAULT 0,
                pregunta TEXT NOT NULL,
                respuesta TEXT NOT NULL,
                origen TEXT DEFAULT 'manual',
                creado TEXT,
                facilidad REAL DEFAULT 2.5,
                intervalo INTEGER DEFAULT 0,
                repeticiones INTEGER DEFAULT 0,
                lapsos INTEGER DEFAULT 0,
                proxima TEXT,
                ultima TEXT,
                introducida TEXT,
                estado TEXT DEFAULT 'nueva',
                suspendida INTEGER DEFAULT 0
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tarjetas_proxima ON tarjetas(proxima)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS repasos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tarjeta_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                calidad INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_repasos_fecha ON repasos(fecha)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurso_id INTEGER DEFAULT 0,
                titulo TEXT,
                creado TEXT,
                total INTEGER,
                aciertos INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_preguntas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quiz_id INTEGER NOT NULL,
                pregunta TEXT,
                opciones TEXT,
                correcta INTEGER,
                elegida INTEGER,
                acierto INTEGER,
                explicacion TEXT
            )
        """)

        # ---------------- Notas y subrayados ----------------
        # tipo: 'nota' | 'subrayado' | 'sesion' (nota rápida al cerrar el lector).
        # rect: "x0,y0,x1,y1" normalizado (0-1) respecto a la página; solo en subrayados.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recurso_id INTEGER NOT NULL,
                pagina INTEGER NOT NULL DEFAULT 1,
                tipo TEXT NOT NULL DEFAULT 'nota',
                texto TEXT DEFAULT '',
                rect TEXT,
                color TEXT DEFAULT 'amarillo',
                creado TEXT,
                actualizado TEXT
            )
        """)

        # ---------------- Mini-proyectos por ruta ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mini_proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                objetivo TEXT NOT NULL,
                etapa INTEGER NOT NULL DEFAULT 0,
                titulo TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                origen TEXT DEFAULT 'manual',
                hecho INTEGER DEFAULT 0,
                creado TEXT,
                hecho_en TEXT
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
    modo, toc_leido = f[11] or "auto", bool(f[12])
    caps_n, caps_total, caps_hechos, max_pag = (f[13] or 0), (f[14] or 0), (f[15] or 0), (f[16] or 0)
    efectivo, motivo = cap.modo_efectivo(modo, titulo, max(paginas, max_pag), caps_n, toc_leido)
    if efectivo == "capitulos" and caps_total > 0 and estado != "Completado":
        avance = caps_hechos / caps_total
    return {
        "id": f[0], "semana_id": f[1], "materia_id": f[2], "nombre_archivo": nombre,
        "titulo": titulo, "ruta": f[4], "estado": estado, "favorito": bool(f[6]),
        "ultima_pagina": ultima, "total_paginas": paginas, "ultima_apertura": f[9],
        "materia": f[10], "area": area, "subcarpeta": sub, "avance": avance,
        "modo_lectura": modo, "modo_efectivo": efectivo, "modo_motivo": motivo, "toc_leido": toc_leido,
        "caps_n": caps_n, "caps_total": caps_total, "caps_hechos": caps_hechos,
    }


_SQL_LIBROS = """
    SELECT r.id, r.semana_id, s.materia_id, r.nombre_archivo, r.ruta_local, r.estado,
           r.es_favorito, r.ultima_pagina, r.total_paginas, r.ultima_apertura, m.nombre,
           r.modo_lectura, r.toc_leido, cs.n, cs.inc, cs.hec, cs.maxp
    FROM recursos r
    JOIN semanas s ON s.id = r.semana_id
    JOIN materias m ON m.id = s.materia_id
    LEFT JOIN (SELECT recurso_id, COUNT(*) AS n, SUM(incluido) AS inc,
                      SUM(CASE WHEN incluido = 1 AND hecho = 1 THEN 1 ELSE 0 END) AS hec,
                      MAX(pagina_fin) AS maxp
               FROM capitulos GROUP BY recurso_id) cs ON cs.recurso_id = r.id
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
        if estado == "Completado":          # marcar el libro como leído marca todos sus capítulos
            conn.execute("UPDATE capitulos SET hecho = 1 WHERE recurso_id = ?", (recurso_id,))
        elif estado == "Sin empezar":
            conn.execute("UPDATE capitulos SET hecho = 0 WHERE recurso_id = ?", (recurso_id,))


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


def _modo_efectivo_conn(conn, recurso_id: int, paginas: int = 0) -> str:
    f = conn.execute("SELECT nombre_archivo, modo_lectura, toc_leido, total_paginas FROM recursos WHERE id = ?",
                     (recurso_id,)).fetchone()
    if not f:
        return "completo"
    n, maxp = conn.execute("SELECT COUNT(*), COALESCE(MAX(pagina_fin), 0) FROM capitulos WHERE recurso_id = ?",
                           (recurso_id,)).fetchone()
    nombre = f[0] or ""
    titulo = nombre[:-4] if nombre.lower().endswith(".pdf") else nombre
    return cap.modo_efectivo(f[1] or "auto", titulo, max(paginas or f[3] or 0, maxp), n, bool(f[2]))[0]


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
        por_capitulos = _modo_efectivo_conn(conn, recurso_id, total) == "capitulos"
        if estado != "Completado":
            if not por_capitulos and total and pagina / total >= UMBRAL_COMPLETADO:
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
        o_caps = conn.execute("SELECT COUNT(*) FROM capitulos WHERE recurso_id = ?", (origen_id,)).fetchone()[0]
        d_caps = conn.execute("SELECT COUNT(*) FROM capitulos WHERE recurso_id = ?", (destino_id,)).fetchone()[0]
        if o_caps and not d_caps:          # el que se conserva no tenía índice leído: hereda el del otro
            conn.execute("UPDATE capitulos SET recurso_id = ? WHERE recurso_id = ?", (destino_id, origen_id))
            conn.execute("UPDATE recursos SET toc_leido = 1, modo_lectura = (SELECT modo_lectura FROM recursos "
                         "WHERE id = ?) WHERE id = ?", (origen_id, destino_id))
        else:
            conn.execute("DELETE FROM capitulos WHERE recurso_id = ?", (origen_id,))
        conn.execute("UPDATE tarjetas SET recurso_id = ? WHERE recurso_id = ?", (destino_id, origen_id))
        if (o[3] or 0) == total:           # mismas páginas: las notas siguen siendo válidas
            conn.execute("UPDATE notas SET recurso_id = ? WHERE recurso_id = ?", (destino_id, origen_id))
        else:
            conn.execute("DELETE FROM notas WHERE recurso_id = ?", (origen_id,))


def marcar_no_disponible(recurso_id: int):
    with obtener_conexion() as conn:
        conn.execute("UPDATE recursos SET disponible = 0 WHERE id = ?", (recurso_id,))


# ============================================================================ orden manual de las rutas
def obtener_orden_rutas() -> list:
    """Ids de rutas en el orden elegido por el usuario ([] = sin orden manual guardado)."""
    crudo = obtener_config("rutas_orden") or ""
    return [x for x in crudo.split("|") if x]


def guardar_orden_rutas(orden: list):
    guardar_config("rutas_orden", "|".join(orden))


def mover_ruta(orden_actual: list, objetivo: str, delta: int) -> list:
    """Devuelve (y guarda) `orden_actual` con `objetivo` movido `delta` posiciones (-1 sube, +1 baja)."""
    orden = list(orden_actual)
    if objetivo not in orden:
        return orden
    i = orden.index(objetivo)
    j = max(0, min(len(orden) - 1, i + delta))
    orden[i], orden[j] = orden[j], orden[i]
    guardar_orden_rutas(orden)
    return orden


# ============================================================================ notas y subrayados
COLORES_SUBRAYADO = {"amarillo": (255, 214, 10), "verde": (52, 211, 153), "rosa": (244, 114, 182), "azul": (96, 165, 250)}


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rect_a_texto(rect) -> str | None:
    return None if not rect else ",".join(f"{float(v):.5f}" for v in rect)


def _rect_de_texto(texto) -> tuple | None:
    try:
        v = tuple(float(x) for x in (texto or "").split(","))
        return v if len(v) == 4 else None
    except ValueError:
        return None


def agregar_nota(recurso_id: int, pagina: int, texto: str = "", tipo: str = "nota", rect=None,
                 color: str = "amarillo") -> int:
    with obtener_conexion() as conn:
        cur = conn.execute(
            "INSERT INTO notas (recurso_id, pagina, tipo, texto, rect, color, creado, actualizado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (recurso_id, int(pagina), tipo, texto or "", _rect_a_texto(rect), color, _ahora(), _ahora()))
        return cur.lastrowid


def listar_notas(recurso_id: int) -> list:
    """Notas de un libro ordenadas por página y luego por creación."""
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute("SELECT * FROM notas WHERE recurso_id = ? ORDER BY pagina, id", (recurso_id,)).fetchall()
    notas = []
    for f in filas:
        n = dict(f)
        n["rect"] = _rect_de_texto(n.get("rect"))
        notas.append(n)
    return notas


def actualizar_nota(nota_id: int, texto: str):
    with obtener_conexion() as conn:
        conn.execute("UPDATE notas SET texto = ?, actualizado = ? WHERE id = ?", (texto, _ahora(), nota_id))


def borrar_nota(nota_id: int):
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM notas WHERE id = ?", (nota_id,))


def contar_notas(recurso_id: int | None = None) -> int:
    with obtener_conexion() as conn:
        if recurso_id is None:
            return conn.execute("SELECT COUNT(*) FROM notas").fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM notas WHERE recurso_id = ?", (recurso_id,)).fetchone()[0]


def exportar_notas_markdown(recurso_id: int | None = None) -> str:
    """Markdown con las notas de un libro, o de toda la biblioteca si no se indica."""
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        if recurso_id is None:
            libros = conn.execute("SELECT DISTINCT r.id, r.nombre_archivo AS titulo FROM recursos r JOIN notas n ON n.recurso_id = r.id "
                                  "ORDER BY r.nombre_archivo COLLATE NOCASE").fetchall()
        else:
            libros = conn.execute("SELECT id, nombre_archivo AS titulo FROM recursos WHERE id = ?", (recurso_id,)).fetchall()
    lineas = ["# Mis notas de estudio", "", f"_Exportado el {datetime.now():%Y-%m-%d %H:%M}_", ""]
    hay = False
    for lib in libros:
        notas = listar_notas(lib["id"])
        if not notas:
            continue
        hay = True
        nombre = lib["titulo"][:-4] if lib["titulo"].lower().endswith(".pdf") else lib["titulo"]
        lineas += [f"## {nombre}", ""]
        pagina_previa = None
        for n in notas:
            if n["pagina"] != pagina_previa:
                lineas += [f"### Página {n['pagina']}", ""]
                pagina_previa = n["pagina"]
            texto = (n["texto"] or "").strip()
            if n["tipo"] == "subrayado":
                cita = "\n> ".join(texto.splitlines()) if texto else "_(zona subrayada sin texto)_"
                lineas += [f"> {cita}", ""]
            elif n["tipo"] == "sesion":
                lineas += [f"- **Al cerrar la sesión ({(n['creado'] or '')[:10]}):** {texto}", ""]
            else:
                lineas += [f"- {texto}", ""]
    if not hay:
        lineas.append("_Todavía no hay notas._")
    return "\n".join(lineas).rstrip() + "\n"


# ============================================================================ capítulos
def indice_leido(recurso_id: int) -> bool:
    with obtener_conexion() as conn:
        f = conn.execute("SELECT toc_leido FROM recursos WHERE id = ?", (recurso_id,)).fetchone()
    return bool(f and f[0])


def guardar_capitulos(recurso_id: int, capitulos: list):
    """Guarda el índice leído del PDF (solo la primera vez: después se respetan tus cambios)."""
    with obtener_conexion() as conn:
        f = conn.execute("SELECT toc_leido FROM recursos WHERE id = ?", (recurso_id,)).fetchone()
        if not f or f[0]:
            return
        conn.execute("DELETE FROM capitulos WHERE recurso_id = ?", (recurso_id,))
        conn.executemany(
            "INSERT INTO capitulos (recurso_id, orden, titulo, nivel, pagina_ini, pagina_fin, incluido, hecho) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            [(recurso_id, i, c["titulo"], c["nivel"], c["pagina_ini"], c["pagina_fin"], c["incluido"])
             for i, c in enumerate(capitulos)])
        conn.execute("UPDATE recursos SET toc_leido = 1 WHERE id = ?", (recurso_id,))


def listar_capitulos(recurso_id: int) -> list:
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        filas = conn.execute("SELECT * FROM capitulos WHERE recurso_id = ? ORDER BY orden", (recurso_id,)).fetchall()
    return [dict(f) for f in filas]


def fijar_modo_lectura(recurso_id: int, modo: str):
    if modo not in cap.MODOS:
        raise ValueError(f"Modo inválido: {modo}")
    with obtener_conexion() as conn:
        conn.execute("UPDATE recursos SET modo_lectura = ? WHERE id = ?", (modo, recurso_id))
    recalcular_estado_capitulos(recurso_id)


def marcar_capitulos(recurso_id: int, ids: list, campo: str, valor: bool):
    """campo: 'hecho' (leído) o 'incluido' (cuenta para el progreso del libro)."""
    if campo not in ("hecho", "incluido") or not ids:
        return
    with obtener_conexion() as conn:
        conn.executemany(f"UPDATE capitulos SET {campo} = ? WHERE id = ? AND recurso_id = ?",
                         [(1 if valor else 0, i, recurso_id) for i in ids])
    recalcular_estado_capitulos(recurso_id)


def marcar_todos_incluidos(recurso_id: int, valor: bool):
    with obtener_conexion() as conn:
        conn.execute("UPDATE capitulos SET incluido = ? WHERE recurso_id = ?", (1 if valor else 0, recurso_id))
    recalcular_estado_capitulos(recurso_id)


def recalcular_estado_capitulos(recurso_id: int) -> str | None:
    """En modo «por capítulos»: Completado cuando todos los capítulos que cuentan están hechos;
    si se desmarca alguno, vuelve a En progreso. Devuelve el estado resultante (o None si no aplica)."""
    with obtener_conexion() as conn:
        if _modo_efectivo_conn(conn, recurso_id) != "capitulos":
            return None
        inc, hec = conn.execute(
            "SELECT COALESCE(SUM(incluido), 0), COALESCE(SUM(CASE WHEN incluido = 1 AND hecho = 1 THEN 1 ELSE 0 END), 0) "
            "FROM capitulos WHERE recurso_id = ?", (recurso_id,)).fetchone()
        estado = conn.execute("SELECT estado FROM recursos WHERE id = ?", (recurso_id,)).fetchone()[0] or "Sin empezar"
        if inc <= 0:
            return estado
        if hec >= inc:
            nuevo = "Completado"
        elif estado == "Completado" or hec > 0:
            nuevo = "En progreso"
        else:
            nuevo = estado
        if nuevo != estado:
            conn.execute("UPDATE recursos SET estado = ? WHERE id = ?", (nuevo, recurso_id))
        return nuevo


def libros_sin_indice(solo_incluidos: bool = True) -> list:
    """(id, ruta) de los libros disponibles cuyo índice aún no se leyó."""
    with obtener_conexion() as conn:
        filas = conn.execute("SELECT id, ruta_local FROM recursos WHERE disponible = 1 AND COALESCE(toc_leido, 0) = 0").fetchall()
    if not solo_incluidos:
        return filas
    excluidas, raiz = areas_excluidas(), obtener_ruta_biblioteca()
    return [(i, r) for i, r in filas if not esta_excluido(r, raiz, excluidas)]


# ============================================================================ repaso espaciado
LIMITE_NUEVAS_DIA = 10
LIMITE_REPASOS_DIA = 150


def _hoy() -> str:
    return date.today().isoformat()


def limite_nuevas() -> int:
    try:
        return max(0, int(obtener_config("repaso_nuevas_dia") or LIMITE_NUEVAS_DIA))
    except ValueError:
        return LIMITE_NUEVAS_DIA


def agregar_tarjetas(recurso_id, pagina: int, tarjetas: list, origen: str = "ia") -> int:
    """Crea tarjetas nuevas (se omiten las preguntas ya existentes del mismo libro). Devuelve cuántas se crearon."""
    recurso_id = recurso_id or 0
    with obtener_conexion() as conn:
        existentes = {rp.normalizar_pregunta(f[0]) for f in
                      conn.execute("SELECT pregunta FROM tarjetas WHERE recurso_id = ?", (recurso_id,))}
        nuevas = 0
        for t in tarjetas:
            clave = rp.normalizar_pregunta(t["pregunta"])
            if not clave or clave in existentes:
                continue
            existentes.add(clave)
            conn.execute(
                "INSERT INTO tarjetas (recurso_id, pagina, pregunta, respuesta, origen, creado, proxima, estado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'nueva')",
                (recurso_id, int(pagina or 0), t["pregunta"], t["respuesta"], origen, _ahora(), _hoy()))
            nuevas += 1
    return nuevas


def _tarjeta_dict(f) -> dict:
    return dict(f)


def tarjetas_pendientes(recurso_id=None, limite_total: int = LIMITE_REPASOS_DIA) -> list:
    """Tarjetas para repasar hoy: primero las vencidas (las más atrasadas antes) y luego las nuevas que
    quepan en el límite diario de nuevas."""
    hoy = _hoy()
    filtro, args = ("AND t.recurso_id = ?", [recurso_id]) if recurso_id is not None else ("", [])
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        vencidas = conn.execute(
            f"SELECT t.* FROM tarjetas t WHERE t.suspendida = 0 AND t.estado != 'nueva' AND t.proxima <= ? {filtro} "
            f"ORDER BY t.proxima, t.id LIMIT ?", [hoy] + args + [limite_total]).fetchall()
        ya_nuevas = conn.execute("SELECT COUNT(*) FROM tarjetas WHERE introducida = ?", (hoy,)).fetchone()[0]
        cupo = max(0, limite_nuevas() - ya_nuevas)
        nuevas = conn.execute(
            f"SELECT t.* FROM tarjetas t WHERE t.suspendida = 0 AND t.estado = 'nueva' {filtro} ORDER BY t.id LIMIT ?",
            args + [cupo]).fetchall() if cupo else []
    return [_tarjeta_dict(f) for f in vencidas] + [_tarjeta_dict(f) for f in nuevas]


def registrar_repaso(tarjeta_id: int, calidad: int) -> dict:
    """Guarda la respuesta y reprograma la tarjeta. Devuelve los campos nuevos."""
    hoy = _hoy()
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        t = conn.execute("SELECT * FROM tarjetas WHERE id = ?", (tarjeta_id,)).fetchone()
        if t is None:
            return {}
        nuevo = rp.programar(dict(t), calidad)
        conn.execute(
            "UPDATE tarjetas SET facilidad = ?, intervalo = ?, repeticiones = ?, lapsos = ?, proxima = ?, ultima = ?, "
            "estado = ?, introducida = COALESCE(introducida, ?) WHERE id = ?",
            (nuevo["facilidad"], nuevo["intervalo"], nuevo["repeticiones"], nuevo["lapsos"], nuevo["proxima"],
             nuevo["ultima"], nuevo["estado"], hoy, tarjeta_id))
        conn.execute("INSERT INTO repasos (tarjeta_id, fecha, calidad) VALUES (?, ?, ?)", (tarjeta_id, hoy, calidad))
    return nuevo


def resumen_repaso(recurso_id=None) -> dict:
    """Números para el Inicio y la pantalla de Repaso."""
    hoy = _hoy()
    filtro, args = ("AND recurso_id = ?", [recurso_id]) if recurso_id is not None else ("", [])
    with obtener_conexion() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM tarjetas WHERE suspendida = 0 {filtro}", args).fetchone()[0]
        vencidas = conn.execute(f"SELECT COUNT(*) FROM tarjetas WHERE suspendida = 0 AND estado != 'nueva' AND proxima <= ? {filtro}",
                                [hoy] + args).fetchone()[0]
        nuevas_total = conn.execute(f"SELECT COUNT(*) FROM tarjetas WHERE suspendida = 0 AND estado = 'nueva' {filtro}", args).fetchone()[0]
        ya_nuevas = conn.execute("SELECT COUNT(*) FROM tarjetas WHERE introducida = ?", (hoy,)).fetchone()[0]
        hechas_hoy = conn.execute("SELECT COUNT(*) FROM repasos WHERE fecha = ?", (hoy,)).fetchone()[0]
        dominadas = conn.execute(f"SELECT COUNT(*) FROM tarjetas WHERE suspendida = 0 AND intervalo >= 21 {filtro}", args).fetchone()[0]
        desde = (date.today() - timedelta(days=30)).isoformat()
        r30 = conn.execute("SELECT COUNT(*), COALESCE(SUM(CASE WHEN calidad >= 1 THEN 1 ELSE 0 END), 0) FROM repasos WHERE fecha >= ?",
                           (desde,)).fetchone()
    nuevas = min(nuevas_total, max(0, limite_nuevas() - ya_nuevas))
    return {"total": total, "vencidas": vencidas, "nuevas": nuevas, "pendientes": vencidas + nuevas,
            "hechas_hoy": hechas_hoy, "dominadas": dominadas, "retencion": (r30[1] / r30[0]) if r30[0] else None,
            "repasos_30d": r30[0]}


def listar_tarjetas(recurso_id=None, texto: str = "", limite: int = 300) -> list:
    sql, args = ["SELECT t.*, r.nombre_archivo AS libro FROM tarjetas t LEFT JOIN recursos r ON r.id = t.recurso_id WHERE 1 = 1"], []
    if recurso_id is not None:
        sql.append("AND t.recurso_id = ?")
        args.append(recurso_id)
    if texto.strip():
        sql.append("AND (t.pregunta LIKE ? OR t.respuesta LIKE ?)")
        args += [f"%{texto.strip()}%"] * 2
    sql.append("ORDER BY t.id DESC LIMIT ?")
    args.append(limite)
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(f) for f in conn.execute(" ".join(sql), args).fetchall()]


def libros_con_tarjetas() -> list:
    """[(recurso_id, título, cantidad)]; recurso_id 0 agrupa las tarjetas sin libro."""
    with obtener_conexion() as conn:
        filas = conn.execute("SELECT t.recurso_id, r.nombre_archivo, COUNT(*) FROM tarjetas t "
                             "LEFT JOIN recursos r ON r.id = t.recurso_id GROUP BY t.recurso_id "
                             "ORDER BY COUNT(*) DESC").fetchall()
    return [(f[0], (f[1][:-4] if f[1] and f[1].lower().endswith(".pdf") else f[1]) or "Sin libro", f[2]) for f in filas]


def actualizar_tarjeta(tarjeta_id: int, pregunta: str, respuesta: str):
    with obtener_conexion() as conn:
        conn.execute("UPDATE tarjetas SET pregunta = ?, respuesta = ? WHERE id = ?", (pregunta, respuesta, tarjeta_id))


def borrar_tarjeta(tarjeta_id: int):
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM tarjetas WHERE id = ?", (tarjeta_id,))
        conn.execute("DELETE FROM repasos WHERE tarjeta_id = ?", (tarjeta_id,))


# ---------------------------------------------------------------- quizzes
def guardar_quiz(recurso_id, titulo: str, preguntas: list) -> int:
    """preguntas: [{'pregunta','opciones','correcta','elegida','explicacion'}] ya contestadas."""
    aciertos = sum(1 for q in preguntas if q.get("elegida") == q["correcta"])
    with obtener_conexion() as conn:
        qid = conn.execute("INSERT INTO quizzes (recurso_id, titulo, creado, total, aciertos) VALUES (?, ?, ?, ?, ?)",
                           (recurso_id or 0, titulo, _ahora(), len(preguntas), aciertos)).lastrowid
        conn.executemany(
            "INSERT INTO quiz_preguntas (quiz_id, pregunta, opciones, correcta, elegida, acierto, explicacion) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(qid, q["pregunta"], json.dumps(q["opciones"], ensure_ascii=False), q["correcta"], q.get("elegida"),
              1 if q.get("elegida") == q["correcta"] else 0, q.get("explicacion", "")) for q in preguntas])
    return qid


def listar_quizzes(limite: int = 25) -> list:
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(f) for f in conn.execute(
            "SELECT * FROM quizzes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()]


# ---------------------------------------------------------------- planificación
def obtener_meta_ruta(objetivo: str):
    """Fecha meta (YYYY-MM-DD) de una ruta, o None."""
    return obtener_config(f"meta_ruta_{objetivo}") or None


def guardar_meta_ruta(objetivo: str, fecha_iso):
    guardar_config(f"meta_ruta_{objetivo}", fecha_iso or "")


def muestras_ritmo_lectura() -> list:
    """[(páginas_leídas, segundos)] por libro con tiempo registrado, para medir tu ritmo de lectura real."""
    with obtener_conexion() as conn:
        filas = conn.execute(
            """SELECT r.ultima_pagina, SUM(s.duracion_segundos) FROM sesiones_estudio s
               JOIN recursos r ON r.id = s.recurso_id GROUP BY r.id""").fetchall()
    return [(f[0] or 0, int(f[1] or 0)) for f in filas]


def segundos_por_dia_rango(dias: int) -> dict:
    """{'YYYY-MM-DD': segundos} solo de los días con estudio, para los últimos `dias` días."""
    desde = (datetime.now() - timedelta(days=dias - 1)).strftime("%Y-%m-%d")
    with obtener_conexion() as conn:
        filas = conn.execute(
            "SELECT substr(fecha_inicio, 1, 10) AS d, SUM(duracion_segundos) FROM sesiones_estudio "
            "WHERE fecha_inicio >= ? GROUP BY d", (desde,)).fetchall()
    return {d: int(s or 0) for d, s in filas}


# ---------------------------------------------------------------- mini-proyectos
def listar_mini_proyectos(objetivo: str) -> list:
    with obtener_conexion() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(f) for f in conn.execute(
            "SELECT * FROM mini_proyectos WHERE objetivo = ? ORDER BY etapa, hecho, id", (objetivo,)).fetchall()]


def agregar_mini_proyectos(objetivo: str, etapa: int, proyectos: list, origen: str = "manual") -> int:
    """proyectos: [{'titulo','descripcion'}]. No repite un título que ya exista en esa etapa. Devuelve cuántos agregó."""
    nuevos = 0
    with obtener_conexion() as conn:
        existentes = {f[0].strip().casefold() for f in conn.execute(
            "SELECT titulo FROM mini_proyectos WHERE objetivo = ? AND etapa = ?", (objetivo, etapa))}
        for p in proyectos:
            titulo = (p.get("titulo") or "").strip()
            if not titulo or titulo.casefold() in existentes:
                continue
            conn.execute(
                "INSERT INTO mini_proyectos (objetivo, etapa, titulo, descripcion, origen, creado) VALUES (?, ?, ?, ?, ?, ?)",
                (objetivo, etapa, titulo[:160], (p.get("descripcion") or "").strip()[:600], origen, _ahora()))
            existentes.add(titulo.casefold())
            nuevos += 1
    return nuevos


def marcar_mini_proyecto(proyecto_id: int, hecho: bool):
    with obtener_conexion() as conn:
        conn.execute("UPDATE mini_proyectos SET hecho = ?, hecho_en = ? WHERE id = ?",
                     (1 if hecho else 0, _ahora() if hecho else None, proyecto_id))


def editar_mini_proyecto(proyecto_id: int, titulo: str, descripcion: str):
    with obtener_conexion() as conn:
        conn.execute("UPDATE mini_proyectos SET titulo = ?, descripcion = ? WHERE id = ?",
                     (titulo.strip()[:160], descripcion.strip()[:600], proyecto_id))


def borrar_mini_proyecto(proyecto_id: int):
    with obtener_conexion() as conn:
        conn.execute("DELETE FROM mini_proyectos WHERE id = ?", (proyecto_id,))
