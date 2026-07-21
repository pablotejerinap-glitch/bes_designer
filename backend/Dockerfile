# Backend FastAPI — sirve bes.api.main:app con uvicorn.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Deps primero para aprovechar la cache de capas.
COPY requirements-base.txt requirements-api.txt ./
RUN pip install -r requirements-api.txt

# Código + instalación editable SIN deps (ya instaladas arriba). El layout src/
# hace que `bes` sea el único paquete importable: imports absolutos
# (from bes.core... etc), sin sys.path.insert.
COPY . .
RUN pip install -e . --no-deps

EXPOSE 8000
CMD ["uvicorn", "bes.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
