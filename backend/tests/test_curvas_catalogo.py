"""Foto de la curva de catálogo de cada bomba."""
from fastapi.testclient import TestClient

from bes.api.main import app

c = TestClient(app)


def test_reda_a_50_hz_devuelve_la_pagina_de_50():
    r = c.get("/api/catalogs/pumps/D5800N/curva-info?hz=50").json()
    assert r["tiene_foto"] and r["hz"] == 50 and "pág. 186" in r["fuente"]
    img = c.get(r["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_centrilift_no_tiene_foto():
    assert c.get("/api/catalogs/pumps/DC1000/curva-info").json()["tiene_foto"] is False


def test_todas_las_reda_y_wood_group_tienen_foto():
    from bes.catalogs.loader import CatalogManager
    for p in CatalogManager().get_all_pumps():
        if p.manufacturer in ("REDA", "Wood Group ESP") and p.model != "D-40":
            assert c.get(f"/api/catalogs/pumps/{p.model}/curva-info").json()["tiene_foto"], p.model
