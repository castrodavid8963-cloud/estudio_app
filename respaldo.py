"""Respaldo y restauración de tus datos (progreso, notas, tarjetas, rutas, tiempo de estudio…).

Un respaldo es un .zip con una copia consistente de `estudios.db` (hecha con la API de copia de SQLite, segura aunque la
app esté abierta) y un manifiesto. NO incluye tus PDF ni el índice de búsqueda: los PDF son tuyos y el índice se puede
reconstruir.
"""
import csv
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime

VERSION_FORMATO = 1
PREFIJO = "estudio_respaldo_"
TABLAS_CLAVE = ("recursos", "notas", "tarjetas", "repasos", "quizzes", "sesiones_estudio", "mini_proyectos", "capitulos")


def _contar(ruta_db: str) -> dict:
    cuentas = {}
    conn = sqlite3.connect(ruta_db)
    try:
        for t in TABLAS_CLAVE:
            try:
                cuentas[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.DatabaseError:
                pass
    finally:
        conn.close()
    return cuentas


def _copia_consistente(ruta_db: str, destino: str):
    origen = sqlite3.connect(ruta_db, timeout=30)
    try:
        copia = sqlite3.connect(destino)
        try:
            origen.backup(copia)
        finally:
            copia.close()
    finally:
        origen.close()


def crear_respaldo(ruta_db: str, carpeta_destino: str, ahora: datetime = None) -> str:
    """Crea `estudio_respaldo_AAAAmmdd_HHMMSS.zip` en `carpeta_destino` y devuelve su ruta."""
    ahora = ahora or datetime.now()
    os.makedirs(carpeta_destino, exist_ok=True)
    zip_ruta = os.path.join(carpeta_destino, f"{PREFIJO}{ahora.strftime('%Y%m%d_%H%M%S')}.zip")
    with tempfile.TemporaryDirectory() as tmp:
        copia = os.path.join(tmp, "estudios.db")
        _copia_consistente(ruta_db, copia)
        manifiesto = {"formato": VERSION_FORMATO, "creado": ahora.isoformat(timespec="seconds"),
                      "contenido": _contar(copia)}
        with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia, "estudios.db")
            z.writestr("manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))
    return zip_ruta


def leer_manifiesto(zip_ruta: str) -> dict:
    """Manifiesto de un respaldo; lanza ValueError si el archivo no es un respaldo válido."""
    try:
        with zipfile.ZipFile(zip_ruta) as z:
            nombres = set(z.namelist())
            if "estudios.db" not in nombres or "manifiesto.json" not in nombres:
                raise ValueError("Este archivo no es un respaldo del Hub de Estudio.")
            return json.loads(z.read("manifiesto.json").decode("utf-8"))
    except zipfile.BadZipFile as e:
        raise ValueError("El archivo está dañado o no es un .zip.") from e


def listar_respaldos(carpeta: str) -> list:
    """[(ruta, manifiesto)] del más reciente al más antiguo; ignora lo que no sea un respaldo válido."""
    if not os.path.isdir(carpeta):
        return []
    salida = []
    for nombre in sorted(os.listdir(carpeta), reverse=True):
        if nombre.startswith(PREFIJO) and nombre.endswith(".zip"):
            ruta = os.path.join(carpeta, nombre)
            try:
                salida.append((ruta, leer_manifiesto(ruta)))
            except ValueError:
                pass
    return salida


def rotar(carpeta: str, mantener: int = 10) -> list:
    """Borra los respaldos más antiguos y conserva `mantener`. Devuelve los borrados."""
    viejos = [r for r, _ in listar_respaldos(carpeta)][mantener:]
    for r in viejos:
        try:
            os.remove(r)
        except OSError:
            pass
    return viejos


def dias_desde_ultimo(carpeta: str, ahora: datetime = None):
    """Días desde el último respaldo, o None si no hay ninguno."""
    ahora = ahora or datetime.now()
    lista = listar_respaldos(carpeta)
    if not lista:
        return None
    try:
        return (ahora - datetime.fromisoformat(lista[0][1]["creado"])).days
    except (KeyError, ValueError):
        return None


def restaurar(zip_ruta: str, ruta_db: str) -> str:
    """Reemplaza la base de datos por la del respaldo. Antes guarda la actual como
    `estudios.antes_de_restaurar.db` junto a ella (devuelve esa ruta, o '' si no había base).
    Verifica la integridad del respaldo antes de tocar nada. Conviene reiniciar la app después."""
    leer_manifiesto(zip_ruta)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_ruta) as z:
            z.extract("estudios.db", tmp)
        nueva = os.path.join(tmp, "estudios.db")
        conn = sqlite3.connect(nueva)
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if ok != "ok":
            raise ValueError("El respaldo está corrupto (falló la verificación de integridad).")
        seguridad = ""
        if os.path.exists(ruta_db):
            seguridad = os.path.join(os.path.dirname(ruta_db), "estudios.antes_de_restaurar.db")
            _copia_consistente(ruta_db, seguridad)
        for sufijo in ("-wal", "-shm"):
            try:
                os.remove(ruta_db + sufijo)
            except OSError:
                pass
        shutil.copyfile(nueva, ruta_db)
    return seguridad


