"""Rutas de estudio: roadmaps por objetivo generados a partir de TU biblioteca."""
import tkinter as tk

import customtkinter as ctk

import database as db
import roadmap
from tema import (C, ESTADO_COLOR, NIVEL_COLOR, fuente, tarjeta, titulo, subtitulo, boton, barra, chip,
                  estado_vacio, recortar, nombre_area)

ANCHO_MIN, ANCHO_MAX = 200, 620
ESTADO_SIGUIENTE = {"Sin empezar": "Completado", "En progreso": "Completado", "Completado": "Sin empezar"}


class VistaRutas(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self.objetivo = None
        self._libros = []
        self._botones_obj = {}
        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)
        try:
            self._ancho_lista = max(ANCHO_MIN, min(ANCHO_MAX, int(db.obtener_config("rutas_ancho", 290))))
        except (TypeError, ValueError):
            self._ancho_lista = 290
        self._etiquetas_nombre = []

        izq = ctk.CTkFrame(self, fg_color=C["lateral"], corner_radius=0, width=self._ancho_lista)
        izq.grid(row=0, column=0, sticky="nsew")
        izq.grid_propagate(False)
        izq.pack_propagate(False)       # sus hijos usan pack: sin esto el ancho lo dicta el contenido
        self.izq = izq
        # Borde arrastrable: cambia el ancho de la lista de rutas
        self.divisor = tk.Frame(self, width=7, bg=C["borde"], cursor="sb_h_double_arrow")
        self.divisor.grid(row=0, column=1, sticky="ns")
        self.divisor.bind("<B1-Motion>", self._arrastrar)
        self.divisor.bind("<ButtonRelease-1>", lambda e: db.guardar_config("rutas_ancho", self._ancho_lista))
        self.divisor.bind("<Enter>", lambda e: self.divisor.configure(bg=C["acento"]))
        self.divisor.bind("<Leave>", lambda e: self.divisor.configure(bg=C["borde"]))
        titulo(izq, "Rutas", 22).pack(anchor="w", padx=20, pady=(24, 0))
        subtitulo(izq, "Elige un objetivo y sigue sus etapas. Usa ▲▼ para ordenarlas a tu gusto.", 12, wraplength=250
                  ).pack(anchor="w", padx=20, pady=(0, 6))
        self.btn_orden_defecto = boton(izq, "↺ Orden por defecto", self._orden_por_defecto, "fantasma", height=24, width=140)
        self.btn_orden_defecto.pack(anchor="w", padx=14, pady=(0, 6))
        self.lista = ctk.CTkScrollableFrame(izq, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self.detalle = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["borde"], width=100)
        self.detalle.grid(row=0, column=2, sticky="nsew", padx=(8, 4))

    # ------------------------------------------------------------------ ciclo de vida
    def al_mostrar(self, objetivo=None):
        self._libros = db.listar_libros()
        if objetivo:
            self.objetivo = objetivo
        elif self.objetivo is None:
            activo = db.obtener_config("objetivo_activo")
            self.objetivo = activo if activo in roadmap.OBJETIVOS else None
        self._pintar_lista()
        self._pintar_detalle()

    def _ajustes_todos(self):
        return {oid: db.obtener_ajustes_roadmap(oid) for oid in roadmap.OBJETIVOS}

    def _pintar_lista(self):
        for w in self.lista.winfo_children():
            w.destroy()
        self._etiquetas_nombre = []
        activo = db.obtener_config("objetivo_activo")
        resumenes = roadmap.resumen_objetivos(self._libros, self._ajustes_todos())
        # La ruta fijada primero; luego por avance (las empezadas arriba)
        resumenes.sort(key=lambda r: (r["id"] != activo, -(r["avance"] > 0), -r["avance"]))
        guardado = db.obtener_orden_rutas()
        if guardado:                                  # orden manual: gana sobre el automático
            pos = {oid: i for i, oid in enumerate(guardado)}
            resumenes.sort(key=lambda r: pos.get(r["id"], len(pos)))      # las nuevas van al final
        self._orden_visible = [r["id"] for r in resumenes]
        if guardado:
            self.btn_orden_defecto.pack(anchor="w", padx=14, pady=(0, 6), before=self.lista._parent_frame)
        else:
            self.btn_orden_defecto.pack_forget()
        for idx, r in enumerate(resumenes):
            sel = r["id"] == self.objetivo
            f = ctk.CTkFrame(self.lista, fg_color=C["acento_suave"] if sel else "transparent", corner_radius=12,
                             border_width=1 if sel else 0, border_color=C["acento"])
            f.pack(fill="x", padx=6, pady=3)
            f.columnconfigure(1, weight=1)
            ctk.CTkLabel(f, text=r["icono"], font=fuente(22), width=40).grid(row=0, column=0, rowspan=2, padx=(8, 0), pady=8)
            nombre = ctk.CTkLabel(f, text=r["nombre"] + ("  📌" if r["id"] == activo else ""), font=fuente(13, "bold"),
                                  text_color=C["texto"], anchor="w", justify="left", wraplength=self._ancho_envoltura())
            nombre.grid(row=0, column=1, sticky="w", padx=8, pady=(8, 0))
            self._etiquetas_nombre.append(nombre)
            ctk.CTkLabel(f, text=f"{r['completados']}/{r['total']} libros", font=fuente(11), text_color=C["texto2"],
                         anchor="w").grid(row=1, column=1, sticky="w", padx=8)
            barra(f, r["avance"], r["color"], alto=4).grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 10))
            for w in [f] + f.winfo_children():
                w.bind("<Button-1>", lambda e, oid=r["id"]: self._elegir(oid))
            # Botones de orden (se crean después del enlace de clic para que no seleccionen la ruta)
            mov = ctk.CTkFrame(f, fg_color="transparent")
            mov.grid(row=0, column=2, rowspan=2, padx=(0, 6))
            for texto, delta, habilitado in (("▲", -1, idx > 0), ("▼", 1, idx < len(resumenes) - 1)):
                ctk.CTkButton(mov, text=texto, width=24, height=20, corner_radius=6, font=fuente(10),
                              fg_color="transparent", hover_color=C["tarjeta_hover"],
                              text_color=C["texto2"] if habilitado else C["pista"],
                              state="normal" if habilitado else "disabled",
                              command=lambda oid=r["id"], d=delta: self._mover(oid, d)).pack()

    def _mover(self, oid, delta):
        db.mover_ruta(self._orden_visible, oid, delta)
        self._pintar_lista()

    def _orden_por_defecto(self):
        db.guardar_orden_rutas([])
        self._pintar_lista()

    def _ancho_envoltura(self) -> int:
        return max(90, self._ancho_lista - 165)

    def _arrastrar(self, e):
        ancho = e.x_root - self.izq.winfo_rootx()
        self._ancho_lista = int(max(ANCHO_MIN, min(ANCHO_MAX, ancho)))
        self.izq.configure(width=self._ancho_lista)
        for et in self._etiquetas_nombre:
            try:
                et.configure(wraplength=self._ancho_envoltura())
            except tk.TclError:
                pass

    def _elegir(self, oid):
        self.objetivo = oid
        self._pintar_lista()
        self._pintar_detalle()
        self.detalle._parent_canvas.yview_moveto(0)

    # ------------------------------------------------------------------ detalle
    def _pintar_detalle(self, conservar_scroll=False):
        pos = self.detalle._parent_canvas.yview()[0] if conservar_scroll else 0
        for w in self.detalle.winfo_children():
            w.destroy()
        d = self.detalle
        d.columnconfigure(0, weight=1)
        if not self.objetivo:
            estado_vacio(d, "🧭", "Elige tu objetivo",
                         "Cada ruta ordena los libros de tu biblioteca de lo básico a lo avanzado. "
                         "Selecciona una a la izquierda; puedes fijar la que quieras seguir.").grid(row=0, column=0, pady=60)
            return

        ajustes = db.obtener_ajustes_roadmap(self.objetivo)
        r = roadmap.generar_roadmap(self.objetivo, self._libros, ajustes)
        activo = db.obtener_config("objetivo_activo") == self.objetivo

        cab = tarjeta(d)
        cab.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 12))
        cab.columnconfigure(1, weight=1)
        ctk.CTkLabel(cab, text=r["icono"], font=fuente(38), width=70).grid(row=0, column=0, rowspan=3, padx=14, pady=14)
        titulo(cab, r["nombre"], 22).grid(row=0, column=1, sticky="w", pady=(16, 0))
        subtitulo(cab, r["descripcion"], 12).grid(row=1, column=1, sticky="w")
        subtitulo(cab, f"{r['completados']} de {r['total']} libros completados · {int(r['avance'] * 100)}% de avance", 12
                  ).grid(row=2, column=1, sticky="w", pady=(0, 6))
        barra(cab, r["avance"], r["color"], alto=8).grid(row=3, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 16))
        botones = ctk.CTkFrame(cab, fg_color="transparent")
        botones.grid(row=0, column=2, rowspan=3, padx=16)
        boton(botones, "📌 Mi ruta" if activo else "Fijar como mi ruta", self._fijar, "suave" if activo else "primario",
              width=140).pack(pady=2)
        if ajustes:
            boton(botones, "Restablecer cambios", self._restablecer, "fantasma", width=140, height=28).pack(pady=2)

        fila = 1
        sig = r["siguiente"]
        if sig:
            h = tarjeta(d, fg_color=C["acento_suave"], border_color=C["acento"])
            h.grid(row=fila, column=0, sticky="ew", padx=20, pady=(0, 12))
            h.columnconfigure(1, weight=1)
            ctk.CTkLabel(h, text="👉", font=fuente(26), width=56).grid(row=0, column=0, rowspan=2, padx=8, pady=12)
            chip(h, "SIGUIENTE LIBRO", C["acento"], C["fondo"]).grid(row=0, column=1, sticky="w", pady=(12, 0))
            titulo(h, recortar(sig["titulo"], 72), 15).grid(row=1, column=1, sticky="w", pady=(0, 12))
            boton(h, "Leer ahora  ›", lambda: self.app.abrir_libro(sig["id"]), width=130).grid(row=0, column=2, rowspan=2, padx=16)
            fila += 1

        for e in r["etapas"]:
            self._etapa(d, fila, e, r)
            fila += 1
        ctk.CTkLabel(d, text="", height=20).grid(row=fila, column=0)
        if conservar_scroll:
            self.after(30, lambda: self.detalle._parent_canvas.yview_moveto(pos))

    def _etapa(self, d, fila, e, r):
        estado = e["estado"]
        color = {"completada": C["ok"], "actual": C["acento"], "pendiente": C["texto3"], "vacia": C["texto3"]}[estado]
        t = tarjeta(d, border_color=color if estado == "actual" else C["borde"])
        t.grid(row=fila, column=0, sticky="ew", padx=20, pady=6)
        t.columnconfigure(1, weight=1)
        marca = "✓" if estado == "completada" else str(e["indice"] + 1)
        ctk.CTkLabel(t, text=marca, width=34, height=34, corner_radius=17, fg_color=color if estado != "pendiente" else C["pista"],
                     text_color="#0e1016" if estado in ("completada", "actual") else C["texto2"],
                     font=fuente(14, "bold")).grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=(14, 0), sticky="n")
        titulo(t, e["titulo"], 16).grid(row=0, column=1, sticky="w", pady=(12, 0))
        info = e["descripcion"] + (f"  ·  {e['completados']}/{e['total']}" if e["total"] else "")
        subtitulo(t, info, 12).grid(row=1, column=1, sticky="w", pady=(0, 6))
        if e["total"]:
            barra(t, e["avance_libros"], color, alto=5).grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=(0, 6))
        fila_i = 3
        for libro in e["libros"]:
            self._fila_libro(t, fila_i, libro, e, opcional=False)
            fila_i += 1
        if not e["libros"]:
            subtitulo(t, "Ningún libro de tu biblioteca encaja aquí todavía.", 12, text_color=C["texto3"]
                      ).grid(row=fila_i, column=1, sticky="w", pady=(0, 6))
            fila_i += 1

        pie = ctk.CTkFrame(t, fg_color="transparent")
        pie.grid(row=fila_i, column=1, sticky="w", pady=(2, 12))
        boton(pie, "＋ Agregar libro", lambda i=e["indice"]: self._dialogo_agregar(i), "fantasma", height=26, width=120).pack(side="left")
        if e["opcionales"]:
            cont = ctk.CTkFrame(t, fg_color="transparent")
            cont.grid(row=fila_i + 1, column=1, sticky="ew", pady=(0, 10))
            cont.columnconfigure(0, weight=1)
            visible = {"v": False}
            btn = boton(pie, f"▸ {len(e['opcionales'])} opcionales y referencias", None, "fantasma", height=26)
            btn.pack(side="left", padx=6)

            def alternar(c=cont, b=btn, ops=e["opcionales"], est=e, v=visible):
                v["v"] = not v["v"]
                for w in c.winfo_children():
                    w.destroy()
                b.configure(text=("▾ " if v["v"] else "▸ ") + f"{len(ops)} opcionales y referencias")
                if v["v"]:
                    for i, lb in enumerate(ops):
                        self._fila_libro(c, i, lb, est, opcional=True, columna=0)
            btn.configure(command=alternar)

    def _fila_libro(self, padre, fila, libro, etapa, opcional, columna=1):
        f = ctk.CTkFrame(padre, fg_color=C["panel"] if not opcional else "transparent", corner_radius=10)
        f.grid(row=fila, column=columna, sticky="ew", padx=(0, 16), pady=2)
        f.columnconfigure(1, weight=1)
        hecho = libro["estado"] == "Completado"
        ctk.CTkButton(f, text="●" if hecho else "○" if libro["estado"] == "Sin empezar" else "◐", width=30, height=30,
                      fg_color="transparent", hover_color=C["tarjeta_hover"], font=fuente(18),
                      text_color=ESTADO_COLOR[libro["estado"]],
                      command=lambda l=libro: self._alternar_estado(l)).grid(row=0, column=0, padx=(6, 0))
        nombre = ctk.CTkLabel(f, text=recortar(libro["titulo"], 64), anchor="w", cursor="hand2",
                              font=fuente(13), text_color=C["texto3"] if hecho else C["texto"])
        nombre.grid(row=0, column=1, sticky="w", padx=6, pady=6)
        nombre.bind("<Button-1>", lambda e, l=libro: self.app.abrir_libro(l["id"]))
        if libro["modo_efectivo"] == "capitulos" and libro["caps_total"]:
            chip(f, f"§ {libro['caps_hechos']}/{libro['caps_total']}", C["acento"]).grid(row=0, column=2, padx=2)
        elif libro["modo_lectura"] == "completo":
            chip(f, "📖 completo", C["texto2"]).grid(row=0, column=2, padx=2)
        chip(f, libro.get("nivel_nombre", ""), NIVEL_COLOR.get(libro.get("nivel", 2), C["texto2"])).grid(row=0, column=3, padx=4)
        if libro.get("manual"):
            chip(f, "manual", C["aviso"]).grid(row=0, column=4, padx=2)
        boton(f, "⋯", lambda l=libro, w=f: self._menu_modo(l, w), "fantasma", width=28, height=26).grid(row=0, column=5, padx=(2, 0))
        if opcional:
            boton(f, "＋", lambda l=libro, i=etapa["indice"]: self._agregar(l["id"], i), "fantasma", width=28, height=26
                  ).grid(row=0, column=6, padx=(2, 6))
        else:
            boton(f, "✕", lambda l=libro: self._quitar(l), "fantasma", width=28, height=26).grid(row=0, column=6, padx=(2, 6))

    # ------------------------------------------------------------------ modo de lectura
    def _menu_modo(self, libro, widget):
        """Menú del libro: cómo se mide su avance (completo o por capítulos)."""
        m = tk.Menu(self, tearoff=0, bg=C["tarjeta"], fg=C["texto"], activebackground=C["acento"], bd=0)
        efectivo = "por capítulos" if libro["modo_efectivo"] == "capitulos" else "completo"
        m.add_command(label=f"Se mide {efectivo}: {libro['modo_motivo']}", state="disabled")
        m.add_separator()
        for modo, etiqueta in (("auto", "Automático (la app decide)"), ("completo", "Leer completo (repasar de principio a fin)"),
                               ("capitulos", "Medir por capítulos")):
            marca = "✓ " if libro["modo_lectura"] == modo else "    "
            m.add_command(label=marca + etiqueta, command=lambda md=modo, l=libro: self._fijar_modo(l, md))
        m.add_separator()
        m.add_command(label="Abrir y elegir capítulos…", command=lambda l=libro: self.app.abrir_libro(l["id"], panel="capitulos"))
        try:
            m.tk_popup(widget.winfo_rootx() + widget.winfo_width() - 40, widget.winfo_rooty() + widget.winfo_height())
        finally:
            m.grab_release()

    def _fijar_modo(self, libro, modo):
        db.fijar_modo_lectura(libro["id"], modo)
        self._refrescar()

    # ------------------------------------------------------------------ acciones
    def _refrescar(self):
        self._libros = db.listar_libros()
        self._pintar_lista()
        self._pintar_detalle(conservar_scroll=True)

    def _alternar_estado(self, libro):
        db.actualizar_estado_libro(libro["id"], ESTADO_SIGUIENTE[libro["estado"]])
        self._refrescar()

    def _fijar(self):
        actual = db.obtener_config("objetivo_activo") == self.objetivo
        db.guardar_config("objetivo_activo", "" if actual else self.objetivo)
        self._refrescar()

    def _quitar(self, libro):
        if libro.get("manual"):
            db.quitar_ajuste_roadmap(self.objetivo, libro["id"])
        else:
            db.ocultar_en_roadmap(self.objetivo, libro["id"])
        self._refrescar()

    def _agregar(self, recurso_id, etapa):
        db.agregar_a_roadmap(self.objetivo, recurso_id, etapa)
        self._refrescar()

    def _restablecer(self):
        db.reiniciar_ajustes_roadmap(self.objetivo)
        self._refrescar()

    def _dialogo_agregar(self, etapa):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Agregar libro a la etapa")
        dlg.geometry("560x520")
        dlg.configure(fg_color=C["fondo"])
        dlg.transient(self.winfo_toplevel())
        dlg.after(120, lambda: (dlg.grab_set(), dlg.focus_force()) if dlg.winfo_exists() else None)
        titulo(dlg, "Agregar libro a la etapa", 16).pack(anchor="w", padx=20, pady=(18, 6))
        var = ctk.StringVar()
        ctk.CTkEntry(dlg, textvariable=var, placeholder_text="🔍  Buscar por título…", height=36).pack(fill="x", padx=20)
        zona = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        zona.pack(fill="both", expand=True, padx=14, pady=10)
        candidatos = [l for l in self._libros if not l["excluido"]]

        def llenar(*_):
            for w in zona.winfo_children():
                w.destroy()
            q = var.get().strip().casefold()
            n = 0
            for l in sorted(candidatos, key=lambda x: x["titulo"].casefold()):
                if q and q not in l["titulo"].casefold():
                    continue
                ctk.CTkButton(zona, text=recortar(l["titulo"], 70), anchor="w", fg_color="transparent",
                              hover_color=C["tarjeta_hover"], text_color=C["texto"], height=30,
                              command=lambda l=l: (dlg.destroy(), self._agregar(l["id"], etapa))).pack(fill="x", pady=1)
                n += 1
                if n >= 40:
                    break
        var.trace_add("write", llenar)
        llenar()
