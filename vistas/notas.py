"""Panel de notas y subrayados del lector, y el pequeño diálogo para escribir texto."""
import tkinter as tk

import customtkinter as ctk

import database as db
from tema import C, fuente, titulo, subtitulo, boton

MAX_TARJETAS = 150
COLOR_TIPO = {"nota": "📝", "subrayado": "🖍", "sesion": "🏁"}


class DialogoTexto(ctk.CTkToplevel):
    """Ventana pequeña con un cuadro de texto: sirve para editar una nota o para la nota rápida al cerrar."""

    def __init__(self, padre, titulo_txt, mensaje, inicial="", al_guardar=None, al_omitir=None,
                 texto_guardar="Guardar", texto_omitir="Omitir"):
        super().__init__(padre)
        self.title(titulo_txt)
        self.configure(fg_color=C["fondo"])
        self.geometry("460x300")
        self.resizable(True, True)
        self.minsize(340, 240)
        self._al_guardar, self._al_omitir, self._hecho = al_guardar, al_omitir, False
        try:
            self.transient(padre.winfo_toplevel())
        except tk.TclError:
            pass
        ctk.CTkLabel(self, text=mensaje, font=fuente(13), text_color=C["texto"], wraplength=420,
                     justify="left", anchor="w").pack(fill="x", padx=18, pady=(16, 8))
        self.caja = ctk.CTkTextbox(self, fg_color=C["tarjeta"], border_color=C["borde"], border_width=1,
                                   text_color=C["texto"], font=fuente(13), wrap="word")
        self.caja.pack(fill="both", expand=True, padx=18)
        if inicial:
            self.caja.insert("1.0", inicial)
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=18, pady=14)
        boton(fila, texto_guardar, self._guardar, width=110).pack(side="right")
        boton(fila, texto_omitir, self._omitir, "suave", width=90).pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self._omitir)
        self.bind("<Escape>", lambda e: self._omitir())
        self.bind("<Control-Return>", lambda e: self._guardar())
        self.after(150, self._enfocar)

    def _enfocar(self):
        try:
            self.lift()
            self.grab_set()
            self.caja.focus_set()
        except tk.TclError:
            pass

    def _cerrar(self):
        self._hecho = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _guardar(self):
        if self._hecho:
            return
        texto = self.caja.get("1.0", "end").strip()
        self._cerrar()
        if self._al_guardar:
            self._al_guardar(texto)

    def _omitir(self):
        if self._hecho:
            return
        self._cerrar()
        if self._al_omitir:
            self._al_omitir()


