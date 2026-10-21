"""Enregistre les résultats des tests dans meta.resultats_tests (affichés par le dashboard)."""
from datetime import datetime
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parent.parent / "warehouse" / "boreal.duckdb"


def enregistrer(suite, resultats):
    """resultats : liste de (nom, description, statut, detail). Remplace le dernier lancement de la suite."""
    con = duckdb.connect(str(DB))
    try:
        con.execute("create schema if not exists meta")
        con.execute("""create table if not exists meta.resultats_tests (
            suite varchar, test varchar, description varchar, statut varchar,
            detail varchar, execute_le timestamp)""")
        con.execute("delete from meta.resultats_tests where suite = ?", [suite])
        maintenant = datetime.now()
        con.executemany("insert into meta.resultats_tests values (?, ?, ?, ?, ?, ?)",
                        [(suite, nom, description, statut, detail, maintenant)
                         for nom, description, statut, detail in resultats])
    finally:
        con.close()