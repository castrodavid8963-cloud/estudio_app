import ollama

def consultar_modelo():
    respuesta = ollama.chat(
        model='qwen2.5-coder:3b',
        messages=[
            {'role': 'user', 'content': 'Dame una breve explicación de qué es SQLite.'}
        ]
    )
    print("Respuesta de la IA local:\n")
    print(respuesta['message']['content'])

if __name__ == '__main__':
    consultar_modelo()