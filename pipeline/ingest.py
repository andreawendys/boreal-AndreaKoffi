"""Ingestion des sources Boréal Assurances dans la couche brute (schéma raw).

La couche brute est une copie fidèle des sources : toutes les valeurs sont lues en texte
et aucune correction n'est appliquée. Chaque ligne conserve son fichier d'origine et sa
date de chargement. Chaque chargement est tracé dans le journal meta.ingestion_log.
Le chargement est idempotent : rejouer un fichier ne crée aucun doublon.

Utilisation :
    python pipeline/ingest.py                  # chargement complet
    python pipeline/ingest.py --mois 2024_03   # rechargement d'un mois de règlements
"""
import argparse
import hashlib
import time
from pathlib import Path

import duckdb

# Chemins du projet, calculés depuis l'emplacement du script.
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources"
DB = ROOT / "warehouse" / "boreal.duckdb"

# Sources livrées en un seul fichier : table brute, fichier, instruction de lecture.
SOURCES_UNIQUES = [
    ("raw.clients", "crm/clients.csv",
     "read_csv(?, delim=';', encoding='latin-1', header=true, all_varchar=true)"),
    ("raw.contrats", "contrats/contrats.csv",
     "read_csv(?, header=true, all_varchar=true)"),
    ("raw.audits", "antifraude/audits.csv",
     "read_csv(?, header=true, all_varchar=true)"),
    ("raw.sinistres", "sinistres/sinistres.jsonl",
     "read_json(?, format='newline_delimited', columns={sinistre_id:'VARCHAR', "
     "contrat_id:'VARCHAR', date_survenance:'VARCHAR', date_declaration:'VARCHAR', "
     "garantie:'VARCHAR', statut:'VARCHAR', reserve_initiale:'VARCHAR'})"),
]


def empreinte(chemin):
    """Calcule l'empreinte SHA-256 du contenu d'un fichier."""
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()[:16]


def preparer(con):
    """Crée les schémas, le journal d'ingestion et la table brute des règlements."""
    con.execute("create schema if not exists raw")
    con.execute("create schema if not exists meta")
    con.execute("""
        create table if not exists meta.ingestion_log (
            fichier varchar, source varchar, empreinte varchar,
            lignes_lues bigint, lignes_rejetees bigint,
            duree_s double, statut varchar, message varchar,
            charge_le timestamp default current_timestamp)
    """)
    # Les deux libellés de la colonne montant sont conservés tels que livrés.
    con.execute("""
        create table if not exists raw.reglements (
            paiement_id varchar, sinistre_id varchar, date_paiement varchar,
            montant varchar, montant_eur varchar,
            _source_file varchar, _loaded_at timestamp)
    """)


def journaliser(con, rel, source, sha, lues, duree, statut, message=""):
    """Enregistre une ligne dans le journal d'ingestion."""
    con.execute(
        "insert into meta.ingestion_log (fichier, source, empreinte, lignes_lues,"
        " lignes_rejetees, duree_s, statut, message) values (?,?,?,?,?,?,?,?)",
        [rel, source, sha, lues, 0, round(duree, 3), statut, message])


def charger_source_unique(con, table, rel, lecture):
    """Charge une source livrée en un seul fichier par reconstruction complète de la table."""
    chemin = SRC / rel
    t0 = time.time()
    sha = empreinte(chemin)
    try:
        con.execute(f"""
            create or replace table {table} as
            select *, ? as _source_file, current_timestamp as _loaded_at
            from {lecture}""", [rel, chemin.as_posix()])
        n = con.execute(f"select count(*) from {table}").fetchone()[0]
        journaliser(con, rel, table, sha, n, time.time() - t0, "OK")
        return n
    except Exception as e:
        journaliser(con, rel, table, sha, 0, time.time() - t0, "ECHEC", str(e)[:300])
        raise


def charger_reglement(con, chemin, forcer=False):
    """Charge un fichier mensuel de règlements de façon idempotente.

    Un fichier déjà chargé avec la même empreinte est ignoré. Sinon, les lignes issues de
    ce fichier sont remplacées au sein d'une transaction, annulée en cas d'erreur.
    """
    chemin = Path(chemin)
    rel = f"reglements/{chemin.name}"
    sha = empreinte(chemin)

    # Contrôle du journal : fichier déjà chargé avec la même empreinte.
    deja = con.execute(
        "select count(*) from meta.ingestion_log where fichier=? and empreinte=? and statut='OK'",
        [rel, sha]).fetchone()[0]
    if deja and not forcer:
        return "ignoré"

    t0 = time.time()
    try:
        con.execute("begin")
        # Suppression des lignes de ce fichier uniquement, puis réinsertion par nom de colonne.
        con.execute("delete from raw.reglements where _source_file = ?", [rel])
        con.execute("""
            insert into raw.reglements by name
            select *, ? as _source_file, current_timestamp as _loaded_at
            from read_csv(?, header=true, all_varchar=true)""",
            [rel, chemin.as_posix()])
        n = con.execute(
            "select count(*) from raw.reglements where _source_file = ?", [rel]).fetchone()[0]
        con.execute("commit")
        statut, message = "OK", ""
    except Exception as e:
        con.execute("rollback")
        n, statut, message = 0, "ECHEC", str(e)[:300]
    journaliser(con, rel, "raw.reglements", sha, n, time.time() - t0, statut, message)
    return statut


def total(con):
    """Retourne le nombre de lignes de la table brute des règlements."""
    return con.execute("select count(*) from raw.reglements").fetchone()[0]


def recharger_mois(con, mois):
    """Recharge un mois de règlements (format AAAA_MM) et compare le total avant et après."""
    chemin = SRC / "reglements" / f"reglements_{mois}.csv"
    if not chemin.exists():
        raise SystemExit(f"Fichier introuvable : {chemin.name} (format attendu : AAAA_MM)")
    avant = total(con)
    statut = charger_reglement(con, chemin, forcer=True)
    apres = total(con)
    print(f"{chemin.name} rechargé ({statut}) : {avant} -> {apres} lignes au total")
    return avant, apres


def verifier_rejeu(con):
    """Vérifie l'idempotence : le rechargement d'un mois ne modifie pas le total."""
    avant, apres = recharger_mois(con, "2024_03")
    assert avant == apres, "Doublon détecté : le rechargement n'est pas idempotent"


def main():
    parser = argparse.ArgumentParser(description="Ingestion des sources Boréal (couche brute)")
    parser.add_argument("--mois", help="recharge uniquement ce mois de règlements, ex. 2024_03")
    args = parser.parse_args()

    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    try:
        preparer(con)

        # Mode rechargement d'un mois.
        if args.mois:
            recharger_mois(con, args.mois)
            return

        # Chargement des sources livrées en un seul fichier.
        for table, rel, lecture in SOURCES_UNIQUES:
            print(f"{rel} -> {table} : {charger_source_unique(con, table, rel, lecture)} lignes")

        # Chargement incrémental des règlements, un fichier par mois.
        for chemin in sorted((SRC / "reglements").glob("reglements_*.csv")):
            print(chemin.name, charger_reglement(con, chemin))

        # Contrôle d'idempotence puis synthèse du journal.
        verifier_rejeu(con)
        print(con.sql("select source, count(*) as fichiers, sum(lignes_lues) as lignes, "
                      "max(statut) as statut from meta.ingestion_log group by 1 order by 1"))
    finally:
        con.close()


if __name__ == "__main__":
    main()