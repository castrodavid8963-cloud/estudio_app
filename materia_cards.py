import customtkinter as ctk

class VistaTarjetasMaterias(ctk.CTkFrame):
    def __init__(self, master, al_seleccionar_materia, **kwargs):
        super().__init__(master, **kwargs)
        self.al_seleccionar = al_seleccionar_materia
        self.materias_datos = []

        # --- BARRA SUPERIOR: Buscador y Filtros ---
        self.frame_top = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_top.pack(fill="x", padx=10, pady=(10, 5))

        self.entry_buscar = ctk.CTkEntry(
            self.frame_top, 
            placeholder_text="🔍 Buscar materia (ej. Python, Redes, IA)...",
            height=38
        )
        self.entry_buscar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_buscar.bind("<KeyRelease>", self._filtrar)

        # --- ÁREA CON SCROLL (GRID DE TARJETAS) ---
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)

    def cargar_materias(self, lista_materias):
        self.materias_datos = lista_materias
        self.renderizar_grid(self.materias_datos)

    def renderizar_grid(self, lista):
        # Limpiar tarjetas anteriores
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not lista:
            lbl_vacio = ctk.CTkLabel(
                self.scroll_frame, 
                text="No se encontraron materias.",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="gray"
            )
            lbl_vacio.pack(pady=40)
            return

        # Distribución en 3 columnas
        columnas = 3
        for idx, m in enumerate(lista):
            col = idx % columnas
            row = idx // columnas

            card = ctk.CTkFrame(
                self.scroll_frame, 
                corner_radius=12, 
                border_width=1, 
                border_color=("#3a3a3a", "#2b2b2b"),
                fg_color=("#2b2b2b", "#1a1a1a")
            )
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            # Hacer que la fila/columna sea adaptable
            self.scroll_frame.grid_columnconfigure(col, weight=1)

            # --- Encabezado de la Tarjeta ---
            frame_header = ctk.CTkFrame(card, fg_color="transparent")
            frame_header.pack(fill="x", padx=12, pady=(12, 4))

            lbl_icono = ctk.CTkLabel(frame_header, text=m["icono"], font=ctk.CTkFont(size=28))
            lbl_icono.pack(side="left", padx=(0, 8))

            lbl_titulo = ctk.CTkLabel(
                frame_header, 
                text=m["nombre"], 
                font=ctk.CTkFont(size=15, weight="bold"),
                anchor="w",
                wraplength=180
            )
            lbl_titulo.pack(side="left", fill="x", expand=True)

            # Badge de Categoria/Tipo (Escuela/Personal)
            lbl_badge = ctk.CTkLabel(
                card, 
                text=f" {m['tipo']} ", 
                font=ctk.CTkFont(size=10),
                fg_color="#1f538d",
                corner_radius=6
            )
            lbl_badge.pack(anchor="w", padx=12, pady=(0, 8))

            # --- Barra de Progreso ---
            frame_progreso = ctk.CTkFrame(card, fg_color="transparent")
            frame_progreso.pack(fill="x", padx=12, pady=4)

            p_bar = ctk.CTkProgressBar(frame_progreso, height=8, corner_radius=4)
            p_bar.set(m["progreso"])
            p_bar.pack(fill="x", pady=(0, 4))

            pct_texto = int(m["progreso"] * 100)
            lbl_stats = ctk.CTkLabel(
                frame_progreso, 
                text=f"📚 {m['completados']}/{m['total_recursos']} docs • {pct_texto}% completado",
                font=ctk.CTkFont(size=11),
                text_color="gray",
                anchor="w"
            )
            lbl_stats.pack(fill="x")

            # --- Última Actividad ---
            lbl_fecha = ctk.CTkLabel(
                card, 
                text=f"Último acceso: {m['ultima_actividad']}", 
                font=ctk.CTkFont(size=10),
                text_color="#808080",
                anchor="w"
            )
            lbl_fecha.pack(fill="x", padx=12, pady=(4, 8))

            # --- Botón Abrir Materia ---
            btn_abrir = ctk.CTkButton(
                card, 
                text="Abrir Asignatura ➔", 
                height=32,
                corner_radius=8,
                command=lambda mat_id=m["id"]: self.al_seleccionar(mat_id)
            )
            btn_abrir.pack(fill="x", padx=12, pady=(0, 12))

    def _filtrar(self, event):
        query = self.entry_buscar.get().lower()
        filtradas = [m for m in self.materias_datos if query in m["nombre"].lower() or query in m["tipo"].lower()]
        self.renderizar_grid(filtradas)