"""
Capa MySQL del pipeline: base de datos ``catalogos_pump``.
==========================================================
* ``bootstrap()`` (root): crea la base y un usuario dedicado. Se corre una
  sola vez; es idempotente.
* ``create_schema()`` (usuario del pipeline): crea las tablas con PK/FK,
  CHECK e indices. ``CREATE TABLE IF NOT EXISTS`` => reejecutable.
* upserts que permiten re-correr el pipeline sin duplicar filas.

Esquema (solo bombas, segun alcance elegido):
    manufacturers 1---N pumps N---1 data_sources
    pumps 1---N pump_housings
    pumps 1---N pump_curves        (puntos digitalizados de la curva)
    processing_log                 (auditoria de cada corrida por PDF)
"""
from __future__ import annotations

import datetime as _dt
from typing import Iterable, Optional

import pymysql

from config import MYSQL

# ----------------------------------------------------------------- conexion
def connect(*, root: bool = False, with_db: bool = True) -> pymysql.connections.Connection:
    """Conexion pymysql. root=True para el bootstrap; with_db=False para DDL
    de la propia base (CREATE DATABASE)."""
    user = MYSQL["root_user"] if root else MYSQL["app_user"]
    pwd = MYSQL["root_password"] if root else MYSQL["app_password"]
    kwargs = dict(host=MYSQL["host"], port=MYSQL["port"], user=user,
                  password=pwd, charset="utf8mb4", autocommit=True,
                  cursorclass=pymysql.cursors.DictCursor)
    if with_db:
        kwargs["database"] = MYSQL["database"]
    return pymysql.connect(**kwargs)


# ----------------------------------------------------------------- bootstrap
def bootstrap() -> None:
    """Crea la base y el usuario dedicado usando root. Idempotente."""
    db = MYSQL["database"]
    au, ap = MYSQL["app_user"], MYSQL["app_password"]
    conn = connect(root=True, with_db=False)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        # usuario dedicado (localhost). ALTER asegura el password si ya existia.
        cur.execute(f"CREATE USER IF NOT EXISTS %s@'localhost' IDENTIFIED BY %s",
                    (au, ap))
        cur.execute(f"ALTER USER %s@'localhost' IDENTIFIED BY %s", (au, ap))
        cur.execute(f"GRANT ALL PRIVILEGES ON `{db}`.* TO %s@'localhost'", (au,))
        cur.execute("FLUSH PRIVILEGES")
    conn.close()


