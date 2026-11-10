"""Panel de capítulos del lector: modo de lectura del libro, qué capítulos cuentan y cuáles ya están hechos."""
import customtkinter as ctk

import capitulos as cap
from tema import texto_sobre, C, fuente, titulo, subtitulo, boton

ETIQUETA_MODO = {"auto": "Automático", "completo": "Completo", "capitulos": "Por capítulos"}
VALOR_MODO = {v: k for k, v in ETIQUETA_MODO.items()}


class PanelCapitulos(ctk.CTkFrame):
    def __init__(self, padre, lector, ancho):
        super().__init__(padre, fg_color=C["lateral"], corner_radius=0, width=ancho)
        self.lector = lector
        self.grid_propagate(False)
        self.rowconfigure(4, weight=1)
        self.columnconfigure(0, weight=1)

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        titulo(cab, "Capítulos", 16).pack(side="left")
        self.lbl_cuenta = ctk.CTkLabel(cab, text="", font=fuente(11), text_color=C["texto3"])
        self.lbl_cuenta.pack(side="right")

        self.seg = ctk.CTkSegmentedButton(self, values=list(ETIQUETA_MODO.values()), command=self._elegir_modo,
                                          height=28, font=fuente(11), selected_color=C["acento"],
                                          selected_hover_color=C["acento_hover"], unselected_color=C["tarjeta"])
        self.seg.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 4))
        self.lbl_modo = subtitulo(self, "", 11)
        self.lbl_modo.configure(wraplength=300, justify="left")
        self.lbl_modo.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 4))

        self.barra_herr = ctk.CTkFrame(self, fg_color="transparent")
        self.barra_herr.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))
        boton(self.barra_herr, "Todos cuentan", lambda: self.lector.marcar_todos_incluidos(True), "fantasma",
              height=24, font=fuente(11), width=100).pack(side="left")
        boton(self.barra_herr, "Ninguno", lambda: self.lector.marcar_todos_incluidos(False), "fantasma",
              height=24, font=fuente(11), width=70).pack(side="left")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista.grid(row=4, column=0, sticky="nsew", padx=(6, 2), pady=(0, 10))

    def _elegir_modo(self, etiqueta):
        self.lector.cambiar_modo(VALOR_MODO[etiqueta])

    def refrescar(self):
        libro = self.lector.libro
        for w in self.lista.winfo_children():
            w.destroy()
        if libro is None:
            return
        caps = self.lector.capitulos()
        self.seg.set(ETIQUETA_MODO.get(libro.get("modo_lectura", "auto"), "Automático"))
        efectivo = libro.get("modo_efectivo", "completo")
        nombre = "por capítulos" if efectivo == "capitulos" else "completo"
        self.lbl_modo.configure(text=f"Se mide {nombre}: {libro.get('modo_motivo', '')}.")
        hechos, total = libro.get("caps_hechos", 0), libro.get("caps_total", 0)
        self.lbl_cuenta.configure(text=f"{hechos}/{total} hechos" if caps else "")
        if not caps:
            ctk.CTkLabel(self.lista, text="Este PDF no trae un índice interno, así que se lee completo\n"
                                          "y el avance se mide por páginas.", font=fuente(12),
                         text_color=C["texto3"], justify="center", wraplength=280).pack(pady=30)
            self.barra_herr.grid_remove()
            return
        self.barra_herr.grid()
        pag_ini, pag_fin = self.lector.paginas_visibles()
        for c in caps:
            self._fila(c, c["pagina_ini"] <= pag_fin and c["pagina_fin"] >= pag_ini)

    def _fila(self, c, actual):
        f = ctk.CTkFrame(self.lista, fg_color=C["acento_suave"] if actual else C["tarjeta"], corner_radius=8)
        f.pack(fill="x", pady=2, padx=2)
        f.columnconfigure(1, weight=1)
        cuenta = bool(c["incluido"])
        caja = ctk.CTkCheckBox(f, text="", width=22, checkbox_width=18, checkbox_height=18, corner_radius=5,
                               fg_color=C["acento"], hover_color=C["acento_hover"], border_color=C["borde"],
                               command=lambda i=c["id"], v=cuenta: self.lector.marcar_incluido(i, not v))
        caja.grid(row=0, column=0, padx=(8, 0), pady=6)
        (caja.select if cuenta else caja.deselect)()
        nombre = ctk.CTkLabel(f, text=c["titulo"], anchor="w", justify="left", wraplength=190, font=fuente(12),
                              text_color=C["texto"] if cuenta else C["texto3"], cursor="hand2")
        nombre.grid(row=0, column=1, sticky="w", padx=6, pady=(5, 0))
        nombre.bind("<Button-1>", lambda e, p=c["pagina_ini"]: self.lector.ir_a(p))
        paginas = f"p. {c['pagina_ini']}" if c["pagina_ini"] == c["pagina_fin"] else f"p. {c['pagina_ini']}–{c['pagina_fin']}"
        ctk.CTkLabel(f, text=paginas + ("" if cuenta else "  ·  no cuenta"), anchor="w", font=fuente(10),
                     text_color=C["texto3"]).grid(row=1, column=1, sticky="w", padx=6, pady=(0, 5))
        hecho = bool(c["hecho"])
        ctk.CTkButton(f, text="✓" if hecho else "○", width=30, height=28, corner_radius=14,
                      fg_color=C["ok"] if hecho else "transparent", hover_color=C["borde"],
                      text_color=texto_sobre(C["ok"]) if hecho else C["texto2"], font=fuente(14, "bold"),
                      state="normal" if cuenta else "disabled",
                      command=lambda i=c["id"], v=hecho: self.lector.marcar_hecho(i, not v)
                      ).grid(row=0, column=2, rowspan=2, padx=8)
