"""
Verificación v3.1 — semántica de SUBCONJUNTO
============================================
Desde la importación de Alkhorayef, la base Excel contiene MÁS equipos
que los JSON legados. La verificación ya no exige igualdad de conteos:
exige que (a) cada equipo del JSON esté presente e IDÉNTICO en Excel,
(b) las selecciones legadas no cambien de resultado, y (c) reporta qué
equipos nuevos amplían cada consulta. Supersede a verify_database_v3.py.

USO:  python verify_database_v31.py
"""
import sys
from pathlib import Path
from pathlib import Path as _P
# El propio directorio: estos scripts se importan entre si por nombre plano.
sys.path.insert(0, str(Path(__file__).parent))
import database_loader_v3 as dbl
from database_loader_v3 import _read_sheet
from bes.core.models import PumpCurve, PumpPerformancePoint
from bes.catalogs.loader import CatalogManager



errors = []
def eq(a, b):
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None: return a is None and b is None
        return abs(float(a) - float(b)) < 1e-9
    return a == b

jc = CatalogManager()
xc = dbl.ExcelCatalogManager()

# --- SUBCONJUNTO: cada bomba JSON debe estar idéntica en Excel ---
xmap = {(p.manufacturer, p.series, p.model): p for p in xc.get_all_pumps()}
for a in jc.get_all_pumps():
    b = xmap.get((a.manufacturer, a.series, a.model))
    name = f"pump:{a.manufacturer}_{a.model}"
    if b is None: errors.append(f"{name}: ausente en Excel"); continue
    for attr in ("od","min_flow","max_flow","bep_flow","max_stages"):
        if not eq(getattr(a,attr), getattr(b,attr)): errors.append(f"{name}.{attr}")
    if sorted(a.housing_options) != sorted(b.housing_options): errors.append(f"{name}.housings")
    if len(a.points) != len(b.points): errors.append(f"{name}.n_puntos")
    else:
        for pa, pb in zip(sorted(a.points, key=lambda p: p.flow_rate), b.points):
            for at in ("flow_rate","head_per_stage","hp_per_stage","efficiency"):
                if not eq(getattr(pa,at), getattr(pb,at)): errors.append(f"{name}.curva.{at}"); break

# --- resto de catálogos: igualdad exacta (sin fabricantes nuevos aún) ---
for label, ref, new, keys in [
    ("motor", jc._motors, xc._motors, ("model","voltage")),
    ("cable", jc._cables, xc._cables, ("type","conductor","size")),
    ("seal", jc._seals, xc._seals, ("model",)),
    ("gas_handler", jc._gas_handlers, xc._gas_handlers, ("model",)),
    ("sensor", jc._sensors, xc._sensors, ("model",))]:
    if len(ref) != len(new): errors.append(f"{label}: {len(ref)} vs {len(new)}"); continue
    for r0, n0 in zip(ref, new):
        for k in set(r0) | set(n0):
            va, vb = r0.get(k), n0.get(k)
            if isinstance(va, dict):
                if va != vb and not all(eq(va.get(t), (vb or {}).get(t)) for t in va):
                    errors.append(f"{label}.{k}")
            elif isinstance(va, list):
                if list(va) != list(vb or []): errors.append(f"{label}.{k}")
            elif not eq(va, vb): errors.append(f"{label}.{k}: {va!r}!={vb!r}")

# --- selecciones legadas inalteradas ---
m1, m2 = jc.get_motor(100,1000,"456"), xc.get_motor(100,1000,"456")
if m1["model"] != m2["model"]: errors.append("get_motor")
c1, c2 = jc.get_cable(40,180,1000), xc.get_cable(40,180,1000)
if (c1["conductor"],c1["size"]) != (c2["conductor"],c2["size"]): errors.append("get_cable")
s1, s2 = jc.get_seal("456",200,5000), xc.get_seal("456",200,5000)
if s1["model"] != s2["model"]: errors.append("get_seal")
# flow range: las selecciones JSON deben ser subconjunto de las Excel
j_set = {(p.manufacturer,p.model) for p in jc.get_pumps_by_flow_range(1300)}
x_set = {(p.manufacturer,p.model) for p in xc.get_pumps_by_flow_range(1300)}
if not j_set <= x_set: errors.append("get_pumps_by_flow_range: faltan legadas")
extra = x_set - j_set

n_curv = len(xc.get_all_pumps()); n_sin = len(getattr(xc, "pumps_without_curves", []))
if errors:
    print(f"FALLÓ ({len(errors)}):"); [print(" -", e) for e in errors[:30]]; sys.exit(1)
print(f"VERIFICADO: las 23 bombas legadas idénticas al JSON dentro de un catálogo "
      f"de {n_curv} bombas con curva ({n_sin} sin curva); motores/cables/sellos/"
      f"separadores/sensores idénticos; selecciones legadas inalteradas.")
print(f"A 1300 bpd ahora también candidatas: {sorted(extra)}")
