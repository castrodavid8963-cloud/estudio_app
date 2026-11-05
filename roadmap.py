"""Motor de roadmaps: convierte la biblioteca en rutas de estudio ordenadas por OBJETIVO.

Cada objetivo (p. ej. "Programador Python") se define con ETAPAS y cada etapa con REGLAS que
escogen libros de la biblioteca por subcarpeta (la que dejó el gestor de biblioteca), palabras del
título y nivel estimado. Los libros se ordenan de lo introductorio a lo avanzado.

* Solo trabaja con diccionarios de libros (ver `database.listar_libros`): no toca la BD ni la UI.
* Los libros de carpetas excluidas (literatura, personal, sin clasificar) nunca entran.
* Un libro aparece una sola vez por objetivo (en la primera etapa que lo reclama).
* Cada etapa tiene "libros" (la ruta recomendada, con tope) y "opcionales" (lo demás que
  encaja, más las referencias rápidas y manuales sueltos).
* Los ajustes manuales del usuario (ocultar / agregar a una etapa) se aplican al final.
"""
import re
import unicodedata

NIVEL_INTRO, NIVEL_MEDIO, NIVEL_AVANZADO, NIVEL_REFERENCIA = 1, 2, 3, 4
NOMBRES_NIVEL = {1: "Introductorio", 2: "Intermedio", 3: "Avanzado", 4: "Referencia"}

_RE_REFERENCIA = re.compile(
    r"pocket reference|cheat ?sheet|quick reference|notes for professionals|definitive reference|"
    r"in a nutshell|essentials? reference|referencia rapida|guia rapida")
_RE_INTRO = re.compile(
    r"\bintro|principiante|beginner|basico|basic\b|basics|fundament|desde cero|primeros pasos|"
    r"aprende|aprender|learn|facil|easy|get(ting)? started|think|absolute|essential|inicial|para todos|"
    r"everybody|from scratch|first |curso|tutorial|\bguia\b|head first|para dummies|simplified|"
    r"pensamiento computacional|how to think|byte of")
_RE_AVANZADO = re.compile(
    r"advanced|avanzad|mastering|expert|internals|in depth|deep dive|definitive guide|"
    r"optimiz|optimizacion|performance|architect|arquitectura|distributed|distribuid|scalab|"
    r"production|produccion|patterns|patrones|design of|engineering|reinforcement|bayesian|"
    r"concurren|microservic|kernel|compiler|compilador|cryptograph|criptograf")
_RE_BASURA = re.compile(r"^(wim[a-z]*|curso de|laboratorio de|bstar|rodent[_ a-z0-9]*|programming|programacion \d|sin titulo|documento\d*)$")


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.replace("_", " ").replace("’", "'")
    return re.sub(r"\s+", " ", texto).strip()


def estimar_nivel(titulo: str) -> int:
    t = normalizar(titulo)
    if _RE_REFERENCIA.search(t):
        return NIVEL_REFERENCIA
    if _RE_AVANZADO.search(t):
        return NIVEL_AVANZADO
    if _RE_INTRO.search(t):
        return NIVEL_INTRO
    return NIVEL_MEDIO


# ----------------------------------------------------------------------------- definición
def R(sub=(), re_=None, no=None, nivel=None, max=6):
    """Regla: libros de estas subcarpetas, cuyo título cumpla `re_` y no `no`, con esos niveles."""
    return {"sub": tuple(sub), "re": re.compile(re_) if re_ else None,
            "no": re.compile(no) if no else None, "nivel": tuple(nivel) if nivel else None, "max": max}


def E(titulo, descripcion, *reglas):
    return {"titulo": titulo, "descripcion": descripcion, "reglas": list(reglas)}


_NO_FUNDAMENTOS_ESCOLARES = r"scratch|aula|secundaria|\bwim|rodent|llevar a la practica|^curso de$|palabras y algoritmos|linux from scratch"
_NO_PYTHON_ESPECIAL = r"hack|raspberry|finanz|vision|pygame|games|transformers|big data|ingenieria de datos|data mining|ciencia|seguridad|cipher|mathem|matemat|electron"
_LEGADO_WEB = r"asp|xml|xslt|xpath|sax2|actionscript|applescript|cgi|dynamic html|xhtml|xml-rpc|oracle|perl|flash|schema"

