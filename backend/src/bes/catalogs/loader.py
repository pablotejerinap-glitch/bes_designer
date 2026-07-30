"""
Equipment catalog loader for BES/ESP system design.
Loads JSON catalog files and provides query/interpolation methods.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.interpolate import interp1d

from bes.core.models import PumpCurve, PumpPerformancePoint

CATALOG_DIR = Path(__file__).parent
"""Directorio de los JSON de catalogo. Viaja con el paquete: no depende del
CWD ni de la raiz del repo. Unico lugar de verdad — usarlo desde los scripts."""


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_optional(path: Path, key: str) -> list[dict]:
    """Load an optional catalog file; return [] if it is absent."""
    if not path.exists():
        return []
    return _load_json(path).get(key, [])


def _parse_pumps(raw: list[dict]) -> list[PumpCurve]:
    pumps: list[PumpCurve] = []
    for entry in raw:
        points = [
            PumpPerformancePoint(
                flow_rate=pt["flow_bpd"],
                head_per_stage=pt["head_ft_per_stage"],
                hp_per_stage=pt["hp_per_stage"],
                efficiency=pt["efficiency"],
            )
            for pt in entry["performance_curve"]
        ]
        pumps.append(
            PumpCurve(
                manufacturer=entry["manufacturer"],
                series=entry["series"],
                model=entry["model"],
                od=entry["od_inches"],
                min_flow=entry["min_flow_bpd"],
                max_flow=entry["max_flow_bpd"],
                bep_flow=entry["bep_flow_bpd"],
                max_stages=entry["max_stages"],
                housing_options=entry["housing_options"],
                points=points,
                housing_pressure_limit_psi=entry.get("housing_pressure_limit_psi", 0.0),
            )
        )
    return pumps


def _interpolate_vdrop_per_amp(cable: dict, temp_f: float) -> float:
    """Return voltage drop in V per amp per 1000 ft, interpolated to temp_f."""
    vd_map = cable["voltage_drop_v_per_amp_per_1000ft"]
    temps = sorted(float(k) for k in vd_map.keys())
    values = [vd_map[str(int(t))] for t in temps]

    if temp_f <= temps[0]:
        return values[0]
    if temp_f >= temps[-1]:
        return values[-1]
    for i in range(len(temps) - 1):
        if temps[i] <= temp_f <= temps[i + 1]:
            frac = (temp_f - temps[i]) / (temps[i + 1] - temps[i])
            return values[i] + frac * (values[i + 1] - values[i])
    return values[-1]


class CatalogManager:
    """Load and query ESP/BES equipment catalogs.

    Args:
        catalog_dir: Directory containing the JSON catalog files.
            Defaults to the ``catalogs/`` package directory.
    """

    def __init__(self, catalog_dir: Optional[str] = None) -> None:
        base = Path(catalog_dir) if catalog_dir else CATALOG_DIR
        self._pumps: list[PumpCurve] = _parse_pumps(
            _load_json(base / "pumps.json")["pumps"]
        )
        self._motors: list[dict] = _load_json(base / "motors.json")["motors"]
        self._cables: list[dict] = _load_json(base / "cables.json")["cables"]
        self._seals: list[dict] = _load_json(base / "seals.json")["seals"]
        # Optional catalogs (added later; load defensively so older deployments
        # without these files still construct a working manager).
        self._gas_handlers: list[dict] = _load_optional(
            base / "gas_handlers.json", "gas_handlers"
        )
        self._sensors: list[dict] = _load_optional(
            base / "sensors.json", "sensors"
        )
        self._controllers: list[dict] = _load_optional(
            base / "controllers.json", "controllers"
        )
        # Tablas dimensionales Tenaris (API 5CT): OD + peso -> ID y drift.
        # Resuelven el ID del casing/tubing que el usuario casi nunca tiene a
        # mano (los catalogos publican OD y peso nominal, no el ID).
        _ct_path = base / "casing_tubing.json"
        _ct = _load_json(_ct_path) if _ct_path.exists() else {}
        self._casing_dims: list[dict] = _ct.get("casing", [])
        self._tubing_dims: list[dict] = _ct.get("tubing", [])

    # ------------------------------------------------------------------
    # Pump queries
    # ------------------------------------------------------------------

    def get_all_pumps(self) -> list[PumpCurve]:
        """Return every pump in the catalog."""
        return list(self._pumps)

    def get_pumps_by_casing(self, casing_id_in: float) -> list[PumpCurve]:
        """Return pumps whose OD fits inside *casing_id_in* (casing inner diameter).

        The filter requires ``pump.od < casing_id_in`` — the caller should pass
        the casing drift/inner diameter so that standard API clearances are
        implicitly respected by the available casing sizes.
        """
        return [p for p in self._pumps if p.od < casing_id_in]

    def get_pumps_by_flow_range(self, flow_bpd: float) -> list[PumpCurve]:
        """Return pumps whose operating range includes *flow_bpd*."""
        return [p for p in self._pumps if p.min_flow <= flow_bpd <= p.max_flow]

    # ------------------------------------------------------------------
    # Casing / tubing dimensional queries (Tenaris API 5CT)
    # ------------------------------------------------------------------
    #
    # El usuario elige un OD y un peso nominal (lo que traen los catalogos);
    # el ID y el drift salen de estas tablas. ``get_casing_dims`` es el punto
    # que resuelve el ID que el modelo ``WellGeometry`` necesita.

    @staticmethod
    def _dims_ods(rows: list[dict]) -> list[dict]:
        """Lista de ODs disponibles (uno por diametro), ordenada, con etiqueta."""
        seen: dict[float, str] = {}
        for r in rows:
            seen.setdefault(r["od_in"], r["od_label"])
        return [
            {"od_in": od, "od_label": lbl}
            for od, lbl in sorted(seen.items())
        ]

    @staticmethod
    def _dims_weights(rows: list[dict], od_in: float) -> list[dict]:
        """Pesos disponibles para un OD, con su ID y drift resueltos."""
        out = [
            {
                "weight_lbft": r["weight_lbft"],
                "wall_in": r["wall_in"],
                "id_in": r["id_in"],
                "drift_in": r["drift_in"],
            }
            for r in rows
            if abs(r["od_in"] - od_in) < 1e-6
        ]
        return sorted(out, key=lambda x: x["weight_lbft"])

    @staticmethod
    def _dims_lookup(rows: list[dict], od_in: float, weight_lbft: float) -> dict:
        for r in rows:
            if abs(r["od_in"] - od_in) < 1e-6 and abs(
                r["weight_lbft"] - weight_lbft
            ) < 1e-6:
                return dict(r)
        raise ValueError(
            f"No hay entrada para OD={od_in} in y peso={weight_lbft} lb/ft en la tabla"
        )

    def list_casing_ods(self) -> list[dict]:
        """ODs de casing disponibles (``od_in`` + ``od_label``)."""
        return self._dims_ods(self._casing_dims)

    def list_tubing_ods(self) -> list[dict]:
        """ODs de tubing disponibles (``od_in`` + ``od_label``)."""
        return self._dims_ods(self._tubing_dims)

    def casing_weights(self, od_in: float) -> list[dict]:
        """Pesos de casing para un OD, cada uno con su ID y drift."""
        return self._dims_weights(self._casing_dims, od_in)

    def tubing_weights(self, od_in: float) -> list[dict]:
        """Pesos de tubing para un OD, cada uno con su ID y drift."""
        return self._dims_weights(self._tubing_dims, od_in)

    def get_casing_dims(self, od_in: float, weight_lbft: float) -> dict:
        """Dimensiones de casing (id_in, drift_in, wall_in) para OD + peso.

        Raises:
            ValueError: si el par (OD, peso) no existe en la tabla Tenaris.
        """
        return self._dims_lookup(self._casing_dims, od_in, weight_lbft)

    def get_tubing_dims(self, od_in: float, weight_lbft: float) -> dict:
        """Dimensiones de tubing (id_in, drift_in, wall_in) para OD + peso."""
        return self._dims_lookup(self._tubing_dims, od_in, weight_lbft)

    def all_casing_dims(self) -> list[dict]:
        """Tabla completa de casing (para exponer por la API al frontend)."""
        return list(self._casing_dims)

    def all_tubing_dims(self) -> list[dict]:
        """Tabla completa de tubing (para exponer por la API al frontend)."""
        return list(self._tubing_dims)

    # ------------------------------------------------------------------
    # Motor queries
    # ------------------------------------------------------------------

    def get_motor(self, hp: float, voltage: float, series: str) -> dict:
        """Return the best-matching motor for the given requirements.

        Selects the smallest HP motor that meets or exceeds *hp*, filtering
        first by *series*; if none found in that series, falls back to all
        series.  Among qualifying motors, picks the one whose voltage rating
        is closest to *voltage*.

        Raises:
            ValueError: If no motor in the catalog meets the HP requirement.
        """
        candidates = [
            m for m in self._motors
            if m["hp_rating"] >= hp and m["series"] == series
        ]
        if not candidates:
            candidates = [m for m in self._motors if m["hp_rating"] >= hp]
        if not candidates:
            raise ValueError(
                f"No motor in catalog rated >= {hp} hp "
                f"(series={series}, target voltage={voltage} V)"
            )
        # smallest HP that covers the load, then closest voltage
        min_hp = min(m["hp_rating"] for m in candidates)
        candidates = [m for m in candidates if m["hp_rating"] == min_hp]
        return min(candidates, key=lambda m: abs(m["voltage"] - voltage))

    # ------------------------------------------------------------------
    # Cable queries
    # ------------------------------------------------------------------

    def get_cable(self, amps: float, temp_f: float, voltage: float) -> dict:
        """Return the most suitable cable for the given operating conditions.

        Filters by ``max_amps >= amps`` and ``max_temp_f >= temp_f``, then
        returns the cable with the lowest voltage drop per 1000 ft at the
        given *amps* and *temp_f* (i.e., the largest suitable conductor).

        Args:
            amps: Required current rating [A].
            temp_f: Maximum operating temperature [°F].
            voltage: System voltage (reserved for future multi-voltage logic).

        Raises:
            ValueError: If no cable in the catalog meets the requirements.
        """
        candidates = [
            c for c in self._cables
            if c["max_amps"] >= amps and c["max_temp_f"] >= temp_f
        ]
        if not candidates:
            raise ValueError(
                f"No cable rated for {amps} A at {temp_f} °F in catalog"
            )
        return min(
            candidates,
            key=lambda c: _interpolate_vdrop_per_amp(c, temp_f) * amps,
        )

    # ------------------------------------------------------------------
    # Pump curve interpolation
    # ------------------------------------------------------------------

    def interpolate_pump_curve(self, pump: PumpCurve, flow_bpd: float) -> dict:
        """Interpolate pump performance at *flow_bpd* using linear interpolation.

        Args:
            pump: A :class:`~core.models.PumpCurve` instance from this catalog.
            flow_bpd: Operating flow rate [bpd].

        Returns:
            dict with keys ``head_per_stage`` [ft], ``hp_per_stage`` [hp],
            and ``efficiency`` [0-1].

        Raises:
            ValueError: If *flow_bpd* is outside the range of the curve data.
        """
        flows = np.array([p.flow_rate for p in pump.points])
        heads = np.array([p.head_per_stage for p in pump.points])
        hps = np.array([p.hp_per_stage for p in pump.points])
        effs = np.array([p.efficiency for p in pump.points])

        f_head = interp1d(flows, heads, kind="linear", bounds_error=True)
        f_hp = interp1d(flows, hps, kind="linear", bounds_error=True)
        f_eff = interp1d(flows, effs, kind="linear", bounds_error=True)

        return {
            "head_per_stage": float(f_head(flow_bpd)),
            "hp_per_stage": float(f_hp(flow_bpd)),
            "efficiency": float(f_eff(flow_bpd)),
        }

    # ------------------------------------------------------------------
    # Seal / protector queries
    # ------------------------------------------------------------------

    def get_all_seals(self) -> list[dict]:
        """Return every seal/protector in the catalog."""
        return list(self._seals)

    def get_seal(
        self,
        motor_series: str,
        temp_f: float,
        thrust_lbs: float,
        prefer_type: str = "labyrinth",
    ) -> dict:
        """Select the most economical protector for the given conditions.

        Selection criteria (Brown §4.5325; ChampionX VIGIL / Reda VSEAL):

        1. Compatibility : ``motor_series`` listed in ``compatible_motor_series``.
        2. Temperature   : ``max_temp_f`` >= ``temp_f``.
        3. Thrust        : ``thrust_capacity_lbs`` >= ``thrust_lbs``.
        4. Type          : prefer *prefer_type*; if none of that type carries the
           load, fall back to any qualifying type.
        5. Economy       : smallest qualifying thrust capacity.

        Args:
            motor_series: Series string of the selected motor (e.g. ``"456"``).
            temp_f: Required temperature rating [°F] (use bottomhole temp).
            thrust_lbs: Estimated axial thrust load [lbs].
            prefer_type: Preferred seal type (``"labyrinth"``/``"bag"``/``"combined"``).

        Returns:
            Seal catalog dict.

        Raises:
            ValueError: If no compatible seal carries the load at temperature.
        """
        compatible = [
            s for s in self._seals
            if motor_series in s.get("compatible_motor_series", [])
            and s.get("max_temp_f", 0) >= temp_f
            and s.get("thrust_capacity_lbs", 0) >= thrust_lbs
        ]
        if not compatible:
            raise ValueError(
                f"No protector for motor series {motor_series} carrying "
                f"{thrust_lbs:.0f} lbs at {temp_f:.0f} °F"
            )
        preferred = [s for s in compatible if s.get("type") == prefer_type]
        pool = preferred if preferred else compatible
        return min(pool, key=lambda s: s["thrust_capacity_lbs"])

    # ------------------------------------------------------------------
    # Gas-handler queries
    # ------------------------------------------------------------------

    def get_all_gas_handlers(self) -> list[dict]:
        """Return every gas handler/separator in the catalog."""
        return list(self._gas_handlers)

    def select_gas_handler(
        self,
        flow_bpd: float,
        casing_id_in: float,
        prefer_type: str = "vortex",
    ) -> Optional[dict]:
        """Select a gas handler for the flow that fits the casing.

        Filters by flow range (``min_flow_bpd <= flow <= max_flow_bpd``) and
        casing fit (``od_inches < casing_id_in``), prefers *prefer_type*
        (vortex separators are highest efficiency), then picks the highest
        ``max_efficiency``. Returns ``None`` if nothing qualifies.
        """
        candidates = [
            g for g in self._gas_handlers
            if g["min_flow_bpd"] <= flow_bpd <= g["max_flow_bpd"]
            and g["od_inches"] < casing_id_in
        ]
        if not candidates:
            return None
        preferred = [g for g in candidates if g.get("type") == prefer_type]
        pool = preferred if preferred else candidates
        return max(pool, key=lambda g: g.get("max_efficiency") or 0.0)

    # ------------------------------------------------------------------
    # Sensor queries
    # ------------------------------------------------------------------

    def get_all_sensors(self) -> list[dict]:
        """Return every downhole sensor in the catalog."""
        return list(self._sensors)

    # ------------------------------------------------------------------
    # Surface controller / switchboard / VSD
    # ------------------------------------------------------------------

    def get_all_controllers(self) -> list[dict]:
        """Return every surface controller in the catalog."""
        return list(self._controllers)

    def get_controller(
        self, voltage: float, kva: float, amps: float, prefer_vsd: bool = False
    ) -> dict:
        """Select the surface controller (switchboard or VSD).

        Se necesita conocer, para dimensionarlo (Brown §4.5325): la **tensión de
        superficie**, la **potencia aparente (kVA)** y el **amperaje** del motor.
        Se filtra por esos tres límites y se prefiere VSD/tablero según
        *prefer_vsd*; entre los que califican se toma el más económico (menor
        kVA).

        Raises:
            ValueError: si no hay controlador en catálogo que cubra las
                condiciones.
        """
        want = "vsd" if prefer_vsd else "switchboard"

        def qualifies(c: dict) -> bool:
            return (
                c["max_voltage"] >= voltage
                and c["max_kva"] >= kva
                and c["max_amps"] >= amps
            )

        pool = [c for c in self._controllers if c["type"] == want and qualifies(c)]
        if not pool:  # sin match del tipo preferido → cualquier tipo que cubra
            pool = [c for c in self._controllers if qualifies(c)]
        if not pool:
            raise ValueError(
                f"No hay controlador de superficie para {voltage:.0f} V, "
                f"{kva:.0f} kVA, {amps:.0f} A"
            )
        return min(pool, key=lambda c: c["max_kva"])

    def select_sensor(
        self,
        intake_pressure_psi: float,
        bottom_temp_f: float,
        motor_voltage: float,
        need_discharge_pressure: bool = False,
    ) -> Optional[dict]:
        """Select the smallest-range sensor that covers the well conditions.

        Filters by intake-pressure range, intake-temperature range, motor
        voltage, and (optionally) the presence of a discharge-pressure
        transducer. Among qualifying models, picks the one with the tightest
        pressure range (best resolution). Returns ``None`` if none qualify.
        """
        candidates = []
        for s in self._sensors:
            if s["intake_pressure_max_psi"] < intake_pressure_psi:
                continue
            if s["intake_temp_max_f"] < bottom_temp_f:
                continue
            if motor_voltage > s.get("max_motor_voltage", 0):
                continue
            if need_discharge_pressure and not s.get("discharge_pressure_max_psi"):
                continue
            candidates.append(s)
        if not candidates:
            return None
        return min(candidates, key=lambda s: s["intake_pressure_max_psi"])
