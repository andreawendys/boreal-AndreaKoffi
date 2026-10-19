"""Exécute, dans l'ordre alphabétique, les fichiers SQL d'une couche.

Utilisation :  python pipeline/run_sql.py 02_prep
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "warehouse" / "boreal.duckdb"


def executer_couche(con, dossier):
    """Crée le schéma de la couche (02_prep -> prep) puis exécute chaque fichier SQL."""
    schema = dossier.split("_", 1)[1]
    con.execute(f"create schema if not exists {schema}")
    for fichier in sorted((ROOT / "sql" / dossier).glob("*.sql")):
        con.execute(fichier.read_text(encoding="utf-8"))
        print(f"OK  {dossier}/{fichier.name}")


if __name__ == "__main__":
    con = duckdb.connect(str(DB))
    try:
        executer_couche(con, sys.argv[1])
    finally:
        con.close()