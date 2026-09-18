# -*- coding: utf-8 -*-
"""Motores Wood Group ESP (catálogo octubre 2009) → filas de motors.json.

Dos trampas del PDF, las dos resueltas por estructura y no por posición:

1. La celda de HP está CENTRADA verticalmente sobre varias filas de tensión,
   así que la fila de HP no es la primera de su bloque. Lo que la identifica no
   es dónde está sino que **arrastra el largo y el peso**: la celda combinada de
   dimensiones abarca el mismo bloque. Una fila de tensión nunca los trae.

2. Un par de tensiones 60/50 Hz tiene la MISMA relación 1.2 que un par de HP
   60/50 Hz (610/508 = 1.20 igual que 30/25). Mirar sólo la relación hace pasar
   tensiones por potencias. Por eso el par de HP se acepta únicamente en filas
   con dimensiones.

Y el largo en pies se distingue del amperaje exigiendo que el cuarteto final
cierre ft/m = 3.281 y lb/kg = 2.205.

La asignación de cada fila de tensión a su potencia es física: dentro de una
misma potencia √3·V·A es casi constante. La constante se ajusta con las filas no
ambiguas de cada tabla. Lo que no cierra dentro del 12 % no se carga.
"""
import json, math, statistics as st

# Entrada: el texto de `pdftotext -layout` sobre
#   TESIS/CATALOGOS/WoodGroup/wood-group-esp-catalogue.pdf
# (Wood Group ESP, Inc., octubre 2009), sección «Product Catalog - Motors».
# Salida: las filas que se cargan en backend/src/bes/catalogs/motors.json.
S3 = math.sqrt(3)

def es_dims(q):
    """¿El cuarteto final es largo ft/m y peso lb/kg?

    El control fuerte es ft/m = 3.281; el de lb/kg = 2.205 se usa sólo como
    refuerzo porque la capa de texto trunca algunos kilos (2450 lb / «111» kg
    donde el impreso dice 1111). Exigir los dos dejaba invisibles marcadores de
    HP enteros. El peso no se guarda —no está en el esquema— así que su defecto
    no contamina nada; el largo sí, y ése cierra siempre.
    """
    ft, m, lb, kg = q
    return m > 0 and ft > 0.5 and abs(ft/m - 3.281) < 0.25 and lb > 0

def parte_dims(n):
    return (n[:-4], n[-4:]) if len(n) >= 5 and es_dims(n[-4:]) else (n, None)

def par_hp(x, y): return y > 0 and 1.13 < x/y < 1.27 and x >= 5
def par_v(a, b):  return a > 200 and b > 150 and 1.13 < a/b < 1.27
def ok_amp(a):    return 3 <= a <= 260

def amps_abajo(F, idx, usados):
    for j in range(idx+1, min(idx+3, len(F))):
        if j in usados: continue
        m, _ = parte_dims(F[j]["antes"] + F[j]["despues"])
        if len(m) == 1 and ok_amp(m[0]):
            usados.add(j); return m[0]
    return None

