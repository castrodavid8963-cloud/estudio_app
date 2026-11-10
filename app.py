"""Hub de Estudio: biblioteca, rutas de estudio, lector con tutor IA y registro automático de tiempo."""
import threading
import time
import tkinter as tk

import customtkinter as ctk

import database as db
import respaldo
import tiempo
from portadas import GestorPortadas
from library_scanner import detectar_cambios_rapido
from services import asegurar_ollama_activo
from tema import C, fuente, configurar, barra
from vistas.biblioteca import VistaBiblioteca
from vistas.buscar import VistaBuscar
from vistas.herramientas import VistaHerramientas
from vistas.inicio import VistaInicio
from vistas.lector import VistaLector
from vistas.repaso import VistaRepaso
from vistas.rutas import VistaRutas

# Inactividad más generosa que la de por defecto: leer una página densa lleva tiempo sin tocar nada.
INACTIVIDAD_LECTURA_S = 180
CIERRE_SESION_S = 600

NAVEGACION = [
    ("inicio", "🏠", "Inicio"),
    ("biblioteca", "📚", "Biblioteca"),
    ("rutas", "🧭", "Rutas"),
    ("repaso", "🧠", "Repaso"),
    ("buscar", "🔎", "Buscar"),
    ("herramientas", "🛠", "Herramientas"),
]


