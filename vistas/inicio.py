"""Pantalla de inicio: continuar leyendo, tiempo de estudio, racha y siguiente paso de tu ruta."""
import customtkinter as ctk

import database as db
import roadmap
import tiempo
from tema import C, fuente, tarjeta, titulo, subtitulo, boton, barra, chip, estado_vacio, recortar, fecha_relativa, nombre_area


class VistaInicio(ctk.CTkScrollableFrame):
    def __init__(self, padre, app):
        super().__init__(padre, fg_color="transparent", scrollbar_button_color=C["borde"])
        self.app = app

    # ------------------------------------------------------------------ ciclo de vida
    def al_mostrar(self):
        for w in self.winfo_children():
            w.destroy()
        self.columnconfigure(0, weight=1)

        libros = db.listar_libros(incluir_excluidos=False)
        titulo(self, "Hola 👋", 26).grid(row=0, column=0, sticky="w", padx=28, pady=(24, 0))
        subtitulo(self, self._frase(libros)).grid(row=1, column=0, sticky="w", padx=28, pady=(2, 16))

        if not libros:
            estado_vacio(self, "📚", "Tu biblioteca está vacía",
                         "Elige la carpeta raíz donde guardas tus PDFs y la app los detectará, "
                         "generará portadas y armará tus rutas de estudio.",
                         "Elegir carpeta de biblioteca", lambda: self.app.ir("herramientas", pestaña="Biblioteca")
                         ).grid(row=2, column=0, pady=20)
            return

        self._tarjeta_continuar(2)
        self._fila_estadisticas(3)
        self._grafica(4)
        self._ruta_activa(libros, 5)
        self._mas_estudiados(6)

    @staticmethod
    def _frase(libros):
        hoy = tiempo.segundos_hoy()
        meta = tiempo.meta_diaria_segundos()
        if hoy >= meta:
            return f"¡Meta de hoy cumplida! Llevas {tiempo.formatear(hoy)} estudiando."
        if hoy > 0:
            return f"Llevas {tiempo.formatear(hoy)} hoy. Te faltan {tiempo.formatear(meta - hoy)} para tu meta."
        return "Abre un libro y el tiempo se registra solo: sin botones de entrada ni salida."

    # ------------------------------------------------------------------ bloques
    def _tarjeta_continuar(self, fila):
        libro = db.libro_para_continuar()
        marco = tarjeta(self, fg_color=C["acento_suave"], border_color=C["acento"])
        marco.grid(row=fila, column=0, sticky="ew", padx=28, pady=(0, 14))
        marco.columnconfigure(1, weight=1)
        if not libro:
            ctk.CTkLabel(marco, text="📖", font=fuente(34)).grid(row=0, column=0, rowspan=2, padx=20, pady=18)
            titulo(marco, "Empieza por donde quieras", 17).grid(row=0, column=1, sticky="w", pady=(16, 0))
            subtitulo(marco, "Elige una ruta de estudio o explora tu biblioteca.").grid(row=1, column=1, sticky="w", pady=(0, 16))
            boton(marco, "Ver rutas", lambda: self.app.ir("rutas")).grid(row=0, column=2, rowspan=2, padx=20)
            return

        portada = ctk.CTkLabel(marco, text="📕", font=fuente(34), width=70)
        portada.grid(row=0, column=0, rowspan=3, padx=(18, 6), pady=16)
        self.app.portadas.pedir(libro["ruta"], lambda img, w=portada: img and w.configure(image=img, text=""),
                                tam=(70, 96))
        chip(marco, "CONTINUAR LEYENDO", C["acento"], C["fondo"]).grid(row=0, column=1, sticky="w", pady=(18, 0))
        titulo(marco, recortar(libro["titulo"], 70), 17).grid(row=1, column=1, sticky="w")
        pag = f"Página {libro['ultima_pagina']} de {libro['total_paginas']}" if libro["total_paginas"] else "Sin abrir el lector aún"
        if libro["modo_efectivo"] == "capitulos" and libro["caps_total"]:
            pag = f"{libro['caps_hechos']} de {libro['caps_total']} capítulos · {pag}"
        subtitulo(marco, f"{pag} · {int(libro['avance'] * 100)}% · {fecha_relativa(libro['ultima_apertura'])}").grid(
            row=2, column=1, sticky="w", pady=(0, 16))
        boton(marco, "Continuar  ›", lambda: self.app.abrir_libro(libro["id"]), width=130, height=38
              ).grid(row=0, column=2, rowspan=3, padx=20)

    def _fila_estadisticas(self, fila):
        marco = ctk.CTkFrame(self, fg_color="transparent")
        marco.grid(row=fila, column=0, sticky="ew", padx=28, pady=(0, 14))
        for i in range(4):
            marco.columnconfigure(i, weight=1, uniform="est")
        hoy, meta = tiempo.segundos_hoy(), tiempo.meta_diaria_segundos()
        racha = tiempo.racha_dias()
        cuentas = db.contar_por_estado()
        datos = [
            ("HOY", tiempo.formatear(hoy), f"meta {tiempo.formatear(meta)}", min(1, hoy / meta), C["acento"]),
            ("RACHA", f"{racha} día{'s' if racha != 1 else ''}", "días seguidos estudiando", None, C["aviso"]),
            ("ESTA SEMANA", tiempo.formatear(tiempo.segundos_semana()), f"total {tiempo.formatear(tiempo.total_segundos())}", None, C["ok"]),
            ("LIBROS", f"{cuentas['Completado']} leídos", f"{cuentas['En progreso']} en curso · {cuentas['Sin empezar']} por empezar", None, "#60a5fa"),
        ]
        tarjetas = []
        for i, (rot, valor, detalle, prog, color) in enumerate(datos):
            t = tarjeta(marco)
            tarjetas.append(t)
            ctk.CTkLabel(t, text=rot, font=fuente(10, "bold"), text_color=C["texto3"]).pack(anchor="w", padx=16, pady=(14, 0))
            ctk.CTkLabel(t, text=valor, font=fuente(22, "bold"), text_color=color).pack(anchor="w", padx=16)
            ctk.CTkLabel(t, text=detalle, font=fuente(11), text_color=C["texto2"], wraplength=150, justify="left").pack(anchor="w", padx=16, pady=(0, 6 if prog is not None else 14))
            if prog is not None:
                barra(t, prog, color).pack(fill="x", padx=16, pady=(0, 14))

        def distribuir(_e=None):
            cols = 4 if marco.winfo_width() >= 700 else 2
            for c in range(4):
                marco.columnconfigure(c, weight=1 if c < cols else 0, uniform="est" if c < cols else "")
            for i, t in enumerate(tarjetas):
                t.grid(row=i // cols, column=i % cols, sticky="nsew", padx=5, pady=5)
        marco.bind("<Configure>", distribuir)
        distribuir()

    def _grafica(self, fila):
        marco = tarjeta(self)
        marco.grid(row=fila, column=0, sticky="ew", padx=28, pady=(0, 14))
        titulo(marco, "Últimos 14 días", 14).pack(anchor="w", padx=18, pady=(14, 0))
        lienzo = ctk.CTkCanvas(marco, height=120, bg=C["tarjeta"], highlightthickness=0)
        lienzo.pack(fill="x", padx=18, pady=(4, 14))
        datos = tiempo.segundos_por_dia(14)
        meta = tiempo.meta_diaria_segundos()

        def dibujar(_e=None):
            lienzo.delete("all")
            w, h = max(lienzo.winfo_width(), 200), 120
            maximo = max(max(datos.values()), meta, 1)
            n = len(datos)
            ancho = w / n
            base = h - 20
            y_meta = base - (base - 8) * meta / maximo
            lienzo.create_line(0, y_meta, w, y_meta, fill=C["borde"], dash=(4, 4))
            for i, (dia, seg) in enumerate(datos.items()):
                alto = (base - 8) * seg / maximo
                x0 = i * ancho + ancho * 0.18
                x1 = (i + 1) * ancho - ancho * 0.18
                color = C["ok"] if seg >= meta else C["acento"] if seg else C["pista"]
                lienzo.create_rectangle(x0, base - max(alto, 3), x1, base, fill=color, outline="")
                if i % 2 == 1 or i == n - 1:
                    lienzo.create_text((x0 + x1) / 2, h - 7, text=dia[8:], fill=C["texto3"], font=("TkDefaultFont", 8))
        lienzo.bind("<Configure>", dibujar)
        self.after(50, dibujar)

    def _ruta_activa(self, libros, fila):
        oid = db.obtener_config("objetivo_activo")
        if oid not in roadmap.OBJETIVOS:
            return
        r = roadmap.generar_roadmap(oid, libros, db.obtener_ajustes_roadmap(oid))
        marco = tarjeta(self)
        marco.grid(row=fila, column=0, sticky="ew", padx=28, pady=(0, 14))
        marco.columnconfigure(1, weight=1)
        ctk.CTkLabel(marco, text=r["icono"], font=fuente(30)).grid(row=0, column=0, rowspan=3, padx=18, pady=16)
        chip(marco, "TU RUTA", r["color"], C["fondo"]).grid(row=0, column=1, sticky="w", pady=(14, 0))
        titulo(marco, r["nombre"], 16).grid(row=1, column=1, sticky="w")
        sig = r["siguiente"]
        txt = f"Siguiente: {recortar(sig['titulo'], 60)}" if sig else "¡Ruta completada!"
        subtitulo(marco, f"{r['completados']}/{r['total']} libros · {txt}").grid(row=2, column=1, sticky="w", pady=(0, 14))
        barra(marco, r["avance"], r["color"]).grid(row=3, column=0, columnspan=3, sticky="ew", padx=18, pady=(0, 14))
        boton(marco, "Abrir ruta", lambda: self.app.ir("rutas", objetivo=oid), "suave", width=110
              ).grid(row=0, column=2, rowspan=3, padx=18)
        if sig:
            boton(marco, "Leer", lambda: self.app.abrir_libro(sig["id"]), width=70).grid(row=0, column=3, rowspan=3, padx=(0, 18))

    def _mas_estudiados(self, fila):
        top = tiempo.libros_mas_estudiados(5)
        if not top:
            return
        marco = tarjeta(self)
        marco.grid(row=fila, column=0, sticky="ew", padx=28, pady=(0, 24))
        titulo(marco, "Lo que más has estudiado", 14).pack(anchor="w", padx=18, pady=(14, 6))
        maximo = max(s for _, _, s in top) or 1
        for rid, nombre, seg in top:
            f = ctk.CTkFrame(marco, fg_color="transparent")
            f.pack(fill="x", padx=18, pady=3)
            f.columnconfigure(1, weight=1)
            n = nombre[:-4] if nombre.lower().endswith(".pdf") else nombre
            ctk.CTkLabel(f, text=recortar(n, 46), font=fuente(12), text_color=C["texto"], anchor="w", width=300
                         ).grid(row=0, column=0, sticky="w")
            barra(f, seg / maximo, C["acento"], alto=8).grid(row=0, column=1, sticky="ew", padx=10)
            ctk.CTkLabel(f, text=tiempo.formatear(seg), font=fuente(12), text_color=C["texto2"], width=80, anchor="e"
                         ).grid(row=0, column=2)
        ctk.CTkLabel(marco, text="", height=8).pack()
