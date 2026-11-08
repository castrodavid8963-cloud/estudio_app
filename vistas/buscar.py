"""Buscar: búsqueda de texto completo en el contenido de todos los libros, y control del índice."""
import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import buscador
import database as db
from tema import C, fuente, tarjeta, titulo, subtitulo, boton, barra, chip, estado_vacio, recortar, nombre_area

AMBITOS = ["Todos los libros", "En curso y leídos", "★ Favoritos"]
POR_PAGINA = 40
MAX_POR_LIBRO = 3


def _tamano(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1024


class VistaBuscar(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self._gen = 0
        self._job = None
        self._resultados = []          # [(libro, pagina, fragmento)]
        self._mostrados = 0
        self._consulta = ""
        self.indexador = buscador.Indexador(self._al_progreso, self._ceder)
        self._moviendo = False

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=28, pady=(24, 4))
        titulo(cab, "Buscar en los libros", 26).pack(side="left")
        subtitulo(self, "Busca una palabra o una «frase entre comillas» dentro del contenido de tus PDF. "
                        "Escribe parte de una palabra y también la encuentra.", 12).pack(anchor="w", padx=30, pady=(0, 10))

        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=28, pady=(0, 6))
        fila.columnconfigure(0, weight=1)
        self.entrada = ctk.CTkEntry(fila, height=42, font=fuente(15), fg_color=C["tarjeta"], border_color=C["borde"],
                                    text_color=C["texto"], placeholder_text="Ej.: punteros, «memoria compartida», normalización…")
        self.entrada.grid(row=0, column=0, sticky="ew")
        self.entrada.bind("<Return>", lambda e: self.buscar())
        self.entrada.bind("<KeyRelease>", self._tecla)
        boton(fila, "Buscar", self.buscar, width=100, height=42).grid(row=0, column=1, padx=(8, 0))

        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.pack(fill="x", padx=28, pady=(0, 6))
        self.seg = ctk.CTkSegmentedButton(filtros, values=AMBITOS, command=lambda v: self.buscar(), height=28,
                                          font=fuente(12), selected_color=C["acento"],
                                          selected_hover_color=C["acento_hover"], unselected_color=C["tarjeta"])
        self.seg.set(AMBITOS[0])
        self.seg.pack(side="left")
        self.var_varios = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(filtros, text="Varios resultados por libro", variable=self.var_varios, font=fuente(12),
                        text_color=C["texto2"], fg_color=C["acento"], border_color=C["borde"], checkbox_width=18,
                        checkbox_height=18, command=self.buscar).pack(side="left", padx=18)
        self.lbl_cuenta = subtitulo(filtros, "", 12)
        self.lbl_cuenta.pack(side="right")

        # --- estado del índice
        self.estado = tarjeta(self)
        self.estado.pack(fill="x", padx=28, pady=(2, 8))
        self.estado.columnconfigure(0, weight=1)
        self.lbl_estado = ctk.CTkLabel(self.estado, text="", font=fuente(13, "bold"), text_color=C["texto"], anchor="w")
        self.lbl_estado.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))
        self.lbl_detalle = subtitulo(self.estado, "", 11)
        self.lbl_detalle.configure(wraplength=620, justify="left")
        self.lbl_detalle.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 4))
        self.barra = barra(self.estado, 0.0, C["acento"], alto=5)
        self.barra.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        botones = ctk.CTkFrame(self.estado, fg_color="transparent")
        botones.grid(row=0, column=1, rowspan=3, padx=12, pady=8)
        self.btn_indexar = boton(botones, "▶ Crear índice", self._alternar_indexado, width=150)
        self.btn_indexar.pack(pady=(0, 4))
        self.btn_detener = boton(botones, "Detener", self.indexador.detener, "suave", width=150, height=28)
        fila_b = ctk.CTkFrame(self.estado, fg_color="transparent")
        fila_b.grid(row=3, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        self.var_ceder = ctk.BooleanVar(value=db.obtener_config("indexar_ceder", "1") == "1")
        ctk.CTkSwitch(fila_b, text="Pausar mientras leo", variable=self.var_ceder, font=fuente(11),
                      text_color=C["texto2"], progress_color=C["acento"],
                      command=lambda: db.guardar_config("indexar_ceder", "1" if self.var_ceder.get() else "0")
                      ).pack(side="left", padx=6)
        boton(fila_b, "📁 Ubicación", self._cambiar_ubicacion, "fantasma", height=26, width=100, font=fuente(11)).pack(side="left", padx=4)
        boton(fila_b, "🗑 Borrar índice", self._borrar_indice, "fantasma", height=26, width=120, font=fuente(11)).pack(side="left")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista.pack(fill="both", expand=True, padx=(22, 14), pady=(0, 14))
        self._pintar_vacio()

    # ------------------------------------------------------------------ ciclo de vida
    def al_mostrar(self, consulta=None):
        if consulta:
            self.entrada.delete(0, "end")
            self.entrada.insert(0, consulta)
            self.buscar()
        self._refrescar_estado()
        self.after(100, self.entrada.focus_set)

    def _ceder(self) -> bool:
        return self.var_ceder.get() and self.app.lector_visible

    # ------------------------------------------------------------------ estado del índice
    def _refrescar_estado(self):
        def trabajo():
            try:
                hechos = buscador.estado_indice()
                lista, total = buscador.pendientes(con_total=True)
                sin_texto = sum(1 for v in hechos.values() if v[2])
                datos = (total - len(lista), len(lista), sin_texto, buscador.tamano_bytes(), buscador.ruta_indice(), total)
            except Exception as e:
                datos = (0, -1, 0, 0, str(e), 0)
            self.app._en_ui(self._pintar_estado, datos)
        threading.Thread(target=trabajo, daemon=True).start()

    def _pintar_estado(self, datos):
        hechos, pend, sin_texto, tam, ruta, total = datos
        if self.indexador.activo and not self.indexador.finalizado:
            return                                 # el progreso ya se pinta desde _al_progreso
        self.btn_detener.pack_forget()
        self.btn_indexar.configure(state="normal")
        if pend < 0:
            self.lbl_estado.configure(text="No se pudo leer el índice", text_color=C["peligro"])
            self.lbl_detalle.configure(text=ruta)
            self.barra.set(0)
            return
        if hechos == 0:
            self.lbl_estado.configure(text="Todavía no hay índice de búsqueda", text_color=C["aviso"])
            self.lbl_detalle.configure(text="Indexar lee el texto de cada PDF una sola vez, en segundo plano y con pausas para no "
                                            "saturar el disco. Puedes seguir usando la app, detenerlo y reanudarlo cuando quieras.")
            self.btn_indexar.configure(text="▶ Crear índice")
        elif pend > 0:
            self.lbl_estado.configure(text=f"Índice parcial: {hechos} de {total} libros", text_color=C["aviso"])
            self.btn_indexar.configure(text="▶ Continuar indexando")
        else:
            self.lbl_estado.configure(text=f"✓ Índice al día: {hechos} libros", text_color=C["ok"])
            self.btn_indexar.configure(text="🔄 Buscar cambios")
        if hechos:
            extra = f" · {sin_texto} sin texto (escaneados: necesitarán OCR)" if sin_texto else ""
            self.lbl_detalle.configure(text=f"{_tamano(tam)} en {os.path.dirname(ruta)}{extra}")
        self.barra.set(hechos / total if total else 0)

    def _alternar_indexado(self):
        if self.indexador.activo:
            self.indexador.pausar(not self.indexador.en_pausa)
            self._pintar_boton_pausa()
            return
        self.btn_indexar.configure(text="⏸ Pausar")
        self.btn_detener.pack()
        self.lbl_estado.configure(text="Indexando…", text_color=C["texto"])
        self.indexador.iniciar()

    def _pintar_boton_pausa(self):
        self.btn_indexar.configure(text="▶ Reanudar" if self.indexador.en_pausa else "⏸ Pausar")

    def _al_progreso(self, hechos, total, nombre, terminado):
        self.app._en_ui(self._pintar_progreso, hechos, total, nombre, terminado)

    def _pintar_progreso(self, hechos, total, nombre, terminado):
        if terminado:
            self._refrescar_estado()
            return
        self.lbl_estado.configure(text=f"Indexando… {hechos} de {total} libros", text_color=C["texto"])
        self.lbl_detalle.configure(text=recortar(nombre, 90) if nombre else "")
        self.barra.set(hechos / total if total else 0)

    def _cambiar_ubicacion(self):
        if self.indexador.activo or self._moviendo:
            messagebox.showinfo("Índice de búsqueda", "Detén la indexación antes de cambiar la ubicación.")
            return
        carpeta = filedialog.askdirectory(title="Carpeta donde guardar el índice (mejor en un disco con espacio)")
        if not carpeta or os.path.normcase(carpeta) == os.path.normcase(buscador.carpeta_indice()):
            return
        origen = buscador.ruta_indice()
        destino = os.path.join(carpeta, buscador.NOMBRE_ARCHIVO)
        db.guardar_config("ruta_indice_busqueda", carpeta)
        if not os.path.exists(origen) or os.path.exists(destino):
            self._refrescar_estado()
            return
        self._moviendo = True
        self.lbl_estado.configure(text="Moviendo el índice…", text_color=C["texto"])

        def mover():
            error = None
            try:
                for suf in ("", "-wal", "-shm"):
                    if os.path.exists(origen + suf):
                        shutil.move(origen + suf, destino + suf)
            except Exception as e:
                error = str(e)
                db.guardar_config("ruta_indice_busqueda", os.path.dirname(origen))
            self.app._en_ui(self._movido, error)
        threading.Thread(target=mover, daemon=True).start()

    def _movido(self, error):
        self._moviendo = False
        if error:
            messagebox.showerror("Índice de búsqueda", f"No se pudo mover el índice:\n{error}")
        self._refrescar_estado()

    def _borrar_indice(self):
        if self.indexador.activo:
            messagebox.showinfo("Índice de búsqueda", "Detén la indexación antes de borrar el índice.")
            return
        if messagebox.askyesno("Borrar índice", "Se borrará el índice de búsqueda (no tus libros ni tus notas). "
                                                "Podrás volver a crearlo cuando quieras. ¿Continuar?"):
            buscador.borrar_indice()
            self._resultados = []
            self._pintar_vacio()
            self._refrescar_estado()

    # ------------------------------------------------------------------ búsqueda
    def _tecla(self, e):
        if e.keysym in ("Return", "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R", "Tab"):
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(450, self.buscar)

    def buscar(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        texto = self.entrada.get().strip()
        self._consulta = texto
        self._gen += 1
        gen = self._gen
        if not texto:
            self._resultados = []
            self.lbl_cuenta.configure(text="")
            self._pintar_vacio()
            return

        def trabajo():
            filas = buscador.buscar(texto, 600)
            self.app._en_ui(self._recibir, gen, texto, filas)
        threading.Thread(target=trabajo, daemon=True).start()

    def _recibir(self, gen, texto, filas):
        if gen != self._gen:
            return                                  # llegó tarde: ya se pidió otra búsqueda
        libros = {l["id"]: l for l in db.listar_libros()}
        ambito = self.seg.get()
        varios = self.var_varios.get()
        por_libro, res = {}, []
        for rid, pagina, frag, _ in filas:
            libro = libros.get(rid)
            if libro is None or libro.get("excluido"):
                continue
            if ambito == AMBITOS[1] and libro["estado"] == "Sin empezar":
                continue
            if ambito == AMBITOS[2] and not libro["favorito"]:
                continue
            if not varios and por_libro.get(rid, 0) >= MAX_POR_LIBRO:
                continue
            por_libro[rid] = por_libro.get(rid, 0) + 1
            res.append((libro, pagina, frag))
        self._resultados, self._mostrados = res, 0
        n_libros = len(por_libro)
        self.lbl_cuenta.configure(text=f"{len(res)} resultados en {n_libros} libros" if res else "")
        self._pintar_resultados(texto)

    # ------------------------------------------------------------------ pintado
    def _limpiar(self):
        for w in self.lista.winfo_children():
            w.destroy()

    def _pintar_vacio(self):
        self._limpiar()
        estado_vacio(self.lista, "🔎", "Busca dentro de tus libros",
                     "Escribe un concepto y verás en qué libros y páginas aparece.").pack(pady=10)

    def _pintar_resultados(self, texto):
        self._limpiar()
        if not self._resultados:
            hay_indice = os.path.exists(buscador.ruta_indice())
            detalle = ("Prueba con otra palabra, quita acentos o amplía el ámbito." if hay_indice
                       else "Primero crea el índice de búsqueda (arriba).")
            estado_vacio(self.lista, "🤷", f"Sin resultados para «{recortar(texto, 40)}»", detalle).pack(pady=10)
            return
        self._mas()

    def _mas(self):
        for w in [w for w in self.lista.winfo_children() if getattr(w, "_es_boton_mas", False)]:
            w.destroy()
        fin = min(len(self._resultados), self._mostrados + POR_PAGINA)
        for libro, pagina, frag in self._resultados[self._mostrados:fin]:
            self._tarjeta(libro, pagina, frag)
        self._mostrados = fin
        if fin < len(self._resultados):
            b = boton(self.lista, f"Mostrar más ({len(self._resultados) - fin})", self._mas, "suave", width=200)
            b._es_boton_mas = True
            b.pack(pady=10)

    def _tarjeta(self, libro, pagina, fragmento):
        t = tarjeta(self.lista)
        t.pack(fill="x", pady=4, padx=4)
        cab = ctk.CTkFrame(t, fg_color="transparent")
        cab.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(cab, text=recortar(libro["titulo"], 70), font=fuente(14, "bold"), text_color=C["texto"],
                     anchor="w").pack(side="left")
        chip(cab, f"p. {pagina}", C["acento"]).pack(side="left", padx=(10, 4))
        chip(cab, nombre_area(libro.get("area")), C["texto2"]).pack(side="left")
        partes = buscador.partir_fragmento(fragmento)
        plano = "".join(t_ for t_, _ in partes)
        lineas = min(4, max(1, len(plano) // 100 + 1))
        caja = tk.Text(t, height=lineas, wrap="word", bg=C["tarjeta"], fg=C["texto2"], relief="flat",
                       highlightthickness=0, borderwidth=0, font=fuente(12), cursor="hand2", padx=2, pady=0)
        caja.tag_configure("hit", foreground=C["acento"], font=fuente(12, "bold"))
        for trozo, es_hit in partes:
            caja.insert("end", trozo, "hit" if es_hit else ())
        caja.configure(state="disabled")
        caja.pack(fill="x", padx=14, pady=(0, 10))
        abrir = lambda e=None, i=libro["id"], p=pagina: self.app.abrir_libro(i, pagina=p)
        for w in (t, cab, caja, *cab.winfo_children()):
            w.bind("<Button-1>", abrir, add="+")
