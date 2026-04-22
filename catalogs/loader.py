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

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.models import PumpCurve, PumpPerformancePoint

_CATALOG_DIR = Path(__file__).parent


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
        base = Path(catalog_dir) if catalog_dir else _CATALOG_DIR
        self._pumps: list[PumpCurve] = _parse_pumps(
            _load_json(base / "pumps.json")["pumps"]
        )
        self._motors: list[dict] = _load_json(base / "motors.json")["motors"]
        self._cables: list[dict] = _load_json(base / "cables.json")["cables"]
        self._seals: list[dict] = _load_json(base / "seals.json")["seals"]

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
