import os
import sys
import logging
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError, OperationalError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================
# CONFIGURAZIONE
# ============================================================

DATA_INIZIO = os.getenv("DATA_INIZIO", "2025-10-01 00:00:00")
DATA_FINE = os.getenv("DATA_FINE", "2026-07-03 00:00:00")

# None = prende tutti gli stati ticket
STATO_TICKET = os.getenv("STATO_TICKET", "").strip()
if STATO_TICKET == "":
    STATO_TICKET = None

# True = prende solo ticket con importo_pagato > 0
SOLO_IMPORTO_PAGATO_POSITIVO = (
    os.getenv("SOLO_IMPORTO_PAGATO_POSITIVO", "true")
    .strip()
    .lower()
    in ["true", "1", "yes", "si", "sì"]
)

CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ";")
CSV_DECIMAL = os.getenv("CSV_DECIMAL", ",")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / os.getenv(
    "OUTPUT_FILE_NAME",
    "report_cf_importi.csv"
)


# ============================================================
# CONFIGURAZIONE DATABASE DA GITHUB SECRETS / .ENV
# ============================================================

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")

if not DB_USER:
    raise ValueError("Variabile DB_USER mancante.")

if not DB_PASSWORD:
    raise ValueError("Variabile DB_PASSWORD mancante.")

if not DB_HOST:
    raise ValueError("Variabile DB_HOST mancante.")

if not DB_PORT:
    raise ValueError("Variabile DB_PORT mancante.")


DB_CONFIGS = {
    "360BET": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_360BET",
    },
    "ADMIRAL": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_ADMIRAL",
    },
    "BBET": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_BBET",
    },
    "DOMUSBET": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_DOMUSBET",
    },
    "MARATHON": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_MARATHON",
    },
    "SKYWIND": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_SKYWIND",
    },
    "SPORTBET": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_SPORTBET",
    },
    "STANLEYBET": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_STANLEYBET",
    },
    "STARCASINO": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_STARCASINO",
    },
    "TOTOSI": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_TOTOSI",
    },
    "VINCITU": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_VINCITU",
    },
    "WILLIAMHILL": {
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "database": "AnalisiTickets_WILLIAMHILL",
    },
}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


# ============================================================
# FUNZIONI BASE
# ============================================================

def crea_engine(cfg: dict):
    user = quote_plus(str(cfg["user"]))
    password = quote_plus(str(cfg["password"]))
    host = cfg["host"]
    port = cfg["port"]
    database = cfg["database"]

    url = (
        f"mysql+mysqlconnector://{user}:{password}"
        f"@{host}:{port}/{database}"
    )

    return create_engine(url)


def salva_csv(df: pd.DataFrame, file_path: Path):
    df.to_csv(
        file_path,
        index=False,
        sep=CSV_SEPARATOR,
        decimal=CSV_DECIMAL,
        encoding="utf-8-sig",
    )


def costruisci_filtro_stato() -> str:
    if STATO_TICKET is None:
        return ""

    if isinstance(STATO_TICKET, (list, tuple, set)):
        stati = [
            "'" + str(stato).replace("'", "''") + "'"
            for stato in STATO_TICKET
        ]

        return f"""
        AND tg.des_stato IN ({",".join(stati)})
        """

    stato = str(STATO_TICKET).replace("'", "''")

    return f"""
    AND tg.des_stato = '{stato}'
    """


def costruisci_filtro_importo() -> str:
    if SOLO_IMPORTO_PAGATO_POSITIVO:
        return """
        AND COALESCE(tg.importo_pagato, 0) > 0
        """

    return ""


# ============================================================
# CARICAMENTO DATI
# ============================================================