OBJETIVOS = {
    "python": {
        "nombre": "Programador Python", "icono": "🐍", "color": "#3b82f6",
        "descripcion": "De cero a escribir software en Python con buenas bases, bases de datos y diseño.",
        "etapas": [
            E("Lógica y fundamentos", "Piensa como programador antes de elegir herramientas.",
              R(["Algoritmos_y_Fundamentos"], r"fundamentos de programacion|aprender a programar|logica de programacion|pensamiento computacional|introduction to computing|entonces|programacion para idear", _NO_FUNDAMENTOS_ESCOLARES, max=3),
              R(["Python"], nivel=[1], no=_NO_PYTHON_ESPECIAL, max=5)),
            E("Python sólido", "Domina el lenguaje: tipos, funciones, objetos, módulos.",
              R(["Python"], nivel=[2, 3], no=_NO_PYTHON_ESPECIAL, max=6)),
            E("Herramientas del oficio", "Control de versiones y terminal.",
              R(["Control_de_Versiones"], max=3), R(["Linux"], r"command|bash|shell|linux", nivel=[1, 2], max=2)),
            E("Datos y web", "Guarda información y exponla con APIs.",
              R(["SQL_y_BasesDeDatos"], nivel=[1, 2], max=4),
              R(["JavaScript_y_Web"], r"api|node|web", no=_LEGADO_WEB, max=3)),
            E("Diseño y calidad", "Algoritmos, patrones y arquitectura para código que dure.",
              R(["Algoritmos_y_Fundamentos"], r"algorit|estructuras de datos", _NO_FUNDAMENTOS_ESCOLARES, nivel=[2, 3], max=3),
              R(["Patrones_y_Arquitectura"], max=5)),
            E("Python aplicado", "Úsalo en datos, seguridad, visión, juegos o finanzas.",
              R(["Python"], r"datos|data|seguridad|hack|finanz|vision|games|ciencia|cipher|transformers|raspberry|mathem|matemat", max=8)),
        ]},
    "web": {
        "nombre": "Desarrollo Web Full-Stack", "icono": "🌐", "color": "#f59e0b",
        "descripcion": "HTML/CSS, JavaScript moderno, APIs, bases de datos y despliegue.",
        "etapas": [
            E("Fundamentos web", "HTML, CSS y buenas prácticas de maquetación.",
              R(["JavaScript_y_Web"], r"html|css|svg|jquery|web design|coding guidelines|frameworks|web apps", _LEGADO_WEB, max=6)),
            E("JavaScript moderno", "El lenguaje y su ecosistema.",
              R(["JavaScript_y_Web"], r"javascript|\bjs\b|node|angular|jamstack|reactiv|modern|static site", _LEGADO_WEB, max=7)),
            E("Backend y APIs", "Servidores, APIs y otros lenguajes web.",
              R(["JavaScript_y_Web"], r"api|services|privacy|security|everyone|everywhere", _LEGADO_WEB, max=4),
              R(["PHP"], max=4), R(["Python"], r"flask|django|web", max=2)),
            E("Bases de datos", "Modelado y SQL para tus aplicaciones.",
              R(["SQL_y_BasesDeDatos"], nivel=[1, 2], max=5)),
            E("Arquitectura", "Patrones y diseño de sistemas web.",
              R(["Patrones_y_Arquitectura"], max=5)),
            E("Despliegue", "Contenedores, servidores y cloud.",
              R(["Contenedores_y_K8s"], max=3), R(["Servidores_y_Cloud"], max=4), R(["Control_de_Versiones"], max=2)),
            E("Web clásica y legado", "XML, ASP, CGI y referencias antiguas, por si las necesitas.",
              R(["JavaScript_y_Web"], _LEGADO_WEB, max=12)),
        ]},
    "datos_ia": {
        "nombre": "Ciencia de Datos e IA", "icono": "🤖", "color": "#8b5cf6",
        "descripcion": "Matemáticas, análisis, machine learning, deep learning e IA generativa.",
        "etapas": [
            E("Bases: Python y matemáticas", "Programar y entender probabilidad, álgebra y estadística.",
              R(["Python"], nivel=[1], no=_NO_PYTHON_ESPECIAL, max=3),
              R(["Matematicas_y_Estadistica"], max=5)),
            E("Análisis y estadística", "Explorar, visualizar y contar historias con datos.",
              R(["Analytics_y_Estadistica"], r"data|analytics|visual|driven|jujitsu|reports|getting", nivel=[1, 2, 3], max=6)),
            E("Machine Learning", "Modelos clásicos y práctica.",
              R(["Machine_Learning_e_IA"], no=r"deep|neural|pytorch|keras|generative|language model|llm|transformer|prompt|chatgpt|reinforcement|generativa|mlops|production|produccion|iot|wml|first responders|educating|ia aplicada|ai engineering|stewart", nivel=[1, 2, 3], max=6)),
            E("Deep Learning e IA generativa", "Redes neuronales, LLMs y refuerzo.",
              R(["Machine_Learning_e_IA"], r"deep|neural|pytorch|keras|generative|language model|llm|transformer|prompt|chatgpt|reinforcement|generativa|ai engineering", max=9),
              R(["Python"], r"transformers|vision|data mining|datos", max=3)),
            E("De prototipo a producción", "MLOps, datos a escala e ingeniería.",
              R(["Machine_Learning_e_IA"], r"mlops|production|produccion|engineering|powered applications|apis", max=4),
              R(["BigData_y_Streaming"], r"spark|stream|pipelines|lake|hadoop|fast data", max=5)),
        ]},
    "devops": {
        "nombre": "DevOps y Cloud", "icono": "☁️", "color": "#06b6d4",
        "descripcion": "Linux, redes, contenedores, cloud y prácticas SRE.",
        "etapas": [
            E("Linux y sistemas", "La base: terminal, procesos y servicios.",
              R(["Linux"], nivel=[1, 2], max=5), R(["Teoria_y_Sistemas_Operativos"], nivel=[1, 2], max=2)),
            E("Redes", "Cómo se comunican los sistemas.",
              R(["Redes_y_Comunicaciones"], nivel=[1, 2], max=6)),
            E("Control de versiones", "Git y flujos de trabajo en equipo.",
              R(["Control_de_Versiones"], max=4)),
            E("Contenedores", "Docker, Kubernetes y orquestación.",
              R(["Contenedores_y_K8s"], max=5)),
            E("Cloud y servidores", "Infraestructura en la nube y servidores.",
              R(["Servidores_y_Cloud"], max=7)),
            E("DevOps y SRE", "Cultura, entrega continua, monitoreo y fiabilidad.",
              R(["DevOps_y_SRE"], max=9)),
        ]},
    "seguridad": {
        "nombre": "Ciberseguridad", "icono": "🛡️", "color": "#ef4444",
        "descripcion": "Fundamentos, criptografía, hacking ético y forense.",
        "etapas": [
            E("Base: redes y sistemas", "Sin redes y Linux no hay seguridad.",
              R(["Redes_y_Comunicaciones"], nivel=[1, 2], max=4), R(["Linux"], r"hack|segur|command|bash", max=2)),
            E("Fundamentos de seguridad", "Conceptos, amenazas y buenas prácticas.",
              R(["Ciberseguridad_y_Pentesting"], r"introduc|basic|guia|manual|nist|misconceptions|libro blanco|al alcance|ciberseguridad|security$|engineering security", r"forens|cripto|crypto|ssl|ssh|kerberos|bug bounty|toolkit", max=6)),
            E("Criptografía", "Cifrado, claves y protocolos seguros.",
              R(["Ciberseguridad_y_Pentesting"], r"cripto|crypto|ssl|ssh|kerberos|openssl", max=6)),
            E("Hacking ético", "Pruebas de penetración y herramientas.",
              R(["Ciberseguridad_y_Pentesting"], r"hack|pentest|bug bounty|ofensiv|tools|toolkit|internet", max=8),
              R(["Python"], r"hack|seguridad|cipher|pentest", max=3)),
            E("Forense y respuesta", "Análisis forense digital.",
              R(["Ciberseguridad_y_Pentesting"], r"forens", max=5)),
        ]},
    "bajo_nivel": {
        "nombre": "Sistemas y Bajo Nivel", "icono": "⚙️", "color": "#64748b",
        "descripcion": "C, ensamblador, sistemas operativos y lenguajes de sistemas.",
        "etapas": [
            E("C y C++", "El lenguaje de los sistemas.", R(["C_y_CPP"], max=8)),
            E("Ensamblador y bajo nivel", "Qué ocurre realmente en la máquina.", R(["Ensamblador_y_BajoNivel"], max=7)),
            E("Teoría de sistemas operativos", "Procesos, memoria y planificación.", R(["Teoria_y_Sistemas_Operativos"], max=8)),
            E("Unix y Linux", "Sistemas en la práctica.", R(["Unix_y_BSD"], max=6), R(["Linux"], max=6)),
            E("Lenguajes modernos de sistemas", "Go y Rust.", R(["Go"], max=6), R(["Rust"], max=2)),
        ]},
    "ingenieria": {
        "nombre": "Ingeniería de Software Sólida", "icono": "🏗️", "color": "#10b981",
        "descripcion": "Algoritmos, patrones, arquitectura y oficio profesional.",
        "etapas": [
            E("Fundamentos", "Lógica, programación y pensamiento computacional.",
              R(["Algoritmos_y_Fundamentos"], nivel=[1], no=_NO_FUNDAMENTOS_ESCOLARES, max=4)),
            E("Algoritmos y estructuras de datos", "Análisis y diseño de algoritmos.",
              R(["Algoritmos_y_Fundamentos"], nivel=[2, 3], no=_NO_FUNDAMENTOS_ESCOLARES, max=8)),
            E("Patrones y arquitectura", "Diseño de software mantenible.",
              R(["Patrones_y_Arquitectura"], max=10)),
            E("Ingeniería y sistemas", "Procesos y visión de conjunto.",
              R(["Ingenieria_y_Sistemas"], max=5)),
            E("Cultura profesional", "Historia, consejos y oficio.",
              R(["Historia_Cultura_y_Consejos"], max=9)),
            E("Liderazgo y proyectos", "Gestión de equipos y proyectos.",
              R(["Liderazgo_y_Proyectos"], max=6)),
        ]},
    "java": {
        "nombre": "Java y Plataformas Empresariales", "icono": "☕", "color": "#f97316",
        "descripcion": "Java desde la base hasta aplicaciones empresariales.",
        "etapas": [
            E("Java esencial", "Sintaxis, objetos y librería estándar.",
              R(["Java"], nivel=[1], no=r"spring|hibernate|ejb|j2ee|jsp|servlet", max=5)),
            E("Java intermedio", "Colecciones, E/S, concurrencia, pruebas.",
              R(["Java"], nivel=[2], no=r"spring|hibernate|ejb|j2ee|jsp|servlet", max=7)),
            E("Frameworks y empresa", "Spring, persistencia, servlets y servidores.",
              R(["Java"], r"spring|hibernate|ejb|j2ee|jsp|servlet|enterprise|persistence|jakarta", max=8)),
            E("Java avanzado", "Rendimiento, arquitectura y la JVM.",
              R(["Java"], nivel=[3], max=7)),
            E("Datos y diseño", "SQL y patrones.", R(["SQL_y_BasesDeDatos"], max=4), R(["Patrones_y_Arquitectura"], max=4)),
        ]},
    "dotnet": {
        "nombre": "C# y .NET", "icono": "🟣", "color": "#a855f7",
        "descripcion": "C# y el ecosistema .NET.",
        "etapas": [
            E("C# esencial", "Lenguaje y fundamentos.", R(["CSharp_DotNet"], nivel=[1], max=5)),
            E("C# intermedio", "Práctica sobre .NET.", R(["CSharp_DotNet"], nivel=[2], max=6)),
            E("C# avanzado", "Profundidad y rendimiento.", R(["CSharp_DotNet"], nivel=[3, 4], max=6)),
            E("Datos y diseño", "SQL y patrones.", R(["SQL_y_BasesDeDatos"], max=4), R(["Patrones_y_Arquitectura"], max=4)),
        ]},
    "electronica": {
        "nombre": "Electrónica, Arduino e IoT", "icono": "🔌", "color": "#eab308",
        "descripcion": "Circuitos, microcontroladores, Arduino/Raspberry, robótica y domótica.",
        "etapas": [
            E("Fundamentos de electrónica", "Circuitos y componentes.",
              R(["Microcontroladores_y_Circuitos"], nivel=[1], max=6)),
            E("Arduino y Raspberry Pi", "Primeros proyectos.",
              R(["Arduino_y_Raspberry"], max=8), R(["Python"], r"raspberry|electron", max=2)),
            E("Microcontroladores", "Programación a fondo.",
              R(["Microcontroladores_y_Circuitos"], nivel=[2, 3], max=9)),
            E("Robótica", "Robots y educación.", R(["Robotica_y_Educacion"], max=5)),
            E("Automatización y domótica", "Casas inteligentes y automatización.", R(["Automation_y_Domotica"], max=9)),
        ]},
    "datos_bd": {
        "nombre": "Bases de Datos y Big Data", "icono": "🗄️", "color": "#14b8a6",
        "descripcion": "SQL, modelado, y datos a gran escala.",
        "etapas": [
            E("SQL desde cero", "Consultas y modelado.", R(["SQL_y_BasesDeDatos"], nivel=[1], max=5)),
            E("SQL y diseño de bases", "Optimización y administración.", R(["SQL_y_BasesDeDatos"], nivel=[2, 3], max=8)),
            E("Big Data", "Hadoop, Spark y arquitecturas de datos.", R(["BigData_y_Streaming"], max=10)),
            E("Analítica", "Convertir datos en decisiones.", R(["Analytics_y_Estadistica"], max=7)),
        ]},
    "sysadmin": {
        "nombre": "Administración de Sistemas y Redes", "icono": "🖧", "color": "#0ea5e9",
        "descripcion": "Linux, Windows, Unix, redes y servidores.",
        "etapas": [
            E("Linux", "Administración diaria.", R(["Linux"], max=7)),
            E("Unix y BSD", "El linaje de Unix.", R(["Unix_y_BSD"], max=6)),
            E("Windows", "Administración de entornos Windows.", R(["Windows"], max=8)),
            E("Redes", "Protocolos, servicios y comunicaciones.", R(["Redes_y_Comunicaciones"], max=9)),
            E("Servidores y cloud", "Servicios y alojamiento.", R(["Servidores_y_Cloud"], max=6)),
        ]},
    "ciencias": {
        "nombre": "Matemáticas y Ciencias", "icono": "📐", "color": "#6366f1",
        "descripcion": "Matemáticas, estadística y física.",
        "etapas": [
            E("Matemáticas base", "Álgebra, cálculo y discreta.",
              R(["Matematicas_y_Estadistica"], nivel=[1, 2], max=7), R(["Algoritmos_y_Fundamentos"], r"discrete|discret", max=2)),
            E("Matemáticas avanzadas", "Profundiza.", R(["Matematicas_y_Estadistica"], nivel=[3, 4], max=6)),
            E("Física y astronomía", "Mundo físico.", R(["Fisica_y_Astronomia"], max=11)),
            E("Estadística aplicada", "Datos y probabilidad.", R(["Analytics_y_Estadistica"], r"estadist|statist|probab", max=5)),
        ]},
    "liderazgo": {
        "nombre": "Liderazgo Técnico y Producto", "icono": "🧭", "color": "#ec4899",
        "descripcion": "Gestión de equipos, proyectos, negocio y UX.",
        "etapas": [
            E("Liderazgo y proyectos", "Dirigir personas y entregas.", R(["Liderazgo_y_Proyectos"], max=8)),
            E("Negocio, fintech y UX", "Producto y mercado.", R(["Negocios_Fintech_y_UX"], max=12)),
            E("Cultura y prácticas", "Oficio, DevOps y equipos.",
              R(["Historia_Cultura_y_Consejos"], max=6), R(["DevOps_y_SRE"], r"playbook|hiring|practice|starting|finance", max=4)),
            E("Educación", "Enseñar y aprender.", R(["Educacion_y_Pedagogia"], max=3)),
        ]},
}


