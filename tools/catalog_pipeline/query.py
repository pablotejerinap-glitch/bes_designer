"""
Consultas rapidas de verificacion sobre catalogos_pump.
USO: python query.py
"""
from __future__ import annotations

import db


def main() -> None:
    print("=== conteos ===")
    for t, n in db.counts().items():
        print(f"  {t:16s} {n}")

    conn = db.connect()
    with conn.cursor() as cur:
        print("\n=== bombas por fabricante y metodo ===")
        cur.execute("SELECT manufacturer_id, extraction_method, COUNT(*) n, "
                    "SUM(review_flag) rev FROM pumps "
                    "GROUP BY manufacturer_id, extraction_method ORDER BY n DESC")
        for r in cur.fetchall():
            print(f"  {r['manufacturer_id']:12s} {r['extraction_method']:14s} "
                  f"n={r['n']}  a_revisar={r['rev']}")

        print("\n=== 8 bombas con mas puntos de curva ===")
        cur.execute("SELECT p.pump_id, p.model, p.min_flow_bpd, p.max_flow_bpd, "
                    "p.bep_flow_bpd, COUNT(c.flow_bpd) pts "
                    "FROM pumps p JOIN pump_curves c ON c.pump_id=p.pump_id "
                    "GROUP BY p.pump_id ORDER BY pts DESC LIMIT 8")
        for r in cur.fetchall():
            print(f"  {r['pump_id']:22s} Q[{r['min_flow_bpd']:.0f}-"
                  f"{r['max_flow_bpd']:.0f}] BEP={r['bep_flow_bpd']:.0f}  "
                  f"{r['pts']} pts")

        print("\n=== curva de ejemplo (primera bomba con curva) ===")
        cur.execute("SELECT pump_id FROM pump_curves LIMIT 1")
        row = cur.fetchone()
        if row:
            pid = row["pump_id"]
            cur.execute("SELECT flow_bpd, head_ft_per_stage, hp_per_stage, "
                        "efficiency FROM pump_curves WHERE pump_id=%s "
                        "ORDER BY flow_bpd", (pid,))
            print(f"  {pid}:")
            for r in cur.fetchall():
                print(f"    Q={r['flow_bpd']:>8.0f}  H={r['head_ft_per_stage']}  "
                      f"HP={r['hp_per_stage']}  eff={r['efficiency']}")

        print("\n=== processing_log (ultima corrida) ===")
        cur.execute("SELECT pdf_file, manufacturer_id, status, pumps_found, "
                    "curves_digitized FROM processing_log "
                    "WHERE run_id=(SELECT run_id FROM processing_log "
                    "ORDER BY id DESC LIMIT 1) ORDER BY id")
        for r in cur.fetchall():
            print(f"  {r['status']:16s} {r['pumps_found']:>3} bombas  "
                  f"{r['curves_digitized']:>3} curvas  {r['pdf_file']}")
    conn.close()


if __name__ == "__main__":
    main()
