"""Tests de la couche brute (Jour 1).

Chaque test vérifie une garantie de l'ingestion. Le script retourne un code de sortie 1
dès qu'un test échoue, ce qui permet d'interrompre le chargement dans un enchaînement.

"""
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "sources"
DB = ROOT / "warehouse" / "boreal.duckdb"

sys.path.insert(0, str(ROOT / "pipeline"))
import ingest  # type: ignore  # noqa: E402
from journal_tests import enregistrer  # type: ignore  # noqa: E402

TABLES = ["raw.clients", "raw.contrats", "raw.audits", "raw.sinistres", "raw.reglements"]
FICHIERS_REGLEMENTS = sorted((SRC / "reglements").glob("reglements_*.csv"))


def lignes_fichier(chemin, encodage="utf-8"):
    """Compte les lignes non vides d'un fichier, sans passer par DuckDB (contrôle indépendant)."""
    with open(chemin, encoding=encodage) as f:
        return sum(1 for ligne in f if ligne.strip())


def valeur(requete, parametres=None):
    """Exécute une requête en lecture seule et retourne la première valeur."""
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(requete, parametres or []).fetchone()[0]
    finally:
        con.close()


def test_reconciliation_lignes_brut_vs_sources():
    """Le nombre de lignes de chaque table brute égale le nombre de lignes des fichiers."""
    attendu = {
        "raw.clients": lignes_fichier(SRC / "crm" / "clients.csv", "latin-1") - 1,
        "raw.contrats": lignes_fichier(SRC / "contrats" / "contrats.csv") - 1,
        "raw.audits": lignes_fichier(SRC / "antifraude" / "audits.csv") - 1,
        "raw.sinistres": lignes_fichier(SRC / "sinistres" / "sinistres.jsonl"),
        "raw.reglements": sum(lignes_fichier(f) - 1 for f in FICHIERS_REGLEMENTS),
    }
    for table, nb_source in attendu.items():
        nb_base = valeur(f"select count(*) from {table}")
        assert nb_base == nb_source, f"{table} : {nb_base} lignes en base, {nb_source} dans la source"


def test_tracabilite_sur_chaque_ligne():
    """Chaque ligne brute porte son fichier d'origine et sa date de chargement."""
    for table in TABLES:
        n = valeur(f"select count(*) from {table} where _source_file is null or _loaded_at is null")
        assert n == 0, f"{table} : {n} lignes sans _source_file ou _loaded_at"


def test_tous_les_fichiers_sont_journalises():
    """Chacun des 68 fichiers sources a au moins une entrée au statut OK dans le journal."""
    attendus = {"crm/clients.csv", "contrats/contrats.csv", "antifraude/audits.csv",
                "sinistres/sinistres.jsonl"}
    attendus |= {f"reglements/{f.name}" for f in FICHIERS_REGLEMENTS}
    con = duckdb.connect(str(DB), read_only=True)
    try:
        journalises = {r[0] for r in con.execute(
            "select distinct fichier from meta.ingestion_log where statut = 'OK'").fetchall()}
    finally:
        con.close()
    manquants = sorted(attendus - journalises)
    assert not manquants, f"{len(manquants)} fichier(s) absents du journal : {manquants[:3]}"


def test_un_seul_jeu_de_lignes_par_fichier_de_reglements():
    """Chaque fichier mensuel de règlements apparaît dans le brut avec ses lignes, une seule fois."""
    con = duckdb.connect(str(DB), read_only=True)
    try:
        en_base = dict(con.execute(
            "select _source_file, count(*) from raw.reglements group by 1").fetchall())
    finally:
        con.close()
    for f in FICHIERS_REGLEMENTS:
        cle = f"reglements/{f.name}"
        attendu = lignes_fichier(f) - 1
        assert en_base.get(cle, 0) == attendu, f"{cle} : {en_base.get(cle, 0)} lignes, {attendu} attendues"


def test_structure_des_montants_absorbee():
    """Chaque règlement a exactement un montant, quel que soit le libellé de colonne du fichier."""
    n = valeur("select count(*) from raw.reglements where (montant is null) = (montant_eur is null)")
    assert n == 0, f"{n} règlements avec zéro ou deux montants"
    mars = valeur("select count(montant_eur) from raw.reglements "
                  "where _source_file = 'reglements/reglements_2024_03.csv'")
    assert mars == lignes_fichier(SRC / "reglements" / "reglements_2024_03.csv") - 1, \
        "le fichier de mars 2024 n'est pas lu via la colonne montant_eur"


def test_rejeu_sans_doublon():
    """Recharger deux fois un mois ne modifie ni le total ni le contenu du mois."""
    dossier = Path(tempfile.mkdtemp())
    try:
        copie = dossier / "copie.duckdb"          # copie de travail : l'entrepôt reste intact
        shutil.copy(DB, copie)
        con = duckdb.connect(str(copie))
        total = lambda: con.execute("select count(*) from raw.reglements").fetchone()[0]
        mois = lambda: con.execute(
            "select count(*) from raw.reglements where _source_file = 'reglements/reglements_2024_03.csv'"
        ).fetchone()[0]
        total_avant, mois_avant = total(), mois()
        for _ in range(2):
            ingest.charger_reglement(con, SRC / "reglements" / "reglements_2024_03.csv", forcer=True)
        assert total() == total_avant, f"total : {total_avant} -> {total()} après rejeu"
        assert mois() == mois_avant, f"mars 2024 : {mois_avant} -> {mois()} lignes après rejeu"
        con.close()
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    echecs = 0
    resultats = []
    for nom, fonction in list(globals().items()):
        if nom.startswith("test_") and callable(fonction):
            description = (fonction.__doc__ or nom).strip().split("\n")[0]
            try:
                fonction()
                print(f"PASS  {nom}")
                resultats.append((nom, description, "PASS", ""))
            except AssertionError as e:
                echecs += 1
                print(f"FAIL  {nom} : {e}")
                resultats.append((nom, description, "FAIL", str(e)[:300]))
    enregistrer("brut", resultats)
    print(f"\n{'ECHEC' if echecs else 'OK'} : {echecs} test(s) en échec")
    sys.exit(1 if echecs else 0)