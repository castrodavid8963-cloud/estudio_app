import os
import json
import threading
from datetime import datetime
from tkinter import filedialog
import customtkinter as ctk
from PIL import Image

from database import inicializar_db, obtener_conexion
from services import asegurar_ollama_activo
from timer import CronometroEstudio
from ai_pdf import extraer_texto_pdf, consultar_ollama_con_contexto
from library_scanner import escanear_e_indexar_biblioteca, obtener_ruta_guardada
from cover_generator import obtener_o_generar_portada

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# PALETA DE COLORES POR ESTADO DE LECTURA
ESTILOS_ESTADO = {
    "Sin empezar": {
        "badge_bg": "#374151",      # Gris oscuro
        "badge_hover": "#4b5563",
        "border_color": "#4b5563",
        "texto_indicador": "⚪ Sin empezar"
    },
    "En progreso": {
        "badge_bg": "#b45309",      # Ámbar / Naranja
        "badge_hover": "#d97706",
        "border_color": "#f59e0b",
        "texto_indicador": "🟡 En progreso"
    },
    "Completado": {
        "badge_bg": "#047857",      # Verde Esmeralda
        "badge_hover": "#059669",
        "border_color": "#10b981",
        "texto_indicador": "🟢 Completado"
    }
}

class AppEstudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Hub de Estudio & Clock-In Inteligente")
        self.geometry("1200x750")
        self.minsize(900, 600)

        self.cronometro = CronometroEstudio()
        self.texto_pdf_actual = ""
        self.nombre_pdf_actual = "Ninguno"
        self.materia_seleccionada_actual = "Seleccionar Materia"
        self.recursos_datos = []
        self.materias_datos = {}
        self._columnas_actuales = 0
        self._bind_id = None
        self.preguntas_sesion_actual = []

        inicializar_db()
        self.ollama_listo = asegurar_ollama_activo()

        self.crear_layout()
        self.cargar_materias()
        self.actualizar_reloj_loop()

    def crear_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ----------------- PANEL IZQUIERDO (SIDEBAR) -----------------
        self.sidebar = ctk.CTkScrollableFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.lbl_sidebar = ctk.CTkLabel(self.sidebar, text="📌 Estado General", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_sidebar.pack(padx=15, pady=(15, 10))

        self.lbl_materia_activa_sidebar = ctk.CTkLabel(
            self.sidebar, 
            text="Materia: Ninguna", 
            font=ctk.CTkFont(size=12, weight="bold"),
            wraplength=220,
            text_color="#38bdf8"
        )
        self.lbl_materia_activa_sidebar.pack(padx=15, pady=5)

        self.btn_nueva_materia = ctk.CTkButton(self.sidebar, text="+ Nueva Materia", command=self.abrir_ventana_nueva_materia)
        self.btn_nueva_materia.pack(padx=15, pady=10, fill="x")

        self.btn_sincronizar = ctk.CTkButton(
            self.sidebar, text="⚡ Indexar Directorio...", fg_color="teal", hover_color="darkslategrey", command=self.indexar_biblioteca
        )
        self.btn_sincronizar.pack(padx=15, pady=5, fill="x")

        self.lbl_pdf_sec = ctk.CTkLabel(self.sidebar, text="📄 PDF Activo en IA", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_pdf_sec.pack(padx=15, pady=(15, 2))

        self.lbl_nombre_pdf = ctk.CTkLabel(self.sidebar, text="Sin PDF cargado", font=ctk.CTkFont(size=11), wraplength=220)
        self.lbl_nombre_pdf.pack(padx=15, pady=2)

        self.lbl_timer_sidebar = ctk.CTkLabel(self.sidebar, text="⏱ 00:00:00", font=ctk.CTkFont(size=14, weight="bold"), text_color="#1f538d")
        self.lbl_timer_sidebar.pack(pady=(15, 5))

        estado_ollama_text = "🟢 IA Local Lista" if self.ollama_listo else "🔴 IA Desconectada"
        self.lbl_estado_ia = ctk.CTkLabel(self.sidebar, text=estado_ollama_text, font=ctk.CTkFont(size=12))
        self.lbl_estado_ia.pack(pady=(10, 10))

        # ----------------- PANEL CENTRAL (TABVIEW) -----------------
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.tab_materias = self.tabview.add("📚 Materias")
        self.tab_timer = self.tabview.add("⏱ Clock-In")
        self.tab_pdf = self.tabview.add("📄 Biblioteca Visual")
        self.tab_ia = self.tabview.add("🤖 Tutor IA")

        # --- Pestaña 0: Vista en Cuadrícula de Materias ---
        self.crear_vista_materias_grid()

        # --- Pestaña 1: Clock-In ---
        self.lbl_materia_activa_timer = ctk.CTkLabel(self.tab_timer, text="Materia Activa: Ninguna", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_materia_activa_timer.pack(pady=(20, 5))

        self.lbl_timer = ctk.CTkLabel(self.tab_timer, text="00:00:00", font=ctk.CTkFont(size=64, weight="bold"))
        self.lbl_timer.pack(pady=(20, 20))

        self.frame_botones = ctk.CTkFrame(self.tab_timer, fg_color="transparent")
        self.frame_botones.pack(pady=10)

        self.btn_clock_in = ctk.CTkButton(self.frame_botones, text="⏱ Clock In", fg_color="green", hover_color="darkgreen", command=self.clock_in)
        self.btn_clock_in.grid(row=0, column=0, padx=10)

        self.btn_pausa = ctk.CTkButton(self.frame_botones, text="⏸️ Pausa", fg_color="orange", hover_color="darkorange", command=self.pausar)
        self.btn_pausa.grid(row=0, column=1, padx=10)

        self.btn_clock_out = ctk.CTkButton(self.frame_botones, text="⏹️ Clock Out", fg_color="red", hover_color="darkred", command=self.clock_out)
        self.btn_clock_out.grid(row=0, column=2, padx=10)

        self.lbl_notas = ctk.CTkLabel(self.tab_timer, text="Notas o temas vistos en la sesión:")
        self.lbl_notas.pack(pady=(30, 5))
        self.txt_notas = ctk.CTkEntry(self.tab_timer, placeholder_text="¿Qué temas o ejercicios abordaste hoy?", width=450)
        self.txt_notas.pack(pady=5)

        # --- Pestaña 2: Biblioteca Visual ---
        self.frame_top_biblio = ctk.CTkFrame(self.tab_pdf, fg_color="transparent")
        self.frame_top_biblio.pack(fill="x", padx=10, pady=5)

        self.lbl_titulo_pdf = ctk.CTkLabel(self.frame_top_biblio, text="📖 Mis Libros y Documentos", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_titulo_pdf.pack(side="left")

        self.filtro_estado_var = ctk.StringVar(value="Todos")
        self.seg_filtro_estado = ctk.CTkSegmentedButton(
            self.frame_top_biblio, values=["Todos", "⭐ Favs", "🟡 En progreso", "🟢 Completados"],
            variable=self.filtro_estado_var, command=self.reagrupar_tarjetas_por_filtro
        )
        self.seg_filtro_estado.pack(side="right")

        self.container_biblio = ctk.CTkFrame(self.tab_pdf, fg_color="transparent")
        self.container_biblio.pack(padx=10, pady=10, fill="both", expand=True)

        self.scroll_grid = ctk.CTkScrollableFrame(
            self.container_biblio,
            scrollbar_button_color="#555555",
            scrollbar_button_hover_color="#777777"
        )
        self.scroll_grid.pack(fill="both", expand=True)

        # BINDING GLOBAL DE SCROLLING
        self.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.bind_all("<Button-4>", self._on_mousewheel_global)
        self.bind_all("<Button-5>", self._on_mousewheel_global)

        self.frame_loading = ctk.CTkFrame(self.container_biblio, fg_color="#1a1a1a", corner_radius=12)
        
        self.lbl_loading_title = ctk.CTkLabel(
            self.frame_loading, text="📚 Cargando Biblioteca...", font=ctk.CTkFont(size=20, weight="bold")
        )
        self.lbl_loading_title.pack(pady=(40, 15))

        self.progress_bar = ctk.CTkProgressBar(self.frame_loading, width=380, height=16)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        self.lbl_loading_status = ctk.CTkLabel(
            self.frame_loading, text="Por favor espera mientras procesamos los documentos...", font=ctk.CTkFont(size=12)
        )
        self.lbl_loading_status.pack(pady=(5, 40))

        self.activar_resize_event()

        # --- Pestaña 3: Tutor IA ---
        self.frame_top_chat = ctk.CTkFrame(self.tab_ia, fg_color="#1f1f1f", height=35)
        self.frame_top_chat.pack(fill="x", padx=10, pady=(5, 0))

        self.lbl_info_chat_materia = ctk.CTkLabel(
            self.frame_top_chat, 
            text="📖 Materia: Selecciona una materia | ⏱️ Sesión: Inactiva", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_info_chat_materia.pack(padx=10, pady=5, side="left")

        self.chat_history = ctk.CTkTextbox(
            self.tab_ia, 
            width=680, 
            height=350, 
            font=ctk.CTkFont(size=13, family="Consolas"),
            fg_color="#0f172a",
            text_color="#e2e8f0"
        )
        self.chat_history.pack(padx=10, pady=10, fill="both", expand=True)

        self.lbl_status_ia = ctk.CTkLabel(self.tab_ia, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="cyan")
        self.lbl_status_ia.pack(pady=(0, 5))

        self.frame_chat_input = ctk.CTkFrame(self.tab_ia, fg_color="transparent")
        self.frame_chat_input.pack(fill="x", padx=10, pady=(0, 10))

        self.txt_pregunta = ctk.CTkEntry(self.frame_chat_input, placeholder_text="Escribe tu consulta y presiona Enter...", font=ctk.CTkFont(size=13))
        self.txt_pregunta.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.txt_pregunta.bind("<Return>", lambda event: self.iniciar_hilo_ia())

        self.btn_enviar_ia = ctk.CTkButton(self.frame_chat_input, text="Enviar 💬", width=110, command=self.iniciar_hilo_ia)
        self.btn_enviar_ia.pack(side="right")

    # ----------------- CUADRÍCULA DE MATERIAS -----------------
    def crear_vista_materias_grid(self):
        """Construye el panel de la pestaña Mis Materias en formato de cuadrícula."""
        top_frame = ctk.CTkFrame(self.tab_materias, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=10)

        lbl_titulo = ctk.CTkLabel(
            top_frame, 
            text="📚 Catálogo de Materias", 
            font=ctk.CTkFont(size=20, weight="bold")
        )
        lbl_titulo.pack(side="left", padx=5)

        self.tipo_var = ctk.StringVar(value="Todas")
        self.seg_tipo = ctk.CTkSegmentedButton(
            top_frame, 
            values=["Todas", "Escuela", "Personal"],
            variable=self.tipo_var, 
            command=self.filtrar_materias_por_tipo
        )
        self.seg_tipo.pack(side="right", padx=5)

        self.grid_materias_frame = ctk.CTkScrollableFrame(self.tab_materias, fg_color="transparent")
        self.grid_materias_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def renderizar_grid_materias(self, materias_filtradas):
        """Dibuja las materias como tarjetas interactivas dentro de un Grid dinámico."""
        for child in self.grid_materias_frame.winfo_children():
            child.destroy()

        if not materias_filtradas:
            lbl_vacio = ctk.CTkLabel(
                self.grid_materias_frame, 
                text="No hay materias registradas en esta categoría.",
                font=ctk.CTkFont(size=14, slant="italic")
            )
            lbl_vacio.pack(pady=40)
            return

        columnas_max = 3
        for i in range(columnas_max):
            self.grid_materias_frame.grid_columnconfigure(i, weight=1)

        col, row = 0, 0
        for nombre_materia, datos in materias_filtradas.items():
            materia_id, tipo = datos[0], datos[1]

            card = ctk.CTkFrame(
                self.grid_materias_frame, 
                corner_radius=12, 
                fg_color="#1e293b",
                border_width=1,
                border_color="#334155"
            )
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

            lbl_icon = ctk.CTkLabel(card, text="📘" if tipo == "Escuela" else "📙", font=ctk.CTkFont(size=36))
            lbl_icon.pack(pady=(15, 5))

            lbl_nombre = ctk.CTkLabel(
                card, 
                text=nombre_materia, 
                font=ctk.CTkFont(size=14, weight="bold"),
                wraplength=180,
                justify="center"
            )
            lbl_nombre.pack(padx=10, pady=2)

            lbl_tipo = ctk.CTkLabel(
                card, 
                text=f"Categoría: {tipo}", 
                font=ctk.CTkFont(size=11),
                text_color="#94a3b8"
            )
            lbl_tipo.pack(pady=(0, 10))

            btn_abrir = ctk.CTkButton(
                card,
                text="Abrir Materia",
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#0284c7",
                hover_color="#0369a1",
                height=30,
                command=lambda m=nombre_materia: self.al_cambiar_materia(m)
            )
            btn_abrir.pack(padx=15, pady=(0, 15), fill="x")

            col += 1
            if col >= columnas_max:
                col = 0
                row += 1

    # ----------------- CONTROLES DE PANTALLA DE CARGA -----------------
    def mostrar_pantalla_carga(self, texto_inicial="Cargando documentos..."):
        self.scroll_grid.pack_forget()
        self.frame_loading.pack(fill="both", expand=True)
        self.progress_bar.set(0.05)
        self.lbl_loading_status.configure(text=texto_inicial)
        self.update()

    def actualizar_progreso_carga(self, valor_0_a_1, texto_estado):
        self.progress_bar.set(valor_0_a_1)
        self.lbl_loading_status.configure(text=texto_estado)
        self.update_idletasks()

    def ocultar_pantalla_carga(self):
        self.frame_loading.pack_forget()
        self.scroll_grid.pack(fill="both", expand=True)
        self.update()

    # ----------------- MANEJO DE SCROLL GLOBAL -----------------
    def _on_mousewheel_global(self, event):
        """Redirige el evento de la rueda del ratón al contenedor visible de forma fluida."""
        pestana_activa = self.tabview.get()
        target_scroll = None

        if pestana_activa == "📄 Biblioteca Visual":
            target_scroll = self.scroll_grid
        elif pestana_activa == "📚 Materias":
            target_scroll = self.grid_materias_frame

        if target_scroll:
            try:
                # Determinar dirección
                if event.num == 4:
                    delta = -1
                elif event.num == 5:
                    delta = 1
                else:
                    delta = int(-1 * (event.delta / 120))
                    if delta == 0:
                        delta = -1 if event.delta > 0 else 1

                # Mover el canvas de CustomTkinter
                target_scroll._parent_canvas.yview_scroll(delta, "units")
            except Exception:
                pass

    def activar_resize_event(self):
        if self._bind_id is None:
            self._bind_id = self.scroll_grid.bind("<Configure>", self._al_redimensionar_ventana)

    def desactivar_resize_event(self):
        if self._bind_id is not None:
            self.scroll_grid.unbind("<Configure>", self._bind_id)
            self._bind_id = None

    # ----------------- MANEJO DE MATERIAS -----------------
    def cargar_materias(self):
        """Carga las materias desde la BD y las envía a la cuadrícula."""
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nombre, COALESCE(tipo, 'Personal') FROM materias ORDER BY nombre ASC")
            filas = cursor.fetchall()

        self.materias_datos = {row[1]: (row[0], row[2]) for row in filas}
        self.filtrar_materias_por_tipo(self.tipo_var.get())

    def filtrar_materias_por_tipo(self, tipo_filtro):
        """Filtra y renderiza únicamente las tarjetas correspondientes a la categoría seleccionada."""
        if tipo_filtro == "Todas":
            materias_filtradas = self.materias_datos
        else:
            materias_filtradas = {
                nombre: datos for nombre, datos in self.materias_datos.items()
                if datos[1].strip().capitalize() == tipo_filtro.strip().capitalize()
            }
        
        self.renderizar_grid_materias(materias_filtradas)

    def al_cambiar_materia(self, materia_seleccionada):
        if materia_seleccionada in self.materias_datos:
            self.materia_seleccionada_actual = materia_seleccionada
            self.lbl_materia_activa_sidebar.configure(text=f"Materia: {materia_seleccionada}")
            self.lbl_materia_activa_timer.configure(text=f"Materia Activa: {materia_seleccionada}")
            self.actualizar_banner_chat_ia()
            self.cargar_recursos_de_materia(materia_seleccionada)
            self.tabview.set("📄 Biblioteca Visual")

    def cargar_recursos_de_materia(self, materia_seleccionada):
        if materia_seleccionada not in self.materias_datos:
            return

        materia_id = self.materias_datos[materia_seleccionada][0]
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT r.id, r.nombre_archivo, r.ruta_local, r.estado, r.es_favorito
            FROM recursos r
            JOIN semanas s ON r.semana_id = s.id
            WHERE s.materia_id = ?
            ORDER BY r.es_favorito DESC, r.nombre_archivo ASC
            """, (materia_id,))
            filas = cursor.fetchall()

        self.recursos_datos = [
            {"id": r[0], "nombre": r[1], "ruta": r[2], "estado": r[3], "favorito": bool(r[4])}
            for r in filas
        ]
        self._columnas_actuales = 0
        self.iniciar_renderizado_con_pantalla_carga()

    # ----------------- CARGA ASÍNCRONA CON PROGRESO -----------------
    def iniciar_renderizado_con_pantalla_carga(self):
        self.mostrar_pantalla_carga("Iniciando procesamiento de biblioteca...")
        threading.Thread(target=self._hilo_procesar_libros, daemon=True).start()

    def _hilo_procesar_libros(self):
        filtro = self.filtro_estado_var.get()
        libros_filtrados = []

        for rec in self.recursos_datos:
            if filtro == "⭐ Favs" and not rec["favorito"]:
                continue
            if filtro == "🟡 En progreso" and rec["estado"] != "En progreso":
                continue
            if filtro == "🟢 Completados" and rec["estado"] != "Completado":
                continue
            libros_filtrados.append(rec)

        total = len(libros_filtrados)
        if total == 0:
            self.after(0, self.renderizar_tarjetas_vacias)
            self.after(0, self.ocultar_pantalla_carga)
            return

        for i, rec in enumerate(libros_filtrados):
            progreso = (i + 1) / total
            msg = f"Procesando {i+1} de {total}: {rec['nombre']}"
            self.after(0, lambda p=progreso, m=msg: self.actualizar_progreso_carga(p, m))
            obtener_o_generar_portada(rec["ruta"])

        self.after(150, lambda: self._calcular_e_invocar_renderizado(libros_filtrados))

    def _calcular_e_invocar_renderizado(self, libros_filtrados):
        ancho_disponible = self.scroll_grid.winfo_width()
        if ancho_disponible < 100:
            ancho_disponible = self.winfo_width() - 320

        columnas_optimas = max(1, ancho_disponible // 220)
        self._columnas_actuales = columnas_optimas
        self.renderizar_grid_libros(libros_filtrados)

    def _al_redimensionar_ventana(self, event):
        ancho = event.width
        if ancho < 50:
            return

        num_columnas = max(1, ancho // 220)

        if num_columnas != self._columnas_actuales:
            self._columnas_actuales = num_columnas
            self.renderizar_grid_libros()

    def renderizar_grid_libros(self, libros_a_renderizar=None):
        self.desactivar_resize_event()

        for widget in self.scroll_grid.winfo_children():
            widget.destroy()

        if libros_a_renderizar is None:
            filtro = self.filtro_estado_var.get()
            libros_filtrados = []
            for rec in self.recursos_datos:
                if filtro == "⭐ Favs" and not rec["favorito"]:
                    continue
                if filtro == "🟡 En progreso" and rec["estado"] != "En progreso":
                    continue
                if filtro == "🟢 Completados" and rec["estado"] != "Completado":
                    continue
                libros_filtrados.append(rec)
        else:
            libros_filtrados = libros_a_renderizar

        if not libros_filtrados:
            self.renderizar_tarjetas_vacias()
            self.ocultar_pantalla_carga()
            self.activar_resize_event()
            return

        col_count = max(1, self._columnas_actuales)

        for i in range(col_count):
            self.scroll_grid.grid_columnconfigure(i, weight=1)

        total_filas = 0
        for idx, rec in enumerate(libros_filtrados):
            row = idx // col_count
            col = idx % col_count
            total_filas = max(total_filas, row)

            estado_actual = rec["estado"] if rec["estado"] in ESTILOS_ESTADO else "Sin empezar"
            estilo = ESTILOS_ESTADO[estado_actual]

            card = ctk.CTkFrame(
                self.scroll_grid, 
                corner_radius=10, 
                fg_color="#2b2b2b",
                border_width=2,
                border_color=estilo["border_color"]
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)

            frame_card_top = ctk.CTkFrame(card, fg_color="transparent")
            frame_card_top.pack(fill="x", padx=5, pady=(5, 0))

            btn_fav_text = "⭐" if rec["favorito"] else "☆"
            btn_fav = ctk.CTkButton(
                frame_card_top, text=btn_fav_text, width=28, height=24, fg_color="transparent",
                hover_color="#444444", command=lambda r=rec: self.toggle_favorito(r)
            )
            btn_fav.pack(side="right")

            lbl_img = ctk.CTkLabel(card, text="📄\nCargando...", font=ctk.CTkFont(size=12), width=120, height=160)
            lbl_img.pack(pady=(0, 5))

            lbl_target = lbl_img
            threading.Thread(
                target=self._cargar_portada_asincrona,
                args=(rec["ruta"], lbl_target),
                daemon=True
            ).start()

            lbl_titulo = ctk.CTkLabel(
                card, text=rec["nombre"], font=ctk.CTkFont(size=11, weight="bold"),
                wraplength=180, justify="center"
            )
            lbl_titulo.pack(padx=8, pady=2, fill="x")

            frame_controles = ctk.CTkFrame(card, fg_color="transparent")
            frame_controles.pack(fill="x", padx=8, pady=(5, 10))

            estado_opt = ctk.CTkOptionMenu(
                frame_controles,
                values=["Sin empezar", "En progreso", "Completado"],
                font=ctk.CTkFont(size=10, weight="bold"),
                height=26,
                fg_color=estilo["badge_bg"],
                button_color=estilo["badge_bg"],
                button_hover_color=estilo["badge_hover"],
                dynamic_resizing=False
            )
            estado_opt.set(estado_actual)
            estado_opt.configure(command=lambda val, r=rec, c=card, opt=estado_opt: self.cambiar_estado_libro_con_estilo(r, val, c, opt))
            estado_opt.pack(fill="x", pady=2)

            btn_estudiar = ctk.CTkButton(
                frame_controles, 
                text="📖 Estudiar", 
                font=ctk.CTkFont(size=11, weight="bold"),
                height=26, 
                fg_color="#1f538d", 
                hover_color="#14375e",
                command=lambda r=rec: self.seleccionar_libro_para_estudio(r)
            )
            btn_estudiar.pack(fill="x", pady=2)

        padding_inferior = ctk.CTkFrame(self.scroll_grid, height=60, fg_color="transparent")
        padding_inferior.grid(row=total_filas + 1, column=0, columnspan=col_count, pady=10, sticky="ew")

# Forzar al Canvas a ajustar sus bordes reales al tamaño exacto de las tarjetas
        self.scroll_grid.update_idletasks()
        self.scroll_grid._parent_canvas.configure(
            scrollregion=self.scroll_grid._parent_canvas.bbox("all")
        )
        self.scroll_grid._parent_canvas.yview_moveto(0.0)

        self.ocultar_pantalla_carga()
        self.after(100, self.activar_resize_event)

    def _cargar_portada_asincrona(self, ruta_pdf, lbl_target):
        ruta_portada = obtener_o_generar_portada(ruta_pdf)
        if ruta_portada and os.path.exists(ruta_portada):
            try:
                img_pil = Image.open(ruta_portada)
                ctk_img = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(120, 160))
                self.after(0, lambda: lbl_target.configure(image=ctk_img, text=""))
            except Exception:
                self.after(0, lambda: lbl_target.configure(text="📄\nSin Portada"))
        else:
            self.after(0, lambda: lbl_target.configure(text="📄\nSin Portada"))

    def renderizar_tarjetas_vacias(self):
        for widget in self.scroll_grid.winfo_children():
            widget.destroy()
        lbl = ctk.CTkLabel(self.scroll_grid, text="No hay libros registrados con este filtro.", font=ctk.CTkFont(size=14))
        lbl.pack(pady=40)

    def reagrupar_tarjetas_por_filtro(self, _val):
        self.iniciar_renderizado_con_pantalla_carga()

    def toggle_favorito(self, rec):
        nuevo_fav = not rec["favorito"]
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE recursos SET es_favorito = ? WHERE id = ?", (int(nuevo_fav), rec["id"]))
            conn.commit()
        rec["favorito"] = nuevo_fav
        self.renderizar_grid_libros()

    def cambiar_estado_libro_con_estilo(self, rec, nuevo_estado, card_widget, opt_widget):
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE recursos SET estado = ? WHERE id = ?", (nuevo_estado, rec["id"]))
            conn.commit()
        rec["estado"] = nuevo_estado

        if nuevo_estado in ESTILOS_ESTADO:
            nuevo_estilo = ESTILOS_ESTADO[nuevo_estado]
            card_widget.configure(border_color=nuevo_estilo["border_color"])
            if opt_widget:
                opt_widget.configure(
                    fg_color=nuevo_estilo["badge_bg"],
                    button_color=nuevo_estilo["badge_bg"],
                    button_hover_color=nuevo_estilo["badge_hover"]
                )

    def seleccionar_libro_para_estudio(self, rec):
        self.nombre_pdf_actual = rec["nombre"]
        self.lbl_nombre_pdf.configure(text=f"📄 {rec['nombre']}")

        self.texto_pdf_actual = extraer_texto_pdf(rec["ruta"])

        self.chat_history.configure(state="normal")
        self.chat_history.delete("1.0", "end")
        self.chat_history.configure(state="disabled")

        historial_guardado = []
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT historial_chat FROM recursos WHERE id = ?", (rec["id"],))
                row = cursor.fetchone()
                if row and row[0]:
                    historial_guardado = json.loads(row[0])
            except Exception:
                historial_guardado = []

        if historial_guardado:
            self.agregar_mensaje_chat("SYSTEM", f"Reanudando sesión para: '{rec['nombre']}'", guardar_bd=False)
            for msg in historial_guardado:
                self.agregar_mensaje_chat(msg["emisor"], msg["texto"], guardar_bd=False)
                
            mensaje_continuar = (
                f"¡Hola de nuevo! Estábamos estudiando **'{rec['nombre']}'**. "
                "¿En qué tema o capítulo te gustaría profundizar hoy?"
            )
            self.agregar_mensaje_chat("IA", mensaje_continuar, recurso_id=rec["id"])
        else:
            self.agregar_mensaje_chat("SYSTEM", f"Libro seleccionado para estudio: '{rec['nombre']}'", guardar_bd=False)
            mensaje_bienvenida = (
                f"¡Hola! He cargado el libro **'{rec['nombre']}'** para esta sesión. "
                "¿Qué tema o capítulo te gustaría repasar hoy, o prefieres un resumen de los puntos clave?"
            )
            self.agregar_mensaje_chat("IA", mensaje_bienvenida, recurso_id=rec["id"])

        if rec["estado"] == "Sin empezar":
            with obtener_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE recursos SET estado = 'En progreso' WHERE id = ?", (rec["id"],))
                conn.commit()
            rec["estado"] = "En progreso"

        materia_seleccionada = self.materia_seleccionada_actual
        if materia_seleccionada in self.materias_datos:
            materia_id = self.materias_datos[materia_seleccionada][0]
            if not self.cronometro.activo:
                self.cronometro.clock_in(materia_id=materia_id)
                self.agregar_mensaje_chat("SYSTEM", f"⏱️ Clock-In automático iniciado para {materia_seleccionada}.", guardar_bd=False)

        self.actualizar_banner_chat_ia()
        self.tabview.set("🤖 Tutor IA")

    def actualizar_banner_chat_ia(self):
        materia = self.materia_seleccionada_actual
        estado = "🟢 En Sesión" if self.cronometro.activo else "🔴 Inactiva"
        tiempo = self.cronometro.obtener_tiempo_formateado()
        self.lbl_info_chat_materia.configure(
            text=f"📖 Materia: {materia} | ⏱ Sesión: {estado} ({tiempo})"
        )

    # ----------------- DEMÁS FUNCIONES -----------------
    def indexar_biblioteca(self):
        ruta_inicial = obtener_ruta_guardada()
        home_dir = os.path.expanduser("~")
        
        directorio_seleccionado = filedialog.askdirectory(
            title="Selecciona la carpeta o disco de PDFs",
            initialdir=ruta_inicial if (ruta_inicial and os.path.exists(ruta_inicial)) else home_dir
        )

        if not directorio_seleccionado:
            return

        self.agregar_mensaje_chat("SYSTEM", f"Escaneando directorio: '{directorio_seleccionado}'...", guardar_bd=False)
        self.update()

        nuevos, actualizados = escanear_e_indexar_biblioteca(directorio_seleccionado)
        self.cargar_materias()

        msg = f"Indexación finalizada.\n • Archivos nuevos: {nuevos}\n • Rutas reubicadas: {actualizados}"
        self.agregar_mensaje_chat("SYSTEM", msg, guardar_bd=False)

    def abrir_ventana_nueva_materia(self):
        dialogo = ctk.CTkInputDialog(text="Nombre de la Materia / Tema:", title="Agregar Materia")
        nombre_materia = dialogo.get_input()

        if nombre_materia and nombre_materia.strip():
            dialogo_tipo = ctk.CTkInputDialog(text="Escribe 'Escuela' o 'Personal':", title="Tipo de Materia")
            tipo = dialogo_tipo.get_input()
            tipo_normalizado = "Escuela" if tipo and "esc" in tipo.lower() else "Personal"

            try:
                with obtener_conexion() as conn:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO materias (nombre, tipo) VALUES (?, ?)", (nombre_materia.strip(), tipo_normalizado))
                    conn.commit()
                self.cargar_materias()
            except Exception as e:
                print(f"[Error] No se pudo guardar la materia: {e}")

    # ----------------- RELOJ Y CRONÓMETRO POR MATERIA -----------------
    def clock_in(self):
        materia_seleccionada = self.materia_seleccionada_actual
        if materia_seleccionada in self.materias_datos:
            materia_id = self.materias_datos[materia_seleccionada][0]
            self.cronometro.clock_in(materia_id=materia_id)
            self.lbl_materia_activa_timer.configure(text=f"Materia Activa: {materia_seleccionada}")
            self.actualizar_banner_chat_ia()
            self.preguntas_sesion_actual = []

    def pausar(self):
        self.cronometro.pausar_o_reanudar()
        self.actualizar_banner_chat_ia()

    def clock_out(self):
        materia_actual = self.materia_seleccionada_actual
        duracion_formateada = self.cronometro.obtener_tiempo_formateado()

        duracion_final = self.cronometro.clock_out(notas=self.txt_notas.get())
        if duracion_final > 0:
            self.txt_notas.delete(0, 'end')
            self.actualizar_banner_chat_ia()

            self.agregar_mensaje_chat("SYSTEM", f"Sesión finalizada ({duracion_formateada}). Generando reporte de estudio...", guardar_bd=False)
            
            prompt_resumen = (
                f"El estudiante acaba de terminar una sesión de estudio de {duracion_formateada} en la materia '{materia_actual}'. "
                f"Las consultas realizadas durante la sesión fueron: {self.preguntas_sesion_actual}. "
                "Por favor, genera un breve reporte de resumen de 3 viñetas motivadoras y puntos aprendidos."
            )

            hilo = threading.Thread(target=self._procesar_resumen_sesion_ia, args=(prompt_resumen,))
            hilo.start()

    def _procesar_resumen_sesion_ia(self, prompt):
        respuesta = consultar_ollama_con_contexto(
            prompt,
            contexto_pdf=self.texto_pdf_actual,
            nombre_pdf=self.nombre_pdf_actual
        )
        self.after(0, lambda: self.agregar_mensaje_chat("IA", f"📊 REPORTE DE SESIÓN:\n{respuesta}"))

    def actualizar_reloj_loop(self):
        self.cronometro.tick()
        tiempo_str = self.cronometro.obtener_tiempo_formateado()
        self.lbl_timer.configure(text=tiempo_str)
        self.lbl_timer_sidebar.configure(text=f"⏱ {tiempo_str}")
        self.actualizar_banner_chat_ia()
        self.after(1000, self.actualizar_reloj_loop)

    # ----------------- CHAT IA CON ESTILOS Y COLORES -----------------
    def agregar_mensaje_chat(self, emisor: str, texto: str, guardar_bd: bool = True, recurso_id: int = None):
        self.chat_history.configure(state="normal")

        tb = self.chat_history._textbox
        tb.tag_config("USUARIO_TAG", foreground="#38bdf8", font=("Consolas", 11, "bold"))
        tb.tag_config("IA_TAG", foreground="#4ade80", font=("Consolas", 11, "bold"))
        tb.tag_config("SYS_TAG", foreground="#facc15", font=("Consolas", 10, "italic"))
        tb.tag_config("TEXTO_TAG", foreground="#e2e8f0", font=("Consolas", 11))
        tb.tag_config("SEP_TAG", foreground="#475569")

        if emisor == "USUARIO":
            self.chat_history.insert("end", "👤 TÚ:\n", "USUARIO_TAG")
            self.chat_history.insert("end", f"{texto}\n", "TEXTO_TAG")
            self.chat_history.insert("end", "─" * 65 + "\n\n", "SEP_TAG")
        elif emisor == "IA":
            self.chat_history.insert("end", "🤖 TUTOR IA:\n", "IA_TAG")
            self.chat_history.insert("end", f"{texto}\n", "TEXTO_TAG")
            self.chat_history.insert("end", "─" * 65 + "\n\n", "SEP_TAG")
        else:
            self.chat_history.insert("end", "⚙️ [SISTEMA]: ", "SYS_TAG")
            self.chat_history.insert("end", f"{texto}\n\n", "SYS_TAG")

        self.chat_history.configure(state="disabled")
        self.chat_history.see("end")

        if guardar_bd and emisor in ["USUARIO", "IA"]:
            id_target = recurso_id
            
            if not id_target:
                for r in self.recursos_datos:
                    if r["nombre"] == self.nombre_pdf_actual:
                        id_target = r["id"]
                        break

            if id_target:
                try:
                    with obtener_conexion() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT historial_chat FROM recursos WHERE id = ?", (id_target,))
                        row = cursor.fetchone()
                        
                        historial = json.loads(row[0]) if (row and row[0]) else []
                        historial.append({"emisor": emisor, "texto": texto})
                        
                        cursor.execute(
                            "UPDATE recursos SET historial_chat = ? WHERE id = ?",
                            (json.dumps(historial, ensure_ascii=False), id_target)
                        )
                        conn.commit()
                except Exception as e:
                    print(f"[Error de BD al guardar chat]: {e}")

    def iniciar_hilo_ia(self):
        pregunta = self.txt_pregunta.get()
        if not pregunta.strip():
            return

        self.agregar_mensaje_chat("USUARIO", pregunta)
        self.preguntas_sesion_actual.append(pregunta)
        self.txt_pregunta.delete(0, 'end')

        self.btn_enviar_ia.configure(state="disabled")
        self.lbl_status_ia.configure(text="⏳ La IA está procesando tu respuesta...")

        hilo = threading.Thread(target=self._procesar_consulta_ia, args=(pregunta,))
        hilo.start()

    def _procesar_consulta_ia(self, pregunta):
        respuesta = consultar_ollama_con_contexto(
            pregunta, 
            contexto_pdf=self.texto_pdf_actual,
            nombre_pdf=self.nombre_pdf_actual
        )
        self.after(0, self._finalizar_consulta_ia, respuesta)

    def _finalizar_consulta_ia(self, respuesta):
        self.agregar_mensaje_chat("IA", respuesta)
        self.lbl_status_ia.configure(text="")
        self.btn_enviar_ia.configure(state="normal")


if __name__ == "__main__":
    app = AppEstudio()
    app.mainloop()