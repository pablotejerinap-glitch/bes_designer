"""FastAPI application for BES Designer.

Thin HTTP layer over ``services/`` + ``core/`` + ``recommender/``. The domain
raises ``ValueError`` for infeasible designs / cross-field validation; the
central handler below turns those into HTTP 422 with the message. Pydantic
handles per-field validation (also 422). See ``.claude/rules/api-contract.md``.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import catalogs, design

app = FastAPI(
    title="BES Designer API",
    version="1.0.0",
    description="Diseño automatizado de sistemas de Bombeo Electrosumergible (BES/ESP), "
                "metodología Kermit Brown Vol. 2b Cap. 4.5.",
)

# CORS para la SPA (Vite dev :5173) y el Streamlit de respaldo (:8501).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8501", "http://127.0.0.1:8501",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Domain ValueError (diseño inviable / validación cruzada) -> HTTP 422."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


app.include_router(design.router)
app.include_router(catalogs.router)
