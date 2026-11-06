"""Pestaña «Duplicados»: encuentra libros repetidos (por contenido, metadatos y título) y los elimina."""
import os
import threading
from tkinter import messagebox

import customtkinter as ctk

import database as db
import duplicados as dp
from tema import C, ESTADO_COLOR, ESTADO_ICONO, fuente, tarjeta, titulo, subtitulo, boton, chip, recortar, nombre_area

LOTE_GRUPOS = 20
COLOR_TIPO = {"identico": C["error"], "metadatos": C["aviso"], "titulo_probable": C["aviso"], "titulo_posible": C["texto2"]}
FILTROS = ["Todos", "Idénticos", "Metadatos", "Mismo título"]


class PestanaDuplicados(ctk.CTkFrame):
    def __init__(self, padre, app, herramientas):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self.herr = herramientas
        self.resultado = None
        self._vars = {}
        self._visibles = []
        self._mostrados = 0
        self._cancelar = threading.Event()
        self._ocupado = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        cab = tarjeta(self)
        cab.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        cab.columnconfigure(0, weight=1)
        titulo(cab, "Libros duplicados", 15).grid(row=0, column=0, sticky="w", padx=18, pady=(14, 0))
        subtitulo(cab, "Compara el contenido real de los archivos, los metadatos del PDF (título y autor) y los nombres, "
                       "no solo el nombre. Nada se borra sin que lo confirmes; tu progreso se pasa a la copia que conservas.",
                  12, wraplength=720).grid(row=1, column=0, sticky="w", padx=18)
        fila = ctk.CTkFrame(cab, fg_color="transparent")
        fila.grid(row=2, column=0, sticky="w", padx=14, pady=(8, 12))
        self.btn_buscar = boton(fila, "🔎  Buscar duplicados", self.buscar, width=170)
        self.btn_buscar.pack(side="left", padx=4)
        self.btn_cancelar = boton(fila, "Cancelar", self._cancelar.set, "peligro", width=90)
        self.var_definitivo = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(fila, text="Borrar definitivamente (sin papelera)", variable=self.var_definitivo, font=fuente(12),
                        checkbox_height=18, checkbox_width=18, command=self._actualizar_pie).pack(side="left", padx=18)

        self.lbl_estado = subtitulo(self, "", 12)
        self.lbl_estado.grid(row=1, column=0, sticky="w", padx=16)
        self.barra = ctk.CTkProgressBar(self, height=6, progress_color=C["acento"], fg_color=C["pista"])
        self.barra.set(0)

        self.resumen = tarjeta(self)
        self.resumen.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 4))
        self.resumen.grid_remove()
        self.lbl_resumen = ctk.CTkLabel(self.resumen, text="", font=fuente(13, "bold"), text_color=C["texto"], anchor="w", justify="left")
        self.lbl_resumen.pack(anchor="w", padx=18, pady=(12, 2))
        self.fila_chips = ctk.CTkFrame(self.resumen, fg_color="transparent")
        self.fila_chips.pack(anchor="w", padx=14, pady=(0, 10))

        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.grid(row=3, column=0, sticky="nsew")
        self.cuerpo.columnconfigure(0, weight=1)
        self.cuerpo.rowconfigure(1, weight=1)
        self.seg = ctk.CTkSegmentedButton(self.cuerpo, values=FILTROS, command=lambda _: self._pintar_lista(),
                                          fg_color=C["panel"], selected_color=C["acento"], selected_hover_color=C["acento_hover"],
                                          unselected_color=C["panel"], unselected_hover_color=C["tarjeta_hover"], height=28)
        self.seg.set("Todos")
        self.seg.grid(row=0, column=0, sticky="w", padx=12, pady=(4, 4))
        self.lista = ctk.CTkScrollableFrame(self.cuerpo, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista.grid(row=1, column=0, sticky="nsew")
        self.cuerpo.grid_remove()

        self.pie = ctk.CTkFrame(self, fg_color="transparent")
        self.pie.grid(row=4, column=0, sticky="ew", padx=10, pady=(6, 4))
        boton(self.pie, "Marcar sugeridos", self._marcar_sugeridos, "suave", height=28, width=130).pack(side="left", padx=3)
        boton(self.pie, "Desmarcar todo", self._desmarcar, "suave", height=28, width=120).pack(side="left", padx=3)
        self.btn_eliminar = boton(self.pie, "Eliminar", self._confirmar, "peligro", width=240)
        self.btn_eliminar.pack(side="right", padx=3)
        self.pie.grid_remove()

    # ------------------------------------------------------------------ búsqueda
    def buscar(self):
        if self._ocupado:
            return
        if not db.obtener_ruta_biblioteca():
            messagebox.showinfo("Duplicados", "Primero elige e indexa tu carpeta de biblioteca.")
            return
        self._ocupar(True, "Leyendo metadatos de los libros…")
        self._cancelar.clear()

        def trabajo():
            try:
                r = dp.buscar(progreso_cb=lambda i, t, n: self.app._en_ui(self._progreso, i, t, n),
                              cancelar=self._cancelar.is_set)
                self.app._en_ui(self._buscado, r, None)
            except Exception as e:
                self.app._en_ui(self._buscado, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _ocupar(self, si, texto=""):
        self._ocupado = si
        self.btn_buscar.configure(state="disabled" if si else "normal")
        if si:
            self.barra.set(0)
            self.barra.grid(row=1, column=0, sticky="ew", padx=16, pady=(20, 0))
            self.btn_cancelar.pack(side="left", padx=4)
            self.lbl_estado.configure(text=texto, text_color=C["texto2"])
        else:
            self.barra.grid_remove()
            self.btn_cancelar.pack_forget()

    def _progreso(self, i, total, nombre):
        self.barra.set(i / total if total else 0)
        self.lbl_estado.configure(text=f"{i}/{total} · {recortar(nombre, 60)}", text_color=C["texto2"])

    def _buscado(self, r, error):
        self._ocupar(False)
        if error:
            self.lbl_estado.configure(text=f"⚠️ {error}", text_color=C["error"])
            return
        if self._cancelar.is_set():
            self.lbl_estado.configure(text="Búsqueda cancelada.", text_color=C["aviso"])
            return
        self.resultado = r
        extra = f" ({r.sin_archivo} sin archivo en disco, omitidos)" if r.sin_archivo else ""
        if not r.grupos:
            self.resumen.grid_remove()
            self.cuerpo.grid_remove()
            self.pie.grid_remove()
            self.lbl_estado.configure(text=f"✓ Sin duplicados: se revisaron {r.revisados} libros{extra}.", text_color=C["ok"])
            return
        self.lbl_estado.configure(text=f"Revisados {r.revisados} libros{extra}.", text_color=C["texto2"])
        self._pintar_resumen()
        self.resumen.grid()
        self.cuerpo.grid()
        self.pie.grid()
        self._preparar_variables()
        self.seg.set("Todos")
        self._pintar_lista()

    def _pintar_resumen(self):
        r = self.resultado
        self.lbl_resumen.configure(
            text=f"Encontré {len(r.grupos)} grupos de duplicados · {r.total_sobrantes} libros de más · "
                 f"{dp.formatear_bytes(r.bytes_sobrantes)} recuperables")
        for w in self.fila_chips.winfo_children():
            w.destroy()
        c = r.por_tipo()
        for tipo, texto in (("identico", "Idénticos (mismo contenido)"), ("metadatos", "Mismos metadatos"),
                            ("titulo_probable", "Mismo título y páginas"), ("titulo_posible", "Título igual, otras páginas")):
            n = c.get(tipo, 0)
            if n:
                chip(self.fila_chips, f"{texto}: {n}", COLOR_TIPO[tipo]).pack(side="left", padx=4)

    # ------------------------------------------------------------------ lista
    def _preparar_variables(self):
        self._vars = {}
        for g in self.resultado.grupos:
            for m in g.miembros:
                self._vars[m.id] = ctk.BooleanVar(value=g.sugerido and m.id != g.conservar_id)

    def _filtrados(self):
        f = self.seg.get()
        permitidos = {"Todos": None, "Idénticos": {"identico"}, "Metadatos": {"metadatos"},
                      "Mismo título": {"titulo_probable", "titulo_posible"}}[f]
        return [g for g in self.resultado.grupos if permitidos is None or g.tipo in permitidos]

    def _pintar_lista(self):
        for w in self.lista.winfo_children():
            w.destroy()
        self._visibles = self._filtrados()
        self._mostrados = 0
        if not self._visibles:
            subtitulo(self.lista, "No hay grupos de este tipo.", 13).pack(pady=30)
        self._mas()
        self._actualizar_pie()

    def _mas(self):
        if hasattr(self, "_btn_mas") and self._btn_mas is not None:
            self._btn_mas.destroy()
            self._btn_mas = None
        fin = min(len(self._visibles), self._mostrados + LOTE_GRUPOS)
        for g in self._visibles[self._mostrados:fin]:
            self._tarjeta_grupo(g)
        self._mostrados = fin
        if fin < len(self._visibles):
            self._btn_mas = boton(self.lista, f"Mostrar más ({len(self._visibles) - fin} grupos)", self._mas, "suave")
            self._btn_mas.pack(pady=10)

    def _tarjeta_grupo(self, g):
        t = tarjeta(self.lista)
        t.pack(fill="x", padx=8, pady=5)
        cab = ctk.CTkFrame(t, fg_color="transparent")
        cab.pack(fill="x", padx=12, pady=(10, 2))
        chip(cab, g.etiqueta, COLOR_TIPO[g.tipo]).pack(side="left")
        subtitulo(cab, f"{len(g.miembros)} copias · sobran {dp.formatear_bytes(g.bytes_sobrantes)}", 11).pack(side="left", padx=10)
        if not g.sugerido:
            subtitulo(cab, "revisa a mano: puede ser otra edición", 11, text_color=C["aviso"]).pack(side="left")
        for m in g.miembros:
            f = ctk.CTkFrame(t, fg_color=C["panel"], corner_radius=8)
            f.pack(fill="x", padx=12, pady=2)
            f.columnconfigure(1, weight=1)
            ctk.CTkCheckBox(f, text="", variable=self._vars[m.id], width=26, checkbox_height=18, checkbox_width=18,
                            command=lambda g=g, m=m: self._alternar(g, m)).grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=6)
            ctk.CTkLabel(f, text=recortar(m.nombre, 80), font=fuente(12, "bold"), text_color=C["texto"], anchor="w"
                         ).grid(row=0, column=1, sticky="w", padx=8, pady=(6, 0))
            ruta_rel = os.path.relpath(m.ruta, db.obtener_ruta_biblioteca()).replace("\\", "/")
            ctk.CTkLabel(f, text=f"{recortar(os.path.dirname(ruta_rel) or '.', 60)}  ·  {dp.formatear_bytes(m.tam)}  ·  "
                                 f"{m.paginas or '?'} pág.", font=fuente(11), text_color=C["texto2"], anchor="w"
                         ).grid(row=1, column=1, sticky="w", padx=8, pady=(0, 6))
            col = 2
            if m.id == g.conservar_id:
                chip(f, "recomendado conservar", C["ok"]).grid(row=0, column=col, rowspan=2, padx=4)
                col += 1
            if m.estado != "Sin empezar" or m.favorito:
                txt = f"{ESTADO_ICONO[m.estado]} {m.estado}" + (" ★" if m.favorito else "")
                chip(f, txt, ESTADO_COLOR[m.estado]).grid(row=0, column=col, rowspan=2, padx=4)
                col += 1
            boton(f, "📖", lambda i=m.id: self.app.abrir_libro(i), "fantasma", width=30, height=26
                  ).grid(row=0, column=col, rowspan=2, padx=(2, 8))
        ctk.CTkLabel(t, text="", height=6).pack()

    # ------------------------------------------------------------------ selección
    def _alternar(self, g, m):
        if all(self._vars[x.id].get() for x in g.miembros):
            self._vars[m.id].set(False)
            self.lbl_estado.configure(text="Deja al menos una copia sin marcar en cada grupo.", text_color=C["aviso"])
        self._actualizar_pie()

    def _marcar_sugeridos(self):
        for g in self.resultado.grupos:
            for m in g.miembros:
                self._vars[m.id].set(g.sugerido and m.id != g.conservar_id)
        self._actualizar_pie()

    def _desmarcar(self):
        for v in self._vars.values():
            v.set(False)
        self._actualizar_pie()

    def _seleccion(self):
        ids = {i for i, v in self._vars.items() if v.get()}
        miembros = [m for g in self.resultado.grupos for m in g.miembros if m.id in ids]
        return ids, sum(m.tam for m in miembros)

    def _actualizar_pie(self):
        if not self.resultado:
            return
        ids, peso = self._seleccion()
        accion = "Borrar" if self.var_definitivo.get() else "Mover a papelera"
        self.btn_eliminar.configure(text=f"{accion} {len(ids)} archivos ({dp.formatear_bytes(peso)})",
                                    state="normal" if ids and not self._ocupado else "disabled")

    # ------------------------------------------------------------------ eliminar
    def _confirmar(self):
        if self._ocupado or not self.resultado:
            return
        ids, peso = self._seleccion()
        if not ids:
            return
        definitivo = self.var_definitivo.get()
        raiz = db.obtener_ruta_biblioteca()
        dudosos = sum(1 for g in self.resultado.grupos if not g.sugerido for m in g.miembros if m.id in ids)
        msg = f"Se van a {'BORRAR DEFINITIVAMENTE' if definitivo else 'mover a la papelera'} {len(ids)} archivos " \
              f"({dp.formatear_bytes(peso)}).\n\n"
        msg += ("Esta acción NO se puede deshacer.\n\n" if definitivo else
                f"La papelera es la carpeta oculta «{dp.CARPETA_PAPELERA}» dentro de tu biblioteca; "
                "desde ahí puedes recuperarlos.\n\n")
        if dudosos:
            msg += f"⚠️ {dudosos} son coincidencias solo por título (podrían ser otra edición).\n\n"
        msg += "El progreso, favoritos y tiempo de estudio pasan a la copia que se conserva.\n¿Continuar?"
        if not messagebox.askyesno("Eliminar duplicados", msg, icon="warning"):
            return
        self._ocupar(True, "Eliminando…")
        grupos = list(self.resultado.grupos)

        def trabajo():
            try:
                r = dp.eliminar(raiz, grupos, ids, definitivo=definitivo,
                                progreso_cb=lambda i, t, n: self.app._en_ui(self._progreso, i, t, n))
                self.app._en_ui(self._eliminado, r, ids, None)
            except Exception as e:
                self.app._en_ui(self._eliminado, None, ids, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _eliminado(self, r, ids, error):
        self._ocupar(False)
        if error:
            self.lbl_estado.configure(text=f"⚠️ {error}", text_color=C["error"])
            return
        texto = f"✓ {r['eliminados']} archivos eliminados ({dp.formatear_bytes(r['bytes'])})."
        if r["carpeta"]:
            texto += f" Están en: {r['carpeta']}"
        if r["errores"]:
            texto += f"  ⚠️ {len(r['errores'])} con problemas: {r['errores'][0]}"
        self.lbl_estado.configure(text=texto, text_color=C["ok"] if not r["errores"] else C["aviso"])
        # Quitar de la lista los eliminados (se quedan los que fallaron)
        for g in self.resultado.grupos:
            g.miembros = [m for m in g.miembros if m.id not in ids or os.path.exists(m.ruta)]
        self.resultado.grupos = [g for g in self.resultado.grupos if len(g.miembros) > 1]
        if self.resultado.grupos:
            self._pintar_resumen()
            self._preparar_variables()
            self._pintar_lista()
        else:
            self.resumen.grid_remove()
            self.cuerpo.grid_remove()
            self.pie.grid_remove()
        self.app.actualizar_biblioteca()
