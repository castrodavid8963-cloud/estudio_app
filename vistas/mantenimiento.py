"""Pestaña Mantenimiento: respaldos, exportación de tus datos, OCR de libros escaneados y ubicación de los datos."""
import os
import subprocess
import sys
import threading
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

import buscador
import database as db
import ocr
import respaldo
from datos import carpeta_datos
from tema import C, fuente, tarjeta, titulo, subtitulo, boton, barra, recortar


def abrir_en_explorador(ruta: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)                                    # noqa: S606 (solo Windows)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", ruta])
        else:
            subprocess.Popen(["xdg-open", ruta])
    except OSError as e:
        messagebox.showinfo("Abrir carpeta", f"No pude abrir la carpeta:\n{ruta}\n\n{e}")


class PestanaMantenimiento(ctk.CTkScrollableFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.app = app
        self.columnconfigure(0, weight=1)
        self.trabajo_ocr = ocr.TrabajoOCR(self._ocr_progreso, debe_ceder=lambda: getattr(app, "lector_visible", False))
        self._pendientes_ocr = []
        self._armar_respaldo()
        self._armar_exportar()
        self._armar_ocr()
        self._armar_datos()

    def al_mostrar(self):
        self._refrescar_respaldo()
        self._refrescar_ocr()

    # ================================================================== respaldo
    def _armar_respaldo(self):
        t = tarjeta(self)
        t.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 10))
        t.columnconfigure(0, weight=1)
        titulo(t, "💾 Respaldo de tus datos", 15).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 0))
        subtitulo(t, "Guarda tu progreso, notas, tarjetas, rutas y tiempo de estudio en un .zip. No incluye tus PDF "
                     "ni el índice de búsqueda (ese se puede reconstruir).", 12, wraplength=640
                  ).grid(row=1, column=0, sticky="w", padx=18)
        self.lbl_respaldo = ctk.CTkLabel(t, text="", font=fuente(13, "bold"), text_color=C["texto"], anchor="w")
        self.lbl_respaldo.grid(row=2, column=0, sticky="w", padx=18, pady=(10, 0))
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.grid(row=3, column=0, sticky="w", padx=14, pady=(8, 4))
        boton(fila, "Crear respaldo ahora", self._crear_respaldo, width=170).pack(side="left", padx=4)
        boton(fila, "Restaurar desde .zip…", self._restaurar, "suave", width=170).pack(side="left", padx=4)
        boton(fila, "Abrir carpeta", lambda: abrir_en_explorador(self._carpeta_respaldos()), "fantasma", width=120
              ).pack(side="left", padx=4)
        self.var_auto = ctk.BooleanVar(value=respaldo.automatico_activo())
        ctk.CTkCheckBox(t, text="Hacer un respaldo automático al cerrar la app (cada 7 días, se conservan los últimos 10)",
                        variable=self.var_auto, font=fuente(12), checkbox_height=18, checkbox_width=18,
                        command=lambda: db.guardar_config("respaldo_auto", "1" if self.var_auto.get() else "0")
                        ).grid(row=4, column=0, sticky="w", padx=18, pady=(6, 0))
        self.lbl_carpeta_resp = subtitulo(t, "", 11, wraplength=620)
        self.lbl_carpeta_resp.grid(row=5, column=0, sticky="w", padx=18, pady=(4, 0))
        boton(t, "Cambiar carpeta de respaldos…", self._cambiar_carpeta, "fantasma", height=24, font=fuente(11), width=200
              ).grid(row=6, column=0, sticky="w", padx=14, pady=(0, 6))
        self.caja_lista = ctk.CTkFrame(t, fg_color="transparent", height=1)
        self.caja_lista.grid(row=7, column=0, sticky="ew", padx=18, pady=(0, 14))

    def _carpeta_respaldos(self) -> str:
        return respaldo.carpeta_respaldos()

    def _refrescar_respaldo(self):
        carpeta = self._carpeta_respaldos()
        dias = respaldo.dias_desde_ultimo(carpeta)
        if dias is None:
            self.lbl_respaldo.configure(text="⚠ Aún no hay ningún respaldo.", text_color=C["aviso"])
        else:
            texto = "hoy" if dias == 0 else f"hace {dias} día{'s' if dias != 1 else ''}"
            self.lbl_respaldo.configure(text=f"Último respaldo: {texto}",
                                        text_color=C["ok"] if dias < 8 else C["aviso"])
        self.lbl_carpeta_resp.configure(text=f"Carpeta: {carpeta}")
        for w in self.caja_lista.winfo_children():
            w.destroy()
        for ruta, m in respaldo.listar_respaldos(carpeta)[:5]:
            c = m.get("contenido", {})
            ctk.CTkLabel(self.caja_lista, anchor="w", font=fuente(11), text_color=C["texto2"],
                         text=f"•  {m.get('creado', '')[:16].replace('T', ' ')}  —  {c.get('recursos', 0)} libros, "
                              f"{c.get('notas', 0)} notas, {c.get('tarjetas', 0)} tarjetas"
                              f"  ({os.path.getsize(ruta) // 1024} KB)").pack(anchor="w")

    def _crear_respaldo(self):
        try:
            ruta = respaldo.crear_respaldo(db.DB_NAME, self._carpeta_respaldos())
            respaldo.rotar(self._carpeta_respaldos(), 10)
        except Exception as e:
            messagebox.showerror("Respaldo", f"No se pudo crear el respaldo:\n{e}")
            return
        self._refrescar_respaldo()
        messagebox.showinfo("Respaldo", f"Listo. Guardado en:\n{ruta}")

    def _cambiar_carpeta(self):
        carpeta = filedialog.askdirectory(title="Carpeta para los respaldos", initialdir=self._carpeta_respaldos())
        if carpeta:
            db.guardar_config("ruta_respaldos", carpeta)
            self._refrescar_respaldo()

    def _restaurar(self):
        zip_ruta = filedialog.askopenfilename(title="Elige un respaldo", initialdir=self._carpeta_respaldos(),
                                              filetypes=[("Respaldo del Hub de Estudio", "*.zip")])
        if not zip_ruta:
            return
        try:
            m = respaldo.leer_manifiesto(zip_ruta)
        except ValueError as e:
            messagebox.showerror("Restaurar", str(e))
            return
        c = m.get("contenido", {})
        if not messagebox.askyesno(
                "Restaurar respaldo",
                f"Respaldo del {m.get('creado', '')[:16].replace('T', ' ')}\n"
                f"({c.get('recursos', 0)} libros, {c.get('notas', 0)} notas, {c.get('tarjetas', 0)} tarjetas)\n\n"
                "Esto REEMPLAZA tus datos actuales. Antes se guarda una copia de seguridad de lo de ahora "
                "(estudios.antes_de_restaurar.db).\n\n¿Continuar?"):
            return
        try:
            seguridad = respaldo.restaurar(zip_ruta, db.DB_NAME)
        except Exception as e:
            messagebox.showerror("Restaurar", f"No se pudo restaurar:\n{e}")
            return
        messagebox.showinfo("Restaurar", "Datos restaurados. La app se cerrará ahora; ábrela de nuevo para ver los cambios."
                            + (f"\n\nTu base anterior quedó en:\n{seguridad}" if seguridad else ""))
        self.app.al_cerrar()

    # ================================================================== exportar
    def _armar_exportar(self):
        t = tarjeta(self)
        t.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        titulo(t, "📤 Exportar lo tuyo", 15).pack(anchor="w", padx=18, pady=(16, 0))
        subtitulo(t, "Formatos abiertos, por si quieres usar tus notas y tarjetas en otra herramienta.", 12
                  ).pack(anchor="w", padx=18)
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.pack(anchor="w", padx=14, pady=(8, 16))
        boton(fila, "Todo en JSON", self._exp_json, "suave", width=130).pack(side="left", padx=4)
        boton(fila, "Tarjetas (CSV: Excel / Anki)", self._exp_csv, "suave", width=210).pack(side="left", padx=4)
        boton(fila, "Notas (Markdown)", self._exp_md, "suave", width=150).pack(side="left", padx=4)

    def _pedir_destino(self, nombre, ext, tipos):
        return filedialog.asksaveasfilename(title="Guardar como", defaultextension=ext, filetypes=tipos,
                                            initialfile=f"{nombre}_{datetime.now().strftime('%Y%m%d')}{ext}")

    def _exp_json(self):
        d = self._pedir_destino("estudio_datos", ".json", [("JSON", "*.json")])
        if d:
            c = respaldo.exportar_json(db.DB_NAME, d)
            messagebox.showinfo("Exportar", "Exportado: " + ", ".join(f"{v} {k}" for k, v in c.items()))

    def _exp_csv(self):
        d = self._pedir_destino("tarjetas", ".csv", [("CSV", "*.csv")])
        if d:
            messagebox.showinfo("Exportar", f"{respaldo.exportar_tarjetas_csv(db.DB_NAME, d)} tarjetas exportadas.")

    def _exp_md(self):
        d = self._pedir_destino("notas", ".md", [("Markdown", "*.md")])
        if d:
            with open(d, "w", encoding="utf-8") as f:
                f.write(db.exportar_notas_markdown(None))
            messagebox.showinfo("Exportar", "Notas exportadas.")

    # ================================================================== OCR
    def _armar_ocr(self):
        t = tarjeta(self)
        t.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        t.columnconfigure(0, weight=1)
        titulo(t, "🔎 Libros escaneados (OCR)", 15).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 0))
        subtitulo(t, "Los PDF que son fotos de páginas no tienen texto: no aparecen en la búsqueda y el tutor no puede leerlos. "
                     "El OCR los reconoce y guarda el texto aparte; tu PDF no se modifica. Es lento (unos segundos por "
                     "página), pero puedes detenerlo y retomarlo cuando quieras.", 12, wraplength=640
                  ).grid(row=1, column=0, sticky="w", padx=18)
        self.lbl_ocr_estado = ctk.CTkLabel(t, text="", font=fuente(12), anchor="w", justify="left", wraplength=640)
        self.lbl_ocr_estado.grid(row=2, column=0, sticky="w", padx=18, pady=(8, 0))
        self.lbl_ocr_cuenta = ctk.CTkLabel(t, text="", font=fuente(13, "bold"), text_color=C["texto"], anchor="w")
        self.lbl_ocr_cuenta.grid(row=3, column=0, sticky="w", padx=18, pady=(4, 0))
        self.barra_ocr = barra(t, 0, C["acento"])
        self.lbl_ocr_prog = subtitulo(t, "", 11, wraplength=620)
        fila = ctk.CTkFrame(t, fg_color="transparent")
        fila.grid(row=6, column=0, sticky="w", padx=14, pady=(8, 16))
        self.btn_ocr = boton(fila, "Aplicar OCR", self._iniciar_ocr, width=170)
        self.btn_ocr.pack(side="left", padx=4)
        self.btn_ocr_parar = boton(fila, "Detener", self.trabajo_ocr.detener, "suave", width=90, state="disabled")
        self.btn_ocr_parar.pack(side="left", padx=4)

    def _refrescar_ocr(self):
        est = ocr.estado()
        self.lbl_ocr_estado.configure(text=("✓ " if est["disponible"] else "⚠ ") + est["mensaje"],
                                      text_color=C["ok"] if est["disponible"] else C["aviso"])
        if self.trabajo_ocr.activo:
            return
        try:
            self._pendientes_ocr = buscador.libros_escaneados()
        except Exception:
            self._pendientes_ocr = []
        n = len(self._pendientes_ocr)
        self.lbl_ocr_cuenta.configure(
            text=(f"{n} libro{'s' if n != 1 else ''} escaneado{'s' if n != 1 else ''} esperando OCR" if n else
                  "No hay libros escaneados pendientes. (Primero deja que termine el indexado de «Buscar».)"))
        self.btn_ocr.configure(state="normal" if (n and est["disponible"]) else "disabled",
                               text=f"Aplicar OCR a {n}" if n else "Aplicar OCR")

    def _iniciar_ocr(self):
        if not self._pendientes_ocr or self.trabajo_ocr.activo:
            return
        if not messagebox.askyesno("OCR", f"Se reconocerán {len(self._pendientes_ocr)} libros. Puede tardar mucho "
                                          "(el equipo trabajará en segundo plano). Puedes detenerlo cuando quieras. ¿Empezar?"):
            return
        self.btn_ocr.configure(state="disabled")
        self.btn_ocr_parar.configure(state="normal")
        self.barra_ocr.grid(row=4, column=0, sticky="ew", padx=18, pady=(8, 2))
        self.lbl_ocr_prog.grid(row=5, column=0, sticky="w", padx=18)
        self.trabajo_ocr.iniciar(list(self._pendientes_ocr))

    def _ocr_progreso(self, libros_hechos, libros_total, titulo_libro, pagina, paginas, terminado):
        self.app._en_ui(self._pintar_ocr, libros_hechos, libros_total, titulo_libro, pagina, paginas, terminado)

    def _pintar_ocr(self, hechos, total, nombre, pagina, paginas, terminado):
        try:
            if terminado:
                self.btn_ocr_parar.configure(state="disabled")
                self.barra_ocr.grid_remove()
                err = self.trabajo_ocr.ultimo_error
                self.lbl_ocr_prog.configure(text=(f"Terminado: {hechos}/{total} libros." if not err else
                                                  f"Terminó con avisos ({self.trabajo_ocr.errores}): {err}"))
                self._refrescar_ocr()
                self.app.vistas["buscar"].al_mostrar() if self.app._vista_actual == "buscar" else None
                return
            frac = ((hechos + (pagina / paginas if paginas else 0)) / total) if total else 0
            self.barra_ocr.set(frac)
            self.lbl_ocr_prog.configure(text=f"Libro {hechos + 1} de {total}: {recortar(nombre, 60)} — página {pagina}/{paginas}")
        except Exception:
            pass

    # ================================================================== datos
    def _armar_datos(self):
        t = tarjeta(self)
        t.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        titulo(t, "📁 Dónde están tus datos", 15).pack(anchor="w", padx=18, pady=(16, 0))
        subtitulo(t, f"Base de datos, portadas e historiales: {carpeta_datos()}\nÍndice de búsqueda: {buscador.ruta_indice()}",
                  12, wraplength=640).pack(anchor="w", padx=18, pady=(0, 6))
        boton(t, "Abrir carpeta de datos", lambda: abrir_en_explorador(carpeta_datos()), "fantasma", width=170
              ).pack(anchor="w", padx=14, pady=(0, 14))
