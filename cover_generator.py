import hashlib
import os
import threading

from PIL import Image

from pdf_core import fitz, PYMUPDF_LOCK

from datos import ruta_datos
CACHE_PORTADAS = ruta_datos("portadas_cache")
os.makedirs(CACHE_PORTADAS, exist_ok=True)


def _ruta_cache(ruta_pdf: str) -> str:
    """Nombre de caché estable entre ejecuciones (a diferencia de hash(), que es aleatorio por proceso).

    Incluye tamaño y fecha de modificación: si el PDF cambia, la portada se regenera.
    """
    try:
        st = os.stat(ruta_pdf)
        firma = f"{os.path.abspath(ruta_pdf)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        firma = os.path.abspath(ruta_pdf)
    digest = hashlib.sha1(firma.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_PORTADAS, f"{digest}.png")


def obtener_o_generar_portada(ruta_pdf: str, tamaño_max: tuple = (120, 160)) -> str:
    """Genera (o reutiliza) una miniatura de la primera página del PDF. Devuelve su ruta o ''."""
    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return ""

    ruta_portada = _ruta_cache(ruta_pdf)
    if os.path.exists(ruta_portada):
        return ruta_portada

    nombre_archivo = os.path.basename(ruta_pdf)
    tmp = f"{ruta_portada}.{os.getpid()}.{threading.get_ident()}.tmp"
    doc = None
    try:
        with PYMUPDF_LOCK:
            doc = fitz.open(ruta_pdf)
            if len(doc) == 0:
                return ""
            pix = doc[0].get_pixmap(dpi=80)  # 80 DPI: suficiente para una miniatura
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        img.thumbnail(tamaño_max, Image.Resampling.LANCZOS)
        # Escritura atómica: nadie lee una portada a medio escribir.
        img.save(tmp, "PNG")
        os.replace(tmp, ruta_portada)
        return ruta_portada
    except Exception as e:
        print(f"[Portadas] No se pudo generar portada para {nombre_archivo}: {e}")
        return ""
    finally:
        if doc is not None:
            with PYMUPDF_LOCK:
                doc.close()
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