def listar_objetivos() -> list:
    return [{"id": k, **{x: v[x] for x in ("nombre", "icono", "color", "descripcion")},
             "etapas": len(v["etapas"])} for k, v in OBJETIVOS.items()]


# ----------------------------------------------------------------------------- generación
def _clave_dedup(titulo: str) -> str:
    return re.sub(r"[ _]\d+$", "", normalizar(titulo))


def _es_basura(titulo: str) -> bool:
    t = normalizar(titulo)
    return len(t) < 4 or bool(_RE_BASURA.match(t))


def _candidatos(libros) -> list:
    """Libros utilizables: disponibles, no excluidos, sin basura ni duplicados evidentes."""
    vistos, resultado = set(), []
    for l in libros:
        if l.get("excluido"):
            continue
        titulo = l.get("titulo") or l.get("nombre_archivo", "")
        if _es_basura(titulo):
            continue
        clave = (l.get("subcarpeta", ""), _clave_dedup(titulo))
        if clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(l)
    return resultado


def _cumple(regla, libro, titulo_norm) -> bool:
    if regla["sub"] and libro.get("subcarpeta") not in regla["sub"]:
        return False
    if regla["re"] and not regla["re"].search(titulo_norm):
        return False
    if regla["no"] and regla["no"].search(titulo_norm):
        return False
    return True