# ------------------------------------------------------------------- esquema
_SCHEMA = [
    # ---- fabricantes ----
    """
    CREATE TABLE IF NOT EXISTS manufacturers (
        manufacturer_id VARCHAR(40)  NOT NULL,
        full_name       VARCHAR(120) NOT NULL,
        country         VARCHAR(60)  NULL,
        PRIMARY KEY (manufacturer_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---- fuentes / trazabilidad ----
    """
    CREATE TABLE IF NOT EXISTS data_sources (
        source_id   VARCHAR(60)  NOT NULL,
        pdf_file    VARCHAR(200) NOT NULL,
        source_type VARCHAR(40)  NOT NULL,
        citation    TEXT         NULL,
        PRIMARY KEY (source_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---- bombas (ficha) ----
    """
    CREATE TABLE IF NOT EXISTS pumps (
        pump_id           VARCHAR(80)  NOT NULL,
        manufacturer_id   VARCHAR(40)  NOT NULL,
        series            VARCHAR(20)  NULL,
        model             VARCHAR(60)  NULL,
        od_inches         DECIMAL(6,3) NULL,
        min_flow_bpd      DECIMAL(10,1) NULL,
        max_flow_bpd      DECIMAL(10,1) NULL,
        bep_flow_bpd      DECIMAL(10,1) NULL,
        max_stages        INT          NULL,
        frequency_hz      INT          NOT NULL DEFAULT 60,
        source_id         VARCHAR(60)  NULL,
        extraction_method VARCHAR(40)  NOT NULL DEFAULT 'pdf-text',
        review_flag       TINYINT(1)   NOT NULL DEFAULT 0,
        review_reason     VARCHAR(255) NULL,
        updated_at        DATETIME     NOT NULL,
        PRIMARY KEY (pump_id),
        CONSTRAINT fk_pump_mfr    FOREIGN KEY (manufacturer_id)
            REFERENCES manufacturers(manufacturer_id),
        CONSTRAINT fk_pump_source FOREIGN KEY (source_id)
            REFERENCES data_sources(source_id),
        CONSTRAINT chk_pump_od     CHECK (od_inches IS NULL OR od_inches > 0),
        CONSTRAINT chk_pump_stages CHECK (max_stages IS NULL OR max_stages > 0),
        INDEX idx_pump_mfr    (manufacturer_id),
        INDEX idx_pump_series (series),
        INDEX idx_pump_flow   (min_flow_bpd, max_flow_bpd),
        INDEX idx_pump_od     (od_inches)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---- housings disponibles ----
    """
    CREATE TABLE IF NOT EXISTS pump_housings (
        pump_id VARCHAR(80) NOT NULL,
        stages  INT         NOT NULL,
        PRIMARY KEY (pump_id, stages),
        CONSTRAINT fk_housing_pump FOREIGN KEY (pump_id)
            REFERENCES pumps(pump_id) ON DELETE CASCADE,
        CONSTRAINT chk_housing_stages CHECK (stages > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---- curvas digitalizadas (puntos discretos) ----
    """
    CREATE TABLE IF NOT EXISTS pump_curves (
        pump_id            VARCHAR(80)  NOT NULL,
        flow_bpd           DECIMAL(10,1) NOT NULL,
        head_ft_per_stage  DECIMAL(10,3) NULL,
        hp_per_stage       DECIMAL(10,4) NULL,
        efficiency         DECIMAL(5,3)  NULL,
        PRIMARY KEY (pump_id, flow_bpd),
        CONSTRAINT fk_curve_pump FOREIGN KEY (pump_id)
            REFERENCES pumps(pump_id) ON DELETE CASCADE,
        CONSTRAINT chk_curve_eff CHECK (efficiency IS NULL
                                        OR (efficiency >= 0 AND efficiency <= 1))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    # ---- log de procesamiento (auditoria por PDF y corrida) ----
    """
    CREATE TABLE IF NOT EXISTS processing_log (
        id               BIGINT AUTO_INCREMENT PRIMARY KEY,
        run_id           VARCHAR(40)  NOT NULL,
        pdf_file         VARCHAR(200) NOT NULL,
        pdf_sha256       CHAR(64)     NULL,
        manufacturer_id  VARCHAR(40)  NULL,
        status           VARCHAR(20)  NOT NULL,
        pumps_found      INT          NOT NULL DEFAULT 0,
        curves_digitized INT          NOT NULL DEFAULT 0,
        message          TEXT         NULL,
        created_at       DATETIME     NOT NULL,
        INDEX idx_log_run (run_id),
        INDEX idx_log_pdf (pdf_file)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def create_schema() -> None:
    conn = connect()
    with conn.cursor() as cur:
        for ddl in _SCHEMA:
            cur.execute(ddl)
    conn.close()


# -------------------------------------------------------------------- upserts
def upsert_manufacturer(conn, mid: str, full_name: str, country: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO manufacturers (manufacturer_id, full_name, country) "
            "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "full_name=VALUES(full_name), country=VALUES(country)",
            (mid, full_name, country))


def upsert_source(conn, source_id: str, pdf_file: str, source_type: str,
                  citation: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO data_sources (source_id, pdf_file, source_type, citation) "
            "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
            "pdf_file=VALUES(pdf_file), source_type=VALUES(source_type), "
            "citation=VALUES(citation)",
            (source_id, pdf_file, source_type, citation))


def upsert_pump(conn, p: dict) -> None:
    cols = ("pump_id", "manufacturer_id", "series", "model", "od_inches",
            "min_flow_bpd", "max_flow_bpd", "bep_flow_bpd", "max_stages",
            "frequency_hz", "source_id", "extraction_method", "review_flag",
            "review_reason")
    vals = [p.get(c) for c in cols]
    updates = ", ".join(f"{c}=VALUES({c})" for c in cols if c != "pump_id")
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO pumps ({', '.join(cols)}, updated_at) "
            f"VALUES ({', '.join(['%s']*len(cols))}, %s) "
            f"ON DUPLICATE KEY UPDATE {updates}, updated_at=VALUES(updated_at)",
            vals + [_dt.datetime.now()])


def replace_housings(conn, pump_id: str, stages: Iterable[int]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pump_housings WHERE pump_id=%s", (pump_id,))
        for s in sorted(set(int(x) for x in stages)):
            cur.execute("INSERT INTO pump_housings (pump_id, stages) VALUES (%s,%s)",
                        (pump_id, s))


def replace_curve_points(conn, pump_id: str, points: list[dict]) -> int:
    """Reemplaza todos los puntos de curva de una bomba (idempotente)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pump_curves WHERE pump_id=%s", (pump_id,))
        n = 0
        for pt in points:
            cur.execute(
                "INSERT INTO pump_curves (pump_id, flow_bpd, head_ft_per_stage, "
                "hp_per_stage, efficiency) VALUES (%s,%s,%s,%s,%s)",
                (pump_id, pt["flow_bpd"], pt.get("head_ft_per_stage"),
                 pt.get("hp_per_stage"), pt.get("efficiency")))
            n += 1
    return n


def log_processing(conn, *, run_id: str, pdf_file: str, pdf_sha256: str | None,
                   manufacturer_id: str | None, status: str, pumps_found: int,
                   curves_digitized: int, message: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO processing_log (run_id, pdf_file, pdf_sha256, "
            "manufacturer_id, status, pumps_found, curves_digitized, message, "
            "created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (run_id, pdf_file, pdf_sha256, manufacturer_id, status, pumps_found,
             curves_digitized, message, _dt.datetime.now()))


def counts() -> dict:
    """Conteos rapidos para verificacion."""
    conn = connect()
    out = {}
    with conn.cursor() as cur:
        for t in ("manufacturers", "pumps", "pump_curves", "pump_housings",
                  "data_sources", "processing_log"):
            cur.execute(f"SELECT COUNT(*) AS n FROM {t}")
            out[t] = cur.fetchone()["n"]
    conn.close()
    return out


if __name__ == "__main__":
    # Uso directo: python db.py  ->  bootstrap + esquema + conteos
    print("Bootstrap (root) ...")
    bootstrap()
    print("Creando esquema (usuario del pipeline) ...")
    create_schema()
    print("Conteos:", counts())
