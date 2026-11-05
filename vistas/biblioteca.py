"""Biblioteca: cuadrícula de portadas con búsqueda, filtros por área/estado y orden."""
import customtkinter as ctk

import database as db
from tema import C, ESTADO_COLOR, ESTADO_ICONO, fuente, tarjeta, titulo, subtitulo, boton, barra, chip, estado_vacio, recortar, nombre_area

TAM_PORTADA = (96, 132)
ANCHO_TARJETA = 168
LOTE = 36
TODAS = "Todas las áreas"
ESTADOS_FILTRO = ["Todos", "Sin empezar", "En progreso", "Completado", "★ Favoritos"]
ORDENES = ["Título", "Recientes", "Más avanzados"]


def enlazar_clic(widget, fn):
    """Hace clicable a un widget y a todos sus hijos (los CTk no propagan el clic)."""
    if isinstance(widget, ctk.CTkButton):
        return                      # los botones tienen su propio comando
    widget.bind("<Button-1>", lambda e: fn(), add="+")
    for h in widget.winfo_children():
        enlazar_clic(h, fn)


class VistaBiblioteca(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self._libros = []
        self._filtrados = []
        self._mostrados = 0
        self._cols = 0
        self._job = None
        self._gen = 0

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=28, pady=(24, 8))
        titulo(cab, "Biblioteca", 26).pack(side="left")
        self.lbl_total = subtitulo(cab, "")
        self.lbl_total.pack(side="left", padx=14, pady=(8, 0))

        barra_f = ctk.CTkFrame(self, fg_color="transparent")
        barra_f.pack(fill="x", padx=28, pady=(0, 10))
        self.var_busqueda = ctk.StringVar()
        self.var_busqueda.trace_add("write", lambda *_: self._programar())
        ctk.CTkEntry(barra_f, textvariable=self.var_busqueda, placeholder_text="🔍  Buscar por título…", width=280,
                     height=36, corner_radius=10, fg_color=C["tarjeta"], border_color=C["borde"],
                     placeholder_text_color=C["texto3"]).pack(side="left")
        self.var_area = ctk.StringVar(value=TODAS)
        self.menu_area = ctk.CTkOptionMenu(barra_f, variable=self.var_area, values=[TODAS], width=230, height=36,
                                           fg_color=C["tarjeta"], button_color=C["tarjeta_hover"],
                                           button_hover_color=C["borde"], command=lambda _: self._aplicar())
        self.menu_area.pack(side="left", padx=8)
        self.var_orden = ctk.StringVar(value=ORDENES[0])
        ctk.CTkOptionMenu(barra_f, variable=self.var_orden, values=ORDENES, width=140, height=36,
                          fg_color=C["tarjeta"], button_color=C["tarjeta_hover"], button_hover_color=C["borde"],
                          command=lambda _: self._aplicar()).pack(side="left")

        self.seg = ctk.CTkSegmentedButton(self, values=ESTADOS_FILTRO, command=lambda _: self._aplicar(),
                                          fg_color=C["tarjeta"], selected_color=C["acento"],
                                          unselected_color=C["tarjeta"], selected_hover_color=C["acento_hover"],
                                          unselected_hover_color=C["tarjeta_hover"], height=32)
        self.seg.set("Todos")
        self.seg.pack(anchor="w", padx=28, pady=(0, 10))

        self.zona = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.zona.pack(fill="both", expand=True, padx=(22, 14), pady=(0, 10))
        self._ancho_previo = 0
        self.bind("<Configure>", self._al_redimensionar)

    # ------------------------------------------------------------------ datos
    def al_mostrar(self, area=None):
        self._libros = db.listar_libros()
        areas = sorted({l["area"] for l in self._libros if l["area"]})
        self.menu_area.configure(values=[TODAS] + [f"{a}" for a in areas])
        self._areas = {a: a for a in areas}
        if area:
            self.var_area.set(area)
        elif self.var_area.get() not in [TODAS] + areas:
            self.var_area.set(TODAS)
        self._aplicar()

    def _programar(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(220, self._aplicar)

    def _aplicar(self):
        self._job = None
        q = self.var_busqueda.get().strip().casefold()
        area, estado, orden = self.var_area.get(), self.seg.get(), self.var_orden.get()
        res = []
        for l in self._libros:
            if area != TODAS and l["area"] != area:
                continue
            if estado == "★ Favoritos":
                if not l["favorito"]:
                    continue
            elif estado != "Todos" and l["estado"] != estado:
                continue
            if q and q not in l["titulo"].casefold():
                continue
            res.append(l)
        if orden == "Recientes":
            res.sort(key=lambda l: l["ultima_apertura"] or "", reverse=True)
        elif orden == "Más avanzados":
            res.sort(key=lambda l: (-l["avance"], l["titulo"].casefold()))
        else:
            res.sort(key=lambda l: l["titulo"].casefold())
        self._filtrados = res
        self.lbl_total.configure(text=f"{len(res)} de {len(self._libros)} libros")
        self._dibujar_desde_cero()

    # ------------------------------------------------------------------ dibujo
    def _columnas(self):
        ancho = max(self.zona.winfo_width(), self.winfo_width() - 60, ANCHO_TARJETA)
        return max(1, ancho // (ANCHO_TARJETA + 12))

    def _al_redimensionar(self, e):
        if abs(e.width - self._ancho_previo) < 40:
            return
        self._ancho_previo = e.width
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(250, lambda: self._dibujar_desde_cero() if self._columnas() != self._cols else None)

    def _dibujar_desde_cero(self):
        self._gen += 1
        for w in self.zona.winfo_children():
            w.destroy()
        self._cols = self._columnas()
        self._mostrados = 0
        if not self._filtrados:
            estado_vacio(self.zona, "🔎", "Nada por aquí",
                         "No hay libros con esos filtros." if self._libros else
                         "Todavía no hay libros indexados. Ve a Herramientas y elige tu carpeta de biblioteca.",
                         None if self._libros else "Ir a Herramientas",
                         None if self._libros else (lambda: self.app.ir("herramientas", pestaña="Biblioteca"))
                         ).grid(row=0, column=0, columnspan=8, pady=30)
            return
        self._mas()

    def _mas(self):
        gen = self._gen
        if hasattr(self, "_btn_mas") and self._btn_mas is not None:
            try:
                self._btn_mas.destroy()
            except Exception:
                pass
            self._btn_mas = None
        fin = min(len(self._filtrados), self._mostrados + LOTE)
        for i in range(self._mostrados, fin):
            fila, col = divmod(i, self._cols)
            t = self._tarjeta(self._filtrados[i])
            t.grid(row=fila, column=col, padx=6, pady=6, sticky="n")
        self._mostrados = fin
        if fin < len(self._filtrados):
            fila = (fin - 1) // self._cols + 1
            self._btn_mas = boton(self.zona, f"Mostrar más ({len(self._filtrados) - fin} restantes)", self._mas, "suave")
            self._btn_mas.grid(row=fila, column=0, columnspan=self._cols, pady=14)

    def _tarjeta(self, libro):
        t = ctk.CTkFrame(self.zona, width=ANCHO_TARJETA, height=290, fg_color=C["tarjeta"], corner_radius=14,
                         border_width=1, border_color=C["borde"])
        t.grid_propagate(False)
        t.columnconfigure(0, weight=1)
        portada = ctk.CTkLabel(t, text="📕", font=fuente(34), width=TAM_PORTADA[0], height=TAM_PORTADA[1],
                               fg_color=C["pista"], corner_radius=8)
        portada.grid(row=0, column=0, pady=(12, 8))
        self.app.portadas.pedir(libro["ruta"], lambda img, w=portada: img and w.configure(image=img, text="", fg_color="transparent"))
        ctk.CTkLabel(t, text=recortar(libro["titulo"], 48), font=fuente(12, "bold"), text_color=C["texto"],
                     wraplength=ANCHO_TARJETA - 24, justify="left", anchor="nw", height=48
                     ).grid(row=1, column=0, sticky="ew", padx=12)
        extra = nombre_area(libro["subcarpeta"] or libro["area"])
        ctk.CTkLabel(t, text=("🔒 " if libro["excluido"] else "") + recortar(extra, 22), font=fuente(10),
                     text_color=C["texto3"], anchor="w").grid(row=2, column=0, sticky="w", padx=12)
        barra(t, libro["avance"], ESTADO_COLOR[libro["estado"]], alto=5).grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 2))
        pie = ctk.CTkFrame(t, fg_color="transparent")
        pie.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 8))
        ctk.CTkLabel(pie, text=f"{ESTADO_ICONO[libro['estado']]} {libro['estado']}", font=fuente(10),
                     text_color=ESTADO_COLOR[libro["estado"]]).pack(side="left", padx=2)
        estrella = ctk.CTkButton(pie, text="★" if libro["favorito"] else "☆", width=26, height=22, fg_color="transparent",
                                 hover_color=C["tarjeta_hover"], font=fuente(15),
                                 text_color=C["aviso"] if libro["favorito"] else C["texto3"])
        estrella.configure(command=lambda l=libro, b=estrella: self._favorito(l, b))
        estrella.pack(side="right")

        enlazar_clic(t, lambda l=libro: self.app.abrir_libro(l["id"]))
        t.bind("<Enter>", lambda e, t=t: t.configure(border_color=C["acento"]))
        t.bind("<Leave>", lambda e, t=t: t.configure(border_color=C["borde"]))
        return t

    def _favorito(self, libro, boton_estrella):
        libro["favorito"] = db.alternar_favorito(libro["id"])
        boton_estrella.configure(text="★" if libro["favorito"] else "☆",
                                 text_color=C["aviso"] if libro["favorito"] else C["texto3"])
        if self.seg.get() == "★ Favoritos" and not libro["favorito"]:
            self._aplicar()
