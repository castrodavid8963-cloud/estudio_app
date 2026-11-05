"""Hub de Estudio: biblioteca, rutas de estudio, lector con tutor IA y registro automático de tiempo."""
import threading
import tkinter as tk

import customtkinter as ctk

import database as db
import tiempo
from portadas import GestorPortadas
from services import asegurar_ollama_activo
from tema import C, fuente, configurar, barra
from vistas.biblioteca import VistaBiblioteca
from vistas.herramientas import VistaHerramientas
from vistas.inicio import VistaInicio
from vistas.lector import VistaLector
from vistas.rutas import VistaRutas

# Inactividad más generosa que la de por defecto: leer una página densa lleva tiempo sin tocar nada.
INACTIVIDAD_LECTURA_S = 180
CIERRE_SESION_S = 600

NAVEGACION = [
    ("inicio", "🏠", "Inicio"),
    ("biblioteca", "📚", "Biblioteca"),
    ("rutas", "🧭", "Rutas"),
    ("herramientas", "🛠", "Herramientas"),
]


class AppEstudio(ctk.CTk):
    def __init__(self):
        configurar()
        super().__init__()
        self.title("Hub de Estudio")
        self.geometry("1280x780")
        self.minsize(1020, 640)
        self.configure(fg_color=C["fondo"])

        db.inicializar_db()
        self.rastreador = tiempo.RastreadorEstudio(inactividad=INACTIVIDAD_LECTURA_S, cierre=CIERRE_SESION_S)
        self.portadas = GestorPortadas(self)
        self.ollama_listo = False
        self._vista_actual = None
        self._vista_previa = "inicio"
        self._tick_n = 0

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
        self.bind_all("<Key>", lambda e: self._actividad_global())
        self.bind_all("<Motion>", lambda e: self._actividad_global())

        self.protocol("WM_DELETE_WINDOW", self.al_cerrar)
        self.ir("inicio")
        self.after(200, self._iniciar_hilo_ollama)
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

    # ------------------------------------------------------------------ barra lateral
    def _crear_lateral(self):
        self.lateral = ctk.CTkFrame(self, fg_color=C["lateral"], corner_radius=0, width=220)
        self.lateral.grid(row=0, column=0, sticky="nsew")
        self.lateral.grid_propagate(False)
        ctk.CTkLabel(self.lateral, text="📖 Hub de Estudio", font=fuente(17, "bold"), text_color=C["texto"]
                     ).pack(anchor="w", padx=20, pady=(26, 22))
        self.botones_nav = {}
        for clave, icono, texto in NAVEGACION:
            b = ctk.CTkButton(self.lateral, text=f"  {icono}   {texto}", anchor="w", height=42, corner_radius=10,
                              fg_color="transparent", hover_color=C["tarjeta_hover"], text_color=C["texto2"],
                              font=fuente(14), command=lambda c=clave: self.ir(c))
            b.pack(fill="x", padx=12, pady=2)
            self.botones_nav[clave] = b

        pie = ctk.CTkFrame(self.lateral, fg_color=C["tarjeta"], corner_radius=12, border_width=1, border_color=C["borde"])
        pie.pack(side="bottom", fill="x", padx=12, pady=14)
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
        for clave, b in self.botones_nav.items():
            activo = clave == nombre
            b.configure(fg_color=C["acento_suave"] if activo else "transparent",
                        text_color=C["texto"] if activo else C["texto2"])
        self._refrescar_pie()

    def abrir_libro(self, recurso_id: int):
        libro = db.obtener_libro(recurso_id)
        if not libro:
            return
        if self._vista_actual:
            self._vista_previa = self._vista_actual
            self.vistas[self._vista_actual].grid_remove()
        self.lateral.grid_remove()
        self.contenedor.grid_remove()
        self.lector.grid()
        self.lector.abrir(libro)
        self.lector.focus_set()

    def cerrar_lector(self, volver=True):
        self.lector.cerrar()
        self.lector.grid_remove()
        self.lateral.grid()
        self.contenedor.grid()
        if volver:
            self._vista_actual = None
            self.ir(self._vista_previa)

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
            if self.lector_visible:
                self.lector.cerrar()
            self.rastreador.cerrar()
        except Exception as e:
            print(f"[Cierre] No se pudo guardar la sesión en curso: {e}")
        finally:
            self.portadas.cerrar()
            self.destroy()


if __name__ == "__main__":
    app = AppEstudio()
    app.mainloop()
