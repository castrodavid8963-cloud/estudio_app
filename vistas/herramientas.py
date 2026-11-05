"""Herramientas: elegir/indexar la biblioteca, organizar y renombrar PDFs (gestor) y ajustes."""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

import database as db
import gestor_biblioteca as gb
import tiempo
from library_scanner import escanear_e_indexar_biblioteca, EXCLUIDAS_POR_DEFECTO
from ai_pdf import MODELO_POR_DEFECTO
from tema import C, fuente, tarjeta, titulo, subtitulo, boton, barra, chip, recortar, nombre_area

MODOS = ["Organizar", "Renombrar", "Ambas", "Reporte", "Deshacer"]
AYUDA_MODO = {
    "Organizar": "Mueve cada PDF a la carpeta temática que le corresponde (por nombre y, si hace falta, por contenido).",
    "Renombrar": "Pone nombres legibles a los PDF con nombres malos (hashes, 'documento1', etc.) usando metadatos o la portada.",
    "Ambas": "Organiza y renombra en un solo paso. Los renombres basados en la portada (poco fiables) se omiten aquí: hazlos con «Renombrar».",
    "Reporte": "Genera un TXT con el mapa de carpetas y archivos de tu biblioteca. No modifica nada.",
    "Deshacer": "Revierte un lote de cambios aplicado antes (cada lote guarda su historial).",
}
COLOR_CONF = {"baja": C["aviso"], "sin_evidencia": C["error"]}      # alta/media: color normal


