"""Gestor de biblioteca de PDFs: organizar en carpetas, renombrar y reporte de estructura.

Es la versión para la app del script GestorBibliotecaPDF_Menu.py. Cambios principales:

* No tiene `input()` ni se ejecuta al importarlo: se usa desde la interfaz (o desde la consola
  con `python gestor_biblioteca.py`, que conserva el menú original).
* NADA se mueve ni se renombra sin pasar antes por un PLAN (vista previa). `planificar()` solo
  lee; `aplicar()` ejecuta lo que el usuario dejó marcado y guarda un historial para DESHACER.
* La clasificación es por PUNTAJE de palabras clave con nivel de confianza, en lugar de "la
  primera expresión regular que coincida". Se eliminaron los términos demasiado cortos o
  genéricos (`go`, `vi`, `motor`, `escuela`...) que provocaban casi todos los errores.
* El texto interno del PDF solo se usa si el nombre no basta, y exige evidencia fuerte; si no
  hay evidencia, el archivo se queda donde está (en vez de adivinar).
* El renombrado descarta títulos basura (genéricos, truncados, con copyright, repetidos en
  varios libros) y por defecto solo toca nombres deficientes.
* Las carpetas protegidas (personales, literatura) no se leen ni se tocan.
* Se usa PyMuPDF (ya requerido por la app) en lugar de pypdf.
"""
import json
import os
import re
import shutil
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from datos import carpeta_datos
from pdf_core import fitz, PYMUPDF_LOCK

# ----------------------------------------------------------------------------- constantes
CARPETA_HISTORIAL = ".gestor_biblioteca"
ARCHIVO_REPORTE = "estructura_biblioteca.txt"
SIN_CLASIFICAR = "12_Sin_Clasificar"
PROTEGIDAS_POR_DEFECTO = ("10_Literatura_y_Ocultismo", "11_Personal_y_Documentos")

PAGINAS_TEXTO = 3        # páginas iniciales que se leen para clasificar por contenido
MAX_CHARS_TEXTO = 6000
MAX_LARGO_NOMBRE = 100

CONFIANZAS = ("alta", "media", "baja", "sin_evidencia")
_RANGO_CONFIANZA = {c: i for i, c in enumerate(CONFIANZAS)}


# ----------------------------------------------------------------------------- normalización
_MOJIBAKE = {
    '├í': 'a', '├é': 'a', '├â': 'a', '├ä': 'a', '├®': 'e', '├¡': 'i',
    '├│': 'o', '├║': 'u', '├▒': 'n', '├ô': 'o', '├Â': 'o', '├û': 'o', '├Ø': 'o',
    '┬í': '', '┬┐': '', 'ÔÇÖ': "'", '├': '',
}


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni signos; unifica C#, C++, .NET y quita URLs y la editorial."""
    if not texto:
        return ""
    for err, corr in _MOJIBAKE.items():
        texto = texto.replace(err, corr)
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn").lower()
    texto = texto.replace("’", "'").replace("`", "'")
    texto = re.sub(r"(https?://|www\.)\S+", " ", texto)           # URLs (antes de tratar .net)
    texto = re.sub(r"\bo'?reilly\b", " ", texto)                   # editorial, no es un tema
    texto = texto.replace("c#", "csharp ").replace("c++", "cpp ").replace("f#", "fsharp ")
    texto = re.sub(r"\.net\b", " dotnet ", texto)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return texto.strip()


