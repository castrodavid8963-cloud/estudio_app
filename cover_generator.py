import os
import pymupdf as fitz
from PIL import Image

# Desactivar advertencias y errores de bajo nivel de MuPDF en la consola
fitz.TOOLS.mupdf_display_errors(False)
fitz.TOOLS.mupdf_display_warnings(False)

CACHE_PORTADAS = os.path.join(os.path.dirname(__file__), "portadas_cache")
os.makedirs(CACHE_PORTADAS, exist_ok=True)

def obtener_o_generar_portada(ruta_pdf: str, tamaño_max: tuple = (120, 160)) -> str:
    """Genera una imagen en miniatura ligera de la primera página del PDF."""
    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return ""

    nombre_archivo = os.path.basename(ruta_pdf)
    hash_nombre = f"{abs(hash(ruta_pdf))}_{nombre_archivo}.png"
    ruta_portada = os.path.join(CACHE_PORTADAS, hash_nombre)

    # Si ya está en caché, retorno inmediato
    if os.path.exists(ruta_portada):
        return ruta_portada

    doc = None
    try:
        doc = fitz.open(ruta_pdf)
        if len(doc) == 0:
            return ""

        pagina = doc[0]
        # Usamos 80 DPI para máxima velocidad de renderizado
        pix = pagina.get_pixmap(dpi=80)
        
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.thumbnail(tamaño_max, Image.Resampling.LANCZOS)
        img.save(ruta_portada, "PNG")
        
        return ruta_portada
    except Exception as e:
        print(f"[Portadas] No se pudo generar portada para {nombre_archivo}: {e}")
        return ""
    finally:
        if doc is not None:
            doc.close()