# ------------------------------------------------------------------ exportaciones legibles
def exportar_json(ruta_db: str, destino: str) -> dict:
    """Vuelca lo tuyo (notas, tarjetas, quizzes, mini-proyectos, estado de cada libro) a un JSON abierto.
    Devuelve las cantidades exportadas."""
    conn = sqlite3.connect(ruta_db)
    conn.row_factory = sqlite3.Row
    try:
        def filas(sql):
            try:
                return [dict(f) for f in conn.execute(sql).fetchall()]
            except sqlite3.DatabaseError:
                return []
        datos = {
            "exportado": datetime.now().isoformat(timespec="seconds"),
            "libros": filas("SELECT nombre_archivo, estado, ultima_pagina, total_paginas, es_favorito, modo_lectura "
                            "FROM recursos WHERE estado IS NOT NULL AND estado != 'Sin empezar'"),
            "notas": filas("SELECT r.nombre_archivo AS libro, n.pagina, n.tipo, n.texto, n.color, n.creado FROM notas n "
                           "LEFT JOIN recursos r ON r.id = n.recurso_id ORDER BY n.recurso_id, n.pagina"),
            "tarjetas": filas("SELECT r.nombre_archivo AS libro, t.pagina, t.pregunta, t.respuesta, t.estado, t.proxima "
                              "FROM tarjetas t LEFT JOIN recursos r ON r.id = t.recurso_id"),
            "quizzes": filas("SELECT titulo, creado, total, aciertos FROM quizzes ORDER BY id"),
            "mini_proyectos": filas("SELECT objetivo, etapa, titulo, descripcion, hecho FROM mini_proyectos"),
        }
    finally:
        conn.close()
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return {k: len(v) for k, v in datos.items() if isinstance(v, list)}


def exportar_tarjetas_csv(ruta_db: str, destino: str) -> int:
    """Tarjetas en CSV «pregunta;respuesta;libro;pagina» (UTF-8 con BOM, abre bien en Excel y se importa en Anki)."""
    conn = sqlite3.connect(ruta_db)
    try:
        filas = conn.execute("SELECT t.pregunta, t.respuesta, r.nombre_archivo, t.pagina FROM tarjetas t "
                             "LEFT JOIN recursos r ON r.id = t.recurso_id ORDER BY t.id").fetchall()
    finally:
        conn.close()
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["pregunta", "respuesta", "libro", "pagina"])
        w.writerows(filas)
    return len(filas)


# ------------------------------------------------------------------ respaldo automático
def carpeta_respaldos() -> str:
    import database as db
    from datos import ruta_datos
    return db.obtener_config("ruta_respaldos") or ruta_datos("respaldos")


def automatico_activo() -> bool:
    import database as db
    return (db.obtener_config("respaldo_auto") or "1") != "0"


def respaldo_automatico(cada_dias: int = 7, mantener: int = 10):
    """Hace un respaldo si el último tiene `cada_dias` días o más (o no hay ninguno). Devuelve su ruta o None.
    Pensado para correr al cerrar la app; nunca lanza excepciones."""
    try:
        import database as db
        if not automatico_activo() or not os.path.exists(db.DB_NAME):
            return None
        carpeta = carpeta_respaldos()
        dias = dias_desde_ultimo(carpeta)
        if dias is not None and dias < cada_dias:
            return None
        ruta = crear_respaldo(db.DB_NAME, carpeta)
        rotar(carpeta, mantener)
        return ruta
    except Exception as e:
        print(f"[Respaldo] No se pudo hacer el respaldo automático: {e}")
        return None
