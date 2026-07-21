"""
Configuracion central del pipeline de catalogos de bombas ESP.
==============================================================
Carga credenciales/rutas desde .env y define las rutas de salida.
Un solo lugar para cambiar paths, patrones de fabricante y constantes.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------- rutas
CATALOGS_DIR = Path(os.getenv("CATALOGS_DIR",
                              "C:/Users/pablo/OneDrive/Desktop/TESIS/CATALOGOS"))

OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = OUTPUT_DIR / "logs"          # logs por corrida y por PDF
TABLES_DIR = OUTPUT_DIR / "tables"     # tablas crudas extraidas por PDF
IMAGES_DIR = OUTPUT_DIR / "images"     # graficos extraidos + overlays QA
CURVES_DIR = OUTPUT_DIR / "curves"     # puntos digitalizados (JSON) por PDF
MANIFEST_PATH = BASE_DIR / "manifest.json"   # hash de PDFs ya procesados

for _d in (OUTPUT_DIR, LOG_DIR, TABLES_DIR, IMAGES_DIR, CURVES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- MySQL
MYSQL = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "database": os.getenv("MYSQL_DB", "catalogos_pump"),
    "app_user": os.getenv("MYSQL_APP_USER", "bes_pipeline"),
    "app_password": os.getenv("MYSQL_APP_PASSWORD", ""),
    "root_user": os.getenv("MYSQL_ROOT_USER", "root"),
    "root_password": os.getenv("MYSQL_ROOT_PASSWORD", ""),
}

# --------------------------------------------------- deteccion de fabricante
# Se busca en el nombre de archivo y en el texto de las primeras paginas.
MANUFACTURER_PATTERNS: list[tuple[str, str]] = [
    ("alkhorayef", "Alkhorayef"),
    ("reda", "Reda"),
    ("centrilift", "Centrilift"),
    ("borets", "Borets"),
    ("wood group", "WoodGroup"),
    ("woodgroup", "WoodGroup"),
    ("schlumberger", "Reda"),
    ("baker hughes", "Centrilift"),
]

MANUFACTURER_FULLNAME = {
    "Alkhorayef": ("Alkhorayef Petroleum", "Arabia Saudita"),
    "Reda": ("Schlumberger REDA (SLB)", "EE.UU."),
    "Centrilift": ("Baker Hughes Centrilift", "EE.UU."),
    "Borets": ("Borets International", "Rusia/EE.UU."),
    "WoodGroup": ("Wood Group ESP", "EE.UU."),
    "Desconocido": ("Fabricante no identificado", ""),
}

# ------------------------------------------------------------- constantes
# Identidad hidraulica ESP: eff = Q[bpd] * H[ft] / (135773 * HP)  (a SG=1.0)
HYDRAULIC_K = 135_773.0
DEFAULT_FREQUENCY_HZ = 60

# PDFs que NO son de bombas (se recorren pero no producen fichas de bomba).
NON_PUMP_HINTS = ("cable", "seal", "transformer", "swbd", "mtr cntrl",
                  "motor", "products-services", "xtreme-performance-motors")