# ----------------------------------------------------------------------------- categorías
# (fuertes=3, medios=2, débiles=1). El ORDEN de este diccionario desempata, igual que en el
# script original. Todos los términos se normalizan al compilarlos.
_ESPEC = {
    # 01. Lenguajes de programación
    "01_Programacion_y_Lenguajes/Python": (
        "python|pypi|pygame|django|flask|pandas|numpy|pyspark|jupyter", "pythonic|scipy|matplotlib", ""),
    "01_Programacion_y_Lenguajes/Java": (
        "java|spring boot|spring framework|hibernate|jvm|j2me|j2ee|jboss|rxjava|javabeans|jdbc|servlet|"
        "servlets|ejb|netbeans|bluej|jsp", "spring|swing|jakarta", ""),
    "01_Programacion_y_Lenguajes/C_y_CPP": (
        "cpp|c tut|beej|programacion en c|programacion con c|lenguaje c|practical c programming|"
        "c programming|programming in c|ansi c|c en poco tiempo", "qt", ""),
    "01_Programacion_y_Lenguajes/CSharp_DotNet": (
        "csharp|dotnet|fsharp|visual basic|vba|delphi|visual csharp|xamarin", "vb|ado|activex|excel macros", ""),
    "01_Programacion_y_Lenguajes/JavaScript_y_Web": (
        "javascript|angularjs|angular|nodejs|node js|jquery|jamstack|html5|html|css3|css|svg|xhtml|xslt|xml|"
        "dhtml|web design|ecmascript|typescript|react|vuejs|json|ajax|web apps|web app|static site|"
        "web development|desarrollo web|getting started with the web|web performance|frontend|front end|"
        "xpath|xpointer|sax2",
        "js|asp|active server pages|cgi|web sites|websites|web site|navegador|browser|actionscript|flash|"
        "web services|xml rpc|soap", ""),
    "01_Programacion_y_Lenguajes/Go": (
        "golang|go en espanol|programming in go|the go programming language|learning go", "", ""),
    "01_Programacion_y_Lenguajes/PHP": ("php|php7|laravel|symfony|wordpress", "", ""),
    "01_Programacion_y_Lenguajes/Rust": ("rust|rustlang", "", ""),
    "01_Programacion_y_Lenguajes/Swift_y_Mobile": (
        "swift|android|palm programming|ios|kotlin|mobile app|mobile apps|flutter|react native|xcode|iphone|"
        "app analytics", "movil|moviles|mobile|smartphone", ""),
    "01_Programacion_y_Lenguajes/Ruby": ("ruby|rails|ruby on rails|chris pine", "", ""),
    "01_Programacion_y_Lenguajes/Perl": ("perl", "", ""),
    "01_Programacion_y_Lenguajes/Prolog_y_Logica": (
        "prolog|programacion logica|la logica como lenguaje|logic programming",
        "logica computacional|logica para informatica|logica matematica", "logica|logic"),
    "01_Programacion_y_Lenguajes/SQL_y_BasesDeDatos": (
        "sql|oracle|mysql|postgresql|mongodb|cassandra|jdbc|pl sql|plsql|bases de datos|base de datos|database|"
        "databases|access database|nosql|sqlite|rman|mariadb|redis", "dba|datos relacionales|relational", ""),
    "01_Programacion_y_Lenguajes/Ensamblador_y_BajoNivel": (
        "ensamblador|assembly|asm|x86 64|qtarmsim|assembler|x86",
        "arquitectura de computadores|bajo nivel|microprocesador", ""),

    # 02. Ingeniería de software
    "02_Ingenieria_de_Software/Algoritmos_y_Fundamentos": (
        "algorithm|algorithms|algoritmo|algoritmos|estructuras de datos|estructura de datos|data structures|"
        "skiena|discrete structures|matematicas discretas|logica de programacion|pensamiento computacional|"
        "computational thinking|fundamentos de programacion|aprender a programar|aprende a programar|"
        "programacion 1|introduccion a la logica|introduccion a la programacion|complejidad computacional|"
        "computabilidad",
        "ciencias de la computacion|computer science|programacion basica|pensar como un programador|"
        "think like a computer scientist|computacion creativa|aprendiendo a programar|arte de programar|"
        "art of computer programming|knuth",
        "scratch|programacion|programming|fundamentos|computacion|computing"),
    "02_Ingenieria_de_Software/Patrones_y_Arquitectura": (
        "design patterns|patrones de diseno|microservices|microservicios|twelve factor|codigo sostenible|"
        "maintainable|refactoring|clean code|uml|software architecture|arquitectura de software|"
        "arquitectura de sistemas|orientado a objetos|orientada a objetos|object oriented|oop|service oriented|"
        "soa|reactive|monolith|software patterns|architecture",
        "arquitectura|patrones|patterns|diseno orientado|procesos distribuidos|distribuidos|api|apis|distributed",
        "design|diseno"),
    "02_Ingenieria_de_Software/Ingenieria_y_Sistemas": (
        "ingenieria de sistemas|introduccion a la informatica|investigacion de operaciones|sistemas de informacion|"
        "introduccion a la ingenieria|ingenieria del software|software engineering|auditoria|gobierno de ti|"
        "cobit|itil|gestion de proyectos|project management|pruebas de software|pruebas de sistemas|"
        "programacion lineal|sistemas digitales|sistemas informaticos|calidad de software",
        "informatica|metodos de investigacion|sistemas computacionales", "sistemas"),
    "02_Ingenieria_de_Software/Historia_Cultura_y_Consejos": (
        "97 cosas|libro negro del programador|nosotros los programadores|free as in freedom|hackstory|"
        "historia del software|history of computing|underground hacker",
        "historia|cronica|biografia|cultura hacker|consejos", ""),
    "02_Ingenieria_de_Software/Videojuegos": (
        "videojuegos|video juegos|game developers|game development|game engine|motor de videojuegos|unity|"
        "unreal|godot|making games", "games|juegos|game", ""),

    # 03. Sistemas operativos
    "03_Sistemas_Operativos/Linux": (
        "linux|gnulinux|gnu linux|ubuntu|debian|centos|fedora|arch linux|red hat|rhel|bash|shell script|sed awk|"
        "linux from scratch|g l u p|glup|slackware", "gnu", ""),
    "03_Sistemas_Operativos/Windows": (
        "windows|registry|powershell|wimlib|wimappend|wimapply|wimcapture|wimdelete|wimdir|wimexport|wimextract|"
        "wiminfo|wimjoin|wimoptimize|wimsplit|wimupdate|wimverify|wimmount|wimunmount|active directory", "", ""),
    "03_Sistemas_Operativos/Unix_y_BSD": (
        "unix|bsd|freebsd|openbsd|netbsd|mac os|macos|os x|solaris", "", ""),
    "03_Sistemas_Operativos/Teoria_y_Sistemas_Operativos": (
        "sistemas operativos|operating system|operating systems|sysadmin|emacs|vi editor|kernel",
        "administracion de sistemas|sistema operativo", ""),

    # 04. Datos e IA
    "04_Data_e_IA/BigData_y_Streaming": (
        "hadoop|spark|impala|data lake|data lakes|stream processing|big data|streaming|data pipelines|kafka|"
        "mapreduce|cloudera|almacenes de datos|data warehouse|data warehousing",
        "fast data|data preparation|data infrastructure|pipelines", ""),
    "04_Data_e_IA/Machine_Learning_e_IA": (
        "machine learning|deep learning|keras|pytorch|reinforcement learning|machine intelligence|data mining|"
        "chatgpt|ia generativa|inteligencia artificial|prompt engineering|opencv|vision artificial|mineria de datos|"
        "aprendizaje automatico|aprendizaje estadistico|neural networks|redes neuronales|llm|large language models|"
        "transformers|mlops|generative ai|generative deep learning|tensorflow|computer vision|ai engineering|"
        "natural language processing|nlp|bayesian|active learning|explainable ai",
        "ai|ia|artificial intelligence|aprendizaje", "learning"),
    "04_Data_e_IA/Analytics_y_Estadistica": (
        "analytics|data visualization|data driven|data scientist|data scientists|predictive maintenance|"
        "statistical methods|business intelligence|data science|ciencia de datos|data jujitsu|data skeptic",
        "metrics|visualization|reporting|statistics|estadistica|webfocus|nvidia", "data|datos"),

    # 05. DevOps, cloud y redes
    "05_DevOps_Cloud_y_Redes/Contenedores_y_K8s": (
        "docker|kubernetes|unikernels|containers|contenedores|k8s|helm", "", ""),
    "05_DevOps_Cloud_y_Redes/Servidores_y_Cloud": (
        "azure|aws|lambda|cloud|apache|openstack|vmware|veeam|postfix|squid|serverless|entorno servidor|nginx|"
        "load balancing|nfs|nis|cloud native|immutable infrastructure", "servidor|servidores|server|servers|backup", ""),
    "05_DevOps_Cloud_y_Redes/Redes_y_Comunicaciones": (
        "cisco|ccna|ccnp|networking|networks|network|redes|snmp|dhcp|dns|ipv6|ansible|ethernet|wifi|wireless|"
        "inalambricas|inalambrica|tcp ip|comunicaciones|vpn|vpns|lan|lans|802 11|routing|switching|telematicas",
        "", ""),
    "05_DevOps_Cloud_y_Redes/Control_de_Versiones": (
        "git|github|version control|control de versiones|subversion|svn|mercurial", "", ""),
    "05_DevOps_Cloud_y_Redes/DevOps_y_SRE": (
        "monitoring|sre|chatops|release engineering|performance engineering|devops|devopssec|continuous delivery|"
        "continuous integration|site reliability|observability", "operations|operaciones|deployment|performance", ""),

    # 06. Seguridad
    "06_Seguridad_y_Hacking/Ciberseguridad_y_Pentesting": (
        "security|seguridad|bug bounty|hacker|hackers|hacking|firewall|firewalls|cryptography|criptografia|ssh|"
        "kerberos|openssl|forense|forensic|forensics|forenze|ciphers|kali|pentest|pentesting|penetration|"
        "penetracion|ciberseguridad|cybersecurity|deep web|malware|privacy|privacidad|anonimato|encryption|"
        "cifrado|secure shell", "cracking|vulnerability|vulnerabilidades|cyber|ciber", ""),

    # 07. Hardware, robótica e IoT
    "07_Hardware_y_IoT/Robotica_y_Educacion": (
        "robot|robots|robotica|robotic|robotics", "", ""),
    "07_Hardware_y_IoT/Arduino_y_Raspberry": (
        "arduino|raspberry|rapberry|pi zero|esp32|esp8266", "", ""),
    "07_Hardware_y_IoT/Microcontroladores_y_Circuitos": (
        "pic|microcontrolador|microcontroladores|555|tiva|circuitos|circuits|electronica|electronics|electricista|"
        "electricos|3d printing|oled|lcd|tv repair|camaras ip|electrical|electricidad|diseno digital|"
        "electronica digital|tecnicas digitales|logica digital", "hardware", ""),
    "07_Hardware_y_IoT/Automation_y_Domotica": (
        "automatas|automatismos|industrial automation|labview|medidas electricas|instalaciones|domotica|iot|"
        "internet of things|internet de las cosas|industrial internet|smart cities|voice interfaces|automation",
        "", ""),

    # 08. Ciencias y matemáticas
    "08_Ciencias_y_Matematicas/Matematicas_y_Estadistica": (
        "calculo|geometria|aritmetica|baldor|probability|probabilidad|muestreo|estadistico|estadistica|algebra|"
        "mathematics|matematicas|matematica|precalculo|ecuaciones diferenciales|differential equations|"
        "calculus|statistics", "", ""),
    "08_Ciencias_y_Matematicas/Fisica_y_Astronomia": (
        "physics|fisica|electrostatics|relativity|solid state physics|heat transfer|astronomy|astronomia|"
        "thermodynamics|quantum", "", ""),

    # 09. Gestión, negocios y educación
    "09_Gestion_y_Educacion/Educacion_y_Pedagogia": (
        "ensenanza de programacion|tecnologias emergentes|educacion|ensenanza|pedagogia|didactica|docentes|"
        "teaching|education", "escuela|alumnos", ""),
    "09_Gestion_y_Educacion/Liderazgo_y_Proyectos": (
        "manager|leader|leadership|one on one|hiring|postmortems|okrs|salary survey|cio|gig economy|inner source|"
        "future of work", "", ""),
    "09_Gestion_y_Educacion/Negocios_Fintech_y_UX": (
        "fintech|payments|pagos|business|negocios|product design|ux|startup|startups|inventarios|procurement|"
        "calidad|venture capital|innovation|emprender|idea de negocio|compliance", "scrum|agile|design|product", ""),

    # 10. Literatura y filosofía (destino permitido; carpeta protegida al salir)
    "10_Literatura_y_Ocultismo/Esoterismo_y_Filosofia": (
        "salomon|abramelin|magia|zohar|torah|tora|tanaj|arbatel|samael|dogma|catecismo|mormon|hebreo|clave mayor|"
        "clavicula|claviculas|gnosis|desarrollo de la luz|pentateuco|biblia|biblico|cabala|kabbalah|alta magia|"
        "eliphas levi|ritual|sefer|talmud", "", ""),
    "10_Literatura_y_Ocultismo/Literatura_General": (
        "dumas|koontz|ready player one|sardou|nostradamus|peregrino del tiempo|quinto acuerdo|cuatro acuerdos|"
        "hornos de hitler|veinte anos despues|novela|novel", "", ""),

    # 11. Documentos personales (solo identificación inequívoca; nunca por contenido)
    "11_Personal_y_Documentos/Documentos_y_Otros": (
        "curriculum|carta de oferta|camscanner|scanned by|pri 5 a|pri 5 b|utel|stel", "oferta", ""),
}

