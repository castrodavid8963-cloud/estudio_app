import os
import re
import sqlite3
from database import obtener_conexion

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

def purgar_datos_obsoletos():
    """Elimina de SQLite las materias y archivos cuyas rutas físicas ya no existen."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()

        # 1. Eliminar recursos cuyas rutas de archivo ya no existen
        cursor.execute("SELECT id, ruta_local FROM recursos")
        recursos = cursor.fetchall()
        for rec_id, ruta in recursos:
            if not os.path.exists(ruta):
                cursor.execute("DELETE FROM recursos WHERE id = ?", (rec_id,))

        # 2. Eliminar semanas y materias huérfanas que se hayan quedado sin recursos/archivos
        cursor.execute("""
        DELETE FROM materias 
        WHERE id NOT IN (
            SELECT DISTINCT s.materia_id 
            FROM semanas s 
            JOIN recursos r ON r.semana_id = s.id
        ) AND tipo = 'Personal'
        """)

        conn.commit()
    print("[Escáner] Purga de registros antiguos completada.")

def escanear_e_indexar_biblioteca(ruta_raiz: str) -> tuple[int, int]:
    if not os.path.exists(ruta_raiz):
        print(f"[Escáner] La ruta {ruta_raiz} no existe.")
        return 0, 0

    # Primero hacemos limpieza de lo que ya no está en esa ubicación
    purgar_datos_obsoletos()

    nuevos_agregados = 0
    archivos_actualizados = 0

    with obtener_conexion() as conn:
        cursor = conn.cursor()

        # Guardar la última ruta válida
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT
        );
        """)
        cursor.execute("INSERT OR REPLACE INTO configuracion (clave, valor) VALUES ('ruta_biblioteca', ?)", (ruta_raiz,))

        for root, dirs, files in os.walk(ruta_raiz):
            # Filtrar directorios basura en el recorrido para no perder tiempo escaneándolos
            dirs[:] = [d for d in dirs if not es_carpeta_basura_o_sistema(d)]

            archivos_pdf = [f for f in files if f.lower().endswith('.pdf')]
            if not archivos_pdf:
                continue

            rel_path = os.path.relpath(root, ruta_raiz)
            partes = rel_path.replace("\\", "/").split("/")
            nombre_materia = partes[-1].replace("_", " ").strip()

            if es_carpeta_basura_o_sistema(nombre_materia):
                continue

            # 1. Obtener o crear la materia activa
            cursor.execute("SELECT id FROM materias WHERE nombre = ?", (nombre_materia,))
            res = cursor.fetchone()
            if res:
                materia_id = res[0]
            else:
                cursor.execute(
                    "INSERT INTO materias (nombre, tipo, descripcion) VALUES (?, ?, ?)",
                    (nombre_materia, 'Personal', f"Carpeta: {rel_path}")
                )
                materia_id = cursor.lastrowid

            # 2. Obtener o crear Semana 1
            cursor.execute("SELECT id FROM semanas WHERE materia_id = ? AND numero_semana = 1", (materia_id,))
            res_sem = cursor.fetchone()
            semana_id = res_sem[0] if res_sem else None

            if not semana_id:
                cursor.execute(
                    "INSERT INTO semanas (materia_id, numero_semana, titulo_tema) VALUES (?, ?, ?)",
                    (materia_id, 1, "General / Documentos")
                )
                semana_id = cursor.lastrowid

            # 3. Insertar / Actualizar los PDFs
            for f in archivos_pdf:
                ruta_completa = os.path.join(root, f)

                cursor.execute("SELECT id FROM recursos WHERE ruta_local = ?", (ruta_completa,))
                if cursor.fetchone():
                    continue

                cursor.execute("SELECT id FROM recursos WHERE nombre_archivo = ?", (f,))
                res_existente = cursor.fetchone()

                if res_existente:
                    recurso_id = res_existente[0]
                    cursor.execute("""
                    UPDATE recursos
                    SET ruta_local = ?, semana_id = ?
                    WHERE id = ?
                    """, (ruta_completa, semana_id, recurso_id))
                    archivos_actualizados += 1
                else:
                    cursor.execute("""
                    INSERT INTO recursos (semana_id, tipo, nombre_archivo, ruta_local)
                    VALUES (?, 'PDF', ?, ?)
                    """, (semana_id, f, ruta_completa))
                    nuevos_agregados += 1

        conn.commit()

    return nuevos_agregados, archivos_actualizados

def obtener_ruta_guardada() -> str:
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM configuracion WHERE clave = 'ruta_biblioteca'")
            res = cursor.fetchone()
            if res:
                return res[0]
    except Exception:
        pass
    return "C:\\"