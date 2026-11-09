"""Repaso: tarjetas con repetición espaciada, quizzes con resultados guardados y gestión de tarjetas."""
import os
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import ai_pdf
import database as db
import repaso as rp
from pdf_core import fitz, PYMUPDF_LOCK
from tema import C, fuente, tarjeta, titulo, subtitulo, boton, barra, chip, estado_vacio, recortar, fecha_relativa

TODOS = "Todos los libros"
COLOR_CALIDAD = {rp.OTRA_VEZ: "#f87171", rp.DIFICIL: "#fbbf24", rp.BIEN: "#34d399", rp.FACIL: "#60a5fa"}


def texto_de_paginas(ruta: str, ini: int, fin: int, max_chars: int = 9000) -> str:
    """Texto de las páginas ini..fin (1-based) de un PDF, cortado a max_chars."""
    partes, total = [], 0
    with PYMUPDF_LOCK:
        doc = fitz.open(ruta)
        try:
            ini, fin = max(1, ini), min(len(doc), fin)
            for n in range(ini, fin + 1):
                t = " ".join((doc[n - 1].get_text("text") or "").split())
                if t:
                    partes.append(f"[Página {n}] {t}")
                    total += len(t)
                if total >= max_chars:
                    break
        finally:
            doc.close()
    return "\n".join(partes)[:max_chars]


class DialogoTarjeta(ctk.CTkToplevel):
    def __init__(self, padre, titulo_txt, pregunta="", respuesta="", al_guardar=None):
        super().__init__(padre)
        self.title(titulo_txt)
        self.configure(fg_color=C["fondo"])
        self.geometry("520x420")
        self.minsize(380, 340)
        self._al_guardar = al_guardar
        try:
            self.transient(padre.winfo_toplevel())
        except tk.TclError:
            pass
        ctk.CTkLabel(self, text="Pregunta (frente)", font=fuente(12, "bold"), text_color=C["texto2"]).pack(anchor="w", padx=18, pady=(16, 2))
        self.p = ctk.CTkTextbox(self, height=100, fg_color=C["tarjeta"], border_color=C["borde"], border_width=1,
                                text_color=C["texto"], font=fuente(13), wrap="word")
        self.p.pack(fill="x", padx=18)
        self.p.insert("1.0", pregunta)
        ctk.CTkLabel(self, text="Respuesta (reverso)", font=fuente(12, "bold"), text_color=C["texto2"]).pack(anchor="w", padx=18, pady=(12, 2))
        self.r = ctk.CTkTextbox(self, fg_color=C["tarjeta"], border_color=C["borde"], border_width=1,
                                text_color=C["texto"], font=fuente(13), wrap="word")
        self.r.pack(fill="both", expand=True, padx=18)
        self.r.insert("1.0", respuesta)
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.pack(fill="x", padx=18, pady=12)
        boton(fila, "Guardar", self._guardar, width=100).pack(side="right")
        boton(fila, "Cancelar", self.destroy, "suave", width=90).pack(side="right", padx=(0, 8))
        self.after(150, self._enfocar)

    def _enfocar(self):
        try:
            self.lift()
            self.grab_set()
            self.p.focus_set()
        except tk.TclError:
            pass

    def _guardar(self):
        p, r = self.p.get("1.0", "end").strip(), self.r.get("1.0", "end").strip()
        if not p or not r:
            messagebox.showinfo("Tarjeta", "Escribe la pregunta y la respuesta.", parent=self)
            return
        self.grab_release()
        self.destroy()
        if self._al_guardar:
            self._al_guardar(p, r)


