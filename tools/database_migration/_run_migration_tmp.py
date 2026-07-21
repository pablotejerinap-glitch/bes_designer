# Copia temporal ejecutable de migrate_json_to_excel.py (workaround de
# un problema de sincronización de archivos; borrar tras ejecutar).
import runpy
import sys
from pathlib import Path

# Ejecuta el módulo real leyendo su fuente desde este mismo directorio
# no es posible (archivo cacheado); replicamos la llamada:
# El propio directorio: estos scripts se importan entre si por nombre plano.
sys.path.insert(0, str(Path(__file__).parent))

# --- contenido idéntico a migrate_json_to_excel.py ---
from __future__ import annotations
