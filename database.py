from __future__ import annotations
from datetime import datetime
import os
import sqlite3

import capitulos as cap
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