class VistaRepaso(ctk.CTkFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent")
        self.app = app
        self._cola, self._pos, self._revelada, self._contadores = [], 0, False, {}
        self._sesion_activa = False
        self._libro_filtro = None            # None = todos
        self._quiz, self._quiz_pos, self._quiz_libro = [], 0, None
        self._gen_quiz = 0
        self._libros_quiz = {}

        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=28, pady=(24, 6))
        titulo(cab, "Repaso", 26).pack(side="left")
        self.seg = ctk.CTkSegmentedButton(cab, values=["Hoy", "Quiz", "Tarjetas"], command=self._cambiar_pestana, height=30,
                                          font=fuente(12), selected_color=C["acento"],
                                          selected_hover_color=C["acento_hover"], unselected_color=C["tarjeta"])
        self.seg.set("Hoy")
        self.seg.pack(side="right")
        self.cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        self.cuerpo.pack(fill="both", expand=True)
        self.t_hoy = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self.t_quiz = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self.t_tarj = ctk.CTkFrame(self.cuerpo, fg_color="transparent")
        self._armar_quiz()
        self._armar_tarjetas()
        top = self.winfo_toplevel()
        for tecla in ("1", "2", "3", "4"):
            top.bind(f"<Key-{tecla}>", lambda e, t=tecla: self._tecla_numero(int(t)), add="+")
        top.bind("<space>", self._tecla_espacio, add="+")

    # ------------------------------------------------------------------ ciclo de vida
    def al_mostrar(self, quiz=None, pestana=None):
        if quiz:
            self._cambiar_pestana("Quiz")
            self.seg.set("Quiz")
            self._preparar_quiz(**quiz)
            return
        if pestana:
            self.seg.set(pestana)
        self._cambiar_pestana(self.seg.get())

    def _cambiar_pestana(self, nombre):
        for t in (self.t_hoy, self.t_quiz, self.t_tarj):
            t.pack_forget()
        {"Hoy": self.t_hoy, "Quiz": self.t_quiz, "Tarjetas": self.t_tarj}[nombre].pack(fill="both", expand=True)
        if nombre == "Hoy":
            self._pintar_hoy()
        elif nombre == "Quiz":
            self._refrescar_quiz_lista()
        else:
            self._pintar_tarjetas()

    # ================================================================== HOY
    def _opciones_libros(self):
        libros = db.libros_con_tarjetas()
        self._mapa_libros = {TODOS: None}
        for rid, nombre, n in libros:
            self._mapa_libros[f"{recortar(nombre, 48)} ({n})"] = rid
        return list(self._mapa_libros)

    def _pintar_hoy(self):
        for w in self.t_hoy.winfo_children():
            w.destroy()
        self._sesion_activa = False
        r = db.resumen_repaso(self._libro_filtro)
        if db.resumen_repaso()["total"] == 0:
            estado_vacio(self.t_hoy, "🧠", "Aún no tienes tarjetas",
                         "En el lector, el tutor puede crear tarjetas de lo que estás leyendo (botón 🃏 Tarjetas). "
                         "También puedes escribirlas tú en la pestaña Tarjetas.", "Crear una tarjeta",
                         lambda: (self.seg.set("Tarjetas"), self._cambiar_pestana("Tarjetas"), self._nueva_tarjeta())
                         ).pack(pady=40)
            return
        fila = ctk.CTkFrame(self.t_hoy, fg_color="transparent")
        fila.pack(fill="x", padx=28, pady=(6, 10))
        for i in range(4):
            fila.columnconfigure(i, weight=1, uniform="r")
        datos = [("Para hoy", str(r["pendientes"]), f"{r['vencidas']} vencidas · {r['nuevas']} nuevas", C["acento"]),
                 ("Hechas hoy", str(r["hechas_hoy"]), "repasos", C["ok"]),
                 ("Dominadas", str(r["dominadas"]), f"de {r['total']} tarjetas", C["aviso"]),
                 ("Retención", f"{int(r['retencion'] * 100)}%" if r["retencion"] is not None else "—",
                  f"{r['repasos_30d']} repasos en 30 días", C["texto2"])]
        for i, (rot, valor, det, color) in enumerate(datos):
            t = tarjeta(fila)
            t.grid(row=0, column=i, sticky="nsew", padx=5)
            subtitulo(t, rot.upper(), 10).pack(anchor="w", padx=16, pady=(12, 0))
            ctk.CTkLabel(t, text=valor, font=fuente(26, "bold"), text_color=color).pack(anchor="w", padx=16)
            subtitulo(t, det, 11).pack(anchor="w", padx=16, pady=(0, 12))

        ctl = ctk.CTkFrame(self.t_hoy, fg_color="transparent")
        ctl.pack(fill="x", padx=28, pady=(4, 8))
        opciones = self._opciones_libros()
        actual = next((k for k, v in self._mapa_libros.items() if v == self._libro_filtro), TODOS)
        self.menu_libro = ctk.CTkOptionMenu(ctl, values=opciones, width=300, command=self._filtrar_libro, fg_color=C["tarjeta"],
                                            button_color=C["tarjeta_hover"], text_color=C["texto"], font=fuente(12))
        self.menu_libro.set(actual)
        self.menu_libro.pack(side="left")
        if r["pendientes"]:
            boton(ctl, f"▶  Empezar repaso ({r['pendientes']})", self._empezar, width=220, height=40).pack(side="right")
        else:
            ctk.CTkLabel(ctl, text="✓ Todo al día por hoy", font=fuente(14, "bold"), text_color=C["ok"]).pack(side="right")
        self.zona_sesion = ctk.CTkFrame(self.t_hoy, fg_color="transparent")
        self.zona_sesion.pack(fill="both", expand=True, padx=28, pady=(0, 14))
        if not r["pendientes"]:
            subtitulo(self.zona_sesion, "Vuelve mañana, o crea más tarjetas desde el lector. Las nuevas se van "
                      f"introduciendo de a {db.limite_nuevas()} por día para no saturarte.", 12, wraplength=640
                      ).pack(anchor="w", pady=20)

    def _filtrar_libro(self, etiqueta):
        self._libro_filtro = self._mapa_libros.get(etiqueta)
        self._pintar_hoy()

    def _empezar(self):
        self._cola = db.tarjetas_pendientes(self._libro_filtro)
        if not self._cola:
            self._pintar_hoy()
            return
        self._pos, self._contadores, self._sesion_activa = 0, {q: 0 for q in range(4)}, True
        self._mostrar_tarjeta()

    def _mostrar_tarjeta(self):
        for w in self.zona_sesion.winfo_children():
            w.destroy()
        if self._pos >= len(self._cola):
            self._fin_sesion()
            return
        t = self._cola[self._pos]
        self._revelada = False
        top = ctk.CTkFrame(self.zona_sesion, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        subtitulo(top, f"Tarjeta {self._pos + 1} de {len(self._cola)}", 12).pack(side="left")
        boton(top, "Salir", self._pintar_hoy, "fantasma", width=60, height=26).pack(side="right")
        barra(self.zona_sesion, self._pos / len(self._cola), C["acento"], alto=5).pack(fill="x", pady=(0, 10))
        marco = tarjeta(self.zona_sesion)
        marco.pack(fill="both", expand=True)
        meta = []
        if t.get("recurso_id"):
            libro = db.obtener_libro(t["recurso_id"])
            if libro:
                meta.append(recortar(libro["titulo"], 60))
        if t.get("pagina"):
            meta.append(f"p. {t['pagina']}")
        if meta:
            subtitulo(marco, " · ".join(meta), 11).pack(anchor="w", padx=22, pady=(16, 0))
        ctk.CTkLabel(marco, text=t["pregunta"], font=fuente(19, "bold"), text_color=C["texto"], wraplength=640,
                     justify="left", anchor="w").pack(fill="x", padx=22, pady=(10, 8))
        self.zona_resp = ctk.CTkFrame(marco, fg_color="transparent")
        self.zona_resp.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self.btn_revelar = boton(self.zona_resp, "Mostrar respuesta   (espacio)", self._revelar, height=42)
        self.btn_revelar.pack(pady=24)

    def _revelar(self):
        if self._revelada or not self._sesion_activa or self._pos >= len(self._cola):
            return
        self._revelada = True
        t = self._cola[self._pos]
        for w in self.zona_resp.winfo_children():
            w.destroy()
        ctk.CTkFrame(self.zona_resp, height=1, fg_color=C["borde"]).pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(self.zona_resp, text=t["respuesta"], font=fuente(16), text_color=C["texto"], wraplength=640,
                     justify="left", anchor="w").pack(fill="x")
        prev = rp.vista_previa(t)
        fila = ctk.CTkFrame(self.zona_resp, fg_color="transparent")
        fila.pack(side="bottom", fill="x", pady=(18, 0))
        for q in range(4):
            fila.columnconfigure(q, weight=1, uniform="q")
            b = ctk.CTkButton(fila, text=f"{rp.NOMBRES[q]}  ({q + 1})\n{prev[q]}", height=52, corner_radius=10,
                              fg_color=C["tarjeta_hover"], hover_color=COLOR_CALIDAD[q], text_color=C["texto"],
                              font=fuente(12, "bold"), command=lambda c=q: self._responder(c))
            b.grid(row=0, column=q, padx=4, sticky="ew")

    def _responder(self, calidad):
        if not (self._sesion_activa and self._revelada) or self._pos >= len(self._cola):
            return
        t = self._cola[self._pos]
        nuevo = db.registrar_repaso(t["id"], calidad)
        self._contadores[calidad] += 1
        if calidad == rp.OTRA_VEZ and nuevo:                  # se vuelve a ver al final de esta sesión
            self._cola.append({**t, **nuevo})
        self._pos += 1
        self.app.actualizar_insignia_repaso()
        self._mostrar_tarjeta()

    def _tecla_numero(self, n):
        if self._sesion_activa and self.winfo_ismapped() and self._revelada:
            self._responder(n - 1)

    def _tecla_espacio(self, e):
        if self._sesion_activa and self.winfo_ismapped() and not self._revelada:
            self._revelar()
            return "break"

    def _fin_sesion(self):
        self._sesion_activa = False
        c = self._contadores
        total = sum(c.values())
        bien = c[rp.BIEN] + c[rp.FACIL] + c[rp.DIFICIL]
        marco = tarjeta(self.zona_sesion, fg_color=C["acento_suave"], border_color=C["acento"])
        marco.pack(fill="x", pady=20)
        titulo(marco, "¡Repaso terminado! 🎉", 22).pack(anchor="w", padx=24, pady=(20, 4))
        subtitulo(marco, f"{total} respuestas · {int(100 * bien / total) if total else 0}% recordadas · "
                         f"{c[rp.OTRA_VEZ]} para repetir pronto", 13).pack(anchor="w", padx=24)
        boton(marco, "Volver", self._pintar_hoy, width=120).pack(anchor="w", padx=24, pady=(14, 20))
        self.app.actualizar_insignia_repaso()

    # ================================================================== QUIZ
    def _armar_quiz(self):
        t = self.t_quiz
        ctl = tarjeta(t)
        ctl.pack(fill="x", padx=28, pady=(6, 8))
        ctl.columnconfigure(0, weight=1)
        subtitulo(ctl, "Elige un libro y un rango de páginas: el tutor escribe preguntas de opción múltiple y tus resultados quedan guardados.",
                  12, wraplength=620).grid(row=0, column=0, columnspan=6, sticky="w", padx=16, pady=(12, 6))
        self.menu_quiz_libro = ctk.CTkOptionMenu(ctl, values=["(sin libros)"], width=330, fg_color=C["tarjeta_hover"],
                                                 button_color=C["borde"], text_color=C["texto"], font=fuente(12),
                                                 command=self._libro_quiz_elegido)
        self.menu_quiz_libro.grid(row=1, column=0, sticky="w", padx=(16, 8), pady=(0, 12))
        self.ent_ini = ctk.CTkEntry(ctl, width=64, placeholder_text="desde", fg_color=C["fondo"], border_color=C["borde"])
        self.ent_ini.grid(row=1, column=1, padx=2, pady=(0, 12))
        self.ent_fin = ctk.CTkEntry(ctl, width=64, placeholder_text="hasta", fg_color=C["fondo"], border_color=C["borde"])
        self.ent_fin.grid(row=1, column=2, padx=2, pady=(0, 12))
        self.seg_n = ctk.CTkSegmentedButton(ctl, values=["3", "5", "8"], width=100, height=28, font=fuente(12),
                                            selected_color=C["acento"], unselected_color=C["tarjeta_hover"])
        self.seg_n.set("5")
        self.seg_n.grid(row=1, column=3, padx=8, pady=(0, 12))
        self.btn_gen_quiz = boton(ctl, "Generar quiz", self._generar_quiz, width=130)
        self.btn_gen_quiz.grid(row=1, column=4, padx=(4, 16), pady=(0, 12))
        self.zona_quiz = ctk.CTkFrame(t, fg_color="transparent")
        self.zona_quiz.pack(fill="both", expand=True, padx=28, pady=(0, 14))

    def _refrescar_quiz_lista(self):
        libros = [l for l in db.listar_libros(incluir_excluidos=False) if l["estado"] != "Sin empezar"]
        libros.sort(key=lambda l: l["ultima_apertura"] or "", reverse=True)
        self._libros_quiz = {recortar(l["titulo"], 58): l for l in libros[:60]}
        if self._quiz_libro and not any(l["id"] == self._quiz_libro["id"] for l in self._libros_quiz.values()):
            self._libros_quiz[recortar(self._quiz_libro["titulo"], 58)] = self._quiz_libro
        nombres = list(self._libros_quiz) or ["(abre un libro primero)"]
        self.menu_quiz_libro.configure(values=nombres)
        if self._quiz_libro:
            self.menu_quiz_libro.set(recortar(self._quiz_libro["titulo"], 58))
        elif self.menu_quiz_libro.get() not in nombres:
            self.menu_quiz_libro.set(nombres[0])
            self._libro_quiz_elegido(nombres[0])
        if not self._quiz and not self._quiz_cargando():
            self._pintar_historial_quiz()

    def _quiz_cargando(self):
        return getattr(self, "_cargando", False)

    def _libro_quiz_elegido(self, nombre):
        libro = self._libros_quiz.get(nombre)
        if not libro:
            return
        self._quiz_libro = libro
        ini = max(1, libro.get("ultima_pagina") or 1)
        self.ent_ini.delete(0, "end")
        self.ent_ini.insert(0, str(ini))
        self.ent_fin.delete(0, "end")
        self.ent_fin.insert(0, str(ini + 3))

    def _preparar_quiz(self, libro_id, ini=None, fin=None):
        libro = db.obtener_libro(libro_id)
        if not libro:
            return
        self._quiz_libro = libro
        self._quiz = []
        self._refrescar_quiz_lista()
        self.menu_quiz_libro.set(recortar(libro["titulo"], 58))
        ini = ini or libro.get("ultima_pagina") or 1
        self.ent_ini.delete(0, "end")
        self.ent_ini.insert(0, str(ini))
        self.ent_fin.delete(0, "end")
        self.ent_fin.insert(0, str(fin or ini + 3))
        self._pintar_historial_quiz()

    def _limpiar_quiz(self):
        for w in self.zona_quiz.winfo_children():
            w.destroy()

    def _pintar_historial_quiz(self):
        self._limpiar_quiz()
        historial = db.listar_quizzes(15)
        if not historial:
            estado_vacio(self.zona_quiz, "✅", "Todavía no has hecho quizzes",
                         "Genera uno arriba y aquí quedará el historial con tu puntaje.").pack(pady=20)
            return
        subtitulo(self.zona_quiz, "HISTORIAL", 11).pack(anchor="w", pady=(6, 4))
        for q in historial:
            f = tarjeta(self.zona_quiz)
            f.pack(fill="x", pady=3)
            f.columnconfigure(0, weight=1)
            ctk.CTkLabel(f, text=recortar(q["titulo"] or "Quiz", 70), font=fuente(13, "bold"), text_color=C["texto"],
                         anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(8, 0))
            subtitulo(f, fecha_relativa(q["creado"]), 11).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))
            pct = q["aciertos"] / q["total"] if q["total"] else 0
            ctk.CTkLabel(f, text=f"{q['aciertos']}/{q['total']}", font=fuente(16, "bold"),
                         text_color=C["ok"] if pct >= 0.7 else C["aviso"] if pct >= 0.4 else C["error"]
                         ).grid(row=0, column=1, rowspan=2, padx=16)

    def _generar_quiz(self):
        libro = self._quiz_libro
        if not libro:
            messagebox.showinfo("Quiz", "Primero abre o elige un libro.")
            return
        if getattr(self, "_cargando", False):
            return
        if not self.app.ollama_listo:
            messagebox.showinfo("Quiz", "La IA no está conectada. Abre Ollama y vuelve a intentarlo.")
            return
        try:
            ini = int(self.ent_ini.get() or libro.get("ultima_pagina") or 1)
            fin = int(self.ent_fin.get() or ini + 3)
        except ValueError:
            messagebox.showinfo("Quiz", "Escribe números en «desde» y «hasta».")
            return
        if fin < ini or fin - ini > 15:
            messagebox.showinfo("Quiz", "Usa un rango de 1 a 15 páginas (desde ≤ hasta).")
            return
        n = int(self.seg_n.get())
        self._cargando = True
        self._gen_quiz += 1
        gen = self._gen_quiz
        self.btn_gen_quiz.configure(state="disabled")
        self._limpiar_quiz()
        ctk.CTkLabel(self.zona_quiz, text="⏳ El tutor está escribiendo las preguntas…\n"
                                          "(la primera vez puede tardar si el modelo se carga desde el disco)",
                     font=fuente(13), text_color=C["texto2"], justify="center").pack(pady=40)

        def trabajo():
            try:
                texto = texto_de_paginas(libro["ruta"], ini, fin)
                preguntas = ai_pdf.generar_quiz_ia(texto, libro["titulo"], n)
                self.app._en_ui(self._quiz_listo, gen, libro, ini, fin, preguntas, None)
            except Exception as e:
                self.app._en_ui(self._quiz_listo, gen, libro, ini, fin, None, str(e))
        threading.Thread(target=trabajo, daemon=True).start()

    def _quiz_listo(self, gen, libro, ini, fin, preguntas, error):
        self._cargando = False
        self.btn_gen_quiz.configure(state="normal")
        if gen != self._gen_quiz:
            return
        self._limpiar_quiz()
        if error:
            ctk.CTkLabel(self.zona_quiz, text=f"⚠️ {error}", font=fuente(13), text_color=C["error"], wraplength=620,
                         justify="left").pack(pady=30, anchor="w")
            return
        self._quiz = [dict(q, elegida=None) for q in preguntas]
        self._quiz_titulo = f"{libro['titulo']} (págs. {ini}–{fin})"
        self._quiz_pos = 0
        self._mostrar_pregunta()

    def _mostrar_pregunta(self):
        self._limpiar_quiz()
        if self._quiz_pos >= len(self._quiz):
            self._fin_quiz()
            return
        q = self._quiz[self._quiz_pos]
        top = ctk.CTkFrame(self.zona_quiz, fg_color="transparent")
        top.pack(fill="x")
        subtitulo(top, f"Pregunta {self._quiz_pos + 1} de {len(self._quiz)}", 12).pack(side="left")
        boton(top, "Cancelar", self._cancelar_quiz, "fantasma", width=70, height=26).pack(side="right")
        barra(self.zona_quiz, self._quiz_pos / len(self._quiz), C["acento"], alto=5).pack(fill="x", pady=(4, 10))
        marco = tarjeta(self.zona_quiz)
        marco.pack(fill="both", expand=True)
        ctk.CTkLabel(marco, text=q["pregunta"], font=fuente(17, "bold"), text_color=C["texto"], wraplength=640,
                     justify="left", anchor="w").pack(fill="x", padx=22, pady=(18, 10))
        self._botones_op = []
        for i, op in enumerate(q["opciones"]):
            b = ctk.CTkButton(marco, text=f"{'ABCD'[i]}.  {op}", anchor="w", height=44, corner_radius=10,
                              fg_color=C["tarjeta_hover"], hover_color=C["borde"], text_color=C["texto"], font=fuente(13),
                              command=lambda k=i: self._elegir(k))
            b.pack(fill="x", padx=22, pady=3)
            self._botones_op.append(b)
        self.zona_explica = ctk.CTkFrame(marco, fg_color="transparent")
        self.zona_explica.pack(fill="x", padx=22, pady=(8, 16))

    def _elegir(self, k):
        q = self._quiz[self._quiz_pos]
        if q["elegida"] is not None:
            return
        q["elegida"] = k
        for i, b in enumerate(self._botones_op):
            b.configure(state="disabled")
            if i == q["correcta"]:
                b.configure(fg_color="#166534", text_color_disabled="#ffffff")
            elif i == k:
                b.configure(fg_color="#991b1b", text_color_disabled="#ffffff")
        ok = k == q["correcta"]
        ctk.CTkLabel(self.zona_explica, text="✓ ¡Correcto!" if ok else f"✗ La correcta era la {'ABCD'[q['correcta']]}.",
                     font=fuente(14, "bold"), text_color=C["ok"] if ok else C["error"]).pack(anchor="w")
        if q.get("explicacion"):
            ctk.CTkLabel(self.zona_explica, text=q["explicacion"], font=fuente(12), text_color=C["texto2"], wraplength=620,
                         justify="left").pack(anchor="w", pady=(2, 0))
        ultimo = self._quiz_pos + 1 >= len(self._quiz)
        boton(self.zona_explica, "Ver resultado" if ultimo else "Siguiente  ›", self._siguiente_pregunta, width=140).pack(anchor="e", pady=(10, 0))

    def _siguiente_pregunta(self):
        self._quiz_pos += 1
        self._mostrar_pregunta()

    def _cancelar_quiz(self):
        self._quiz = []
        self._pintar_historial_quiz()

    def _fin_quiz(self):
        total = len(self._quiz)
        aciertos = sum(1 for q in self._quiz if q["elegida"] == q["correcta"])
        db.guardar_quiz(self._quiz_libro["id"] if self._quiz_libro else 0, self._quiz_titulo, self._quiz)
        falladas = [q for q in self._quiz if q["elegida"] != q["correcta"]]
        marco = tarjeta(self.zona_quiz, fg_color=C["acento_suave"], border_color=C["acento"])
        marco.pack(fill="x", pady=10)
        titulo(marco, f"{aciertos} de {total} correctas", 24).pack(anchor="w", padx=24, pady=(18, 2))
        subtitulo(marco, "Resultado guardado en tu historial." + ("" if not falladas else
                  f" Fallaste {len(falladas)}: puedes convertirlas en tarjetas para repasarlas."), 12, wraplength=600
                  ).pack(anchor="w", padx=24)
        fila = ctk.CTkFrame(marco, fg_color="transparent")
        fila.pack(anchor="w", padx=24, pady=(12, 18))
        if falladas:
            self.btn_falladas = boton(fila, f"🃏 Guardar {len(falladas)} falladas como tarjetas",
                                      lambda: self._falladas_a_tarjetas(falladas), width=270)
            self.btn_falladas.pack(side="left", padx=(0, 8))
        boton(fila, "Hacer otro", self._cancelar_quiz, "suave", width=110).pack(side="left")
        self._quiz = []

    def _falladas_a_tarjetas(self, falladas):
        tarjetas = [{"pregunta": q["pregunta"],
                     "respuesta": q["opciones"][q["correcta"]] + (f" — {q['explicacion']}" if q.get("explicacion") else "")}
                    for q in falladas]
        n = db.agregar_tarjetas(self._quiz_libro["id"] if self._quiz_libro else 0, 0, tarjetas, "quiz")
        self.btn_falladas.configure(text=f"✓ {n} tarjetas creadas", state="disabled")
        self.app.actualizar_insignia_repaso()

    # ================================================================== TARJETAS
    def _armar_tarjetas(self):
        t = self.t_tarj
        ctl = ctk.CTkFrame(t, fg_color="transparent")
        ctl.pack(fill="x", padx=28, pady=(6, 8))
        ctl.columnconfigure(1, weight=1)
        self.menu_tarj_libro = ctk.CTkOptionMenu(ctl, values=[TODOS], width=260, command=self._filtrar_tarjetas,
                                                 fg_color=C["tarjeta"], button_color=C["tarjeta_hover"],
                                                 text_color=C["texto"], font=fuente(12))
        self.menu_tarj_libro.grid(row=0, column=0)
        self.ent_buscar_t = ctk.CTkEntry(ctl, placeholder_text="Buscar en las tarjetas…", fg_color=C["tarjeta"], border_color=C["borde"])
        self.ent_buscar_t.grid(row=0, column=1, sticky="ew", padx=8)
        self.ent_buscar_t.bind("<KeyRelease>", lambda e: self._pintar_tarjetas(False))
        boton(ctl, "＋ Nueva tarjeta", self._nueva_tarjeta, width=140).grid(row=0, column=2)
        self.lista_t = ctk.CTkScrollableFrame(t, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.lista_t.pack(fill="both", expand=True, padx=(22, 14), pady=(0, 14))
        self._filtro_t = None

    def _filtrar_tarjetas(self, etiqueta):
        self._filtro_t = self._mapa_t.get(etiqueta)
        self._pintar_tarjetas(False)

    def _pintar_tarjetas(self, refrescar_menu=True):
        if refrescar_menu:
            self._mapa_t = {TODOS: None}
            for rid, nombre, n in db.libros_con_tarjetas():
                self._mapa_t[f"{recortar(nombre, 40)} ({n})"] = rid
            self.menu_tarj_libro.configure(values=list(self._mapa_t))
            self.menu_tarj_libro.set(next((k for k, v in self._mapa_t.items() if v == self._filtro_t), TODOS))
        for w in self.lista_t.winfo_children():
            w.destroy()
        tarjetas = db.listar_tarjetas(self._filtro_t, self.ent_buscar_t.get(), 200)
        if not tarjetas:
            estado_vacio(self.lista_t, "🃏", "No hay tarjetas",
                         "Crea una con «＋ Nueva tarjeta» o pídele al tutor que las genere desde el lector.").pack(pady=20)
            return
        for t in tarjetas:
            self._fila_tarjeta(t)

    def _fila_tarjeta(self, t):
        f = tarjeta(self.lista_t)
        f.pack(fill="x", pady=3, padx=2)
        f.columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=recortar(t["pregunta"], 200), font=fuente(13, "bold"), text_color=C["texto"], anchor="w",
                     justify="left", wraplength=560).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(f, text=recortar(t["respuesta"], 260), font=fuente(12), text_color=C["texto2"], anchor="w",
                     justify="left", wraplength=560).grid(row=1, column=0, sticky="w", padx=14)
        libro = (t.get("libro") or "")
        libro = libro[:-4] if libro.lower().endswith(".pdf") else libro
        meta = [recortar(libro, 40)] if libro else []
        if t["pagina"]:
            meta.append(f"p. {t['pagina']}")
        meta.append("nueva" if t["estado"] == "nueva" else f"próximo repaso: {t['proxima']}")
        subtitulo(f, " · ".join(meta), 10).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))
        acc = ctk.CTkFrame(f, fg_color="transparent")
        acc.grid(row=0, column=1, rowspan=3, padx=8)
        for simbolo, cmd in (("✎", lambda x=t: self._editar_tarjeta(x)), ("✕", lambda x=t: self._borrar_tarjeta(x))):
            ctk.CTkButton(acc, text=simbolo, width=30, height=28, fg_color="transparent", hover_color=C["borde"],
                          text_color=C["texto2"], font=fuente(13), command=cmd).pack(side="left")

    def _nueva_tarjeta(self):
        def guardar(p, r):
            libro = self._filtro_t or 0
            db.agregar_tarjetas(libro, 0, [{"pregunta": p, "respuesta": r}], "manual")
            self._pintar_tarjetas()
            self.app.actualizar_insignia_repaso()
        DialogoTarjeta(self, "Nueva tarjeta", al_guardar=guardar)

    def _editar_tarjeta(self, t):
        def guardar(p, r):
            db.actualizar_tarjeta(t["id"], p, r)
            self._pintar_tarjetas()
        DialogoTarjeta(self, "Editar tarjeta", t["pregunta"], t["respuesta"], guardar)

    def _borrar_tarjeta(self, t):
        if messagebox.askyesno("Borrar tarjeta", "¿Borrar esta tarjeta y su historial de repasos?"):
            db.borrar_tarjeta(t["id"])
            self._pintar_tarjetas()
            self.app.actualizar_insignia_repaso()
