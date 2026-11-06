"""Lector de PDF integrado + tutor IA. Aquí es donde el tiempo de estudio se registra solo."""
import io
import os
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk

import database as db
import tiempo
from ai_pdf import extraer_fragmentos_pdf, IndiceLibro, consultar_ollama_con_contexto, ErrorOllama
from pdf_core import fitz, PYMUPDF_LOCK
from tema import C, ESTADO_COLOR, ESTADO_ICONO, fuente, titulo, subtitulo, boton, recortar

ZOOM_MIN, ZOOM_MAX, ZOOM_PASO = 0.5, 3.0, 0.15
MAX_HISTORIAL_GUARDADO = 200
ANCHO_TUTOR_MIN, ANCHO_TUTOR_MAX, ANCHO_TUTOR_DEFECTO = 280, 700, 380
FONDO_CLARO, FONDO_OSCURO = "#2a2d3a", "#0b0c10"
ACCIONES_RAPIDAS = [
    ("📄 Resumir", "Resume en viñetas claras el contenido de la página {n}."),
    ("💡 Conceptos", "Explica con lenguaje sencillo y un ejemplo los conceptos clave de la página {n}."),
    ("🧠 Quiz", "Hazme 3 preguntas de opción múltiple sobre la página {n}. Pon las respuestas correctas al final."),
]


