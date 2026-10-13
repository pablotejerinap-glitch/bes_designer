# -*- coding: utf-8 -*-
"""Memoria de cálculo paso a paso (HTML imprimible y PDF).

Es el mismo modelo que la memoria de la tesis: cada caso con IPR, PIP, TDH o
escalera de incrementos, corrección por viscosidad si corresponde, selección
de la bomba y del aparejo completo, con fórmula, sustitución, resultado y cita
verificada.

Uso típico::

    # la fila la arma la capa API: bes.api.memoria_datos.caso_convencional / caso_gas
    html = memoria_html([("Caso", "POZO DE DISEÑO", fila)], catalog)
    pdf = html_a_pdf(html)                            # requiere WeasyPrint
"""
from __future__ import annotations

from bes.reports.memoria.render import documento

__all__ = ["memoria_html", "html_a_pdf", "PDFNoDisponible"]


class PDFNoDisponible(RuntimeError):
    """WeasyPrint no está instalado: se puede entregar el HTML e imprimirlo."""


def memoria_html(casos, catalog, subtitulo: str = "", pie: str = "") -> str:
    return documento(casos, catalog, subtitulo=subtitulo, pie=pie)


def html_a_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:  # ImportError o librerías del sistema ausentes
        raise PDFNoDisponible(
            "La generación directa de PDF necesita WeasyPrint. Abrí la memoria en "
            "formato HTML y usá «Imprimir / guardar como PDF» del navegador."
        ) from exc
    return HTML(string=html).write_pdf()