CATEGORIAS = list(_ESPEC.keys())
_ORDEN = {ruta: i for i, ruta in enumerate(CATEGORIAS)}
_NO_POR_TEXTO = {"11_Personal_y_Documentos/Documentos_y_Otros"}


def _compilar():
    resultado = {}
    for ruta, (fuertes, medios, debiles) in _ESPEC.items():
        vistos, lista = set(), []
        for peso, cadena in ((3, fuertes), (2, medios), (1, debiles)):
            for termino in cadena.split("|"):
                t = normalizar(termino)
                if t and t not in vistos:
                    vistos.add(t)
                    rx = re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])")
                    lista.append((peso, t, rx))
        resultado[ruta] = lista
    return resultado


_TERMINOS = _compilar()


# ----------------------------------------------------------------------------- clasificación
def puntuar(texto_norm: str, por_frecuencia: bool = False) -> dict:
    """Puntaje por categoría: {ruta: (puntos, [términos])}.

    Por nombre: suma los pesos de los términos DISTINTOS que aparecen.
    Por contenido (`por_frecuencia`): solo términos de peso >= 2, contando hasta 3 apariciones,
    y se excluyen las categorías que nunca se deducen del contenido.
    """
    resultado = {}
    for ruta, terminos in _TERMINOS.items():
        if por_frecuencia and ruta in _NO_POR_TEXTO:
            continue
        encontrados = []                                   # (peso, término, apariciones)
        for peso, t, rx in terminos:
            if por_frecuencia:
                if peso < 2:
                    continue
                n = len(rx.findall(texto_norm))
                if n:
                    encontrados.append((peso, t, n))
            elif rx.search(texto_norm):
                encontrados.append((peso, t, 1))
        # un término contenido en otro más largo que también coincidió no suma dos veces
        # ("web" dentro de "web services", "programacion" dentro de "fundamentos de programacion")
        largos = [f" {t} " for _, t, _ in encontrados]
        encontrados = [e for e in encontrados
                       if not any(f" {e[1]} " in l and f" {e[1]} " != l for l in largos)]
        total = sum(peso * min(n, 3) for peso, _, n in encontrados)
        if total:
            resultado[ruta] = (total, [t for _, t, _ in encontrados])
    return resultado


