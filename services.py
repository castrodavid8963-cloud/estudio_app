import subprocess
import time
import urllib.request
import sys

OLLAMA_URL = "http://localhost:11434"

def ollama_esta_activo() -> bool:
    """Comprueba si el servidor local de Ollama está respondiendo."""
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def asegurar_ollama_activo() -> bool:
    """Verifica Ollama y lo inicia en segundo plano si está apagado."""
    if ollama_esta_activo():
        print("[Servicios] Ollama ya está ejecutándose.")
        return True
    
    print("[Servicios] Iniciando servidor de Ollama en segundo plano...")
    try:
        if sys.platform.startswith("win"):
            # Lógica para Windows
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            subprocess.Popen(["ollama", "serve"], creationflags=flags)
        else:
            # Lógica para Linux (CachyOS / systemd o proceso en background)
            try:
                # Intenta iniciarlo como servicio de systemd primero
                subprocess.run(["systemctl", "start", "ollama"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback: ejecutar 'ollama serve' desacoplado en segundo plano
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

        # Esperar hasta 5 segundos a que el servicio responda en http://localhost:11434
        for _ in range(10):
            time.sleep(0.5)
            if ollama_esta_activo():
                print("[Servicios] Ollama se inició correctamente.")
                return True

    except FileNotFoundError:
        print("[Servicios] Advertencia: No se encontró la orden 'ollama' en el PATH del sistema.")
        return False
    
    print("[Servicios] Advertencia: No se pudo confirmar el inicio de Ollama tras varios intentos.")
    return False