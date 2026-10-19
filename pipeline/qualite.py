"""Contrôles de qualité des données (Jour 2).

Chaque règle est une requête SQL qui renvoie les lignes en anomalie (une clé et un détail).
Le script :
  1. exécute les règles sur la couche prep ;
  2. enregistre chaque anomalie dans qualite.anomalies ;
  3. place dans qualite.quarantaine les lignes à écarter (traitement Exclure ou Corriger) ;
  4. enregistre dans qualite.registre la définition et le volume constaté de chaque règle.

Aucune ligne n'est supprimée des tables prep : une ligne écartée reste retrouvable avec son motif.

Utilisation :  python pipeline/qualite.py
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "warehouse" / "boreal.duckdb"

# Date d'extraction des données : aucune date ne doit lui être postérieure.
DATE_EXTRACTION = "2025-06-30"

# Chaque requête renvoie deux colonnes : cle (identifiant de la ligne) et detail (valeur en cause).
REGLES = [
    # ---------------------------------------------------------------- Complétude
    dict(id="Q01", categorie="Complétude", table="prep.clients", gravite="Mineure", traitement="Signaler",
         description="Date de naissance absente",
         sql="""select client_id::varchar as cle, null::varchar as detail
                from prep.clients where date_naissance is null"""),
    dict(id="Q02", categorie="Complétude", table="prep.contrats", gravite="Bloquante", traitement="Exclure",
         description="Date d'effet du contrat absente",
         sql="""select contrat_id::varchar, null::varchar
                from prep.contrats where date_effet is null"""),
    dict(id="Q03", categorie="Complétude", table="prep.reglements", gravite="Bloquante", traitement="Exclure",
         description="Montant du règlement absent",
         sql="""select paiement_id::varchar, _source_file
                from prep.reglements where montant is null"""),
    # ------------------------------------------------------------------ Unicité
    dict(id="Q04", categorie="Unicité", table="prep.clients", gravite="Majeure", traitement="Corriger",
         description="Client en double (même email_hash) : on écarte les non-survivants",
         sql="""with t as (
                    select client_id, email_hash,
                           min(client_id) over (partition by email_hash) as survivant,
                           count(*) over (partition by email_hash) as n
                    from prep.clients)
                select client_id::varchar, 'survivant=' || survivant::varchar
                from t where n > 1 and client_id <> survivant"""),
    dict(id="Q05", categorie="Unicité", table="prep.contrats", gravite="Bloquante", traitement="Exclure",
         description="Identifiant de contrat dupliqué",
         sql="""select contrat_id::varchar, count(*)::varchar
                from prep.contrats group by contrat_id having count(*) > 1"""),
    dict(id="Q06", categorie="Unicité", table="prep.sinistres", gravite="Bloquante", traitement="Exclure",
         description="Identifiant de sinistre dupliqué",
         sql="""select sinistre_id::varchar, count(*)::varchar
                from prep.sinistres group by sinistre_id having count(*) > 1"""),
    dict(id="Q07", categorie="Unicité", table="prep.reglements", gravite="Majeure", traitement="Exclure",
         description="Paiement rejoué dans un fichier d'un autre mois : on écarte la copie hors mois",
         sql=r"""with t as (
                    select paiement_id, _source_file,
                           count(*) over (partition by paiement_id) as n,
                           strftime(date_paiement, '%Y_%m') = regexp_extract(_source_file, '(\d{4}_\d{2})', 1) as bon_mois
                    from prep.reglements)
                select paiement_id::varchar, _source_file from t where n > 1 and not bon_mois"""),
    # ----------------------------------------------------------------- Validité
    dict(id="Q08", categorie="Validité", table="prep.contrats", gravite="Majeure", traitement="Exclure",
         description="Prime annuelle nulle ou négative",
         sql="""select contrat_id::varchar, 'prime=' || prime_annuelle::varchar
                from prep.contrats where prime_annuelle <= 0"""),
    dict(id="Q09", categorie="Validité", table="prep.clients", gravite="Mineure", traitement="Signaler",
         description="Date de naissance antérieure à 1920",
         sql="""select client_id::varchar, date_naissance::varchar
                from prep.clients where date_naissance < date '1920-01-01'"""),
    dict(id="Q10", categorie="Validité", table="prep.clients", gravite="Majeure", traitement="Signaler",
         description="Titulaire mineur à la date d'extraction",
         sql=f"""select client_id::varchar, date_naissance::varchar
                 from prep.clients
                 where date_naissance > date '{DATE_EXTRACTION}' - interval 18 year
                   and client_id in (select client_id from prep.contrats)"""),
    dict(id="Q11", categorie="Validité", table="prep.reglements", gravite="Bloquante", traitement="Exclure",
         description="Montant de règlement nul ou négatif",
         sql="""select paiement_id::varchar, montant::varchar
                from prep.reglements where montant <= 0"""),
    dict(id="Q12", categorie="Validité", table="prep.contrats, prep.sinistres", gravite="Majeure", traitement="Signaler",
         description="Valeur hors domaine (produit, formule, canal, statut, garantie)",
         sql="""select contrat_id::varchar, 'produit=' || produit from prep.contrats where produit not in ('AUTO', 'HABITATION')
                union all select contrat_id::varchar, 'formule=' || formule from prep.contrats where formule not in ('ESSENTIELLE', 'CONFORT', 'PREMIUM')
                union all select contrat_id::varchar, 'canal=' || canal_distribution from prep.contrats where canal_distribution not in ('WEB', 'AGENT', 'COURTIER')
                union all select sinistre_id::varchar, 'statut=' || statut from prep.sinistres where statut not in ('OUVERT', 'CLOTURE', 'REJETE', 'SANS_SUITE')
                union all select sinistre_id::varchar, 'garantie=' || garantie from prep.sinistres
                          where garantie not in ('COLLISION', 'RC', 'BRIS_GLACE', 'VOL', 'DEGAT_EAUX', 'TEMPETE', 'INCENDIE')"""),
    dict(id="Q13", categorie="Validité", table="prep.sinistres", gravite="Majeure", traitement="Signaler",
         description="Réserve initiale extrême (supérieure à 1 000 000 euros)",
         sql="""select sinistre_id::varchar, 'reserve=' || reserve_initiale::varchar
                from prep.sinistres where reserve_initiale > 1000000"""),
    # -------------------------------------------------- Cohérence entre tables
    dict(id="Q14", categorie="Cohérence entre tables", table="prep.contrats", gravite="Bloquante", traitement="Exclure",
         description="Contrat rattaché à un client inexistant",
         sql="""select contrat_id::varchar, 'client_id=' || client_id::varchar
                from prep.contrats where client_id not in (select client_id from prep.clients)"""),
    dict(id="Q15", categorie="Cohérence entre tables", table="prep.sinistres", gravite="Bloquante", traitement="Exclure",
         description="Sinistre rattaché à un contrat inexistant",
         sql="""select sinistre_id::varchar, 'contrat_id=' || contrat_id::varchar
                from prep.sinistres where contrat_id not in (select contrat_id from prep.contrats)"""),
    dict(id="Q16", categorie="Cohérence entre tables", table="prep.reglements", gravite="Bloquante", traitement="Exclure",
         description="Règlement rattaché à un sinistre inexistant",
         sql="""select paiement_id::varchar, 'sinistre_id=' || sinistre_id::varchar
                from prep.reglements where sinistre_id not in (select sinistre_id from prep.sinistres)"""),
    dict(id="Q17", categorie="Cohérence entre tables", table="prep.sinistres", gravite="Majeure", traitement="Signaler",
         description="Garantie incompatible avec le produit du contrat",
         sql="""select s.sinistre_id::varchar, c.produit || '/' || s.garantie
                from prep.sinistres s join prep.contrats c using (contrat_id)
                where (c.produit = 'AUTO' and s.garantie not in ('COLLISION', 'RC', 'BRIS_GLACE', 'VOL'))
                   or (c.produit = 'HABITATION' and s.garantie not in ('DEGAT_EAUX', 'TEMPETE', 'VOL', 'INCENDIE'))"""),
    dict(id="Q18", categorie="Cohérence entre tables", table="prep.reglements", gravite="Majeure", traitement="Signaler",
         description="Règlement versé sur un sinistre rejeté ou sans suite",
         sql="""select r.paiement_id::varchar, s.statut
                from prep.reglements r join prep.sinistres s using (sinistre_id)
                where s.statut in ('REJETE', 'SANS_SUITE')"""),
    # -------------------------------------------------- Cohérence temporelle
    dict(id="Q19", categorie="Cohérence temporelle", table="prep.contrats", gravite="Bloquante", traitement="Exclure",
         description="Résiliation antérieure ou égale à la date d'effet (exposition nulle ou négative)",
         sql="""select contrat_id::varchar, 'effet=' || date_effet::varchar || ' resiliation=' || date_resiliation::varchar
                from prep.contrats where date_resiliation <= date_effet"""),
    dict(id="Q20", categorie="Cohérence temporelle", table="prep.sinistres", gravite="Majeure", traitement="Signaler",
         description="Déclaration antérieure à la survenance du sinistre",
         sql="""select sinistre_id::varchar, 'survenance=' || date_survenance::varchar || ' declaration=' || date_declaration::varchar
                from prep.sinistres where date_declaration < date_survenance"""),
    dict(id="Q21", categorie="Cohérence temporelle", table="prep.sinistres", gravite="Majeure", traitement="Signaler",
         description="Sinistre survenu hors période de couverture du contrat",
         sql="""select s.sinistre_id::varchar, 'survenance=' || s.date_survenance::varchar
                from prep.sinistres s join prep.contrats c using (contrat_id)
                where s.date_survenance < c.date_effet
                   or (c.date_resiliation is not null and s.date_survenance > c.date_resiliation)"""),
    dict(id="Q22", categorie="Cohérence temporelle", table="prep.reglements", gravite="Majeure", traitement="Signaler",
         description="Règlement antérieur à la survenance du sinistre",
         sql="""select r.paiement_id::varchar, 'paiement=' || r.date_paiement::varchar
                from prep.reglements r join prep.sinistres s using (sinistre_id)
                where r.date_paiement < s.date_survenance"""),
    dict(id="Q23", categorie="Cohérence temporelle", table="toutes les tables prep", gravite="Majeure", traitement="Signaler",
         description="Date postérieure à la date d'extraction (30/06/2025)",
         sql=f"""select contrat_id::varchar, 'contrat' from prep.contrats
                   where date_effet > date '{DATE_EXTRACTION}' or date_resiliation > date '{DATE_EXTRACTION}'
                 union all select sinistre_id::varchar, 'sinistre' from prep.sinistres
                   where date_survenance > date '{DATE_EXTRACTION}' or date_declaration > date '{DATE_EXTRACTION}'
                 union all select paiement_id::varchar, 'reglement' from prep.reglements
                   where date_paiement > date '{DATE_EXTRACTION}'
                 union all select sinistre_id::varchar, 'audit' from prep.audits
                   where date_audit > date '{DATE_EXTRACTION}'"""),
]


def executer(con):
    """Exécute toutes les règles et reconstruit les tables du schéma qualite."""
    con.execute("create schema if not exists qualite")
    con.execute("""
        create or replace table qualite.anomalies (
            regle_id varchar, table_source varchar, cle varchar, detail varchar,
            motif varchar, traitement varchar, detecte_le timestamp default current_timestamp)
    """)
    for r in REGLES:
        con.execute(
            f"""insert into qualite.anomalies (regle_id, table_source, cle, detail, motif, traitement)
                select ?, ?, cle, detail, ?, ? from ({r['sql']}) as t(cle, detail)""",
            [r["id"], r["table"], r["description"], r["traitement"]])

    # Quarantaine : toutes les lignes à écarter du cœur, avec leur règle et leur motif.
    con.execute("""
        create or replace table qualite.quarantaine as
        select regle_id, table_source, cle, detail, motif, traitement, detecte_le
        from qualite.anomalies where traitement in ('Exclure', 'Corriger')
    """)

    # Registre : définition de chaque règle et volume constaté.
    con.execute("""
        create or replace table qualite.registre (
            regle_id varchar, categorie varchar, description varchar, table_source varchar,
            gravite varchar, traitement varchar, requete varchar, volume bigint)
    """)
    for r in REGLES:
        con.execute(
            "insert into qualite.registre select ?, ?, ?, ?, ?, ?, ?, "
            "(select count(*) from qualite.anomalies where regle_id = ?)",
            [r["id"], r["categorie"], r["description"], r["table"], r["gravite"],
             r["traitement"], " ".join(r["sql"].split()), r["id"]])


if __name__ == "__main__":
    con = duckdb.connect(str(DB))
    try:
        executer(con)
        con.sql("""select regle_id, categorie, description, gravite, traitement, volume
                   from qualite.registre order by regle_id""").show(max_width=250, max_rows=40)
        print(con.sql("""select traitement, count(*) as regles, sum(volume) as lignes_concernees
                         from qualite.registre group by 1 order by 1"""))
        print(con.sql("select count(*) as lignes_en_quarantaine from qualite.quarantaine"))
    finally:
        con.close()