def _veredicto(puntajes: dict, modo: str):
    """Elige la mejor categoría y su confianza, o None si la evidencia no alcanza."""
    if not puntajes:
        return None
    ranking = sorted(puntajes.items(), key=lambda kv: (-kv[1][0], _ORDEN[kv[0]]))
    mejor, (s1, terminos) = ranking[0]
    s2 = ranking[1][1][0] if len(ranking) > 1 else 0
    margen = s1 - s2

    if modo == "nombre":
        if s1 < 2:
            return None
        confianza = "alta" if margen >= 3 else "media" if margen >= 1 else "baja"
    else:  # contenido: solo cuenta si es contundente y con al menos 2 términos distintos
        if len(terminos) < 2:
            return None
        if s1 >= 12 and margen >= 6:
            confianza = "media"
        elif s1 >= 8 and margen >= 3:
            confianza = "baja"
        else:
            return None

    return {
        "categoria": mejor, "confianza": confianza, "puntaje": s1, "margen": margen,
        "origen": modo, "terminos": terminos,
        "alternativas": [r for r, (s, _) in ranking[1:4] if s >= max(2, s1 - 2)],
    }


def clasificar_nombre(nombre: str):
    """Clasifica solo por el nombre del archivo. Devuelve el veredicto o None."""
    return _veredicto(puntuar(normalizar(nombre)), "nombre")


# ----------------------------------------------------------------------------- lectura de PDFs
def _titulo_por_fuente(pagina) -> str:
    """Texto de mayor tamaño de la primera página (suele ser el título real del libro)."""
    try:
        bloques = pagina.get_text("dict").get("blocks", [])
    except Exception:
        return ""
    lineas = []
    for b in bloques:
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            spans = ln.get("spans", [])
            txt = "".join(s.get("text", "") for s in spans).strip()
            if len(txt) > 1 and spans:
                lineas.append((ln["bbox"][1], max(s.get("size", 0) for s in spans), txt))
    if not lineas:
        return ""
    tam = max(t for _, t, _ in lineas)
    elegidas = sorted((l for l in lineas if l[1] >= tam * 0.92), key=lambda x: x[0])
    return " ".join(t for _, _, t in elegidas[:3])[:160]


def leer_pdf(ruta: str) -> dict:
    """Lee metadatos, título por tamaño de fuente y texto inicial. Nunca lanza excepciones."""
    info = {"meta_titulo": "", "meta_extra": "", "titulo_portada": "", "texto": ""}
    doc = None
    try:
        with PYMUPDF_LOCK:
            doc = fitz.open(ruta)
            if doc.needs_pass:
                return info
            md = doc.metadata or {}
            info["meta_titulo"] = (md.get("title") or "").strip()
            info["meta_extra"] = " ".join((md.get("subject") or "", md.get("keywords") or "")).strip()
            textos = []
            for i in range(min(len(doc), PAGINAS_TEXTO)):
                textos.append(doc[i].get_text("text") or "")
                if i == 0:
                    info["titulo_portada"] = _titulo_por_fuente(doc[0])
            info["texto"] = " ".join(textos)[:MAX_CHARS_TEXTO]
    except Exception:
        pass
    finally:
        if doc is not None:
            try:
                with PYMUPDF_LOCK:
                    doc.close()
            except Exception:
                pass
    return info


