"""OCR opcional para PDF escaneados (páginas que son imágenes, sin texto).

Usa Tesseract, un programa externo y gratuito que hay que instalar aparte. Si no está, la app sigue funcionando igual:
solo no podrá buscar ni usar el tutor en los libros escaneados. El texto reconocido se guarda en el índice de búsqueda
(`busqueda.db`); NUNCA se modifica tu PDF.
"""
import os
import shutil
import subprocess
import sys
import threading
import time

IDIOMAS_PREFERIDOS = ("spa", "eng")
DPI = 200
TIEMPO_MAX_PAGINA_S = 180
_CREAR_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)       # evita parpadeos de consola en Windows
_RUTAS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
INSTRUCCIONES = (
    "Instala Tesseract (gratis): en Windows, el instalador de UB Mannheim (busca «tesseract ocr windows»); marca el "
    "idioma Spanish en la instalación. Luego reinicia la app."
)


def ruta_tesseract():
    forzada = os.environ.get("ESTUDIO_TESSERACT")
    if forzada and os.path.exists(forzada):
        return forzada
    en_path = shutil.which("tesseract")
    if en_path:
        return en_path
    local = os.environ.get("LOCALAPPDATA")
    candidatas = list(_RUTAS_WINDOWS) + ([os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe")] if local else [])
    return next((r for r in candidatas if os.path.exists(r)), None)


def idiomas_instalados(exe: str = None) -> set:
    exe = exe or ruta_tesseract()
    if not exe:
        return set()
    try:
        r = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20,
                           creationflags=_CREAR_SIN_VENTANA)
    except (OSError, subprocess.SubprocessError):
        return set()
    lineas = (r.stdout + "\n" + r.stderr).splitlines()
    return {l.strip() for l in lineas if l.strip() and not l.startswith("List of") and l.strip() != "osd"}


def idioma_a_usar(instalados: set) -> str:
    """«spa+eng» si están ambos, el que haya si solo hay uno, o '' si no hay ninguno útil."""
    usar = [i for i in IDIOMAS_PREFERIDOS if i in instalados]
    return "+".join(usar)


def estado() -> dict:
    """{'disponible', 'ruta', 'idioma', 'mensaje'} para mostrar en pantalla."""
    exe = ruta_tesseract()
    if not exe:
        return {"disponible": False, "ruta": None, "idioma": "", "mensaje": "Tesseract no está instalado. " + INSTRUCCIONES}
    idioma = idioma_a_usar(idiomas_instalados(exe))
    if not idioma:
        return {"disponible": False, "ruta": exe, "idioma": "",
                "mensaje": "Tesseract está instalado pero sin idiomas útiles (spa / eng). Reinstálalo marcando Spanish."}
    aviso = "" if "spa" in idioma else " (sin español: instala el paquete «spa» para mejores resultados)"
    return {"disponible": True, "ruta": exe, "idioma": idioma, "mensaje": f"Listo · idioma {idioma}{aviso}"}


def reconocer_png(png: bytes, idioma: str, exe: str = None) -> str:
    """Texto de una imagen PNG. Lanza RuntimeError si Tesseract falla."""
    exe = exe or ruta_tesseract()
    try:
        r = subprocess.run([exe, "stdin", "stdout", "-l", idioma, "--psm", "3"], input=png, capture_output=True,
                           timeout=TIEMPO_MAX_PAGINA_S, creationflags=_CREAR_SIN_VENTANA)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Tesseract tardó demasiado en una página.") from e
    except OSError as e:
        raise RuntimeError(f"No se pudo ejecutar Tesseract: {e}") from e
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[:300] or "Tesseract falló.")
    return " ".join(r.stdout.decode("utf-8", "replace").split())


class TrabajoOCR:
    """Hilo de fondo que aplica OCR a los libros escaneados. Se puede pausar y detener; lo hecho se conserva por páginas."""

    def __init__(self, al_progreso=None, debe_ceder=None):
        self.al_progreso = al_progreso or (lambda *a: None)      # (libros_hechos, libros_total, titulo, pagina, paginas, terminado)
        self.debe_ceder = debe_ceder or (lambda: False)
        self._hilo = None
        self._parar = threading.Event()
        self.libros_hechos = self.libros_total = self.errores = 0
        self.ultimo_error = ""

    @property
    def activo(self) -> bool:
        return bool(self._hilo and self._hilo.is_alive())

    def iniciar(self, libros: list):
        """libros: [(recurso_id, ruta, firma)]"""
        if self.activo:
            return
        self._parar.clear()
        self.libros_hechos, self.libros_total, self.errores, self.ultimo_error = 0, len(libros), 0, ""
        self._hilo = threading.Thread(target=self._trabajo, args=(libros,), daemon=True)
        self._hilo.start()

    def detener(self):
        self._parar.set()

    def _esperar(self):
        while self.debe_ceder() and not self._parar.is_set():
            time.sleep(0.5)

    def _trabajo(self, libros):
        import buscador
        est = estado()
        try:
            if not est["disponible"]:
                self.ultimo_error = est["mensaje"]
                return
            for rid, ruta, firma in libros:
                if self._parar.is_set():
                    break
                nombre = os.path.basename(ruta)
                try:
                    completo = buscador.ocr_libro(
                        rid, ruta, firma, est["idioma"], est["ruta"], self._parar.is_set, self._esperar,
                        lambda p, n, nombre=nombre: self.al_progreso(self.libros_hechos, self.libros_total, nombre, p, n, False))
                    if completo:
                        self.libros_hechos += 1
                except Exception as e:
                    self.errores += 1
                    self.ultimo_error = str(e)
        finally:
            self.al_progreso(self.libros_hechos, self.libros_total, "", 0, 0, True)
