import hashlib
import os
import re

from database import obtener_conexion

TAM_HUELLA = 1024 * 1024      # se leen los primeros 1 MB para la huella
TAM_COLA_HUELLA = 64 * 1024   # y los últimos 64 KB (si el archivo es mayor)
LOTE_COMMIT = 50              # confirma en BD cada N archivos para no bloquear a la UI
# Carpetas de primer nivel que NO se indexan (documentos personales). Se pueden cambiar al llamar.
EXCLUIDAS_POR_DEFECTO = ("11_Personal_y_Documentos",)


def es_carpeta_basura_o_sistema(nombre_carpeta: str) -> bool:
    """Detecta si una carpeta es de sistema, temporal, papelera o contiene GUIDs/hashes."""
    nombre_lower = nombre_carpeta.lower()

    # Carpetas típicas de sistema y ocultas
    if nombre_lower.startswith(('.', '$')) or nombre_lower in ['system volume information', 'recycle.bin', 'tools']:
        return True

    # Patrón para identificar carpetas con identificadores hexadecimales/UUIDs (ej: 00000000-0000-...)
    if re.match(r'^[0-9a-fA-F]{8}[-0-9a-fA-F\-]{8,}$', nombre_carpeta):
        return True

    return False


def calcular_huella(ruta: str):
    """Huella barata del CONTENIDO (tamaño + inicio + final). Sirve para reconocer un PDF movido
    o renombrado sin depender del nombre. Devuelve None si no se puede leer."""
    try:
        tam = os.path.getsize(ruta)
        h = hashlib.sha1()
        h.update(str(tam).encode("ascii"))
        with open(ruta, "rb") as f:
            h.update(f.read(TAM_HUELLA))
            if tam > TAM_HUELLA + TAM_COLA_HUELLA:
                f.seek(-TAM_COLA_HUELLA, os.SEEK_END)
                h.update(f.read(TAM_COLA_HUELLA))
        return h.hexdigest()
    except OSError:
        return None


def _norm(ruta: str) -> str:
    return os.path.normcase(os.path.abspath(ruta))


def _esta_dentro(ruta: str, raiz_normalizada: str) -> bool:
    return _norm(ruta).startswith(raiz_normalizada.rstrip(os.sep) + os.sep)


