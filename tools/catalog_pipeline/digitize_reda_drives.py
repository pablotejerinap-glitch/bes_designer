"""Digitaliza los accionamientos de superficie REDA: FixStar (FSD) y SpeedStar (VSD).

El *REDA ESP Catalog* publica los accionamientos en tablas de texto limpias, no
en gráficos, así que esto es transcripción con verificación — no hay lectura de
curvas ni calibración de ejes.

Qué se lee
----------
- **FixStar** (accionamiento de velocidad fija, págs. 508-509): el catálogo
  publica **tensión máxima y corriente** por modelo. Es lo que el proyecto
  llama ``type = "switchboard"``.
- **SpeedStar** (variadores, págs. 524-530): el catálogo publica la **potencia
  nominal a 480 V/60 Hz y a 380 V/50 Hz**, la **corriente de salida** y, en el
  MVD, los **kVA de salida** directamente. Es ``type = "vsd"``.

Los kVA que no vienen impresos
------------------------------
``get_controller()`` filtra por tensión, kVA y corriente. Los kVA sólo están
impresos en el SpeedStar MVD; en el resto se calculan con la **definición** de
potencia aparente trifásica::

    kVA = √3 · V · A / 1000

No es una estimación ni una correlación: es la identidad, con la tensión y la
corriente que publica el fabricante. Queda marcado en ``_source`` de cada
entrada para que se pueda distinguir de los kVA impresos del MVD.

Qué NO se carga, y por qué
--------------------------
Los accesorios sin rating eléctrico —kits de luces piloto, registradores de
corriente Bristol, transformadores de instrumento, módulos TVSS StarShield,
hardware de espWatcher— no entran: el modelo no los usa y cargarlos sólo
agregaría números de parte. Se listan en el informe de auditoría.

Uso::

    python tools/catalog_pipeline/digitize_reda_drives.py --pdf RUTA [--out RUTA]
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import pdfplumber

#: Páginas (índice 0) con las tablas de accionamientos.
PAGINA_FIXSTAR = (508, 509)
PAGINAS_SPEEDSTAR = (524, 525, 527, 528, 529, 530)

#: Tensión de entrada nominal a la que el catálogo declara la potencia de los
#: SpeedStar de baja tensión. El propio encabezado lo dice: «Rating at 480 V,
#: 60 Hz». No es un supuesto del proyecto.
TENSION_SPEEDSTAR_BT = 480.0

#: Ídem a 50 Hz. Las dos columnas conviven en la misma tabla.
TENSION_SPEEDSTAR_BT_50HZ = 380.0

_NUM = r"[\d,]+(?:\.\d+)?"


def _f(s: str) -> float:
    """Convierte un número del impreso a float. Los miles van con coma."""
    return float(s.replace(",", ""))


def kva_trifasico(voltios: float, amperes: float) -> float:
    """Potencia aparente trifásica [kVA]. Es la definición, no una correlación."""
    return math.sqrt(3.0) * voltios * amperes / 1000.0


# --------------------------------------------------------------------------
# FixStar — accionamiento de velocidad fija
# --------------------------------------------------------------------------

_FIXSTAR = re.compile(
    rf"(FixStar\s+\d+-\d+)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*\[",
)


def leer_fixstar(pdf) -> list[dict]:
    """Los FixStar de las tablas «Max. Voltage Rating / Current Rating»."""
    salida: list[dict] = []
    for pagina in PAGINA_FIXSTAR:
        texto = pdf.pages[pagina].extract_text() or ""
        for modelo, volt, amp, peso in _FIXSTAR.findall(texto):
            v, a = _f(volt), _f(amp)
            salida.append({
                "manufacturer": "REDA",
                "model": modelo.strip(),
                "type": "switchboard",
                "min_voltage": None,
                "max_voltage": v,
                "max_amps": a,
                "max_kva": round(kva_trifasico(v, a), 1),
                "weight_lbs": _f(peso),
                "_source": (
                    f"REDA ESP Catalog, «{modelo.strip()}», pág. {pagina + 1}. "
                    f"Tensión máxima y corriente IMPRESAS. Los kVA NO están "
                    f"impresos: se calculan con kVA = √3·V·A/1000, que es la "
                    f"definición de potencia aparente trifásica."
                ),
            })
    return salida


# --------------------------------------------------------------------------
# SpeedStar — variadores
# --------------------------------------------------------------------------

#: Filas de los SpeedStar de baja tensión: hp a 480 V/60 Hz, hp a 380 V/50 Hz,
#: corriente de salida, peso.
_SPEEDSTAR_BT = re.compile(
    rf"^\s*({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*\[", re.M,
)

#: Filas del SpeedStar MVD: «hp/A» y los kVA de salida, que acá SÍ vienen
#: impresos.
_SPEEDSTAR_MVD = re.compile(rf"^\s*({_NUM})/({_NUM})\s+({_NUM})\s+104\s*\[", re.M)

#: Encabezado de tabla de SpeedStar. Cada página tiene VARIAS, con el mismo
#: rango de potencias y distinto gabinete, número de pulsos y temperatura
#: ambiente. Leer la página entera como una sola tabla mezcla las variantes y
#: produce modelos repetidos que en realidad son equipos distintos.
_ENCABEZADO = re.compile(
    r"(?P<familia>SpeedStar[^\n—]*?)\*?\s*VSDs?—"
    r"NEMA\s*(?P<gabinete>[\w\s]+?),\s*"
    r"(?:(?P<pulsos>\d+)\s*Pulse[^,]*,\s*)?"
    r"(?:(?P<ambiente>\d+)\s*°F)?",
)


def _bloques(texto: str) -> list[tuple[re.Match, str]]:
    """Parte el texto de una página en (encabezado, cuerpo) por cada tabla."""
    marcas = list(_ENCABEZADO.finditer(texto))
    salida = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        salida.append((m, texto[m.end():fin]))
    return salida


def _sufijo(m: re.Match) -> str:
    """Etiqueta corta que distingue una variante de otra: «NEMA 1 12P 122F»."""
    partes = [f"NEMA {(m.group('gabinete') or '').strip()}"]
    if m.group("pulsos"):
        partes.append(f"{m.group('pulsos')}P")
    if m.group("ambiente"):
        partes.append(f"{m.group('ambiente')}F")
    return " ".join(partes)


def leer_speedstar(pdf) -> list[dict]:
    """Los SpeedStar de baja tensión y el MVD, tabla por tabla."""
    salida: list[dict] = []

    for pagina in PAGINAS_SPEEDSTAR:
        texto = pdf.pages[pagina].extract_text() or ""

        # --- MVD: 4160 V de entrada, kVA IMPRESOS -------------------------
        # No lleva encabezado con NEMA/pulsos en el mismo formato, así que se
        # busca sobre la página entera. Sus kVA impresos son además el mejor
        # control cruzado que tiene todo este script (ver verificar()).
        for hp, amp, kva in _SPEEDSTAR_MVD.findall(texto):
            salida.append({
                "manufacturer": "REDA",
                "model": f"SpeedStar MVD {_f(hp):.0f}hp",
                "type": "vsd",
                "min_voltage": None,
                "max_voltage": 4160.0,
                "max_amps": _f(amp),
                "max_kva": _f(kva),
                "kva_impresos": True,
                "hp_rating": _f(hp),
                "_source": (
                    f"REDA ESP Catalog, «SpeedStar MVD», pág. {pagina + 1}. "
                    f"Potencia, corriente y kVA de salida a 4,160 V IMPRESOS."
                ),
            })

        # --- Baja tensión: 480 V / 60 Hz y 380 V / 50 Hz ------------------
        for enc, cuerpo in _bloques(texto):
            familia = enc.group("familia").strip()
            sufijo = _sufijo(enc)
            for hp60, hp50, amp, peso in _SPEEDSTAR_BT.findall(cuerpo):
                a = _f(amp)
                salida.append({
                    "manufacturer": "REDA",
                    "model": f"{familia} {_f(hp60):.0f}hp {sufijo}",
                    "type": "vsd",
                    "min_voltage": None,
                    "max_voltage": TENSION_SPEEDSTAR_BT,
                    "max_amps": a,
                    "max_kva": round(kva_trifasico(TENSION_SPEEDSTAR_BT, a), 1),
                    "kva_impresos": False,
                    "hp_rating": _f(hp60),
                    "hp_rating_50hz": _f(hp50),
                    "weight_lbs": _f(peso),
                    "enclosure": f"NEMA {(enc.group('gabinete') or '').strip()}",
                    "pulses": int(enc.group("pulsos")) if enc.group("pulsos") else None,
                    "ambient_temp_f": (
                        float(enc.group("ambiente")) if enc.group("ambiente") else None
                    ),
                    "_source": (
                        f"REDA ESP Catalog, «{familia} VSDs—{sufijo}», "
                        f"pág. {pagina + 1}. Potencia a 480 V/60 Hz y a "
                        f"380 V/50 Hz y corriente de salida IMPRESAS. Los kVA "
                        f"NO están impresos: se calculan con "
                        f"kVA = √3·480·A/1000, con la tensión que declara el "
                        f"propio encabezado de la tabla."
                    ),
                })
    return salida


# --------------------------------------------------------------------------
# Verificación
# --------------------------------------------------------------------------

def verificar(entradas: list[dict]) -> list[str]:
    """Controles de plausibilidad. No corrige: informa.

    El control más fuerte es el del SpeedStar MVD: el catálogo imprime tensión,
    corriente **y kVA**, y las tres tienen que cerrar con √3·V·A/1000. Si la
    identidad se cumple fila por fila, es que las tres columnas se leyeron bien
    — y eso valida de paso el método con que se calculan los kVA de las demás
    familias, donde no vienen impresos y no hay con qué contrastarlos.

    **No se compara la corriente contra la potencia en hp sin mirar la tensión.**
    A 480 V un hp pide del orden de 1.2 A, pero a 4,160 V pide 0.12 A: 500 hp
    con 62 A es correcto en el MVD y sería absurdo en un SpeedStar de baja
    tensión. La comparación se hace en kVA, que es la magnitud que no depende
    de la tensión.
    """
    problemas: list[str] = []
    for e in entradas:
        if not e["max_voltage"] or not e["max_amps"]:
            problemas.append(f"{e['model']}: sin tensión o sin corriente")
        if e["max_kva"] <= 0:
            problemas.append(f"{e['model']}: kVA no positivos")

        if e.get("kva_impresos"):
            calculado = kva_trifasico(e["max_voltage"], e["max_amps"])
            desvio = abs(calculado - e["max_kva"]) / e["max_kva"]
            if desvio > 0.02:
                problemas.append(
                    f"{e['model']}: los kVA impresos ({e['max_kva']:.0f}) no "
                    f"cierran con √3·V·A/1000 ({calculado:.0f}), "
                    f"{desvio:.1%} de desvío — alguna columna se leyó mal"
                )

        hp = e.get("hp_rating")
        if hp and e["max_kva"] < hp * 0.746:
            problemas.append(
                f"{e['model']}: {e['max_kva']:.0f} kVA no alcanzan para "
                f"{hp:.0f} hp ({hp * 0.746:.0f} kW de eje)"
            )
        hp50 = e.get("hp_rating_50hz")
        if hp and hp50 and hp50 >= hp:
            problemas.append(
                f"{e['model']}: la potencia a 50 Hz ({hp50:.0f}) no es menor "
                f"que a 60 Hz ({hp:.0f})"
            )

    modelos = [e["model"] for e in entradas]
    repetidos = {m for m in modelos if modelos.count(m) > 1}
    if repetidos:
        problemas.append(f"modelos repetidos: {sorted(repetidos)}")
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    pdf = pdfplumber.open(args.pdf)
    # Un mismo equipo puede figurar en dos páginas —el catálogo repite la tabla
    # del Titan en la página de continuación—. Se deduplica por la FICHA
    # ELÉCTRICA completa, no por el nombre: dos filas con el mismo modelo pero
    # distinta corriente son variantes distintas y las dos tienen que quedar.
    entradas: list[dict] = []
    firmas: set[tuple] = set()
    for e in leer_fixstar(pdf) + leer_speedstar(pdf):
        firma = (e["model"], e["max_voltage"], e["max_amps"], e["max_kva"])
        if firma in firmas:
            continue
        firmas.add(firma)
        entradas.append(e)

    problemas = verificar(entradas)

    print(f"accionamientos leídos: {len(entradas)}")
    for e in entradas:
        print(f"  {e['type']:11} {e['model']:26} {e['max_voltage']:7.0f} V "
              f"{e['max_amps']:7.0f} A {e['max_kva']:9.1f} kVA")
    for p in problemas:
        print("  PROBLEMA:", p)

    if args.out:
        args.out.write_text(
            json.dumps({"controllers": entradas, "problemas": problemas},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("escrito:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