# ----------------------------------------------------------------------------- nombres / títulos
_PALABRAS_FINALES = {
    "de", "del", "la", "el", "los", "las", "y", "e", "o", "u", "en", "con", "para", "por", "a", "al", "un",
    "una", "of", "the", "and", "for", "to", "in", "on", "with", "an", "or",
}
_TITULOS_GENERICOS = {
    "title", "untitled", "documento", "document", "portada", "cover", "index", "indice", "contents",
    "introduccion", "introduction", "presentacion", "presentation", "microsoft word", "sin titulo", "unknown",
    "prologo", "preface", "free ebooks", "ebook", "book", "libro", "manual", "curso", "tesis", "anonymous",
}
_BASURA_TITULO = re.compile(
    r"(copyright|all rights reserved|todos los derechos|\bisbn\b|www\.|https?:|\.indd|\.qxd|\.pmd|\.docx?\b|"
    r"\.pdf\b|\.tmp\b|microsoft word|powerpoint|untitled|sin titulo|scanned by|camscanner|\bdraft\b|\bborrador\b)",
    re.IGNORECASE)


def limpiar_nombre_archivo(texto: str, maximo: int = MAX_LARGO_NOMBRE) -> str:
    """Quita caracteres no permitidos (Windows/NTFS), compacta espacios y corta en límite de palabra."""
    texto = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", texto or "")
    texto = " ".join(texto.split()).strip(" .")
    if len(texto) > maximo:
        corte = texto[:maximo]
        texto = (corte.rsplit(" ", 1)[0] if " " in corte[maximo // 2:] else corte).strip(" .-")
    return texto


def titulo_valido(titulo: str) -> bool:
    """¿Sirve como nombre de archivo? Descarta genéricos, truncados, con copyright o sin sentido."""
    t = limpiar_nombre_archivo(titulo)
    palabras = t.split()
    if len(t) < 8 or len(palabras) < 2 or len(t) > 140:
        return False
    if normalizar(t) in _TITULOS_GENERICOS or _BASURA_TITULO.search(t):
        return False
    ultima = normalizar(palabras[-1])
    if ultima in _PALABRAS_FINALES:          # "Curso de", "Fundamentos de": título cortado
        return False
    letras = sum(c.isalpha() for c in t)
    digitos = sum(c.isdigit() for c in t)
    if letras < len(t) * 0.5 or digitos > len(t) * 0.35:
        return False
    return True


def nombre_deficiente(stem: str) -> bool:
    """¿El nombre actual es malo (genérico, copia numerada, truncado, con URL...)?"""
    s = stem.strip()
    n = normalizar(s)
    palabras = n.split()
    if len(palabras) <= 1:
        return True
    if n in _TITULOS_GENERICOS or _BASURA_TITULO.search(s):
        return True
    if palabras[-1] in _PALABRAS_FINALES:
        return True
    if re.search(r"_\d+$", s):               # copia numerada por un renombrado anterior
        return True
    if re.fullmatch(r"[\W\d_]*", s):
        return True
    return False


def _nombre_libre(directorio: str, stem: str, ocupados: set, ext: str = ".pdf") -> str:
    """Ruta completa sin colisión (insensible a mayúsculas), añadiendo _1, _2... como el script original."""
    candidata = os.path.join(directorio, stem + ext)
    contador = 1
    while candidata.casefold() in ocupados or os.path.exists(candidata):
        candidata = os.path.join(directorio, f"{stem}_{contador}{ext}")
        contador += 1
    return candidata


# ----------------------------------------------------------------------------- plan de cambios
@dataclass
class Cambio:
    origen: str
    destino: str
    tipo: str                      # "mover" | "renombrar" | "mover y renombrar"
    confianza: str                 # alta | media | baja | sin_evidencia
    motivo: str = ""
    alternativas: list = field(default_factory=list)
    seleccionado: bool = True

    @property
    def carpeta_destino(self) -> str:
        return os.path.dirname(self.destino)


@dataclass
class Opciones:
    organizar: bool = False
    renombrar: bool = False
    renombrar_todos: bool = False          # False: solo nombres deficientes (recomendado)
    usar_contenido: bool = True            # leer texto del PDF si el nombre no alcanza
    protegidas: tuple = PROTEGIDAS_POR_DEFECTO


@dataclass
class Plan:
    raiz: str
    cambios: list = field(default_factory=list)
    total_pdfs: int = 0
    protegidos: int = 0
    sin_cambios: int = 0
    notas: list = field(default_factory=list)       # avisos para mostrar al usuario
    cancelado: bool = False

    def contar_por_confianza(self) -> dict:
        c = Counter(x.confianza for x in self.cambios)
        return {k: c.get(k, 0) for k in CONFIANZAS}

    def contar_por_carpeta(self, solo_seleccionados: bool = True) -> dict:
        c = Counter()
        for x in self.cambios:
            if solo_seleccionados and not x.seleccionado:
                continue
            c[os.path.relpath(x.carpeta_destino, self.raiz).replace("\\", "/")] += 1
        return dict(sorted(c.items()))


def _es_oculta(nombre: str) -> bool:
    n = nombre.lower()
    return n.startswith((".", "$")) or n in ("system volume information", "lost+found", "recycle.bin")


def listar_pdfs(raiz: str, protegidas=PROTEGIDAS_POR_DEFECTO):
    """(pdfs_a_gestionar, cantidad_protegida). Ignora carpetas ocultas y de sistema."""
    protegidas_cf = {p.casefold() for p in protegidas}
    pdfs, protegidos = [], 0
    for carpeta, dirs, archivos in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if not _es_oculta(d))
        rel = os.path.relpath(carpeta, raiz)
        primera = "" if rel == "." else rel.replace("\\", "/").split("/")[0]
        for a in sorted(archivos):
            if not a.lower().endswith(".pdf"):
                continue
            if primera.casefold() in protegidas_cf:
                protegidos += 1
            else:
                pdfs.append(os.path.join(carpeta, a))
    return pdfs, protegidos


def _carpeta_actual(raiz: str, ruta: str):
    """(categoria_conocida|None, en_raiz). La categoría solo cuenta si la carpeta coincide exactamente."""
    rel = os.path.relpath(os.path.dirname(ruta), raiz).replace("\\", "/")
    if rel == ".":
        return None, True
    for cat in CATEGORIAS + [SIN_CLASIFICAR]:
        if rel.casefold() == cat.casefold():
            return cat, False
    return None, False


def planificar(raiz: str, opciones: Opciones, progreso_cb=None, cancelar=None) -> Plan:
    """Calcula los cambios SIN tocar el disco. `progreso_cb(i, total, nombre)`; `cancelar()` -> bool."""
    raiz = os.path.abspath(raiz)
    plan = Plan(raiz=raiz)
    if not os.path.isdir(raiz):
        plan.notas.append(f"La carpeta no existe: {raiz}")
        return plan

    pdfs, plan.protegidos = listar_pdfs(raiz, opciones.protegidas)
    plan.total_pdfs = len(pdfs) + plan.protegidos
    if plan.protegidos:
        plan.notas.append(f"{plan.protegidos} PDFs en carpetas protegidas no se leyeron ni se tocaron.")

    # ---- Fase 1: leer lo necesario de cada archivo
    infos = {}
    total = len(pdfs)
    for i, ruta in enumerate(pdfs):
        if cancelar and cancelar():
            plan.cancelado = True
            return plan
        if progreso_cb:
            progreso_cb(i, total, os.path.basename(ruta))
        stem = os.path.splitext(os.path.basename(ruta))[0]
        necesita = opciones.renombrar
        if opciones.organizar and opciones.usar_contenido and not necesita:
            necesita = clasificar_nombre(stem) is None          # solo si el nombre no basta
        infos[ruta] = leer_pdf(ruta) if necesita else None
    if progreso_cb:
        progreso_cb(total, total, "")

    # ---- Fase 2: nombres propuestos
    propuestos = {}                                  # ruta -> (nuevo_stem, fuente)
    if opciones.renombrar:
        candidatos = {}
        # el mismo título en los metadatos de varios archivos es basura (p. ej. una plantilla de
        # conversión): en ese caso se ignora el metadato y se prueba con el texto de la portada
        meta_repetido = Counter()
        for ruta in pdfs:
            m = limpiar_nombre_archivo((infos[ruta] or {}).get("meta_titulo", ""))
            if m:
                meta_repetido[normalizar(m)] += 1
        ignorados = 0
        for ruta in pdfs:
            info = infos[ruta] or {}
            stem = os.path.splitext(os.path.basename(ruta))[0]
            if not opciones.renombrar_todos and not nombre_deficiente(stem):
                continue
            for fuente, bruto in (("metadatos", info.get("meta_titulo", "")),
                                  ("portada", info.get("titulo_portada", ""))):
                limpio = limpiar_nombre_archivo(bruto)
                if fuente == "metadatos" and limpio and meta_repetido[normalizar(limpio)] > 1:
                    ignorados += 1
                    continue
                if titulo_valido(limpio):
                    candidatos[ruta] = (limpio, fuente)
                    break
        if ignorados:
            plan.notas.append(f"{ignorados} archivos comparten el mismo título en sus metadatos (metadato "
                              "basura): se usó el texto de la portada.")
        # un mismo título propuesto para varios libros es un metadato basura (p. ej. "Introduction to
        # Computing..." en 15 libros distintos): se descarta para todos
        repetidos = Counter(normalizar(t) for t, _ in candidatos.values())
        descartados = 0
        for ruta, (t, fuente) in candidatos.items():
            if repetidos[normalizar(t)] > 1:
                descartados += 1
                continue
            if normalizar(t) == normalizar(os.path.splitext(os.path.basename(ruta))[0]):
                continue                                          # ya se llama así
            propuestos[ruta] = (t, fuente)
        if descartados:
            plan.notas.append(f"{descartados} títulos descartados por repetirse en varios libros (metadato basura).")

    # ---- Fase 3: clasificación y armado de cambios
    ocupados = {p.casefold() for p in pdfs}
    for ruta in pdfs:
        carpeta = os.path.dirname(ruta)
        stem = os.path.splitext(os.path.basename(ruta))[0]
        nuevo_stem, fuente = propuestos.get(ruta, (None, None))
        stem_final = nuevo_stem or stem
        destino_dir, confianza, motivo, alternativas = carpeta, None, "", []
        mover = False

        if opciones.organizar:
            actual, en_raiz = _carpeta_actual(raiz, ruta)
            res_n = puntuar(normalizar(stem_final + " " + stem))
            veredicto = _veredicto(res_n, "nombre")
            res_t = {}
            if veredicto is None and opciones.usar_contenido:
                info = infos.get(ruta) or leer_pdf(ruta)
                infos[ruta] = info
                texto = " ".join((info["meta_titulo"], info["meta_extra"], info["titulo_portada"], info["texto"]))
                res_t = puntuar(normalizar(texto), por_frecuencia=True)
                veredicto = _veredicto(res_t, "contenido")

            if veredicto is not None:
                cat = veredicto["categoria"]
                p_actual = (res_n.get(actual) or res_t.get(actual) or (0, []))[0] if actual else 0
                if actual == cat:
                    pass
                elif actual and actual != SIN_CLASIFICAR and p_actual >= max(2, veredicto["puntaje"] - 1):
                    pass                                          # empate: se respeta la carpeta actual
                else:
                    mover = True
                    destino_dir = os.path.join(raiz, *cat.split("/"))
                    confianza = veredicto["confianza"]
                    origen_txt = "nombre" if veredicto["origen"] == "nombre" else "contenido del PDF"
                    motivo = f"{origen_txt}: {', '.join(veredicto['terminos'][:4])}"
                    alternativas = veredicto["alternativas"]
                    # Conflicto: la carpeta ACTUAL también tiene respaldo en el nombre y la nueva no la
                    # supera por mucho. No se marca por defecto: que lo decida el usuario.
                    if actual and actual != SIN_CLASIFICAR and p_actual >= 3 \
                            and veredicto["puntaje"] - p_actual < 6:
                        confianza = "baja"
                        t_actual = (res_n.get(actual) or res_t.get(actual) or (0, []))[1]
                        motivo += f" · conflicto: la carpeta actual también coincide ({', '.join(t_actual[:3])})"
            elif en_raiz:
                mover = True                                      # como el script original: suelto sin tema
                destino_dir = os.path.join(raiz, *SIN_CLASIFICAR.split("/"))
                confianza, motivo = "sin_evidencia", "sin palabras clave reconocibles"
            elif actual and actual.startswith("01_Programacion_y_Lenguajes/"):
                ev_n = (res_n.get(actual) or (0, []))[0]
                ev_t = (res_t.get(actual) or (0, []))[0]
                if ev_n < 2 and ev_t < 4:                         # la carpeta actual no tiene respaldo
                    mover = True
                    destino_dir = os.path.join(raiz, *SIN_CLASIFICAR.split("/"))
                    confianza = "sin_evidencia"
                    motivo = f"nada en el libro justifica estar en {actual.split('/')[-1]}"

        renombra = nuevo_stem is not None
        if renombra and mover and fuente == "portada":
            # el título leído de la portada es menos fiable: no debe condicionar el movimiento
            renombra, nuevo_stem, stem_final = False, None, stem
            plan.notas.append(f"Renombrado omitido (poco fiable): {stem}")
        if not mover and not renombra:
            plan.sin_cambios += 1
            continue

        nuevo_destino = _nombre_libre(destino_dir, stem_final, ocupados - {ruta.casefold()})
        ocupados.add(nuevo_destino.casefold())

        if renombra and not mover:
            tipo = "renombrar"
            confianza = "media" if fuente == "metadatos" else "baja"
            motivo = f"título del PDF ({'metadatos' if fuente == 'metadatos' else 'texto de la portada'})"
        elif renombra and mover:
            tipo = "mover y renombrar"
        else:
            tipo = "mover"

        plan.cambios.append(Cambio(
            origen=ruta, destino=nuevo_destino, tipo=tipo, confianza=confianza or "media",
            motivo=motivo, alternativas=alternativas,
            seleccionado=(confianza or "media") in ("alta", "media"),
        ))

    plan.cambios.sort(key=lambda c: (_RANGO_CONFIANZA[c.confianza], c.destino.casefold()))
    return plan


# ----------------------------------------------------------------------------- aplicar / deshacer
def _carpeta_historial(raiz: str) -> str:
    destino = os.path.join(raiz, CARPETA_HISTORIAL)
    try:
        os.makedirs(destino, exist_ok=True)
        probe = os.path.join(destino, ".w")
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return destino
    except OSError:
        alt = os.path.join(carpeta_datos(), CARPETA_HISTORIAL)
        os.makedirs(alt, exist_ok=True)
        return alt


def aplicar(raiz: str, cambios, progreso_cb=None, cancelar=None) -> dict:
    """Ejecuta los cambios `seleccionado`. Devuelve {'aplicados', 'errores', 'historial'}."""
    raiz = os.path.abspath(raiz)
    elegidos = [c for c in cambios if c.seleccionado]
    hechos, errores = [], []
    try:
        for i, c in enumerate(elegidos):
            if cancelar and cancelar():
                errores.append("Cancelado por el usuario.")
                break
            if progreso_cb:
                progreso_cb(i, len(elegidos), os.path.basename(c.origen))
            try:
                if not os.path.isfile(c.origen):
                    raise FileNotFoundError("el archivo ya no existe")
                destino = c.destino
                if os.path.exists(destino):                       # nunca se sobrescribe nada
                    stem, ext = os.path.splitext(os.path.basename(destino))
                    destino = _nombre_libre(os.path.dirname(destino), stem, set(), ext)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.move(c.origen, destino)
                hechos.append({"origen": c.origen, "destino": destino, "tipo": c.tipo})
            except Exception as e:
                errores.append(f"{os.path.basename(c.origen)}: {e}")
    finally:
        ruta_historial = ""
        if hechos:
            carpeta = _carpeta_historial(raiz)
            ruta_historial = os.path.join(carpeta, f"historial_{datetime.now():%Y%m%d_%H%M%S}.json")
            with open(ruta_historial, "w", encoding="utf-8") as f:
                json.dump({"fecha": datetime.now().isoformat(timespec="seconds"), "raiz": raiz,
                           "cambios": hechos}, f, ensure_ascii=False, indent=1)
    if progreso_cb:
        progreso_cb(len(elegidos), len(elegidos), "")
    return {"aplicados": len(hechos), "errores": errores, "historial": ruta_historial}


def listar_historiales(raiz: str) -> list:
    """Historiales de cambios aplicados, del más reciente al más antiguo."""
    encontrados = []
    for carpeta in (os.path.join(os.path.abspath(raiz), CARPETA_HISTORIAL),
                    os.path.join(carpeta_datos(), CARPETA_HISTORIAL)):
        if os.path.isdir(carpeta):
            for f in os.listdir(carpeta):
                if f.startswith("historial_") and f.endswith(".json"):
                    encontrados.append(os.path.join(carpeta, f))
    return sorted(set(encontrados), key=os.path.basename, reverse=True)


def deshacer(ruta_historial: str, progreso_cb=None) -> dict:
    """Revierte un historial (en orden inverso). Lo que no se puede revertir se informa, no se fuerza."""
    with open(ruta_historial, encoding="utf-8") as f:
        datos = json.load(f)
    cambios = list(reversed(datos.get("cambios", [])))
    revertidos, errores = 0, []
    for i, c in enumerate(cambios):
        if progreso_cb:
            progreso_cb(i, len(cambios), os.path.basename(c["destino"]))
        try:
            if not os.path.isfile(c["destino"]):
                raise FileNotFoundError("ya no está en su nueva ubicación")
            if os.path.exists(c["origen"]):
                raise FileExistsError("la ubicación original está ocupada")
            os.makedirs(os.path.dirname(c["origen"]), exist_ok=True)
            shutil.move(c["destino"], c["origen"])
            revertidos += 1
        except Exception as e:
            errores.append(f"{os.path.basename(c['destino'])}: {e}")
    if not errores:
        try:
            os.replace(ruta_historial, ruta_historial + ".deshecho")
        except OSError:
            pass
    return {"revertidos": revertidos, "errores": errores}


# ----------------------------------------------------------------------------- reporte
def generar_reporte(raiz: str, incluir_protegidas: bool = False, progreso_cb=None,
                    protegidas=PROTEGIDAS_POR_DEFECTO, ruta_salida: str = None) -> dict:
    """Mapa de la biblioteca en un TXT (mismo formato que el script original)."""
    raiz = os.path.abspath(raiz)
    protegidas_cf = {p.casefold() for p in protegidas}
    lineas = ["=" * 60, " REPORTE DE ESTRUCTURA DE LA BIBLIOTECA DE PDFs", "=" * 60 + "\n"]
    total_pdfs = total_carpetas = omitidos = 0

    for carpeta, dirs, archivos in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if not _es_oculta(d))
        rel = os.path.relpath(carpeta, raiz)
        primera = "" if rel == "." else rel.replace("\\", "/").split("/")[0]
        pdfs = sorted(a for a in archivos if a.lower().endswith(".pdf"))
        if primera.casefold() in protegidas_cf and not incluir_protegidas:
            omitidos += len(pdfs)
            continue
        if not pdfs and not dirs:
            continue
        total_carpetas += 1
        if progreso_cb:
            progreso_cb(total_carpetas, 0, rel)
        lineas.append(f"📁 Carpeta: [{rel}]")
        lineas.append(f"   └─ Subcarpetas encontradas: {len(dirs)}")
        lineas.append(f"   └─ Archivos PDF ({len(pdfs)}):")
        for a in pdfs:
            lineas.append(f"      • {a}")
            total_pdfs += 1
        lineas.append("-" * 60)

    resumen = ["📊 RESUMEN GENERAL:",
               f"   • Total de directorios analizados: {total_carpetas}",
               f"   • Total de archivos PDF encontrados: {total_pdfs}",
               "=" * 60 + "\n"]
    if omitidos:
        resumen.insert(3, f"   • PDFs en carpetas protegidas no listados: {omitidos}")
    lineas[3:3] = resumen

    ruta_salida = ruta_salida or os.path.join(raiz, ARCHIVO_REPORTE)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return {"total_pdfs": total_pdfs, "total_carpetas": total_carpetas, "omitidos": omitidos, "ruta": ruta_salida}


