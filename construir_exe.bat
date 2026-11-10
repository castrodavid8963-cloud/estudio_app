@echo off
REM Construye HubEstudio.exe (Windows). Requiere Python 3.10+ instalado y en el PATH.
REM Resultado: carpeta dist\HubEstudio\  (copia toda la carpeta donde quieras; los datos se guardan junto al .exe)
setlocal
cd /d "%~dp0"

if not exist .venv-build (
    echo Creando entorno de construccion...
    python -m venv .venv-build || goto :error
)
call .venv-build\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :error

echo Ejecutando pruebas automaticas...
python -m unittest discover -s tests -t . || goto :error

echo Empaquetando...
pyinstaller estudio.spec --noconfirm || goto :error

echo.
echo Listo: dist\HubEstudio\HubEstudio.exe
echo Para el OCR instala Tesseract aparte (ver README.md).
pause
exit /b 0

:error
echo.
echo Algo fallo. Revisa el mensaje de arriba.
pause
exit /b 1
