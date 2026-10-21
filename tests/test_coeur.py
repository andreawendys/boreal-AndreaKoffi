"""Tests de la couche cœur : clés, intégrité, réconciliation, exposition.

Chaque test renvoie le nombre d'anomalies ; zéro signifie que le test est réussi.
Un test en échec fait sortir le script avec le code 1, ce qui interrompt le chargement.

Utilisation :  python tests/test_coeur.py
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "warehouse" / "boreal.duckdb"

sys.path.insert(0, str(ROOT / "pipeline"))
from journal_tests import enregistrer  # type: ignore  # noqa: E402

def un(con, requete):
    """Renvoie la première valeur d'une requête."""
    return con.execute(requete).fetchone()[0]

def doublons(con, table, colonnes):
    """Nombre de clés présentes plus d'une fois."""
    return un(con, f"select count(*) from (select 1 from {table} group by {colonnes} having count(*) > 1)")

def orphelins(con, table, colonne, ref, cle):
    """Nombre de lignes dont la clé étrangère n'existe pas dans la table de référence."""
    return un(con, f"select count(*) from {table} where {colonne} not in (select {cle} from {ref})")

def test_cles_dimensions_uniques(con):
    return sum(doublons(con, t, c) for t, c in [
        ("core.dim_client", "client_id"), ("core.dim_contrat", "contrat_id"),
        ("core.dim_garantie", "garantie_id"), ("core.dim_segment_risque", "segment_id"),
        ("core.dim_date", "date_jour")])

def test_cles_faits_uniques(con):
    return sum(doublons(con, t, c) for t, c in [
        ("core.fait_sinistre", "sinistre_id"), ("core.fait_reglement", "paiement_id"),
        ("core.fait_exposition", "contrat_id, annee")])

def test_aucun_client_en_double(con):
    """Après déduplication, deux clients du cœur ne partagent jamais le même email_hash."""
    return un(con, "select count(*) - count(distinct email_hash) "
                   "from core.dim_client join prep.clients using (client_id)")

def test_integrite_contrat_vers_client(con):
    return orphelins(con, "core.dim_contrat", "client_id", "core.dim_client", "client_id")

def test_integrite_sinistre_vers_contrat_et_garantie(con):
    return (orphelins(con, "core.fait_sinistre", "contrat_id", "core.dim_contrat", "contrat_id")
            + orphelins(con, "core.fait_sinistre", "garantie_id", "core.dim_garantie", "garantie_id"))

def test_integrite_reglement_vers_sinistre(con):
    return orphelins(con, "core.fait_reglement", "sinistre_id", "core.fait_sinistre", "sinistre_id")

def test_integrite_exposition_vers_contrat(con):
    return orphelins(con, "core.fait_exposition", "contrat_id", "core.dim_contrat", "contrat_id")

def test_reconciliation_reglements_brut_vers_coeur(con):
    """Lignes et montants : préparation = cœur + quarantaine (règle Q07)."""
    ecart_lignes = un(con, """select (select count(*) from prep.reglements)
        - (select count(*) from core.fait_reglement)
        - (select count(*) from qualite.quarantaine where regle_id = 'Q07')""")
    ecart_montant = un(con, """select round((select sum(montant) from prep.reglements)
        - (select sum(montant) from core.fait_reglement)
        - (select coalesce(sum(r.montant), 0) from prep.reglements r
           join qualite.quarantaine q on q.regle_id = 'Q07'
            and q.cle = r.paiement_id::varchar and q.detail = r._source_file), 2)""")
    return int(ecart_lignes != 0) + int(ecart_montant != 0)

def test_reconciliation_clients_et_contrats(con):
    """Aucune ligne perdue : préparation = cœur + doublons ou contrats en quarantaine."""
    clients = un(con, "select (select count(*) from prep.clients) - (select count(*) from core.dim_client) "
                      "- (select count(*) from qualite.quarantaine where regle_id = 'Q04')")
    contrats = un(con, "select (select count(*) from prep.contrats) - (select count(*) from core.dim_contrat)")
    return int(clients != 0) + int(contrats != 0)

def test_montants_sinistres_egaux_aux_reglements(con):
    return int(un(con, "select round((select sum(montant_regle) from core.fait_sinistre) "
                       "- (select sum(montant) from core.fait_reglement), 2)") != 0)

def test_exposition_toujours_positive(con):
    return un(con, "select count(*) from core.fait_exposition where annees_police <= 0 or jours_couverture <= 0")

def test_exposition_au_plus_une_annee_et_avant_extraction(con):
    return un(con, "select count(*) from core.fait_exposition where annees_police > 1 or date_fin > date '2025-06-30'")

def test_contrats_actifs_tous_exposes(con):
    return un(con, "select count(*) from core.dim_contrat where not en_quarantaine "
                   "and contrat_id not in (select contrat_id from core.fait_exposition)")

TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

def main():
    con = duckdb.connect(str(DB), read_only=True)
    echecs = 0
    resultats = []
    try:
        for test in TESTS:
            anomalies = test(con)
            echecs += anomalies != 0
            print(f"{'PASS' if anomalies == 0 else 'FAIL'}  {test.__name__}" + ("" if anomalies == 0 else f"  ({anomalies})"))
            description = (test.__doc__ or test.__name__.replace("test_", "").replace("_", " ")).strip().split("\n")[0]
            resultats.append((test.__name__, description, "PASS" if anomalies == 0 else "FAIL",
                              "" if anomalies == 0 else f"{anomalies} anomalie(s)"))
    finally:
        con.close()
    enregistrer("coeur", resultats)
    print(f"\n{'OK' if echecs == 0 else 'ECHEC'} : {echecs} test(s) en échec sur {len(TESTS)}")
    sys.exit(1 if echecs else 0)

if __name__ == "__main__":
    main()