class VistaHerramientas(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self._indexando = False
        self._trabajando = False
        self._plan = None
        self._cancelar = threading.Event()
        self._filas = {}                   # iid del treeview -> Cambio
        self._historiales = {}

        titulo(self, "Herramientas", 26).pack(anchor="w", padx=28, pady=(24, 8))
        self.tabs = ctk.CTkTabview(self, fg_color=C["panel"], segmented_button_selected_color=C["acento"],
                                   segmented_button_unselected_color=C["tarjeta"],
                                   segmented_button_selected_hover_color=C["acento_hover"],
                                   segmented_button_unselected_hover_color=C["tarjeta_hover"], corner_radius=14)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        for nombre in ("Biblioteca", "Organizar PDFs", "Ajustes"):
            self.tabs.add(nombre)
        self._tab_biblioteca(self.tabs.tab("Biblioteca"))
        self._tab_gestor(self.tabs.tab("Organizar PDFs"))
        self._tab_ajustes(self.tabs.tab("Ajustes"))

    def al_mostrar(self, pestaña=None):
        if pestaña:
            self.tabs.set("Organizar PDFs" if pestaña.startswith("Organizar") else pestaña)
        self._refrescar_resumen()
        self._refrescar_ajustes()

    # ================================================================== carpeta raíz compartida
    def _raiz(self) -> str:
        return db.obtener_ruta_biblioteca()

    def _elegir_carpeta(self):
        inicial = self._raiz() or os.path.expanduser("~")
        ruta = filedialog.askdirectory(title="Elige la carpeta raíz de tu biblioteca", initialdir=inicial)
        if ruta:
            self._fijar_raiz(ruta)

    def _fijar_raiz(self, ruta):
        db.guardar_config("ruta_biblioteca", ruta)
        self._plan = None
        self._limpiar_plan()
        self._refrescar_resumen()

    # ================================================================== pestaña Biblioteca
    def _tab_biblioteca(self, tab):
        tab.columnconfigure(0, weight=1)
        t = tarjeta(tab)
        t.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        t.columnconfigure(0, weight=1)
        titulo(t, "Carpeta raíz de la biblioteca", 15).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 0))
        self.lbl_raiz = subtitulo(t, "", 13, wraplength=620)
        self.lbl_raiz.grid(row=1, column=0, sticky="w", padx=18, pady=(2, 8))
        botones = ctk.CTkFrame(t, fg_color="transparent")
        botones.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 6))
        boton(botones, "📁  Elegir carpeta…", self._elegir_carpeta, "suave").pack(side="left", padx=4)
        self.btn_indexar = boton(botones, "🔄  Indexar ahora", self.indexar)
        self.btn_indexar.pack(side="left", padx=4)
        self.barra_idx = ctk.CTkProgressBar(t, mode="indeterminate", height=6, progress_color=C["acento"], fg_color=C["pista"])
        self.lbl_idx = subtitulo(t, "", 12)
        self.lbl_idx.grid(row=4, column=0, sticky="w", padx=18, pady=(4, 14))

        self.tarjeta_resumen = tarjeta(tab)
        self.tarjeta_resumen.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        titulo(self.tarjeta_resumen, "Qué hay indexado", 15).pack(anchor="w", padx=18, pady=(16, 6))
        self.lbl_resumen = subtitulo(self.tarjeta_resumen, "", 13)
        self.lbl_resumen.pack(anchor="w", padx=18, pady=(0, 16))
        nota = subtitulo(tab, "Indexar no mueve ni borra archivos: solo registra los PDF, genera portadas y detecta los que "
                              "cambiaron de lugar. Lo que deja de existir se marca como no disponible (se conserva tu progreso).",
                         12, wraplength=700, text_color=C["texto3"])
        nota.grid(row=2, column=0, sticky="w", padx=14)

    def _refrescar_resumen(self):
        raiz = self._raiz()
        self.lbl_raiz.configure(text=raiz or "Aún no has elegido una carpeta.")
        self.lbl_raiz_g.configure(text=raiz or "(sin elegir)")
        libros = db.listar_libros(solo_disponibles=False)
        if not libros:
            self.lbl_resumen.configure(text="Todavía no hay libros. Elige tu carpeta y pulsa «Indexar ahora».")
            return
        todos = db.listar_libros()
        excl = sum(1 for l in todos if l["excluido"])
        no_disp = len(libros) - len(todos)
        self.lbl_resumen.configure(
            text=f"{len(todos)} libros disponibles · {len(todos) - excl} en rutas y tutor IA · {excl} en áreas excluidas"
                 + (f" · {no_disp} no disponibles (archivo movido o disco desconectado)" if no_disp else ""))

    def indexar(self, al_terminar=None):
        raiz = self._raiz()
        if self._indexando:
            return
        if not raiz or not os.path.isdir(raiz):
            messagebox.showinfo("Biblioteca", "Primero elige una carpeta raíz válida.")
            return
        self._indexando = True
        self.btn_indexar.configure(state="disabled")
        self.barra_idx.grid(row=3, column=0, sticky="ew", padx=18)
        self.barra_idx.start()
        self.lbl_idx.configure(text="Indexando… (la primera vez puede tardar)")

        def trabajo():
            try:
                r = escanear_e_indexar_biblioteca(
                    raiz, progreso_cb=lambda n: self.app._en_ui(self.lbl_idx.configure, text=f"Revisados {n} archivos…"),
                    excluir=EXCLUIDAS_POR_DEFECTO)
                self.app._en_ui(self._indexado, r, None, al_terminar)
            except Exception as e:
                self.app._en_ui(self._indexado, None, str(e), al_terminar)
        threading.Thread(target=trabajo, daemon=True).start()

    def _indexado(self, r, error, al_terminar):
        self._indexando = False
        self.barra_idx.stop()
        self.barra_idx.grid_remove()
        self.btn_indexar.configure(state="normal")
        if error:
            self.lbl_idx.configure(text=f"⚠️ {error}", text_color=C["error"])
        else:
            nuevos, reub, nd = r
            self.lbl_idx.configure(text=f"✓ Listo: {nuevos} nuevos · {reub} reubicados · {nd} no disponibles",
                                   text_color=C["ok"])
        self._refrescar_resumen()
        if al_terminar:
            al_terminar()

    # ================================================================== pestaña Organizar PDFs
    def _tab_gestor(self, tab):
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)
        cab = tarjeta(tab)
        cab.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        cab.columnconfigure(1, weight=1)
        ctk.CTkLabel(cab, text="Carpeta raíz:", font=fuente(12), text_color=C["texto2"]).grid(row=0, column=0, padx=(16, 6), pady=(12, 0))
        self.lbl_raiz_g = ctk.CTkLabel(cab, text="", font=fuente(12, "bold"), text_color=C["texto"], anchor="w")
        self.lbl_raiz_g.grid(row=0, column=1, sticky="w", pady=(12, 0))
        boton(cab, "Cambiar…", self._elegir_carpeta, "suave", width=90, height=28).grid(row=0, column=2, padx=12, pady=(12, 0))

        self.var_modo = ctk.StringVar(value="Organizar")
        ctk.CTkSegmentedButton(cab, values=MODOS, variable=self.var_modo, command=self._cambio_modo,
                               fg_color=C["panel"], selected_color=C["acento"], selected_hover_color=C["acento_hover"],
                               unselected_color=C["panel"], unselected_hover_color=C["tarjeta_hover"]
                               ).grid(row=1, column=0, columnspan=3, sticky="w", padx=16, pady=(10, 4))
        self.lbl_ayuda = subtitulo(cab, AYUDA_MODO["Organizar"], 12, wraplength=760)
        self.lbl_ayuda.grid(row=2, column=0, columnspan=3, sticky="w", padx=16)

        self.fila_opc = ctk.CTkFrame(cab, fg_color="transparent")
        self.fila_opc.grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(4, 0))
        self.var_todos = ctk.BooleanVar(value=False)
        self.var_contenido = ctk.BooleanVar(value=True)
        self.chk_todos = ctk.CTkCheckBox(self.fila_opc, text="Renombrar todos (no solo los nombres malos)",
                                         variable=self.var_todos, font=fuente(12), checkbox_height=18, checkbox_width=18)
        self.chk_contenido = ctk.CTkCheckBox(self.fila_opc, text="Leer el contenido del PDF si el nombre no basta",
                                             variable=self.var_contenido, font=fuente(12), checkbox_height=18, checkbox_width=18)
        self.chk_contenido.pack(side="left", padx=4)
        self.chk_todos.pack(side="left", padx=14)

        acciones = ctk.CTkFrame(cab, fg_color="transparent")
        acciones.grid(row=4, column=0, columnspan=3, sticky="w", padx=12, pady=(8, 14))
        self.btn_analizar = boton(acciones, "🔍  Analizar", self._ejecutar_modo, width=130)
        self.btn_analizar.pack(side="left", padx=4)
        self.btn_cancelar = boton(acciones, "Cancelar", self._cancelar.set, "peligro", width=90)
        self.menu_hist = ctk.CTkOptionMenu(acciones, values=["(sin historiales)"], width=260, fg_color=C["panel"],
                                           button_color=C["tarjeta_hover"], button_hover_color=C["borde"])

        self.lbl_estado_g = subtitulo(tab, "", 12)
        self.lbl_estado_g.grid(row=1, column=0, sticky="w", padx=16)
        self.barra_g = ctk.CTkProgressBar(tab, height=6, progress_color=C["acento"], fg_color=C["pista"])
        self.barra_g.set(0)

        self.panel_plan = ctk.CTkFrame(tab, fg_color="transparent")
        self.panel_plan.grid(row=3, column=0, sticky="nsew", padx=10, pady=(4, 6))
        self.panel_plan.columnconfigure(0, weight=1)
        self.panel_plan.rowconfigure(1, weight=1)
        self._crear_tabla()
        self._cambio_modo("Organizar")

    def _crear_tabla(self):
        est = ttk.Style()
        try:
            est.theme_use("clam")
        except tk.TclError:
            pass
        est.configure("Estudio.Treeview", background=C["tarjeta"], fieldbackground=C["tarjeta"], foreground=C["texto"],
                      rowheight=26, borderwidth=0, font=("TkDefaultFont", 10))
        est.configure("Estudio.Treeview.Heading", background=C["panel"], foreground=C["texto2"], relief="flat",
                      font=("TkDefaultFont", 10, "bold"))
        est.map("Estudio.Treeview", background=[("selected", C["acento_suave"])], foreground=[("selected", C["texto"])])
        est.map("Estudio.Treeview.Heading", background=[("active", C["tarjeta_hover"])])

        self.lbl_resumen_plan = subtitulo(self.panel_plan, "", 12)
        self.lbl_resumen_plan.grid(row=0, column=0, sticky="w", padx=6, pady=(0, 4))
        marco = ctk.CTkFrame(self.panel_plan, fg_color=C["tarjeta"], corner_radius=10)
        marco.grid(row=1, column=0, sticky="nsew")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        cols = ("ok", "archivo", "destino", "conf", "motivo")
        self.tabla = ttk.Treeview(marco, columns=cols, show="headings", style="Estudio.Treeview", selectmode="browse")
        for c, t, w, st in (("ok", "✔", 36, False), ("archivo", "Archivo", 250, True), ("destino", "Destino", 300, True),
                            ("conf", "Confianza", 90, False), ("motivo", "Motivo", 380, True)):
            self.tabla.heading(c, text=t)
            self.tabla.column(c, width=w, stretch=st, anchor="center" if c in ("ok", "conf") else "w")
        for conf, color in COLOR_CONF.items():
            self.tabla.tag_configure(conf, foreground=color)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        sb = ctk.CTkScrollbar(marco, command=self.tabla.yview, button_color=C["borde"])
        sb.grid(row=0, column=1, sticky="ns")
        self.tabla.configure(yscrollcommand=sb.set)
        self.tabla.bind("<Button-1>", self._clic_tabla)

        self.pie_plan = ctk.CTkFrame(self.panel_plan, fg_color="transparent")
        self.pie_plan.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        boton(self.pie_plan, "Solo confianza alta", lambda: self._marcar("alta"), "suave", height=28, width=140).pack(side="left", padx=3)
        boton(self.pie_plan, "Alta + media", lambda: self._marcar("media"), "suave", height=28, width=110).pack(side="left", padx=3)
        boton(self.pie_plan, "Todas", lambda: self._marcar("todas"), "suave", height=28, width=70).pack(side="left", padx=3)
        boton(self.pie_plan, "Ninguna", lambda: self._marcar("ninguna"), "suave", height=28, width=80).pack(side="left", padx=3)
        self.btn_aplicar = boton(self.pie_plan, "Aplicar cambios", self._confirmar_aplicar, width=170)
        self.btn_aplicar.pack(side="right", padx=3)
        self.panel_plan.grid_remove()

    # ---------------------------------------------------------------- modos
    def _cambio_modo(self, modo):
        self.lbl_ayuda.configure(text=AYUDA_MODO[modo])
        self.lbl_raiz_g.configure(text=self._raiz() or "(sin elegir)")
        self._limpiar_plan()
        self.lbl_estado_g.configure(text="")
        usa_opts = modo in ("Organizar", "Renombrar", "Ambas")
        if usa_opts:
            self.fila_opc.grid()
        else:
            self.fila_opc.grid_remove()
        if modo in ("Renombrar", "Ambas"):
            self.chk_todos.pack(side="left", padx=14)
        else:
            self.chk_todos.pack_forget()
        if modo == "Deshacer":
            self._cargar_historiales()
            self.menu_hist.pack(side="left", padx=4)
            self.btn_analizar.configure(text="↩  Deshacer lote")
        else:
            self.menu_hist.pack_forget()
            self.btn_analizar.configure(text="📄  Generar reporte…" if modo == "Reporte" else "🔍  Analizar")

    def _cargar_historiales(self):
        raiz = self._raiz()
        self._historiales = {}
        if raiz and os.path.isdir(raiz):
            for ruta in gb.listar_historiales(raiz):
                self._historiales[os.path.basename(ruta)] = ruta
        nombres = list(self._historiales) or ["(sin historiales)"]
        self.menu_hist.configure(values=nombres)
        self.menu_hist.set(nombres[0])

    def _validar_raiz(self):
        raiz = self._raiz()
        if not raiz or not os.path.isdir(raiz):
            messagebox.showinfo("Organizar PDFs", "Primero elige la carpeta raíz de tu biblioteca.")
            return None
        return raiz

    def _ejecutar_modo(self):
        if self._trabajando:
            return
        raiz = self._validar_raiz()
        if not raiz:
            return
        modo = self.var_modo.get()
        if modo == "Reporte":
            return self._reporte(raiz)
        if modo == "Deshacer":
            return self._deshacer()
        opc = gb.Opciones(organizar=modo in ("Organizar", "Ambas"), renombrar=modo in ("Renombrar", "Ambas"),
                          renombrar_todos=bool(self.var_todos.get()) and modo in ("Renombrar", "Ambas"),
                          usar_contenido=bool(self.var_contenido.get()))
        self._ocupado(True, "Analizando (no se toca ningún archivo)…")
        self._cancelar.clear()

        def trabajo():
            try:
                plan = gb.planificar(raiz, opc, progreso_cb=self._progreso, cancelar=self._cancelar.is_set)
                self.app._en_ui(self._plan_listo, plan, None)
            except Exception as e:
                self.app._en_ui(self._plan_listo, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _progreso(self, i, total, nombre):
        if i % 4 == 0 or i == total:
            self.app._en_ui(self._pintar_progreso, i, total, nombre)

    def _pintar_progreso(self, i, total, nombre):
        self.barra_g.set(i / total if total else 0)
        self.lbl_estado_g.configure(text=f"{i}/{total} · {recortar(nombre, 60)}", text_color=C["texto2"])

    def _ocupado(self, si, texto=""):
        self._trabajando = si
        self.btn_analizar.configure(state="disabled" if si else "normal")
        if si:
            self.barra_g.set(0)
            self.barra_g.grid(row=2, column=0, sticky="ew", padx=16, pady=(2, 4))
            self.btn_cancelar.pack(side="left", padx=4)
            self.lbl_estado_g.configure(text=texto, text_color=C["texto2"])
        else:
            self.barra_g.grid_remove()
            self.btn_cancelar.pack_forget()

    # ---------------------------------------------------------------- plan
    def _limpiar_plan(self):
        self._plan = None
        self._filas = {}
        if hasattr(self, "tabla"):
            self.tabla.delete(*self.tabla.get_children())
            self.panel_plan.grid_remove()

    def _plan_listo(self, plan, error):
        self._ocupado(False)
        if error:
            self.lbl_estado_g.configure(text=f"⚠️ {error}", text_color=C["error"])
            return
        if plan.cancelado:
            self.lbl_estado_g.configure(text="Análisis cancelado.", text_color=C["aviso"])
            return
        self._plan = plan
        self.tabla.delete(*self.tabla.get_children())
        self._filas = {}
        raiz = plan.raiz
        for i, c in enumerate(plan.cambios):
            iid = str(i)
            self._filas[iid] = c
            self.tabla.insert("", "end", iid=iid, tags=(c.confianza,), values=(
                "☑" if c.seleccionado else "☐",
                os.path.relpath(c.origen, raiz).replace("\\", "/"),
                os.path.relpath(c.destino, raiz).replace("\\", "/"),
                c.confianza.replace("_", " "), c.motivo))
        notas = " ".join(plan.notas)
        if not plan.cambios:
            self.panel_plan.grid_remove()
            self.lbl_estado_g.configure(
                text=f"✓ Nada que cambiar: {plan.total_pdfs} PDFs revisados. {notas}".strip(), text_color=C["ok"])
            return
        self.lbl_estado_g.configure(text=notas, text_color=C["texto3"])
        self.panel_plan.grid()
        self._actualizar_resumen_plan()

    def _actualizar_resumen_plan(self):
        if not self._plan:
            return
        sel = sum(1 for c in self._plan.cambios if c.seleccionado)
        cnt = self._plan.contar_por_confianza()
        self.lbl_resumen_plan.configure(
            text=f"{len(self._plan.cambios)} cambios propuestos · alta {cnt['alta']} · media {cnt['media']} · "
                 f"baja {cnt['baja']} · sin evidencia {cnt['sin_evidencia']}   —   haz clic en ☑ para marcar/desmarcar")
        self.btn_aplicar.configure(text=f"Aplicar {sel} cambios", state="normal" if sel else "disabled")

    def _clic_tabla(self, ev):
        if self.tabla.identify("region", ev.x, ev.y) != "cell" or self.tabla.identify_column(ev.x) != "#1":
            return
        iid = self.tabla.identify_row(ev.y)
        c = self._filas.get(iid)
        if c:
            c.seleccionado = not c.seleccionado
            self.tabla.set(iid, "ok", "☑" if c.seleccionado else "☐")
            self._actualizar_resumen_plan()

    def _marcar(self, criterio):
        orden = {"alta": ("alta",), "media": ("alta", "media"), "todas": gb.CONFIANZAS, "ninguna": ()}[criterio]
        for iid, c in self._filas.items():
            c.seleccionado = c.confianza in orden
            self.tabla.set(iid, "ok", "☑" if c.seleccionado else "☐")
        self._actualizar_resumen_plan()

    def _confirmar_aplicar(self):
        if not self._plan or self._trabajando:
            return
        sel = [c for c in self._plan.cambios if c.seleccionado]
        if not sel:
            return
        bajas = sum(1 for c in sel if c.confianza in ("baja", "sin_evidencia"))
        msg = f"Se van a mover/renombrar {len(sel)} archivos dentro de:\n{self._plan.raiz}\n\n"
        if bajas:
            msg += f"⚠️ {bajas} de ellos son de confianza baja: revísalos antes.\n\n"
        msg += "No se sobrescribe nada y se guarda un historial para poder deshacer.\n¿Continuar?"
        if not messagebox.askyesno("Aplicar cambios", msg, icon="warning"):
            return
        raiz = self._plan.raiz
        self._ocupado(True, "Aplicando cambios…")
        self._cancelar.clear()

        def trabajo():
            try:
                r = gb.aplicar(raiz, self._plan.cambios, progreso_cb=self._progreso, cancelar=self._cancelar.is_set)
                self.app._en_ui(self._aplicado, r, None)
            except Exception as e:
                self.app._en_ui(self._aplicado, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _aplicado(self, r, error):
        self._ocupado(False)
        if error:
            self.lbl_estado_g.configure(text=f"⚠️ {error}", text_color=C["error"])
            return
        texto = f"✓ {r['aplicados']} cambios aplicados."
        if r["errores"]:
            texto += f" {len(r['errores'])} con error (ej.: {r['errores'][0]})"
        self._limpiar_plan()
        self.lbl_estado_g.configure(text=texto + "  Actualizando la biblioteca…", text_color=C["ok"])
        self.indexar(al_terminar=lambda: self.lbl_estado_g.configure(
            text=texto + "  Biblioteca reindexada: tu progreso y favoritos se conservaron.", text_color=C["ok"]))

    # ---------------------------------------------------------------- reporte y deshacer
    def _reporte(self, raiz):
        ruta = filedialog.asksaveasfilename(title="Guardar reporte", initialdir=raiz, initialfile=gb.ARCHIVO_REPORTE,
                                            defaultextension=".txt", filetypes=[("Texto", "*.txt")])
        if not ruta:
            return
        self._ocupado(True, "Generando reporte…")

        def trabajo():
            try:
                r = gb.generar_reporte(raiz, ruta_salida=ruta, progreso_cb=lambda n, _t, rel: None)
                self.app._en_ui(self._reporte_listo, r, None)
            except Exception as e:
                self.app._en_ui(self._reporte_listo, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _reporte_listo(self, r, error):
        self._ocupado(False)
        if error:
            self.lbl_estado_g.configure(text=f"⚠️ {error}", text_color=C["error"])
        else:
            self.lbl_estado_g.configure(
                text=f"✓ Reporte guardado: {r['total_pdfs']} PDFs en {r['total_carpetas']} carpetas → {r['ruta']}",
                text_color=C["ok"])

    def _deshacer(self):
        ruta = self._historiales.get(self.menu_hist.get())
        if not ruta:
            messagebox.showinfo("Deshacer", "No hay historiales para deshacer en esta biblioteca.")
            return
        if not messagebox.askyesno("Deshacer", f"¿Revertir el lote «{self.menu_hist.get()}»?\n"
                                   "Los archivos volverán a su carpeta y nombre anteriores.", icon="warning"):
            return
        self._ocupado(True, "Deshaciendo…")

        def trabajo():
            try:
                r = gb.deshacer(ruta, progreso_cb=self._progreso)
                self.app._en_ui(self._deshecho, r, None)
            except Exception as e:
                self.app._en_ui(self._deshecho, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _deshecho(self, r, error):
        self._ocupado(False)
        if error:
            self.lbl_estado_g.configure(text=f"⚠️ {error}", text_color=C["error"])
            return
        texto = f"✓ {r.get('revertidos', 0)} archivos revertidos."
        if r.get("errores"):
            texto += f" {len(r['errores'])} no se pudieron revertir."
        self.lbl_estado_g.configure(text=texto + "  Actualizando la biblioteca…", text_color=C["ok"])
        self._cargar_historiales()
        self.indexar(al_terminar=lambda: self.lbl_estado_g.configure(text=texto, text_color=C["ok"]))

    # ================================================================== pestaña Ajustes
    def _tab_ajustes(self, tab):
        tab.columnconfigure(0, weight=1)
        t = tarjeta(tab)
        t.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        titulo(t, "Meta diaria de estudio", 15).pack(anchor="w", padx=18, pady=(16, 0))
        subtitulo(t, "El tiempo se cuenta solo mientras lees o consultas al tutor. Tu meta se muestra en el Inicio.", 12
                  ).pack(anchor="w", padx=18)
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(fill="x", padx=18, pady=(8, 16))
        self.slider_meta = ctk.CTkSlider(fila, from_=10, to=240, number_of_steps=46, width=320, command=self._cambio_meta,
                                         progress_color=C["acento"], button_color=C["acento"], button_hover_color=C["acento_hover"])
        self.slider_meta.pack(side="left")
        self.lbl_meta = ctk.CTkLabel(fila, text="", font=fuente(13, "bold"), text_color=C["texto"], width=100)
        self.lbl_meta.pack(side="left", padx=12)

        self.tarjeta_areas = tarjeta(tab)
        self.tarjeta_areas.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        titulo(self.tarjeta_areas, "Áreas excluidas de rutas y tutor IA", 15).pack(anchor="w", padx=18, pady=(16, 0))
        subtitulo(self.tarjeta_areas, "Los libros de estas carpetas siguen en la biblioteca, pero no entran a ninguna ruta "
                  "y el tutor IA no los lee.", 12, wraplength=700).pack(anchor="w", padx=18, pady=(0, 6))
        self.caja_areas = ctk.CTkFrame(self.tarjeta_areas, fg_color="transparent")
        self.caja_areas.pack(fill="x", padx=18, pady=(0, 14))
        self._vars_areas = {}

        t3 = tarjeta(tab)
        t3.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        titulo(t3, "Tutor IA", 15).pack(anchor="w", padx=18, pady=(16, 0))
        self.lbl_modelo = subtitulo(t3, "", 12, wraplength=700)
        self.lbl_modelo.pack(anchor="w", padx=18, pady=(0, 16))

    def _refrescar_ajustes(self):
        minutos = int(round(tiempo.meta_diaria_segundos() / 60))
        self.slider_meta.set(minutos)
        self.lbl_meta.configure(text=f"{minutos} min / día")
        for w in self.caja_areas.winfo_children():
            w.destroy()
        presentes = sorted({l["area"] for l in db.listar_libros(solo_disponibles=False) if l["area"]}
                           | set(db.areas_excluidas()))
        excl = {a.casefold() for a in db.areas_excluidas()}
        self._vars_areas = {}
        for a in presentes:
            v = ctk.BooleanVar(value=a.casefold() in excl)
            self._vars_areas[a] = v
            ctk.CTkCheckBox(self.caja_areas, text=a.replace("_", " "), variable=v, font=fuente(12),
                            checkbox_height=18, checkbox_width=18, command=self._guardar_areas).pack(anchor="w", pady=2)
        self.lbl_modelo.configure(
            text=f"Modelo actual: {MODELO_POR_DEFECTO}. Para usar otro, define la variable de entorno ESTUDIO_MODELO "
                 f"(por ejemplo llama3.2:3b) antes de abrir la app.")

    def _cambio_meta(self, valor):
        minutos = int(round(valor / 5) * 5)
        self.lbl_meta.configure(text=f"{minutos} min / día")
        db.guardar_config("meta_diaria_min", minutos)

    def _guardar_areas(self):
        db.guardar_areas_excluidas([a for a, v in self._vars_areas.items() if v.get()])
        self._refrescar_resumen()