class PanelNotas(ctk.CTkFrame):
    """Lista de notas del libro abierto. Toda la lógica de datos vive en el lector (self.lector)."""

    def __init__(self, padre, lector, ancho):
        super().__init__(padre, fg_color=C["lateral"], corner_radius=0, width=ancho)
        self.lector = lector
        self.grid_propagate(False)
        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)
        self._solo_pagina = True

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        titulo(cab, "Notas", 16).pack(side="left")
        self.lbl_cuenta = ctk.CTkLabel(cab, text="", font=fuente(11), text_color=C["texto3"])
        self.lbl_cuenta.pack(side="right")

        herr = ctk.CTkFrame(self, fg_color="transparent")
        herr.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 6))
        self.btn_sub = boton(herr, "🖍 Subrayar", self.lector.alternar_subrayado, "suave", height=30, font=fuente(12))
        self.btn_sub.pack(side="left", padx=(0, 6))
        self.btn_exp = boton(herr, "⬇ Exportar", self._menu_exportar, "suave", height=30, font=fuente(12))
        self.btn_exp.pack(side="left")
        filtro = ctk.CTkFrame(self, fg_color="transparent")
        filtro.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.seg = ctk.CTkSegmentedButton(filtro, values=["Esta página", "Todas"], command=self._cambiar_filtro,
                                          height=28, font=fuente(11), selected_color=C["acento"],
                                          selected_hover_color=C["acento_hover"], unselected_color=C["tarjeta"])
        self.seg.set("Esta página")
        self.seg.pack(fill="x")
        self.lbl_ayuda = subtitulo(filtro, "", 11)
        self.lbl_ayuda.configure(wraplength=300, justify="left")
        self.lbl_ayuda.pack(fill="x", pady=(4, 0))

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista.grid(row=3, column=0, sticky="nsew", padx=(6, 2))

        pie = ctk.CTkFrame(self, fg_color="transparent")
        pie.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 4))
        pie.columnconfigure(0, weight=1)
        self.caja = ctk.CTkTextbox(pie, height=64, fg_color=C["tarjeta"], border_color=C["borde"], border_width=1,
                                   text_color=C["texto"], font=fuente(12), wrap="word")
        self.caja.grid(row=0, column=0, sticky="ew")
        self.caja.bind("<Control-Return>", lambda e: (self._anadir(), "break")[1])
        self.btn_add = boton(pie, "＋ Nota", self._anadir, height=64, width=70)
        self.btn_add.grid(row=0, column=1, padx=(6, 0))
        self.var_cierre = ctk.BooleanVar(value=db.obtener_config("nota_al_cerrar", "1") == "1")
        ctk.CTkSwitch(self, text="Pedir una nota rápida al salir", variable=self.var_cierre, font=fuente(11),
                      text_color=C["texto2"], progress_color=C["acento"],
                      command=lambda: db.guardar_config("nota_al_cerrar", "1" if self.var_cierre.get() else "0")
                      ).grid(row=5, column=0, sticky="w", padx=16, pady=(2, 12))

    # ------------------------------------------------------------------ acciones
    def _cambiar_filtro(self, valor):
        self._solo_pagina = valor == "Esta página"
        self.refrescar()

    def _anadir(self):
        texto = self.caja.get("1.0", "end").strip()
        if not texto:
            return
        self.caja.delete("1.0", "end")
        self.lector.agregar_nota(texto)

    def _menu_exportar(self):
        m = tk.Menu(self, tearoff=0, bg=C["tarjeta"], fg=C["texto"], activebackground=C["acento"], bd=0)
        m.add_command(label="Notas de este libro (.md)", command=lambda: self.lector.exportar(False))
        m.add_command(label="Notas de toda la biblioteca (.md)", command=lambda: self.lector.exportar(True))
        x = self.btn_exp.winfo_rootx()
        y = self.btn_exp.winfo_rooty() + self.btn_exp.winfo_height()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def pintar_subrayado(self, activo: bool):
        self.btn_sub.configure(fg_color=C["acento"] if activo else C["tarjeta_hover"],
                               text="🖍 Subrayando…" if activo else "🖍 Subrayar")
        self.lbl_ayuda.configure(
            text="Arrastra sobre la página para marcar una zona. Clic derecho sobre ella para quitarla."
            if activo else "")

    # ------------------------------------------------------------------ pintado
    def refrescar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        notas = self.lector.notas()
        pag_ini, pag_fin = self.lector.paginas_visibles()
        visibles = [n for n in notas if not self._solo_pagina or pag_ini <= n["pagina"] <= pag_fin]
        total = len(notas)
        self.lbl_cuenta.configure(text=f"{total} en el libro" if total else "")
        if not visibles:
            ctk.CTkLabel(self.lista, text=("Sin notas en esta página." if self._solo_pagina and total
                                           else "Todavía no hay notas.\nEscribe una abajo o subraya en la página."),
                         font=fuente(12), text_color=C["texto3"], justify="center").pack(pady=30)
            return
        ancho = max(120, self.winfo_width() - 90)
        for n in visibles[:MAX_TARJETAS]:
            self._tarjeta(n, ancho)
        if len(visibles) > MAX_TARJETAS:
            ctk.CTkLabel(self.lista, text=f"… y {len(visibles) - MAX_TARJETAS} más (se incluyen al exportar)",
                         font=fuente(11), text_color=C["texto3"]).pack(pady=8)

    def _tarjeta(self, n, ancho):
        t = ctk.CTkFrame(self.lista, fg_color=C["tarjeta"], corner_radius=10)
        t.pack(fill="x", pady=3, padx=2)
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(fill="x", padx=8, pady=(6, 0))
        rgb = db.COLORES_SUBRAYADO.get(n.get("color"), (255, 214, 10))
        color = "#%02x%02x%02x" % rgb
        ctk.CTkLabel(fila, text=f"{COLOR_TIPO.get(n['tipo'], '📝')}  p. {n['pagina']}", font=fuente(11, "bold"),
                     text_color=color if n["tipo"] == "subrayado" else C["texto2"]).pack(side="left")
        for simbolo, cmd in (("🗑", lambda i=n["id"]: self.lector.borrar_nota(i)),
                             ("✎", lambda i=n["id"]: self.lector.editar_nota(i)),
                             ("↗", lambda p=n["pagina"]: self.lector.ir_a(p))):
            ctk.CTkButton(fila, text=simbolo, width=26, height=22, fg_color="transparent", hover_color=C["borde"],
                          text_color=C["texto2"], font=fuente(12), command=cmd).pack(side="right")
        texto = (n["texto"] or "").strip() or ("(zona subrayada)" if n["tipo"] == "subrayado" else "(vacía)")
        lbl = ctk.CTkLabel(t, text=texto if len(texto) < 600 else texto[:600] + "…", font=fuente(12),
                           text_color=C["texto"] if n["tipo"] != "subrayado" else C["texto2"],
                           wraplength=ancho, justify="left", anchor="w")
        lbl.pack(fill="x", padx=10, pady=(2, 8))
        lbl.bind("<Button-1>", lambda e, p=n["pagina"]: self.lector.ir_a(p))
