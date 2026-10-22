"""Déclencheur : lance la chaîne dès qu'un nouveau fichier mensuel de règlements arrive.

Un fichier est « nouveau » s'il est dans data/sources mais pas encore chargé dans raw.reglements.

Utilisation :
  python pipeline/declencheur.py              # surveille en continu (vérifie toutes les 60 secondes)
  python pipeline/declencheur.py --une-fois   # une seule vérification (pour le planificateur Windows)
"""
import argparse
import re
import time
from pathlib import Path

import duckdb

from run_all import ROOT, ecrire, JOURNAL, lancer

DB = ROOT / "warehouse" / "boreal.duckdb"


def fichiers_charges():
    if not DB.exists():
        return set()
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return {Path(str(f)).name for (f,) in con.execute("select distinct _source_file from raw.reglements").fetchall()}
    except duckdb.Error:   # table absente : rien n'est encore chargé
        return set()
    finally:
        con.close()


def nouveaux_mois():
    charges = fichiers_charges()
    trouves = sorted((ROOT / "data" / "sources").rglob("reglements_*.csv"), key=lambda p: p.name)
    return [m.group(1) for p in trouves if p.name not in charges and (m := re.search(r"reglements_(\d{4}_\d{2})\.csv", p.name))]


def verifier(deja_en_echec):
    for mois in nouveaux_mois():
        if mois in deja_en_echec:
            continue
        print(f"Nouveau fichier détecté : reglements_{mois}.csv")
        ecrire(JOURNAL, f"Nouveau fichier détecté : reglements_{mois}.csv")
        if lancer(mois) != 0:
            deja_en_echec.add(mois)   # on n'insiste pas : l'alerte a été envoyée
            return


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--une-fois", action="store_true")
    a = p.parse_args()
    echecs = set()
    while True:
        if not nouveaux_mois():
            print(f"{time.strftime('%H:%M:%S')}  Aucun nouveau fichier.")
        else:
            verifier(echecs)
        if a.une_fois:
            break
        time.sleep(60)