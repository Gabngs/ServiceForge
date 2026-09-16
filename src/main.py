"""Punto de entrada del prototipo — usado tanto en `python src/main.py` como
por PyInstaller para armar el .exe (ver .github/workflows/build-exe.yml)."""

from generador.gui import main

if __name__ == "__main__":
    main()
