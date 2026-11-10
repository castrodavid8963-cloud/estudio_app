# Hub de Estudio

Biblioteca de PDF con tutor local (Ollama), rutas de estudio, seguimiento automático del tiempo, notas, repaso espaciado,
búsqueda en el contenido de todos tus libros y planificación con metas.

## Instalar y ejecutar

```
pip install -r requirements.txt
python app.py
```

Para el tutor IA hace falta [Ollama](https://ollama.com) con un modelo de chat instalado (por ejemplo `qwen2.5-coder:7b`).
Sin Ollama todo lo demás funciona.

## Dónde se guardan tus datos

Junto al código (o junto al `.exe`): `estudios.db`, `portadas_cache/`, `respaldos/`. El índice de búsqueda (`busqueda.db`)
puede ocupar varios GB con una biblioteca grande: muévelo a otro disco con `ESTUDIO_INDICE` o desde la pestaña Buscar.

| Variable de entorno | Para qué |
|---|---|
| `ESTUDIO_DATOS` | Carpeta de datos (base, portadas, respaldos) |
| `ESTUDIO_INDICE` | Carpeta del índice de búsqueda |
| `ESTUDIO_MODELO` | Modelo de Ollama por defecto |
| `ESTUDIO_TESSERACT` | Ruta a `tesseract.exe` si no está en el PATH |

## Temas e iconos

Herramientas › Ajustes › Apariencia: Medianoche, Onyx, Negro, Verde bosque, Océano, Vino, Blanco y Papel. Al elegir uno la
app se reinicia sola. La elección se guarda en `tema.json` (junto a tus datos). Los iconos son [Lucide](https://lucide.dev)
(licencia ISC, en `assets/`) y toman el color del tema; para añadir un tema nuevo, agrega una paleta a `TEMAS` en `tema.py`.

## Respaldo

Herramientas › Mantenimiento. Un respaldo es un `.zip` con tu base de datos (progreso, notas, tarjetas, rutas, tiempo).
Se hace uno automático al cerrar si el último tiene 7 días o más (se conservan 10). Restaurar guarda antes una copia de lo
que había (`estudios.antes_de_restaurar.db`). Tus PDF no forman parte del respaldo.

## OCR para PDF escaneados (opcional)

1. Instala Tesseract (Windows: instalador de UB Mannheim) y marca el idioma **Spanish** durante la instalación.
2. Deja que termine el indexado en la pestaña Buscar; los libros sin texto se cuentan como «escaneados».
3. Herramientas › Mantenimiento › Aplicar OCR. Se puede detener y retomar; el PDF original no se modifica.

## Pruebas automáticas

```
python -m unittest discover -s tests -t .
```

Usan carpetas temporales: nunca tocan tus datos. Las de OCR se omiten si no hay Tesseract.

## Crear el ejecutable (Windows)

Doble clic en `construir_exe.bat`. Instala lo necesario, corre las pruebas y deja `dist\HubEstudio\HubEstudio.exe`.
Copia la carpeta `dist\HubEstudio` completa donde quieras; los datos se guardan junto al `.exe`
(o en `%APPDATA%\HubEstudio` si esa carpeta no permite escribir).