def generar_roadmap(objetivo_id: str, libros, ajustes=()) -> dict:
    meta = OBJETIVOS[objetivo_id]
    utiles = _candidatos(libros)
    por_id = {l["id"]: l for l in libros}
    ocultos = {a["recurso_id"] for a in ajustes if a["accion"] == "ocultar"}
    agregados = {a["recurso_id"]: a["etapa"] for a in ajustes if a["accion"] == "agregar"}
    tomados = set()
    etapas = []

    for idx, etapa in enumerate(meta["etapas"]):
        principales, opcionales = [], []
        for regla in etapa["reglas"]:
            encaja = []
            for l in utiles:
                if l["id"] in tomados or l["id"] in ocultos or l["id"] in agregados:
                    continue
                tn = normalizar(l.get("titulo") or l.get("nombre_archivo", ""))
                if not _cumple(regla, l, tn):
                    continue
                nivel = estimar_nivel(tn)
                if regla["nivel"] and nivel not in regla["nivel"] and nivel != NIVEL_REFERENCIA:
                    continue
                encaja.append((nivel, tn, l))
            encaja.sort(key=lambda x: (x[0] == NIVEL_REFERENCIA, x[0], x[1]))
            cupo = regla["max"]
            for nivel, _, l in encaja:
                tomados.add(l["id"])
                item = {**l, "nivel": nivel, "nivel_nombre": NOMBRES_NIVEL[nivel]}
                if nivel == NIVEL_REFERENCIA or cupo <= 0:
                    opcionales.append(item)
                else:
                    principales.append(item)
                    cupo -= 1
        etapas.append({"indice": idx, "titulo": etapa["titulo"], "descripcion": etapa["descripcion"],
                       "libros": principales, "opcionales": opcionales})

    # Ajustes manuales: agregar libros a la etapa elegida
    for rid, idx in agregados.items():
        l = por_id.get(rid)
        if not l or rid in ocultos or idx is None or not (0 <= idx < len(etapas)):
            continue
        tn = normalizar(l.get("titulo") or l.get("nombre_archivo", ""))
        nivel = estimar_nivel(tn)
        etapas[idx]["libros"].append({**l, "nivel": nivel, "nivel_nombre": NOMBRES_NIVEL[nivel], "manual": True})

    return _resumir(objetivo_id, meta, etapas)