class VistaLector(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color=C["fondo"])
        self.app = app
        self.libro = None
        self._doc = None
        self._pagina = 1
        self._total = 0
        self._zoom = 1.0
        self._foto = None
        self._gen = 0
        self._guardar_job = None
        self._reajuste_job = None
        self._ultimo_cambio = 0.0
        self._ultima_act = 0.0
        # tutor
        self._indice = None
        self._leyendo = False
        self._ia_ocupada = False
        self._historial = []
        self._tutor_visible = db.obtener_config("lector_tutor_visible") != "0"
        self._tutor_previo = None          # estado del tutor antes de entrar al modo compacto
        self._angosto = False
        self._tutor_permitido = True
        # preferencias (se recuerdan entre sesiones)
        self._lado = "izquierda" if db.obtener_config("lector_lado") == "izquierda" else "derecha"
        try:
            self._ancho_tutor = max(ANCHO_TUTOR_MIN, min(ANCHO_TUTOR_MAX, int(db.obtener_config("lector_ancho_tutor", ANCHO_TUTOR_DEFECTO))))
        except (TypeError, ValueError):
            self._ancho_tutor = ANCHO_TUTOR_DEFECTO
        self._dos = db.obtener_config("lector_dos_paginas") == "1"
        self._oscuro = db.obtener_config("lector_oscuro") == "1"

        self.rowconfigure(1, weight=1)
        self._crear_barra_superior()
        self._crear_visor()
        self._crear_tutor()
        self._crear_divisor()
        self._enlazar_eventos()
        self.bind("<Configure>", self._al_cambiar_tamano)
        self._disponer()
        self._pintar_toggles()

    # ================================================================== construcción
    def _crear_barra_superior(self):
        b = ctk.CTkFrame(self, fg_color=C["lateral"], corner_radius=0, height=54)
        b.grid(row=0, column=0, columnspan=3, sticky="ew")
        b.grid_propagate(False)
        b.columnconfigure(1, weight=1)
        boton(b, "‹  Volver", self.app.cerrar_lector, "suave", width=90).grid(row=0, column=0, padx=(14, 10), pady=10)
        self.lbl_titulo = ctk.CTkLabel(b, text="", font=fuente(14, "bold"), text_color=C["texto"], anchor="w")
        self.lbl_titulo.grid(row=0, column=1, sticky="w")

        nav = ctk.CTkFrame(b, fg_color="transparent")
        nav.grid(row=0, column=2, padx=6)
        boton(nav, "‹", lambda: self.ir_a(self._pagina - self._paso()), "fantasma", width=30).pack(side="left")
        self.ent_pagina = ctk.CTkEntry(nav, width=52, height=30, justify="center", fg_color=C["tarjeta"], border_color=C["borde"])
        self.ent_pagina.pack(side="left", padx=2)
        self.ent_pagina.bind("<Return>", self._ir_desde_entrada)
        self.lbl_total = ctk.CTkLabel(nav, text="/ 0", font=fuente(13), text_color=C["texto2"], width=48)
        self.lbl_total.pack(side="left")
        boton(nav, "›", lambda: self.ir_a(self._pagina + self._paso()), "fantasma", width=30).pack(side="left")

        zoom = ctk.CTkFrame(b, fg_color="transparent")
        zoom.grid(row=0, column=3, padx=6)
        self.zoom_marco = zoom
        self._zoom_ctrl = [boton(zoom, "−", lambda: self.cambiar_zoom(-ZOOM_PASO), "fantasma", width=28)]
        self.lbl_zoom = ctk.CTkLabel(zoom, text="100%", font=fuente(12), text_color=C["texto2"], width=44)
        self._zoom_ctrl += [self.lbl_zoom, boton(zoom, "+", lambda: self.cambiar_zoom(ZOOM_PASO), "fantasma", width=28)]
        for w in self._zoom_ctrl:
            w.pack(side="left")
        self.btn_dos = boton(zoom, "▯▯", self.alternar_dos_paginas, "fantasma", width=36)
        self.btn_dos.pack(side="left", padx=(22, 0))
        self.btn_oscuro = boton(zoom, "🌙", self.alternar_oscuro, "fantasma", width=36)
        self.btn_oscuro.pack(side="left", padx=(10, 0))

        self.var_estado = ctk.StringVar(value="Sin empezar")
        self.menu_estado = ctk.CTkOptionMenu(b, variable=self.var_estado, values=list(db.ESTADOS), width=138, height=30,
                                             fg_color=C["tarjeta"], button_color=C["tarjeta_hover"],
                                             button_hover_color=C["borde"], command=self._cambiar_estado)
        self.menu_estado.grid(row=0, column=4, padx=6)
        self.btn_fav = ctk.CTkButton(b, text="☆", width=34, height=30, font=fuente(17), fg_color="transparent",
                                     hover_color=C["tarjeta_hover"], text_color=C["texto3"], command=self._favorito)
        self.btn_fav.grid(row=0, column=5)
        self.lbl_sesion = ctk.CTkLabel(b, text="", font=fuente(12, "bold"), text_color=C["texto3"], width=110, anchor="e")
        self.lbl_sesion.grid(row=0, column=6, padx=(4, 6))
        grupo = ctk.CTkFrame(b, fg_color="transparent")
        grupo.grid(row=0, column=7, padx=(0, 14))
        self.btn_encima = boton(grupo, "📌", lambda: self.app.alternar_encima(), "suave", width=34)
        self.btn_encima.pack(side="left", padx=(0, 4))
        self.btn_compacto = boton(grupo, "🗗", lambda: self.app.alternar_compacto(), "suave", width=34)
        self.btn_compacto.pack(side="left", padx=(0, 4))
        self.btn_lado = boton(grupo, "⇄", self.cambiar_lado, "suave", width=34)
        self.btn_lado.pack(side="left", padx=(0, 4))
        self.btn_tutor = boton(grupo, "🤖 Tutor", self.alternar_tutor, "suave", width=86)
        self.btn_tutor.pack(side="left")

    def _crear_visor(self):
        self.marco_visor = ctk.CTkFrame(self, fg_color=C["panel"], corner_radius=0)
        self.marco_visor.rowconfigure(0, weight=1)
        self.marco_visor.columnconfigure(0, weight=1)
        self.lienzo = tk.Canvas(self.marco_visor, bg=FONDO_CLARO, highlightthickness=0, bd=0)
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self.scroll = ctk.CTkScrollbar(self.marco_visor, command=self.lienzo.yview, button_color=C["borde"])
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.scroll_x = ctk.CTkScrollbar(self.marco_visor, command=self.lienzo.xview, orientation="horizontal",
                                         button_color=C["borde"], height=12)
        self.scroll_x.grid(row=1, column=0, sticky="ew")
        self.lienzo.configure(yscrollcommand=self.scroll.set, xscrollcommand=self.scroll_x.set)
        self._id_img = None
        self._id_msg = self.lienzo.create_text(0, 0, text="", fill=C["texto2"], font=("TkDefaultFont", 13), justify="center")

    def _crear_tutor(self):
        self.tutor = ctk.CTkFrame(self, fg_color=C["lateral"], corner_radius=0, width=self._ancho_tutor)
        self.tutor.grid_propagate(False)
        self.tutor.rowconfigure(2, weight=1)
        self.tutor.columnconfigure(0, weight=1)
        cab = ctk.CTkFrame(self.tutor, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        titulo(cab, "Tutor IA", 16).pack(side="left")
        self.lbl_ia = ctk.CTkLabel(cab, text="", font=fuente(11), text_color=C["texto3"])
        self.lbl_ia.pack(side="right")
        self.lbl_contexto = subtitulo(self.tutor, "", 11)
        self.lbl_contexto.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        self.chat = tk.Text(self.tutor, wrap="word", bg=C["lateral"], fg=C["texto"], bd=0, highlightthickness=0,
                            padx=14, pady=6, font=("TkDefaultFont", 10), state="disabled", cursor="arrow",
                            spacing1=2, spacing3=2, insertbackground=C["texto"], selectbackground=C["acento_suave"])
        self.chat.grid(row=2, column=0, sticky="nsew", padx=(4, 0))
        sb = ctk.CTkScrollbar(self.tutor, command=self.chat.yview, button_color=C["borde"], width=10)
        sb.grid(row=2, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=sb.set)
        self.chat.tag_configure("quien_u", foreground=C["acento"], font=("TkDefaultFont", 10, "bold"), spacing1=12)
        self.chat.tag_configure("quien_ia", foreground=C["ok"], font=("TkDefaultFont", 10, "bold"), spacing1=12)
        self.chat.tag_configure("quien_s", foreground=C["texto3"], font=("TkDefaultFont", 10, "bold"), spacing1=12)
        self.chat.tag_configure("u", foreground=C["texto"], lmargin1=8, lmargin2=8, background=C["acento_suave"])
        self.chat.tag_configure("ia", foreground=C["texto"], lmargin1=8, lmargin2=8)
        self.chat.tag_configure("s", foreground=C["texto2"], lmargin1=8, lmargin2=8, font=("TkDefaultFont", 10, "italic"))
        self.chat.tag_configure("e", foreground=C["error"], lmargin1=8, lmargin2=8)

        fila_acc = ctk.CTkFrame(self.tutor, fg_color="transparent")
        fila_acc.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 0))
        self.botones_acc = []
        for texto, prompt in ACCIONES_RAPIDAS:
            b = boton(fila_acc, texto, lambda p=prompt: self._accion_rapida(p), "suave", height=28, font=fuente(11))
            b.pack(side="left", padx=2, expand=True, fill="x")
            self.botones_acc.append(b)

        entrada = ctk.CTkFrame(self.tutor, fg_color="transparent")
        entrada.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=10)
        entrada.columnconfigure(0, weight=1)
        self.ent_pregunta = ctk.CTkEntry(entrada, placeholder_text="Pregunta algo sobre este libro…", height=38,
                                         fg_color=C["tarjeta"], border_color=C["borde"], corner_radius=10,
                                         placeholder_text_color=C["texto3"])
        self.ent_pregunta.grid(row=0, column=0, sticky="ew")
        self.ent_pregunta.bind("<Return>", lambda e: self.enviar())
        self.btn_enviar = boton(entrada, "➤", self.enviar, width=40, height=38)
        self.btn_enviar.grid(row=0, column=1, padx=(6, 0))

    def _enlazar_eventos(self):
        self.lienzo.bind("<MouseWheel>", self._rueda)
        self.lienzo.bind("<Button-4>", lambda e: self._rueda(e, 1))
        self.lienzo.bind("<Button-5>", lambda e: self._rueda(e, -1))
        self.lienzo.bind("<Configure>", self._al_redimensionar)
        self.lienzo.bind("<Motion>", lambda e: self._actividad())
        self.lienzo.bind("<Enter>", lambda e: self.lienzo.focus_set())
        self.lienzo.bind("<Button-1>", lambda e: (self.lienzo.focus_set(), self._actividad()))
        for tecla, delta in (("<Right>", 1), ("<Next>", 1), ("<Left>", -1), ("<Prior>", -1)):
            self.lienzo.bind(tecla, lambda e, d=delta: self.ir_a(self._pagina + d * self._paso()))
        self.lienzo.bind("<Home>", lambda e: self.ir_a(1))
        self.lienzo.bind("<End>", lambda e: self.ir_a(self._total))
        self.lienzo.bind("<Control-d>", lambda e: self.alternar_oscuro())
        self.lienzo.bind("<Control-plus>", lambda e: self.cambiar_zoom(ZOOM_PASO))
        self.lienzo.bind("<Control-minus>", lambda e: self.cambiar_zoom(-ZOOM_PASO))

    # ================================================================== disposición, vista doble y modo oscuro
    def _crear_divisor(self):
        """Franja arrastrable entre el visor y el tutor: cambia el ancho de la conversación."""
        self.divisor = tk.Frame(self, width=7, bg=C["borde"], cursor="sb_h_double_arrow")
        self.divisor.bind("<B1-Motion>", self._arrastrar_divisor)
        self.divisor.bind("<ButtonRelease-1>", lambda e: db.guardar_config("lector_ancho_tutor", self._ancho_tutor))
        self.divisor.bind("<Enter>", lambda e: self.divisor.configure(bg=C["acento"]))
        self.divisor.bind("<Leave>", lambda e: self.divisor.configure(bg=C["borde"]))

    def _disponer(self):
        """Coloca visor, divisor y tutor según el lado elegido (cada columna con su peso)."""
        for w in (self.marco_visor, self.divisor, self.tutor):
            w.grid_forget()
        for c in range(3):
            self.columnconfigure(c, weight=0, minsize=0)
        if not self._tutor_visible:
            self.columnconfigure(0, weight=1)
            self.marco_visor.grid(row=1, column=0, columnspan=3, sticky="nsew")
            return
        col_visor, col_tutor = (0, 2) if self._lado == "derecha" else (2, 0)
        self.columnconfigure(col_visor, weight=1)
        self.columnconfigure(1, weight=0)
        self.tutor.configure(width=self._ancho_efectivo())
        self.tutor.grid_propagate(False)
        self.marco_visor.grid(row=1, column=col_visor, sticky="nsew")
        self.divisor.grid(row=1, column=1, sticky="ns")
        self.tutor.grid(row=1, column=col_tutor, sticky="nsew")
        self.btn_tutor.configure(fg_color=C["acento_suave"] if self._tutor_visible else C["tarjeta_hover"])

    def _ancho_efectivo(self) -> int:
        """El tutor nunca debe dejar menos de ~380 px al PDF (ventanas estrechas)."""
        total = self._ancho_total()
        if total <= 1:
            return self._ancho_tutor
        return int(max(ANCHO_TUTOR_MIN, min(self._ancho_tutor, total - 380)))

    def _ancho_total(self) -> int:
        """Ancho realmente disponible para el lector (ventana menos barra lateral)."""
        try:
            lateral = self.app.lateral.winfo_width() if self.app.lateral.winfo_ismapped() else 0
            return self.winfo_toplevel().winfo_width() - lateral
        except Exception:
            return self.winfo_width()

    def _al_cambiar_tamano(self, e=None):
        ancho = self._ancho_total()
        self._angosto = ancho < 900
        if self._tutor_visible and self.tutor.winfo_ismapped():
            self.tutor.configure(width=self._ancho_efectivo())
        nivel = 0 if ancho >= 1250 else 1 if ancho >= 1100 else 2 if ancho >= 1000 else 3
        if nivel != getattr(self, "_nivel_barra", None):
            self._nivel_barra = nivel
            self._adaptar_barra(nivel)

    def _adaptar_barra(self, nivel):
        """Simplifica la barra superior cuando hay poco ancho (por ejemplo, media pantalla junto a VS Code)."""
        def mostrar(w, si, **kw):
            if si:
                if not w.winfo_ismapped():
                    w.grid(**kw)
            else:
                w.grid_remove()
        mostrar(self.lbl_titulo, nivel == 0, row=0, column=1, sticky="w")
        mostrar(self.menu_estado, nivel <= 1, row=0, column=4, padx=6)
        mostrar(self.btn_fav, nivel <= 1, row=0, column=5)
        # nivel 3 (≈ media pantalla): se quitan los controles de zoom, pero se conservan ▯▯ y 🌙
        for w in self._zoom_ctrl:
            w.pack_forget()
        if nivel < 3:
            for w in self._zoom_ctrl:
                w.pack(side="left", before=self.btn_dos)
        self.lbl_sesion.configure(width=110 if nivel < 3 else 70)

    def set_modo_compacto(self, activo: bool):
        """Compacto: oculta el tutor (sin cambiar tu preferencia guardada) y lo restaura al salir."""
        if activo:
            self._tutor_previo = self._tutor_visible
            self._tutor_visible = False
        elif self._tutor_previo is not None:
            self._tutor_visible = self._tutor_previo
            self._tutor_previo = None
        self._disponer()
        self.btn_compacto.configure(fg_color=C["acento"] if activo else C["tarjeta_hover"])

    def pintar_encima(self, activo: bool):
        self.btn_encima.configure(fg_color=C["acento"] if activo else C["tarjeta_hover"])

    def cambiar_lado(self):
        self._lado = "izquierda" if self._lado == "derecha" else "derecha"
        db.guardar_config("lector_lado", self._lado)
        if not self._tutor_visible:
            self._tutor_visible = True
        self._disponer()

    def _arrastrar_divisor(self, e):
        total = self.winfo_width()
        if self._lado == "derecha":
            ancho = self.tutor.winfo_rootx() + self.tutor.winfo_width() - e.x_root
        else:
            ancho = e.x_root - self.tutor.winfo_rootx()
        tope = min(ANCHO_TUTOR_MAX, max(ANCHO_TUTOR_MIN, total - 420))
        self._ancho_tutor = int(max(ANCHO_TUTOR_MIN, min(tope, ancho)))
        self.tutor.configure(width=self._ancho_tutor)

    def alternar_dos_paginas(self):
        self._dos = not self._dos
        db.guardar_config("lector_dos_paginas", "1" if self._dos else "0")
        self._pintar_toggles()
        if self._doc is not None:
            self._pagina = self._normalizar(self._pagina)
            self._actividad(forzar=True)
            self._renderizar(scroll="inicio")

    def alternar_oscuro(self):
        self._oscuro = not self._oscuro
        db.guardar_config("lector_oscuro", "1" if self._oscuro else "0")
        self._pintar_toggles()
        if self._doc is not None:
            self._renderizar()

    def _pintar_toggles(self):
        for b, activo in ((self.btn_dos, self._dos), (self.btn_oscuro, self._oscuro)):
            b.configure(fg_color=C["acento_suave"] if activo else "transparent",
                        text_color=C["texto"] if activo else C["texto2"])
        self.lienzo.configure(bg=FONDO_OSCURO if self._oscuro else FONDO_CLARO)

    # ================================================================== abrir / cerrar
    def abrir(self, libro: dict):
        self.cerrar()
        self.libro = libro
        self._gen += 1
        self.lbl_titulo.configure(text=recortar(libro["titulo"], 80))
        self.var_estado.set(libro["estado"])
        self._pintar_favorito()
        self._tutor_permitido = not libro.get("excluido")

        if not os.path.exists(libro["ruta"]):
            self._mensaje_visor("No se encuentra el archivo.\n¿Está en un disco externo? Conéctalo o vuelve a\n"
                                "indexar la biblioteca desde Herramientas.")
            self._preparar_tutor_sin_libro()
            return
        try:
            with PYMUPDF_LOCK:
                self._doc = fitz.open(libro["ruta"])
                self._total = len(self._doc)
        except Exception as e:
            self._mensaje_visor(f"No se pudo abrir este PDF.\n{e}")
            self._preparar_tutor_sin_libro()
            return
        if self._total == 0:
            self._mensaje_visor("Este PDF no tiene páginas.")
            return

        db.marcar_apertura(libro["id"])
        self.app.rastreador.iniciar_contexto(libro["id"], libro.get("materia_id"))
        self.app.rastreador.actividad()

        self.lbl_total.configure(text=f"/ {self._total}")
        inicio = libro["ultima_pagina"] if 0 < libro["ultima_pagina"] <= self._total else 1
        self._zoom = 1.0
        self._pagina = self._normalizar(inicio)
        self.after(60, lambda: self._renderizar(scroll="inicio"))
        self._preparar_tutor()

    def cerrar(self):
        """Libera el PDF, guarda el progreso y detiene el registro de tiempo."""
        if self._guardar_job:
            self.after_cancel(self._guardar_job)
            self._guardar_job = None
        if self.libro is not None and self._doc is not None:
            self._guardar_progreso()
        self.app.rastreador.sin_contexto()
        self._gen += 1
        if self._doc is not None:
            with PYMUPDF_LOCK:
                try:
                    self._doc.close()
                except Exception:
                    pass
        self._doc = None
        self._indice = None
        self._ia_ocupada = False
        self.libro = None

    # ================================================================== visor
    def _mensaje_visor(self, texto):
        if self._id_img:
            self.lienzo.delete(self._id_img)
            self._id_img = None
        w, h = max(self.lienzo.winfo_width(), 400), max(self.lienzo.winfo_height(), 300)
        self.lienzo.coords(self._id_msg, w / 2, h / 2)
        self.lienzo.itemconfigure(self._id_msg, text=texto)
        self.lienzo.configure(scrollregion=(0, 0, w, h))

    def _paso(self) -> int:
        return 2 if self._dos else 1

    def _normalizar(self, pagina: int) -> int:
        """En vista doble las parejas son (1,2), (3,4)…: la página inicial siempre es impar."""
        pagina = max(1, min(self._total, int(pagina)))
        if self._dos:
            pagina -= (pagina - 1) % 2
        return pagina

    def _ultima_visible(self) -> int:
        return min(self._total, self._pagina + (1 if self._dos else 0))

    def _renderizar(self, scroll=None):
        if self._doc is None:
            return
        self.lienzo.itemconfigure(self._id_msg, text="")
        gen, pagina, zoom, dos, oscuro = self._gen, self._pagina, self._zoom, self._dos, self._oscuro
        ancho_disp = max(self.lienzo.winfo_width() - 32, 300)
        self.ent_pagina.delete(0, "end")
        self.ent_pagina.insert(0, str(pagina))
        self.lbl_zoom.configure(text=f"{int(zoom * 100)}%")
        self.lbl_total.configure(text=f"/ {self._total}")

        def trabajo():
            try:
                numeros = [pagina] + ([pagina + 1] if dos and pagina + 1 <= self._total else [])
                ancho_pag = (ancho_disp - (10 if len(numeros) > 1 else 0)) / (2 if dos else 1)
                imgs = []
                with PYMUPDF_LOCK:
                    for n in numeros:
                        pg = self._doc[n - 1]
                        base = ancho_pag / max(pg.rect.width, 1)
                        pix = pg.get_pixmap(matrix=fitz.Matrix(base * zoom, base * zoom), alpha=False)
                        imgs.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
                if len(imgs) == 1:
                    img = imgs[0]
                    if dos:        # última página impar: se deja a la izquierda con su hueco a la derecha
                        lienzo = Image.new("RGB", (img.width * 2 + 10, img.height), (255, 255, 255))
                        lienzo.paste(img, (0, 0))
                        img = lienzo
                else:
                    alto = max(i.height for i in imgs)
                    img = Image.new("RGB", (sum(i.width for i in imgs) + 10, alto), (255, 255, 255))
                    x = 0
                    for i in imgs:
                        img.paste(i, (x, 0))
                        x += i.width + 10
                if oscuro:
                    img = self._a_oscuro(img)
            except Exception as e:
                self.app._en_ui(self._mostrar_error_pagina, gen, str(e))
                return
            self.app._en_ui(self._mostrar_pagina, gen, pagina, img, scroll)
        threading.Thread(target=trabajo, daemon=True).start()

    @staticmethod
    def _a_oscuro(img):
        """Invierte la página y suaviza el contraste (negro puro y blanco puro cansan igual)."""
        inv = ImageOps.invert(img)
        return inv.point(lambda v: 18 + int(v * 0.80))

    def _mostrar_error_pagina(self, gen, error):
        if gen == self._gen:
            self._mensaje_visor(f"No se pudo dibujar la página.\n{error}")

    def _mostrar_pagina(self, gen, pagina, img, scroll):
        if gen != self._gen or pagina != self._pagina:
            return
        self._foto = ImageTk.PhotoImage(img)
        w_lienzo = max(self.lienzo.winfo_width(), img.width + 32)
        x = max(16, (w_lienzo - img.width) // 2)
        if self._id_img:
            self.lienzo.delete(self._id_img)
        self._id_img = self.lienzo.create_image(x, 16, image=self._foto, anchor="nw")
        self.lienzo.configure(scrollregion=(0, 0, w_lienzo, img.height + 32))
        if scroll == "inicio":
            self.lienzo.yview_moveto(0)
        elif scroll == "fin":
            self.lienzo.yview_moveto(1)

    def ir_a(self, pagina, scroll="inicio"):
        if self._doc is None:
            return
        pagina = self._normalizar(pagina)
        self._actividad(forzar=True)
        if pagina == self._pagina:
            return
        self._pagina = pagina
        self._renderizar(scroll=scroll)
        if self._guardar_job:
            self.after_cancel(self._guardar_job)
        self._guardar_job = self.after(900, self._guardar_progreso)

    def _ir_desde_entrada(self, _e=None):
        try:
            self.ir_a(int(self.ent_pagina.get()))
        except ValueError:
            self.ent_pagina.delete(0, "end")
            self.ent_pagina.insert(0, str(self._pagina))
        self.lienzo.focus_set()

    def cambiar_zoom(self, delta):
        if self._doc is None:
            return
        nuevo = round(max(ZOOM_MIN, min(ZOOM_MAX, self._zoom + delta)), 2)
        if nuevo != self._zoom:
            self._zoom = nuevo
            self._actividad(forzar=True)
            self._renderizar()

    def _al_redimensionar(self, e):
        if self._doc is None:
            return
        if self._reajuste_job:
            self.after_cancel(self._reajuste_job)
        self._reajuste_job = self.after(300, self._renderizar)

    def _rueda(self, e, direccion=None):
        if self._doc is None:
            return
        self._actividad()
        if direccion is None:
            direccion = 1 if e.delta > 0 else -1
        estado = getattr(e, "state", 0)
        if estado & 0x4:                       # Ctrl + rueda = zoom
            self.cambiar_zoom(ZOOM_PASO * direccion)
            return
        if estado & 0x1:                       # Shift + rueda = desplazamiento horizontal
            self.lienzo.xview_scroll(-3 * direccion, "units")
            return
        ahora = time.monotonic()
        arriba, abajo = self.lienzo.yview()
        if direccion < 0 and abajo >= 0.999 and ahora - self._ultimo_cambio > 0.4:
            self._ultimo_cambio = ahora
            self.ir_a(self._pagina + self._paso(), "inicio")
        elif direccion > 0 and arriba <= 0.001 and ahora - self._ultimo_cambio > 0.4 and self._pagina > 1:
            self._ultimo_cambio = ahora
            self.ir_a(self._pagina - self._paso(), "fin")
        else:
            self.lienzo.yview_scroll(-3 * direccion, "units")

    # ================================================================== progreso y estado
    def _actividad(self, forzar=False):
        """Avisa al rastreador (con tope de 1 vez por segundo para no gastar CPU en cada movimiento)."""
        ahora = time.monotonic()
        if forzar or ahora - self._ultima_act > 1.0:
            self._ultima_act = ahora
            self.app.rastreador.actividad()

    def _guardar_progreso(self):
        self._guardar_job = None
        if self.libro is None or self._doc is None:
            return
        visible = self._ultima_visible()
        estado = db.guardar_progreso_lectura(self.libro["id"], visible, self._total)
        self.libro["ultima_pagina"], self.libro["total_paginas"], self.libro["estado"] = visible, self._total, estado
        if self.var_estado.get() != estado:
            self.var_estado.set(estado)

    def _cambiar_estado(self, estado):
        if self.libro:
            db.actualizar_estado_libro(self.libro["id"], estado)
            self.libro["estado"] = estado

    def _favorito(self):
        if self.libro:
            self.libro["favorito"] = db.alternar_favorito(self.libro["id"])
            self._pintar_favorito()

    def _pintar_favorito(self):
        fav = bool(self.libro and self.libro.get("favorito"))
        self.btn_fav.configure(text="★" if fav else "☆", text_color=C["aviso"] if fav else C["texto3"])

    def actualizar_indicador(self):
        """Lo llama la app cada segundo: muestra si el tiempo se está contando."""
        r = self.app.rastreador
        if self.libro is None:
            return
        t = tiempo.formatear(r.segundos_sesion)
        if r.activo:
            self.lbl_sesion.configure(text=f"● {t}" if self._angosto else f"● Registrando · {t}", text_color=C["ok"])
        else:
            self.lbl_sesion.configure(text=f"⏸ {t}" if self._angosto else f"⏸ En pausa · {t}", text_color=C["texto3"])

    # ================================================================== tutor IA
    def alternar_tutor(self):
        self._tutor_visible = not self._tutor_visible
        db.guardar_config("lector_tutor_visible", "1" if self._tutor_visible else "0")
        self._disponer()

    def _escribir(self, quien, texto, tag_quien, tag_texto):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{quien}\n", tag_quien)
        self.chat.insert("end", f"{texto}\n", tag_texto)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _limpiar_chat(self):
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")

    def _habilitar_entrada(self, activo: bool):
        estado = "normal" if activo else "disabled"
        self.ent_pregunta.configure(state=estado)
        self.btn_enviar.configure(state=estado)
        for b in self.botones_acc:
            b.configure(state=estado)

    def _preparar_tutor_sin_libro(self):
        self._limpiar_chat()
        self._habilitar_entrada(False)
        self.lbl_ia.configure(text="")
        self.lbl_contexto.configure(text="")

    def _preparar_tutor(self):
        self._limpiar_chat()
        self._indice = None
        if not self._tutor_permitido:
            self._habilitar_entrada(False)
            self.lbl_contexto.configure(text="Este libro está en un área excluida del tutor IA (Herramientas › Ajustes).")
            self._escribir("SISTEMA", "El tutor IA está desactivado para esta área. Puedes leer con normalidad; "
                           "el tiempo de estudio sí se registra.", "quien_s", "s")
            return
        self._habilitar_entrada(True)
        self._historial = db.cargar_historial_chat(self.libro["id"])
        self.lbl_contexto.configure(text="Leyendo el libro para poder responderte…")
        self._leyendo = True
        self._actualizar_etiqueta_ia()
        for m in self._historial:
            if m["emisor"] == "USUARIO":
                self._escribir("TÚ", m["texto"], "quien_u", "u")
            elif m["emisor"] == "IA":
                self._escribir("TUTOR", m["texto"], "quien_ia", "ia")
        if not self._historial:
            self._escribir("TUTOR", "¡Hola! Estoy leyendo el libro. Pregúntame lo que quieras o usa los atajos de abajo: "
                           "trabajan sobre la página que tienes abierta.", "quien_ia", "ia")
        gen, rid, ruta = self._gen, self.libro["id"], self.libro["ruta"]

        def leer():
            indice = IndiceLibro(extraer_fragmentos_pdf(ruta))
            self.app._en_ui(self._indice_listo, gen, indice)
        threading.Thread(target=leer, daemon=True).start()

    def _indice_listo(self, gen, indice):
        if gen != self._gen:
            return
        self._leyendo = False
        self._indice = indice
        self.lbl_contexto.configure(
            text="Listo: respondo con fragmentos del libro y su página." if indice
            else "Sin texto legible (¿PDF escaneado?). Responderé solo con el título como guía.")

    def _actualizar_etiqueta_ia(self):
        self.lbl_ia.configure(text="🟢 IA lista" if self.app.ollama_listo else "🔴 IA desconectada")

    def actualizar_estado_ia(self):
        if self.libro is not None:
            self._actualizar_etiqueta_ia()

    def _texto_pagina(self, n):
        try:
            with PYMUPDF_LOCK:
                return (self._doc[n - 1].get_text("text") or "").strip()
        except Exception:
            return ""

    def _accion_rapida(self, plantilla):
        self._consultar(plantilla.format(n=self._pagina), mostrar=plantilla.format(n=self._pagina), solo_pagina=True)

    def enviar(self):
        pregunta = self.ent_pregunta.get().strip()
        if not pregunta:
            return
        self.ent_pregunta.delete(0, "end")
        self._consultar(pregunta, mostrar=pregunta, solo_pagina=False)

    def _consultar(self, pregunta, mostrar, solo_pagina):
        if self._ia_ocupada or self.libro is None or not self._tutor_permitido:
            return
        if self._leyendo:
            self._escribir("SISTEMA", "Aún estoy leyendo el libro, inténtalo en unos segundos.", "quien_s", "s")
            return
        self._actividad(forzar=True)
        rid, nombre, pagina = self.libro["id"], self.libro["titulo"], self._pagina
        historial_previo = list(self._historial)
        if solo_pagina:
            texto = self._texto_pagina(pagina)
            contexto = f"[Página {pagina}]\n{texto[:6500]}" if texto else ""
        else:
            contexto = self._indice.contexto_para(pregunta) if self._indice else ""
            pregunta_modelo = f"(Estoy leyendo la página {pagina}.) {pregunta}"
        pregunta_modelo = pregunta if solo_pagina else pregunta_modelo

        self._historial.append({"emisor": "USUARIO", "texto": mostrar})
        self._escribir("TÚ", mostrar, "quien_u", "u")
        self._ia_ocupada = True
        self._habilitar_entrada(False)
        self.lbl_contexto.configure(text="⏳ El tutor está pensando…")
        gen = self._gen

        def trabajo():
            try:
                r = consultar_ollama_con_contexto(pregunta_modelo, contexto_pdf=contexto, nombre_pdf=nombre,
                                                  historial=historial_previo)
                self.app._en_ui(self._respuesta, gen, rid, r, None)
            except ErrorOllama as e:
                self.app._en_ui(self._respuesta, gen, rid, None, str(e))
            except Exception as e:
                self.app._en_ui(self._respuesta, gen, rid, None, f"Error inesperado: {e}")
        threading.Thread(target=trabajo, daemon=True).start()

    def _respuesta(self, gen, rid, respuesta, error):
        if error:
            # Los errores no se guardan como si fueran respuestas del tutor.
            if gen == self._gen:
                if self._historial and self._historial[-1]["emisor"] == "USUARIO":
                    self._historial.pop()
                self._escribir("ERROR", error, "quien_s", "e")
        else:
            if gen == self._gen:
                self._historial.append({"emisor": "IA", "texto": respuesta})
                self._escribir("TUTOR", respuesta, "quien_ia", "ia")
                db.guardar_historial_chat(rid, self._historial[-MAX_HISTORIAL_GUARDADO:])
            else:      # el usuario cambió de libro: se guarda en el suyo
                h = db.cargar_historial_chat(rid)
                h.append({"emisor": "IA", "texto": respuesta})
                db.guardar_historial_chat(rid, h[-MAX_HISTORIAL_GUARDADO:])
        if gen == self._gen:
            self._ia_ocupada = False
            self._habilitar_entrada(True)
            self.lbl_contexto.configure(text="Listo.")
            self._actividad(forzar=True)