class AppEstudio(ctk.CTk):
    def __init__(self):
        configurar()
        super().__init__()
        self.title("Hub de Estudio")
        self.geometry("1280x780")
        self.minsize(520, 440)
        self.configure(fg_color=C["fondo"])

        db.inicializar_db()
        self.rastreador = tiempo.RastreadorEstudio(inactividad=INACTIVIDAD_LECTURA_S, cierre=CIERRE_SESION_S)
        self.portadas = GestorPortadas(self)
        self.ollama_listo = False
        self._vista_actual = None
        self._vista_previa = "inicio"
        self._tick_n = 0
        self._geom_previa = None
        self._encima = False
        self._lateral_compacto = None
        self._job_lateral = None
        self.cambios_pendientes = 0
        self.repaso_pendiente = 0
        self._comprobando = False
        self._ultima_comprobacion = 0.0

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._crear_lateral()
        self.contenedor = ctk.CTkFrame(self, fg_color="transparent")
        self.contenedor.grid(row=0, column=1, sticky="nsew")
        self.contenedor.rowconfigure(0, weight=1)
        self.contenedor.columnconfigure(0, weight=1)

        self.vistas = {
            "inicio": VistaInicio(self.contenedor, self),
            "biblioteca": VistaBiblioteca(self.contenedor, self),
            "rutas": VistaRutas(self.contenedor, self),
            "repaso": VistaRepaso(self.contenedor, self),
            "buscar": VistaBuscar(self.contenedor, self),
            "herramientas": VistaHerramientas(self.contenedor, self),
        }
        for v in self.vistas.values():
            v.grid(row=0, column=0, sticky="nsew")
            v.grid_remove()
        self.lector = VistaLector(self, self)
        self.lector.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.lector.grid_remove()

        for i, (clave, _, _) in enumerate(NAVEGACION, start=1):
            self.bind(f"<Control-Key-{i}>", lambda e, c=clave: self.ir(c) if not self.lector_visible else None)
        self.bind("<Configure>", self._al_cambiar_tamano)
        self.bind_all("<Control-k>", lambda e: self.ir("buscar") if not self.lector_visible else None)
        self.bind_all("<Control-t>", lambda e: self.lector.alternar_panel() if self.lector_visible else None)
        self.bind_all("<Key>", lambda e: self._actividad_global())
        self.bind_all("<Motion>", lambda e: self._actividad_global())

        self.protocol("WM_DELETE_WINDOW", self.al_cerrar)
        self.ir("inicio")
        self.after(200, self._iniciar_hilo_ollama)
        self.after(1500, self.comprobar_cambios)
        self.bind("<FocusIn>", lambda e: self.comprobar_cambios() if e.widget is self else None)
        self.after(1000, self._tick)

    @property
    def lector_visible(self) -> bool:
        return self.lector.winfo_ismapped()

    # ------------------------------------------------------------------ utilidades
    def _en_ui(self, fn, *args, **kwargs):
        """Ejecuta `fn` en el hilo de la interfaz. Seguro de llamar desde hilos de trabajo."""
        try:
            self.after(0, lambda: fn(*args, **kwargs))
        except (RuntimeError, tk.TclError):
            pass

    def _iniciar_hilo_ollama(self):
        def tarea():
            listo = asegurar_ollama_activo()
            self._en_ui(self._estado_ollama, listo)
        threading.Thread(target=tarea, daemon=True).start()

    def _estado_ollama(self, listo):
        self.ollama_listo = listo
        self.lbl_ia.configure(text="● IA lista" if listo else "● IA desconectada",
                              text_color=C["ok"] if listo else C["error"])
        self.lector.actualizar_estado_ia()

    # ------------------------------------------------------------------ ventana compacta
    def _al_cambiar_tamano(self, e):
        if e.widget is not self:
            return
        if self._job_lateral:
            self.after_cancel(self._job_lateral)
        if self.lector_visible:
            self.lector._al_cambiar_tamano()
        self._job_lateral = self.after(150, lambda: self._ajustar_lateral(e.width))

    def _ajustar_lateral(self, ancho):
        """En ventanas estrechas la barra lateral se reduce a iconos."""
        compacto = ancho < 1000
        if compacto == self._lateral_compacto:
            return
        self._lateral_compacto = compacto
        self.lateral.configure(width=64 if compacto else 220)
        self.titulo_lateral.configure(text="📖" if compacto else "📖 Hub de Estudio")
        for clave, icono, texto in NAVEGACION:
            self.botones_nav[clave].configure(text=icono if compacto else f"  {icono}   {texto}",
                                              anchor="center" if compacto else "w")
        if compacto:
            self.pie_lateral.pack_forget()
        else:
            self.pie_lateral.pack(side="bottom", fill="x", padx=12, pady=14)
        self._pintar_insignia()
        self.actualizar_insignia_repaso()
        if self.lector_visible:
            self.lector._al_cambiar_tamano()

    def alternar_compacto(self):
        """Pone la ventana en la mitad derecha de la pantalla con el tutor oculto (para trabajar junto a
        VS Code o el navegador). Pulsar otra vez devuelve tamaño y posición anteriores."""
        if self._geom_previa is None:
            self._geom_previa = (self.state(), self.geometry())
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            ancho = max(560, sw // 2)
            try:
                self.state("normal")
            except tk.TclError:
                pass
            self.geometry(f"{ancho}x{max(480, sh - 80)}+{sw - ancho}+0")
            self.lector.set_modo_compacto(True)
        else:
            estado, geom = self._geom_previa
            self._geom_previa = None
            self.lector.set_modo_compacto(False)
            try:
                self.state("normal")
                self.geometry(geom)
                if estado == "zoomed":
                    self.state("zoomed")
            except tk.TclError:
                pass

    def alternar_encima(self):
        self._encima = not self._encima
        try:
            self.attributes("-topmost", self._encima)
        except tk.TclError:
            self._encima = False
        self.lector.pintar_encima(self._encima)

    # ------------------------------------------------------------------ barra lateral
    def _crear_lateral(self):
        self.lateral = ctk.CTkFrame(self, fg_color=C["lateral"], corner_radius=0, width=220)
        self.lateral.grid(row=0, column=0, sticky="nsew")
        self.lateral.grid_propagate(False)
        self.titulo_lateral = ctk.CTkLabel(self.lateral, text="📖 Hub de Estudio", font=fuente(17, "bold"), text_color=C["texto"])
        self.titulo_lateral.pack(anchor="w", padx=20, pady=(26, 22))
        self.botones_nav = {}
        for clave, icono, texto in NAVEGACION:
            b = ctk.CTkButton(self.lateral, text=f"  {icono}   {texto}", anchor="w", height=42, corner_radius=10,
                              fg_color="transparent", hover_color=C["tarjeta_hover"], text_color=C["texto2"],
                              font=fuente(14), command=lambda c=clave: self.ir(c))
            b.pack(fill="x", padx=12, pady=2)
            self.botones_nav[clave] = b

        pie = ctk.CTkFrame(self.lateral, fg_color=C["tarjeta"], corner_radius=12, border_width=1, border_color=C["borde"])
        pie.pack(side="bottom", fill="x", padx=12, pady=14)
        self.pie_lateral = pie
        ctk.CTkLabel(pie, text="HOY", font=fuente(10, "bold"), text_color=C["texto3"]).pack(anchor="w", padx=14, pady=(10, 0))
        self.lbl_hoy = ctk.CTkLabel(pie, text="0 s", font=fuente(18, "bold"), text_color=C["texto"])
        self.lbl_hoy.pack(anchor="w", padx=14)
        self.barra_hoy = barra(pie, 0, C["acento"])
        self.barra_hoy.pack(fill="x", padx=14, pady=(2, 4))
        self.lbl_meta = ctk.CTkLabel(pie, text="", font=fuente(11), text_color=C["texto2"])
        self.lbl_meta.pack(anchor="w", padx=14)
        self.lbl_ia = ctk.CTkLabel(pie, text="● IA comprobando…", font=fuente(11), text_color=C["texto3"])
        self.lbl_ia.pack(anchor="w", padx=14, pady=(4, 10))

    def _refrescar_pie(self):
        hoy, meta = tiempo.segundos_hoy(), tiempo.meta_diaria_segundos()
        self.lbl_hoy.configure(text=tiempo.formatear(hoy))
        self.barra_hoy.set(min(1.0, hoy / meta))
        self.lbl_meta.configure(text=f"meta {tiempo.formatear(meta)}" + ("  ✓" if hoy >= meta else ""))

    # ------------------------------------------------------------------ navegación
    def ir(self, nombre, **kw):
        if self.lector_visible:
            self.cerrar_lector(volver=False)
        if self._vista_actual and self._vista_actual in self.vistas:
            self.vistas[self._vista_actual].grid_remove()
        self._vista_actual = nombre
        vista = self.vistas[nombre]
        vista.grid()
        vista.al_mostrar(**kw)
        if nombre == "biblioteca":
            self.comprobar_cambios()
        for clave, b in self.botones_nav.items():
            activo = clave == nombre
            b.configure(fg_color=C["acento_suave"] if activo else "transparent",
                        text_color=C["texto"] if activo else C["texto2"])
        self._refrescar_pie()
        self.actualizar_insignia_repaso()

    def abrir_libro(self, recurso_id: int, panel: str = None, pagina: int = None):
        libro = db.obtener_libro(recurso_id)
        if not libro:
            return
        if pagina:
            libro["ultima_pagina"] = pagina
        if self._vista_actual:
            self._vista_previa = self._vista_actual
            self.vistas[self._vista_actual].grid_remove()
        self.lateral.grid_remove()
        self.contenedor.grid_remove()
        self.lector.grid()
        self.lector.abrir(libro)
        if panel:
            self.lector.mostrar_panel(panel, forzar=True)
        self.lector.focus_set()

    def volver_del_lector(self):
        """Botón «Volver»: si la sesión fue de más de 2 minutos, ofrece dejar una nota rápida."""
        l = self.lector
        if l.libro is not None and db.obtener_config("nota_al_cerrar", "1") == "1" and self.rastreador.segundos_sesion >= 120:
            l.pedir_nota_sesion(self.cerrar_lector)
        else:
            self.cerrar_lector()

    def cerrar_lector(self, volver=True):
        self.lector.cerrar()
        self.lector.grid_remove()
        self.lateral.grid()
        self.contenedor.grid()
        if volver:
            self._vista_actual = None
            self.ir(self._vista_previa)

    # ------------------------------------------------------------------ cambios en la biblioteca
    def comprobar_cambios(self, forzar=False):
        """Compara en segundo plano lo que hay en disco con lo indexado (rápido, no lee los PDF).
        Se llama al abrir la app, al abrir la Biblioteca y al volver a la ventana (máx. 1 vez por minuto)."""
        raiz = db.obtener_ruta_biblioteca()
        ahora = time.monotonic()
        if (not raiz or self._comprobando or self.vistas["herramientas"]._indexando
                or (not forzar and ahora - self._ultima_comprobacion < 60)):
            return
        self._comprobando = True
        self._ultima_comprobacion = ahora

        def tarea():
            try:
                info = detectar_cambios_rapido(raiz)
            except Exception as e:
                print(f"[Cambios] {e}")
                info = None
            self._en_ui(self._cambios_detectados, info)
        threading.Thread(target=tarea, daemon=True).start()

    def _cambios_detectados(self, info):
        self._comprobando = False
        if info is None:
            return
        self.cambios_pendientes = info["nuevos"] + info["faltantes"]
        self._pintar_insignia()
        self.vistas["biblioteca"].mostrar_cambios(info)

    def actualizar_insignia_repaso(self):
        """Marca en la barra lateral cuántas tarjetas hay para repasar hoy."""
        try:
            n = db.resumen_repaso()["pendientes"]
        except Exception:
            n = 0
        self.repaso_pendiente = n
        if self._lateral_compacto:
            texto = "🧠●" if n else "🧠"
        else:
            texto = "  🧠   Repaso" + (f"   ● {n}" if n else "")
        if "repaso" in self.botones_nav:
            self.botones_nav["repaso"].configure(text=texto)

    def _pintar_insignia(self):
        if self._lateral_compacto:
            texto = "📚●" if self.cambios_pendientes else "📚"
        else:
            texto = "  📚   Biblioteca" + (f"   ● {self.cambios_pendientes}" if self.cambios_pendientes else "")
        self.botones_nav["biblioteca"].configure(text=texto)

    def actualizar_biblioteca(self):
        """Reindexa la carpeta raíz (no mueve ni borra nada) y refresca la pantalla actual."""
        h = self.vistas["herramientas"]
        if not db.obtener_ruta_biblioteca():
            self.ir("herramientas", pestaña="Biblioteca")
            return
        if h._indexando:
            return
        self.vistas["biblioteca"].marcar_actualizando(True)
        h.indexar(al_terminar=self._tras_actualizar)

    def _tras_actualizar(self, resultado):
        self.cambios_pendientes = 0
        self._pintar_insignia()
        b = self.vistas["biblioteca"]
        b.marcar_actualizando(False)
        b.mostrar_resultado(resultado)
        if not self.lector_visible and self._vista_actual in ("inicio", "biblioteca", "rutas"):
            self.vistas[self._vista_actual].al_mostrar()
        self._ultima_comprobacion = time.monotonic()

    # ------------------------------------------------------------------ tiempo de estudio
    def _actividad_global(self):
        if self.lector_visible:
            self.lector._actividad()

    def _tick(self):
        """Cada segundo: refresca el indicador; cada 5 s cierra sesiones inactivas y actualiza el contador."""
        self._tick_n += 1
        try:
            if self.lector_visible:
                self.lector.actualizar_indicador()
            if self._tick_n % 5 == 0:
                self.rastreador.revisar()
                self._refrescar_pie()
        except Exception as e:
            print(f"[Tick] {e}")
        self.after(1000, self._tick)

    def al_cerrar(self):
        try:
            self.vistas["buscar"].indexador.detener()
            if self.lector_visible:
                self.lector.cerrar()
            self.rastreador.cerrar()
        except Exception as e:
            print(f"[Cierre] No se pudo guardar la sesión en curso: {e}")
        finally:
            respaldo.respaldo_automatico()
            self.portadas.cerrar()
            self.destroy()


if __name__ == "__main__":
    app = AppEstudio()
    app.mainloop()