# ----------------------------------------------------------------------------- consola
def _imprimir_plan(plan: Plan, limite: int = 60):
    print(f"\n{len(plan.cambios)} cambios propuestos de {plan.total_pdfs} PDFs "
          f"({plan.sin_cambios} sin cambios).")
    for c, n in plan.contar_por_confianza().items():
        if n:
            print(f"  - {c}: {n}")
    for c in plan.cambios[:limite]:
        marca = "[x]" if c.seleccionado else "[ ]"
        print(f" {marca} ({c.confianza}) {os.path.basename(c.origen)}  ➔  "
              f"{os.path.relpath(c.destino, plan.raiz)}   [{c.motivo}]")
    if len(plan.cambios) > limite:
        print(f"  ... y {len(plan.cambios) - limite} más")
    for nota in plan.notas:
        print("  ℹ", nota)


def main():
    """Menú de consola equivalente al del script original (con vista previa y deshacer)."""
    print("=" * 46 + "\n     GESTOR DE BIBLIOTECA DIGITAL PDF\n" + "=" * 46)
    ruta = input("Carpeta raíz de tus PDFs:\n> ").strip().strip('"').strip("'")
    if not os.path.isdir(ruta):
        print("⚠️ La carpeta no existe.")
        return
    while True:
        print("\n1. Solo organizar / clasificar en carpetas\n2. Solo renombrar PDFs\n"
              "3. Renombrar y luego organizar\n4. Generar reporte de estructura (TXT)\n"
              "5. Deshacer el último cambio aplicado\n6. Salir")
        op = input("\nElige una opción (1-6): ").strip()
        if op in ("1", "2", "3"):
            plan = planificar(ruta, Opciones(organizar=op in ("1", "3"), renombrar=op in ("2", "3")),
                              progreso_cb=lambda i, t, n: print(f"\r  leyendo {i}/{t}", end="", flush=True))
            _imprimir_plan(plan)
            if plan.cambios and input("\n¿Aplicar los marcados [x]? (s/N): ").strip().lower() == "s":
                r = aplicar(ruta, plan.cambios)
                print(f"✅ Aplicados: {r['aplicados']}  Errores: {len(r['errores'])}")
                for e in r["errores"]:
                    print("  ⚠️", e)
        elif op == "4":
            r = generar_reporte(ruta)
            print(f"✅ {r['total_pdfs']} PDFs en {r['total_carpetas']} carpetas → {r['ruta']}")
        elif op == "5":
            hist = listar_historiales(ruta)
            if not hist:
                print("No hay cambios que deshacer.")
            else:
                r = deshacer(hist[0])
                print(f"↩️ Revertidos: {r['revertidos']}  Errores: {len(r['errores'])}")
        elif op == "6":
            break


if __name__ == "__main__":
    main()