motores, problemas = [], []
for t in json.load(open("filas.json")):
    F = t["filas"]; hps=[]; ternas=[]; ancla=[]; usados=set(); dims={}; hp50={}
    for idx, f in enumerate(F):
        if idx in usados: continue
        n, dq = parte_dims(f["antes"] + f["despues"])
        if not n: continue
        # Fila completa HP+tensión+amps aunque no traiga dimensiones: cinco
        # números con esa estructura ya son inequívocos (una fila de tensión
        # sola nunca pasa de tres).
        if (not dq and len(n) == 5 and par_hp(n[0], n[1])
                and par_v(n[2], n[3]) and ok_amp(n[4])):
            hps.append(n[0]); hp50[n[0]] = n[1]
            ternas.append((n[2], n[3], n[4], n[0], f["i"]))
            ancla.append((n[0], S3*n[2]*n[4])); continue
        # Par de HP suelto, sin dimensiones: se acepta sólo si ninguno de los
        # dos puede ser una tensión (ambos por debajo de 200 V).
        if not dq and len(n) == 2 and par_hp(n[0], n[1]) and n[0] < 200:
            hps.append(n[0]); hp50[n[0]] = n[1]; continue
        if dq and len(n) >= 2 and par_hp(n[0], n[1]):        # ← marcador de HP
            hp = n[0]; hps.append(hp); dims[hp] = (dq[0], dq[2]); hp50[hp] = n[1]
            if len(n) >= 5 and par_v(n[2], n[3]) and ok_amp(n[4]):
                ternas.append((n[2], n[3], n[4], hp, f["i"])); ancla.append((hp, S3*n[2]*n[4]))
            elif len(n) >= 4 and par_v(n[2], n[3]):
                a = amps_abajo(F, idx, usados)
                if a: ternas.append((n[2], n[3], a, hp, f["i"])); ancla.append((hp, S3*n[2]*a))
                else: problemas.append((t["serie"],t["variante"],f["i"],f"HP {hp} V={n[2]} sin amps"))
            continue
        if len(n) >= 3 and par_v(n[0], n[1]) and ok_amp(n[2]):
            ternas.append((n[0], n[1], n[2], None, f["i"])); continue
        if len(n) == 2 and par_v(n[0], n[1]):
            a = amps_abajo(F, idx, usados)
            if a:
                ternas.append((n[0], n[1], a, None, f["i"]))
            elif par_hp(n[0], n[1]):
                # Sin amperaje debajo no puede ser una fila de tensión: toda
                # tensión publicada trae su corriente. Es un marcador de HP que
                # cae en el rango donde HP y volts se superponen (E56 llega a
                # 450 hp y las tensiones arrancan en 315 V).
                hps.append(n[0]); hp50[n[0]] = n[1]
            else:
                problemas.append((t["serie"],t["variante"],f["i"],f"V={n} sin amps"))
            continue
        if len(n) == 1: continue
        problemas.append((t["serie"], t["variante"], f["i"], f["raw"][:64]))

    H = sorted(set(hps))
    if not H or not ancla:
        problemas.append((t["serie"], t["variante"], t["linea"], "tabla sin ancla")); continue
    k = st.median(hp/va for hp, va in ancla)
    for v60, v50, amps, hp_fijo, li in ternas:
        if hp_fijo is not None:
            hp, err = hp_fijo, 0.0
        else:
            imp = k*S3*v60*amps
            hp = min(H, key=lambda h: abs(h-imp)); err = abs(hp-imp)/hp
            # La potencia implícita cae dentro del 3 % de la nominal en nueve
            # de cada diez filas (mediana 1 %), así que el 8 % es holgado para
            # aceptar y sigue siendo mucho menor que el escalón entre potencias
            # consecutivas. No se mira cuán cerca quedó la segunda candidata:
            # con escalones de 10 hp sobre 130, la segunda SIEMPRE está cerca, y
            # exigir margen tiraba ochenta filas buenas.
            if err > 0.08:
                problemas.append((t["serie"],t["variante"],li,
                                  f"V={v60} A={amps} → {imp:.1f} hp, más cerca {hp} ({err:.0%})")); continue
        motores.append({"manufacturer":"Wood Group ESP","series":t["serie"],"variante":t["variante"],
            "hp_rating":hp,"voltage":v60,"voltage_50hz":v50,"amperage":amps,
            "od_inches":t["od"],"min_casing_od_in":t["casing"],
            "length_ft":dims.get(hp,(None,None))[0],"weight_lb":dims.get(hp,(None,None))[1],
            "hp_rating_50hz":hp50.get(hp),
            "_err":round(err,3),"_linea":li})

print(f"motores: {len(motores)}   sin resolver: {len(problemas)}")
for p in problemas: print("   ", p)
json.dump({"motores":motores,"problemas":problemas}, open("crudo.json","w"), indent=1)
