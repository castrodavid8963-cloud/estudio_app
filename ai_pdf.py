import pymupdf as fitz
import ollama

def extraer_texto_pdf(ruta_pdf: str, max_paginas: int = 30) -> str:
    """Extrae el texto de las primeras N páginas del PDF usando PyMuPDF."""
    if not ruta_pdf or not fitz:
        return ""

    try:
        doc = fitz.open(ruta_pdf)
        texto = ""
        total_paginas = min(len(doc), max_paginas)

        for i in range(total_paginas):
            pagina = doc[i]
            pagina_texto = pagina.get_text("text") or ""
            if pagina_texto.strip():
                texto += f"\n--- Página {i+1} ---\n" + pagina_texto

        doc.close()
        return texto.strip()
    except Exception as e:
        print(f"[PDF] Error extrayendo texto de {ruta_pdf}: {e}")
        return ""

def consultar_ollama_con_contexto(
    pregunta: str, 
    contexto_pdf: str = "", 
    nombre_pdf: str = "", 
    modelo: str = "qwen2.5-coder:3b"
) -> str:
    """Envía la consulta a Ollama especificando el título del libro y su contenido extraído."""
    
    # Construir prompt de sistema explícito con el título del libro
    if nombre_pdf and nombre_pdf != "Ninguno":
        prompt_sistema = (
            f"Eres un tutor de estudio experto. El estudiante está estudiando el libro titulado: '{nombre_pdf}'.\n"
            "Tu objetivo es explicar conceptos, hacer resúmenes, responder dudas y sugerir guías de estudio basándote "
            "en este libro y en el material de referencia adjunto."
        )
    else:
        prompt_sistema = (
            "Eres un tutor de estudio personal experto y didáctico. "
            "Responde a las preguntas del estudiante de forma clara, estructurada y concisa."
        )

    # Construir contenido
    if contexto_pdf.strip():
        contenido_usuario = (
            f"LIBRO ACTIVO DE REFERENCIA: {nombre_pdf}\n\n"
            f"FRAGMENTO/TEXTO EXTRAÍDO DEL LIBRO:\n{contexto_pdf[:12000]}\n\n"  # Límite de seguridad
            f"PREGUNTA DEL ESTUDIANTE:\n{pregunta}"
        )
    else:
        contenido_usuario = (
            f"LIBRO ACTIVO DE REFERENCIA: {nombre_pdf}\n"
            f"(Nota: No se pudo extraer texto legible directamente del archivo PDF, pero usa el título como guía principal).\n\n"
            f"PREGUNTA DEL ESTUDIANTE:\n{pregunta}"
        )

    try:
        respuesta = ollama.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": contenido_usuario}
            ]
        )
        return respuesta['message']['content']
    except Exception as e:
        return f"⚠️ Error al conectar con Ollama: {e}"