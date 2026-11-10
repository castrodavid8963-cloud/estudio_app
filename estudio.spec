# -*- mode: python ; coding: utf-8 -*-
# Empaqueta el Hub de Estudio como carpeta con .exe (PyInstaller):  pyinstaller estudio.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datos = collect_data_files("customtkinter") + [("assets", "assets")]   # CustomTkinter + iconos Lucide
ocultos = collect_submodules("vistas") + ["ollama", "PIL._tkinter_finder", "iconos_codigos"]

a = Analysis(
    ["app.py"],
    pathex=["."],
    datas=datos,
    hiddenimports=ocultos,
    excludes=["tests", "test_ollama"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="HubEstudio",
    console=False,          # sin ventana de consola negra
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="HubEstudio")