def carica_report_concessionario(
    engine,
    concessionario: str,
) -> pd.DataFrame:
    filtro_stato = costruisci_filtro_stato()
    filtro_importo = costruisci_filtro_importo()

    query = f"""
    SELECT
        '{concessionario}' AS concessionario,
        tg.cf AS cf,
        tg.categoria AS categoria,
        COUNT(DISTINCT tg.id_ticket) AS numero_ticket,
        SUM(COALESCE(tg.importo_pagato, 0)) AS importo_giocato_cent,
        SUM(COALESCE(tg.importo_vincita, 0)) AS importo_vincita_cent
    FROM Ticket_General tg
    WHERE STR_TO_DATE(tg.data_ora_vend, '%Y%m%d %H:%i:%s')
        BETWEEN STR_TO_DATE('{DATA_INIZIO}', '%Y-%m-%d %H:%i:%s')
        AND STR_TO_DATE('{DATA_FINE}', '%Y-%m-%d %H:%i:%s')
    {filtro_stato}
    {filtro_importo}
    GROUP BY
        tg.cf,
        tg.categoria
    """

    return pd.read_sql(query, engine)


# ============================================================
# PREPARAZIONE REPORT
# ============================================================

def prepara_report_finale(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["cf"] = (
        df["cf"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["categoria"] = (
        df["categoria"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["numero_ticket"] = pd.to_numeric(
        df["numero_ticket"],
        errors="coerce",
    ).fillna(0).astype(int)

    df["importo_giocato_cent"] = pd.to_numeric(
        df["importo_giocato_cent"],
        errors="coerce",
    ).fillna(0)

    df["importo_vincita_cent"] = pd.to_numeric(
        df["importo_vincita_cent"],
        errors="coerce",
    ).fillna(0)

    # Conversione da centesimi a euro
    df["importo_giocato"] = (
        df["importo_giocato_cent"] / 100
    ).round(2)

    df["importo_vincita"] = (
        df["importo_vincita_cent"] / 100
    ).round(2)

    # Rapporto richiesto:
    # importo_vincita / importo_giocato * 100
    df["rapporto_vincita_giocato_percent"] = df.apply(
        lambda row: round(
            (row["importo_vincita"] / row["importo_giocato"]) * 100,
            2,
        ) if row["importo_giocato"] > 0 else 0,
        axis=1,
    )

    colonne_finali = [
        "concessionario",
        "cf",
        "categoria",
        "numero_ticket",
        "importo_giocato",
        "importo_vincita",
        "rapporto_vincita_giocato_percent",
    ]

    df = df[colonne_finali]

    df = df.sort_values(
        by=[
            "concessionario",
            "rapporto_vincita_giocato_percent",
            "importo_giocato",
        ],
        ascending=[True, False, False],
    )

    return df


# ============================================================
# MAIN
# ============================================================

def main():
    all_frames = []

    for concessionario, cfg in DB_CONFIGS.items():
        try:
            logging.info(f"Caricamento dati per {concessionario}...")

            engine = crea_engine(cfg)

            df = carica_report_concessionario(
                engine=engine,
                concessionario=concessionario,
            )

            if df is not None and not df.empty:
                all_frames.append(df)

            logging.info(
                f"{concessionario}: caricate {len(df)} righe CF/categoria."
            )

        except (ProgrammingError, OperationalError) as e:
            logging.warning(f"Database saltato {concessionario}: {e}")

        except Exception as e:
            logging.error(f"Errore su {concessionario}: {e}")

    if not all_frames:
        logging.info("Nessun dato utile caricato. Termino.")
        return

    report = pd.concat(all_frames, ignore_index=True)

    if report.empty:
        logging.info("Nessun record trovato nel periodo indicato.")
        return

    report_finale = prepara_report_finale(report)

    salva_csv(report_finale, OUTPUT_FILE)

    logging.info(f"File generato correttamente: {OUTPUT_FILE}")
    logging.info(f"Righe generate: {len(report_finale)}")


if __name__ == "__main__":
    try:
        main()
        sys.exit(0)

    except Exception:
        logging.exception("Errore durante l'esecuzione dello script")
        sys.exit(1)