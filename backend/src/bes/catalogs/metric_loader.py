"""
Loader for the metric ("ESP 01" método de cátedra) equipment catalog.

Kept separate from :class:`bes.catalogs.loader.CatalogManager` on purpose: the
metric catalog stores pump curves per operating *frequency* in métric units
(m³/d, m/etapa) and carries housing/shaft/bearing engineering limits that the
field catalog schema does not model.  Loading it apart keeps the field design
path and its catalogs completely untouched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_CATALOG_FILE = Path(__file__).parent / "metric_catalog.json"


class MetricCatalog:
    """Load and query the metric ESP catalog (pumps, motors, seals, cable)."""

    def __init__(self, path: Optional[str] = None) -> None:
        file = Path(path) if path else _CATALOG_FILE
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._pumps: list[dict] = data["pumps"]
        self._motors: list[dict] = data["motors"]
        self._seals: list[dict] = data["seals"]
        self._cables: list[dict] = data["cables"]
        self._cable_temp_correction: list[list[float]] = data["cable_temp_correction"]

    # ------------------------------------------------------------------
    # Pumps
    # ------------------------------------------------------------------

    def get_all_pumps(self) -> list[dict]:
        """Return every metric pump entry."""
        return list(self._pumps)

    def get_pump(self, model: str) -> dict:
        """Return the pump entry whose ``model`` matches (case-insensitive)."""
        for p in self._pumps:
            if p["model"].lower() == model.lower():
                return p
        raise ValueError(f"Pump '{model}' not in metric catalog")

    def get_pumps_by_casing(self, casing_id_in: float) -> list[dict]:
        """Return metric pumps whose OD fits inside *casing_id_in*."""
        return [p for p in self._pumps if p["od_inches"] < casing_id_in]

    # ------------------------------------------------------------------
    # Motors
    # ------------------------------------------------------------------

    def get_all_motors(self) -> list[dict]:
        """Return every metric motor entry."""
        return list(self._motors)

    def max_single_motor_hp(self) -> float:
        """Largest single-motor HP rating available."""
        return max(m["hp_rating"] for m in self._motors)

    # ------------------------------------------------------------------
    # Seals / protectors
    # ------------------------------------------------------------------

    def get_all_seals(self) -> list[dict]:
        """Return every metric seal/protector entry."""
        return list(self._seals)

    # ------------------------------------------------------------------
    # Cable
    # ------------------------------------------------------------------

    def get_all_cables(self) -> list[dict]:
        """Return every metric cable entry."""
        return list(self._cables)

    def cable_temp_correction_factor(self, temp_c: float) -> float:
        """Interpolate the cable voltage-drop temperature-correction factor.

        Uses the ``cable_temp_correction`` table (ambient °C → factor); clamps
        outside the tabulated range.
        """
        table = sorted(self._cable_temp_correction, key=lambda r: r[0])
        temps = [r[0] for r in table]
        facs = [r[1] for r in table]
        if temp_c <= temps[0]:
            return facs[0]
        if temp_c >= temps[-1]:
            return facs[-1]
        for i in range(len(temps) - 1):
            if temps[i] <= temp_c <= temps[i + 1]:
                frac = (temp_c - temps[i]) / (temps[i + 1] - temps[i])
                return facs[i] + frac * (facs[i + 1] - facs[i])
        return facs[-1]
