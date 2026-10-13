# Backend FastAPI — sirve bes.api.main:app con uvicorn.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Librerías del sistema que WeasyPrint carga por FFI en tiempo de ejecución, no
# al instalar: sin ellas `pip install weasyprint` pasa y el `import weasyprint`
# falla recién cuando alguien pide la memoria en PDF. Son las que renderizan
# texto (Pango), vectores (Cairo) e imágenes (gdk-pixbuf), más un juego de
# fuentes: una imagen slim no trae ninguna, y sin fuentes el PDF sale en blanco.
# Van antes de las deps de Python para que esta capa quede cacheada.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Deps primero para aprovechar la cache de capas.
COPY requirements-base.txt requirements-api.txt ./
RUN pip install -r requirements-api.txt

# Código + instalación editable SIN deps (ya instaladas arriba). El layout src/
# hace que `bes` sea el único paquete importable: imports absolutos
# (from bes.core... etc), sin sys.path.insert.
COPY . .
RUN pip install -e . --no-deps

EXPOSE 8000

# El puerto lo impone el entorno: Render asigna el suyo por la variable PORT
# (10000 por defecto) y el servicio tiene que escuchar ahí. Sin la variable
# cae en 8000, que es lo que mapea docker-compose.yml, así que el
# `docker compose up` local se comporta exactamente igual que antes.
#
# Va en forma shell —y no en la forma exec de lista— porque la exec NO invoca
# un shell: escrito como ["--port", "${PORT:-8000}"] el texto llegaría literal
# y uvicorn fallaría al parsearlo como entero.
#
# El `exec` no es decorativo: sin él, sh queda como PID 1 y no reenvía el
# SIGTERM del apagado, así que uvicorn no se entera y el contenedor muere
# recién por timeout. Con exec, uvicorn ES el PID 1 y cierra limpio.
CMD ["sh", "-c", "exec uvicorn bes.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