def escanear_e_indexar_biblioteca(ruta_raiz: str, progreso_cb=None,
                                 excluir=EXCLUIDAS_POR_DEFECTO) -> tuple[int, int, int]:
    """Indexa los PDF de `ruta_raiz`. Devuelve (nuevos, reubicados, no_disponibles).

    A diferencia de la versión anterior, NUNCA borra registros: lo que ya no está en la carpeta
    escaneada se marca `disponible = 0` (se conservan favoritos, estados y chats) y vuelve a
    aparecer solo si el archivo reaparece. Los archivos movidos se reconocen por su huella.

    `progreso_cb(archivos_revisados)` es opcional y se llama de vez en cuando.
    `excluir`: carpetas de primer nivel que no se indexan (por defecto, los documentos personales).
    """
    if not ruta_raiz or not os.path.isdir(ruta_raiz):
        print(f"[Escáner] La ruta {ruta_raiz} no existe.")
        return 0, 0, 0

    raiz_norm = _norm(ruta_raiz)
    excluir_cf = {e.casefold() for e in (excluir or ())}
    nuevos = reubicados = revisados = 0
    vistos = set()          # rutas normalizadas encontradas en este escaneo
    reclamados = set()      # ids de recursos ya reubicados en este escaneo

    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('ruta_biblioteca', ?)",
            (ruta_raiz,),
        )

        for root, dirs, files in os.walk(ruta_raiz):
            # No entrar a carpetas basura/sistema
            dirs[:] = [d for d in dirs if not es_carpeta_basura_o_sistema(d)]
            # Carpetas excluidas (solo las de primer nivel): no se indexan, así que tampoco se les
            # generan portadas ni se pueden abrir en el Tutor IA.
            if _norm(root) == raiz_norm and excluir_cf:
                dirs[:] = [d for d in dirs if d.casefold() not in excluir_cf]

            archivos_pdf = [f for f in files if f.lower().endswith('.pdf')]
            if not archivos_pdf:
                continue

            rel_path = os.path.relpath(root, ruta_raiz)
            if rel_path == ".":
                # PDFs sueltos en la raíz: la materia se llama como la carpeta raíz
                nombre_materia = os.path.basename(os.path.normpath(ruta_raiz)).replace("_", " ").strip()
            else:
                nombre_materia = rel_path.replace("\\", "/").split("/")[-1].replace("_", " ").strip()

            if not nombre_materia or es_carpeta_basura_o_sistema(nombre_materia):
                continue

            # 1. Materia (obtener o crear)
            cursor.execute("SELECT id FROM materias WHERE nombre = ?", (nombre_materia,))
            res = cursor.fetchone()
            if res:
                materia_id = res[0]
            else:
                cursor.execute(
                    "INSERT INTO materias (nombre, tipo, descripcion) VALUES (?, ?, ?)",
                    (nombre_materia, 'Personal', f"Carpeta: {rel_path}"),
                )
                materia_id = cursor.lastrowid

            # 2. Semana 1 (obtener o crear)
            cursor.execute("SELECT id FROM semanas WHERE materia_id = ? AND numero_semana = 1", (materia_id,))
            res_sem = cursor.fetchone()
            if res_sem:
                semana_id = res_sem[0]
            else:
                cursor.execute(
                    "INSERT INTO semanas (materia_id, numero_semana, titulo_tema) VALUES (?, ?, ?)",
                    (materia_id, 1, "General / Documentos"),
                )
                semana_id = cursor.lastrowid

            # 3. PDFs
            for f in archivos_pdf:
                ruta_completa = os.path.join(root, f)
                vistos.add(_norm(ruta_completa))
                revisados += 1
                if progreso_cb and revisados % 25 == 0:
                    progreso_cb(revisados)
                if revisados % LOTE_COMMIT == 0:
                    conn.commit()

                # 3a. Ya registrado en esta misma ruta
                cursor.execute("SELECT id, huella FROM recursos WHERE ruta_local = ?", (ruta_completa,))
                existente = cursor.fetchone()
                if existente:
                    rec_id, huella_guardada = existente
                    if huella_guardada:
                        cursor.execute("UPDATE recursos SET disponible = 1 WHERE id = ?", (rec_id,))
                    else:
                        cursor.execute(
                            "UPDATE recursos SET disponible = 1, huella = ? WHERE id = ?",
                            (calcular_huella(ruta_completa), rec_id),
                        )
                    continue

                # 3b. ¿Es un archivo conocido que se movió o renombró?
                huella = calcular_huella(ruta_completa)
                candidato = None
                if huella:
                    cursor.execute("SELECT id, ruta_local FROM recursos WHERE huella = ?", (huella,))
                    candidato = _primer_candidato_perdido(cursor.fetchall(), reclamados)
                if candidato is None:
                    # Registros antiguos sin huella: se reconoce por nombre, pero SOLO si
                    # su ruta anterior ya no existe (así no se confunden dos "apuntes.pdf").
                    cursor.execute(
                        "SELECT id, ruta_local FROM recursos WHERE huella IS NULL AND nombre_archivo = ?", (f,)
                    )
                    candidato = _primer_candidato_perdido(cursor.fetchall(), reclamados)

                if candidato is not None:
                    reclamados.add(candidato)
                    cursor.execute(
                        """
                        UPDATE recursos
                        SET ruta_local = ?, nombre_archivo = ?, semana_id = ?, huella = ?, disponible = 1
                        WHERE id = ?
                        """,
                        (ruta_completa, f, semana_id, huella, candidato),
                    )
                    reubicados += 1
                    continue

                # 3c. Archivo realmente nuevo
                cursor.execute(
                    """
                    INSERT INTO recursos (semana_id, tipo, nombre_archivo, ruta_local, huella, disponible)
                    VALUES (?, 'PDF', ?, ?, ?, 1)
                    """,
                    (semana_id, f, ruta_completa, huella),
                )
                nuevos += 1

        # 4. Lo que estaba registrado bajo esta carpeta y ya no existe se marca, NO se borra.
        cursor.execute("SELECT id, ruta_local FROM recursos WHERE disponible = 1")
        a_marcar = [
            rec_id for rec_id, ruta in cursor.fetchall()
            if ruta and _esta_dentro(ruta, raiz_norm) and _norm(ruta) not in vistos
        ]
        for rec_id in a_marcar:
            cursor.execute("UPDATE recursos SET disponible = 0 WHERE id = ?", (rec_id,))
        no_disponibles = len(a_marcar)

    if progreso_cb:
        progreso_cb(revisados)
    return nuevos, reubicados, no_disponibles


def _primer_candidato_perdido(filas, reclamados):
    """Primer recurso (id, ruta) cuyo archivo ya no existe en su ruta anterior y no fue reclamado."""
    for rec_id, ruta in filas:
        if rec_id in reclamados:
            continue
        if not ruta or not os.path.exists(ruta):
            return rec_id
    return None


def obtener_ruta_guardada() -> str:
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM configuracion WHERE clave = 'ruta_biblioteca'")
            res = cursor.fetchone()
            if res and res[0]:
                return res[0]
    except Exception:
        pass
    return os.path.expanduser("~")