def _resumir(objetivo_id, meta, etapas) -> dict:
    actual_marcada = False
    total = completados = 0
    for e in etapas:
        n = len(e["libros"])
        c = sum(1 for l in e["libros"] if l["estado"] == "Completado")
        e["total"], e["completados"] = n, c
        e["progreso"] = (c / n) if n else 0.0
        e["avance_libros"] = (sum(l["avance"] for l in e["libros"]) / n) if n else 0.0
        if n == 0:
            e["estado"] = "vacia"
        elif c == n:
            e["estado"] = "completada"
        elif not actual_marcada:
            e["estado"] = "actual"
            actual_marcada = True
        else:
            e["estado"] = "pendiente"
        total += n
        completados += c

    siguiente = None
    for e in etapas:
        if e["estado"] == "actual":
            pendientes = [l for l in e["libros"] if l["estado"] != "Completado"]
            en_curso = [l for l in pendientes if l["estado"] == "En progreso"]
            siguiente = (en_curso or pendientes or [None])[0]
            break

    return {
        "id": objetivo_id, "nombre": meta["nombre"], "icono": meta["icono"], "color": meta["color"],
        "descripcion": meta["descripcion"], "etapas": etapas, "total": total, "completados": completados,
        "progreso": (completados / total) if total else 0.0, "siguiente": siguiente,
        "etapa_actual": next((e["indice"] for e in etapas if e["estado"] == "actual"), None),
    }


def resumen_objetivos(libros, ajustes_por_objetivo=None) -> list:
    """Tarjeta de cada objetivo con su avance (para la pantalla de elegir ruta)."""
    ajustes_por_objetivo = ajustes_por_objetivo or {}
    salida = []
    for oid in OBJETIVOS:
        r = generar_roadmap(oid, libros, ajustes_por_objetivo.get(oid, ()))
        salida.append({k: r[k] for k in ("id", "nombre", "icono", "color", "descripcion", "total", "completados", "progreso")})
    return salida
