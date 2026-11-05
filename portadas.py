"""Carga de portadas en segundo plano con caché en memoria (no bloquea la interfaz)."""
import threading
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk
from PIL import Image

from cover_generator import obtener_o_generar_portada


class GestorPortadas:
    def __init__(self, app, tam=(96, 132)):
        self.app = app
        self.tam = tam
        self._cache = {}                      # (ruta, tam) -> CTkImage | None
        self._pendientes = {}                 # (ruta, tam) -> [callbacks]
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="portadas")

    def en_cache(self, ruta, tam=None):
        return self._cache.get((ruta, tam or self.tam))

    def pedir(self, ruta, callback, tam=None):
        """Llama `callback(ctk_imagen_o_None)` en el hilo de la interfaz cuando la portada esté lista."""
        tam = tam or self.tam
        clave = (ruta, tam)
        if clave in self._cache:
            callback(self._cache[clave])
            return
        with self._lock:
            if clave in self._pendientes:
                self._pendientes[clave].append(callback)
                return
            self._pendientes[clave] = [callback]
        self._pool.submit(self._trabajo, ruta, tam)

    def _trabajo(self, ruta, tam):
        imagen = None
        try:
            png = obtener_o_generar_portada(ruta)
            if png:
                with Image.open(png) as im:
                    pil = im.convert("RGB")
                pil.thumbnail((tam[0] * 2, tam[1] * 2))
                w, h = pil.size
                escala = min(tam[0] / w, tam[1] / h)
                imagen = (pil, (max(1, int(w * escala)), max(1, int(h * escala))))
        except Exception as e:
            print(f"[Portadas] {e}")
        self.app._en_ui(self._entregar, ruta, tam, imagen)

    def _entregar(self, ruta, tam, imagen):
        ctk_img = None
        if imagen:
            pil, tam_real = imagen
            ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=tam_real)
        self._cache[(ruta, tam)] = ctk_img
        with self._lock:
            callbacks = self._pendientes.pop((ruta, tam), [])
        for cb in callbacks:
            try:
                cb(ctk_img)
            except Exception:
                pass   # el widget pudo destruirse mientras tanto

    def cerrar(self):
        self._pool.shutdown(wait=False, cancel_futures=True)
