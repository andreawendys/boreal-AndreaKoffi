"""Génère le catalogue des données (catalogue.md) et le schéma de lignage du ratio (images/lignage_ratio.png).

Le catalogue liste, depuis l'entrepôt, chaque table et chaque colonne avec son type et sa définition.

Utilisation :  python pipeline/catalogue.py
"""
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "warehouse" / "boreal.duckdb"

SCHEMAS = {
    "meta": "Méta : journal des chargements et résultats des tests.",
    "raw": "Brut (raw) : copie fidèle des sources, tout en texte, sans aucune transformation.",
    "prep": "Préparation (prep) : types corrigés et valeurs nettoyées ; aucune ligne supprimée.",
    "qualite": "Qualité : anomalies détectées, lignes mises en quarantaine et registre des règles.",
    "core": "Cœur (core) : modèle en étoile, dédoublonné, prêt pour le calcul des indicateurs.",
    "marts": "Marts : tables d'analyse alimentant le dashboard (une table par besoin de lecture).",
}

TABLES = {
    "meta.ingestion_log": "Journal d'ingestion : fichier, empreinte, lignes lues, durée, statut de chaque chargement.",
    "meta.resultats_tests": "Résultats des tests de qualité à chaque exécution (couches brute et cœur).",
    "raw.clients": "Clients, tels que livrés par le CRM.",
    "raw.contrats": "Contrats auto et habitation, tels que livrés.",
    "raw.sinistres": "Sinistres déclarés, tels que livrés.",
    "raw.reglements": "Paiements de sinistres, un fichier mensuel par livraison.",
    "raw.audits": "Audits antifraude (dossiers contrôlés uniquement).",
    "prep.clients": "Clients typés et nettoyés.",
    "prep.contrats": "Contrats typés et nettoyés.",
    "prep.sinistres": "Sinistres typés et nettoyés.",
    "prep.reglements": "Règlements typés ; les deux intitulés de montant sont unifiés.",
    "prep.audits": "Audits antifraude typés.",
    "qualite.anomalies": "Une ligne par anomalie détectée par une règle de qualité.",
    "qualite.quarantaine": "Lignes écartées des calculs, avec leur motif.",
    "qualite.registre": "Définition et volume constaté de chaque règle de qualité.",
    "core.dim_client": "Dimension client (clients survivants après déduplication).",
    "core.dim_contrat": "Dimension contrat, avec marquage des contrats en quarantaine.",
    "core.dim_date": "Dimension calendrier, un jour par ligne.",
    "core.dim_garantie": "Dimension garantie (par produit).",
    "core.dim_segment_risque": "Dimension segment de risque (produit, classe de risque, zone).",
    "core.fait_exposition": "Fait : couverture de chaque contrat, année par année (années-police et prime acquise).",
    "core.fait_sinistre": "Fait : un sinistre par ligne, avec règlements cumulés et fraude confirmée.",
    "core.fait_reglement": "Fait : un paiement par ligne.",
    "core.pont_client_survivant": "Pont entre chaque client et le client survivant de son groupe de doublons.",
    "marts.base_technique": "Base technique annuelle par produit, zone, formule, canal et tranche d'âge.",
    "marts.indicateurs": "Indicateurs (fréquence, coût moyen, ratio...) par axe d'analyse.",
    "marts.contributions_segments": "Contribution de chaque segment au ratio, par année.",
    "marts.evolution_annuelle": "Évolution annuelle du ratio et décomposition de sa variation.",
    "marts.evolution_mensuelle": "Série mensuelle par produit, zone et canal : source des graphiques de la page Portefeuille.",
    "marts.retention_cohortes": "Rétention des contrats par cohorte de souscription.",
    "marts.retention_multidetention": "Rétention selon le niveau de détention (mono ou multi-produits).",
    "marts.valeur_client": "Valeur de chaque client : primes acquises moins sinistres payés.",
    "marts.delais_sinistres": "Délais de gestion de chaque sinistre.",
    "marts.exploitation": "État de la chaîne : chargements, règles de qualité et tests.",
}

COLONNES = {
    # identifiants et sources
    "client_id": "Identifiant du client.", "contrat_id": "Identifiant du contrat.",
    "sinistre_id": "Identifiant du sinistre.", "paiement_id": "Identifiant du paiement.",
    "_source_file": "Fichier d'origine de la ligne (traçabilité).",
    "_loaded_at": "Horodatage du chargement de la ligne.",
    # journal d'ingestion et résultats de tests
    "fichier": "Fichier chargé.", "source": "Table brute alimentée par le fichier.",
    "empreinte": "Empreinte SHA-256 du contenu du fichier (détecte un fichier déjà chargé).",
    "lignes_lues": "Nombre de lignes lues dans le fichier.", "lignes_rejetees": "Nombre de lignes rejetées à la lecture.",
    "duree_s": "Durée du chargement, en secondes.", "message": "Message d'erreur éventuel.",
    "charge_le": "Date et heure du chargement.",
    "suite": "Groupe de tests : couche brute ou couche cœur.", "test": "Nom du test exécuté.",
    "execute_le": "Date et heure d'exécution du test.",
    # clients
    "date_naissance": "Date de naissance du client.", "region": "Région du client.",
    "csp": "Catégorie socioprofessionnelle du client.",
    "consent_marketing": "Consentement du client à la prospection commerciale.",
    "email_hash": "Empreinte (hash) de l'e-mail : pseudonyme servant à repérer les doublons.",
    "age": "Âge du client à la date d'arrêté.", "tranche_age": "Tranche d'âge du client.",
    # contrats
    "produit": "Produit : AUTO ou HABITATION.", "date_effet": "Date de début de couverture du contrat.",
    "date_resiliation": "Date de résiliation du contrat (vide si en vigueur).",
    "formule": "Formule du contrat (ESSENTIELLE, CONFORT, PREMIUM).",
    "canal_distribution": "Canal de vente (AGENT, COURTIER, WEB).", "canal": "Canal de vente (AGENT, COURTIER, WEB).",
    "zone_risque": "Zone de risque, de 1 à 5.", "franchise": "Franchise du contrat, en euros.",
    "bonus_malus": "Coefficient de bonus-malus (auto).", "puissance_cv": "Puissance fiscale du véhicule, en chevaux (auto).",
    "surface_m2": "Surface du logement, en m² (habitation).", "prime_annuelle": "Prime annuelle du contrat, en euros.",
    "segment_id": "Identifiant du segment de risque.", "classe_risque": "Classe de risque du segment.",
    "en_quarantaine": "Vrai si le contrat est écarté des calculs.", "motif_quarantaine": "Motif de la mise en quarantaine.",
    # sinistres, règlements, audits
    "date_survenance": "Date à laquelle le sinistre est survenu.", "date_declaration": "Date de déclaration du sinistre.",
    "garantie": "Garantie mobilisée par le sinistre.", "garantie_id": "Identifiant de la garantie.",
    "statut": "Statut du sinistre (OUVERT, CLOTURE, REJETE, SANS_SUITE) ; pour les tables de suivi, statut du chargement ou du test.",
    "reserve_initiale": "Provision constituée à l'ouverture du dossier, en euros.",
    "date_paiement": "Date du paiement.", "montant": "Montant du paiement, en euros.",
    "montant_eur": "Montant du paiement dans les fichiers qui utilisent cet autre intitulé de colonne.",
    "date_audit": "Date de l'audit antifraude.", "fraude_confirmee": "Vrai si l'audit a confirmé une fraude.",
    "montant_regle": "Total réglé sur le sinistre, en euros.", "nb_reglements": "Nombre de paiements du sinistre.",
    "contrat_en_quarantaine": "Vrai si le contrat du sinistre est en quarantaine.",
    "client_id_survivant": "Client conservé pour le groupe de doublons.", "est_doublon": "Vrai si le client est un doublon écarté.",
    # calendrier
    "date_jour": "Jour du calendrier.", "annee": "Année.", "trimestre": "Trimestre (1 à 4).",
    "annee_mois": "Année et mois (AAAA-MM).", "jour_semaine": "Jour de la semaine (1 = lundi).",
    # exposition et indicateurs
    "date_debut": "Début de la période de couverture dans l'année.", "date_fin": "Fin de la période de couverture dans l'année.",
    "jours_couverture": "Nombre de jours couverts dans l'année.",
    "annees_police": "Années-police : jours couverts ÷ jours de l'année (mesure d'exposition).",
    "prime_acquise": "Prime acquise : prime annuelle × années-police, en euros.",
    "nb_contrats": "Nombre de contrats.", "contrats_actifs": "Contrats en vigueur le mois considéré.",
    "nb_resiliations": "Nombre de résiliations.", "nb_sinistres": "Nombre de sinistres retenus (OUVERT ou CLOTURE).",
    "nb_sans_suite": "Nombre de sinistres sans suite (exclus).", "nb_rejetes": "Nombre de sinistres rejetés (exclus).",
    "paye": "Montant payé, en euros.", "reserve_restante": "Provision restante sur les dossiers, en euros.",
    "frequence": "Fréquence : sinistres ÷ années-police.", "cout_moyen": "Coût moyen : montant payé ÷ sinistres.",
    "prime_moyenne": "Prime moyenne : primes acquises ÷ années-police, en euros.",
    "ratio": "Ratio sinistres/primes : montant payé ÷ primes acquises.",
    "ratio_paye": "Ratio sinistres/primes : montant payé ÷ primes acquises.",
    "ratio_avec_reserve": "Ratio incluant la provision restante.",
    "ratio_hors_exceptionnel": "Ratio sans le sinistre exceptionnel (> 1 M€).",
    "taux_resiliation": "Taux de résiliation : résiliations ÷ années-police.",
    "part_dossiers_ouverts": "Part des dossiers encore ouverts.",
    "annee_incomplete": "Vrai si l'année n'est pas complète (données arrêtées en cours d'année).",
    "variation_ratio": "Variation du ratio par rapport à l'année précédente (en points).",
    "effet_frequence": "Part de la variation du ratio due à la fréquence.",
    "effet_cout": "Part de la variation du ratio due au coût moyen.",
    "effet_prime": "Part de la variation du ratio due à la prime moyenne.",
    "variation_sinistres": "Variation du montant des sinistres sur un an.",
    "sinistres_effet_volume": "Part due au volume d'exposition.", "sinistres_effet_frequence": "Part due à la fréquence.",
    "sinistres_effet_cout": "Part due au coût moyen.", "variation_primes": "Variation du montant des primes sur un an.",
    "primes_effet_volume": "Part due au volume d'exposition.", "primes_effet_prime": "Part due à la prime moyenne.",
    "axe": "Axe d'analyse (zone, formule, canal, tranche d'âge, produit).", "modalite": "Valeur de l'axe d'analyse.",
    "part_ratio": "Part du segment dans l'exposition ou les primes.", "contribution": "Contribution du segment au ratio.",
    "nb_exceptionnels": "Nombre de sinistres exceptionnels (> 1 M€).", "paye_exceptionnel": "Montant payé sur les sinistres exceptionnels.",
    "mois": "Mois.", "mois_num": "Numéro du mois (1 à 12).",
    # rétention, clients, délais
    "cohorte": "Année de souscription de la cohorte.", "k": "Nombre d'années écoulées depuis la souscription.",
    "contrats": "Contrats de la cohorte.", "retenus": "Contrats encore en vigueur au 31/12.",
    "retention_pct": "Part des contrats conservés.", "niveau": "Niveau de détention (mono ou multi-produits).",
    "effectif": "Nombre de contrats ou clients observés.", "nb_produits": "Nombre de produits détenus par le client.",
    "primes_acquises": "Primes acquises du client, en euros.", "valeur": "Valeur : primes acquises − sinistres payés, en euros.",
    "delai_declaration": "Jours entre la survenance et la déclaration.",
    "delai_premier_reglement": "Jours entre la déclaration et le premier règlement.",
    "delai_cloture": "Jours entre la déclaration et le dernier règlement (dossiers clôturés).",
    # qualité et exploitation
    "regle_id": "Identifiant de la règle de qualité (Q01...).", "table_source": "Table contrôlée.",
    "cle": "Identifiant de la ligne concernée.", "detail": "Détail de l'anomalie ou de la ligne.",
    "motif": "Motif du rejet ou de l'anomalie.", "traitement": "Traitement appliqué (Signaler, Corriger, Exclure).",
    "detecte_le": "Horodatage de la détection.", "categorie": "Catégorie de la règle (complétude, unicité...).",
    "description": "Description de la règle.", "gravite": "Gravité (Mineure, Majeure, Bloquante).",
    "requete": "Requête SQL de la règle.", "volume": "Nombre de lignes concernées.",
    "rubrique": "Rubrique : CHARGEMENT, REGLE ou TEST.", "element": "Source, règle ou test concerné.",
    "valeur2": "Valeur complémentaire de la ligne (selon la rubrique).",
    "horodatage": "Date et heure de l'exécution.", "derniere_date_donnee": "Date la plus récente présente dans les données.",
}
# définitions propres à une table (écrasent la définition générale)
SPECIFIQUES = {
    ("core.dim_date", "mois"): "Numéro du mois (1 à 12).",
    ("marts.evolution_mensuelle", "mois"): "Premier jour du mois.",
    ("marts.exploitation", "valeur"): "Lignes chargées, lignes signalées ou rejetées, ou nombre de tests selon la rubrique.",
    ("marts.retention_cohortes", "contrats"): "Contrats de la cohorte.",
    ("marts.exploitation", "statut"): "Statut du chargement, gravité ou traitement de la règle, résultat du test.",
}


def lignage():
    """Dessine le parcours du ratio sinistres/primes, des fichiers sources au graphique."""
    fig, ax = plt.subplots(figsize=(16, 6.5))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 6.5)
    ax.axis("off")
    couleurs = {"src": "#e8eef7", "raw": "#dbe4f0", "prep": "#c7d6ea", "core": "#a9c1e0", "mart": "#6f97c9", "app": "#14213d"}

    def boite(x, y, texte, genre, w=2.1, h=0.9):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1", fc=couleurs[genre],
                                    ec="#14213d", lw=1))
        ax.text(x + w / 2, y + h / 2, texte, ha="center", va="center", fontsize=8.5,
                color="white" if genre in ("mart", "app") else "#14213d")

    def fleche(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#14213d", lw=1.2))

    lignes = [
        (4.7, "contrats.csv", "raw.contrats", "prep.contrats", "core.dim_contrat\ncore.fait_exposition\n(prime_acquise)"),
        (2.9, "sinistres.jsonl", "raw.sinistres", "prep.sinistres", "core.fait_sinistre\n(garantie, statut)"),
        (1.1, "reglements_AAAA_MM.csv\n(64 fichiers)", "raw.reglements", "prep.reglements", "core.fait_reglement\n(montant payé)"),
    ]
    xs = [0.2, 2.9, 5.6, 8.3]
    genres = ["src", "raw", "prep", "core"]
    for y, *textes in lignes:
        for i, (x, t, g) in enumerate(zip(xs, textes, genres)):
            boite(x, y, t, g, h=1.0 if i == 3 else 0.9)
            if i:
                fleche(xs[i - 1] + 2.1, y + 0.45, x, y + 0.45)
        fleche(xs[3] + 2.1, y + 0.45, 11.0, 3.1)
    boite(11.0, 2.65, "marts.evolution_mensuelle\n(prime_acquise, paye)", "mart", w=2.4, h=0.9)
    boite(14.0, 2.65, "app.py\nCarte « Ratio »\nGraphique mensuel", "app", w=1.9, h=0.9)
    fleche(13.4, 3.1, 14.0, 3.1)
    ax.text(0.2, 0.35, "Ratio sinistres/primes = montant payé (règlements des sinistres retenus, au mois de survenance) "
                       "÷ primes acquises (prime annuelle × années-police)", fontsize=9, color="#14213d")
    for x, t in zip(xs + [11.0, 14.0], ["Sources", "Brut (raw)", "Préparation (prep)", "Cœur (core)", "Marts", "Dashboard"]):
        ax.text(x + 1.05, 6.05, t, ha="center", fontsize=10, fontweight="bold", color="#14213d")
    ax.text(5.6, 0.75, "Entre prep et core : contrôles de qualité (23 règles) ; les lignes écartées vont en quarantaine avec leur motif.",
            fontsize=8.5, color="#555")
    (ROOT / "images").mkdir(exist_ok=True)
    fig.savefig(ROOT / "images" / "lignage_ratio.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    con = duckdb.connect(str(DB), read_only=True)
    cols = con.execute("""select table_schema, table_name, column_name, data_type from information_schema.columns
                          where table_schema in ('raw','meta','prep','qualite','core','marts')
                          order by table_schema, table_name, ordinal_position""").fetchall()
    manques = []
    out = ["# Catalogue des données", "",
           "Chaque table et chaque colonne de l'entrepôt `warehouse/boreal.duckdb`. Généré par `python pipeline/catalogue.py`.", ""]
    for schema, intitule in SCHEMAS.items():
        tables = sorted({t for s, t, *_ in cols if s == schema})
        if not tables:
            continue
        out += [f"## Schéma `{schema}`", "", intitule, ""]
        for t in tables:
            if f"{schema}.{t}" not in TABLES:
                manques.append(f"{schema}.{t} (table)")
            n = con.execute(f"select count(*) from {schema}.{t}").fetchone()[0]
            out += [f"### `{schema}.{t}`", "", f"{TABLES.get(f'{schema}.{t}', 'À compléter')} ({format(n, ',').replace(',', ' ')} lignes)", "",
                    "| Colonne | Type | Définition |", "|---|---|---|"]
            for s, tt, c, ty in cols:
                if (s, tt) == (schema, t):
                    d = SPECIFIQUES.get((f"{schema}.{t}", c)) or COLONNES.get(c)
                    if not d:
                        manques.append(f"{schema}.{t}.{c}")
                    out.append(f"| `{c}` | {ty} | {d or 'À compléter'} |")
            out.append("")
    out += ["## Lignage du ratio sinistres/primes", "", "![Lignage](images/lignage_ratio.png)", "",
            "```mermaid", "flowchart LR",
            "  A[contrats.csv] --> B[raw.contrats] --> C[prep.contrats] --> D[core.dim_contrat + fait_exposition]",
            "  E[sinistres.jsonl] --> F[raw.sinistres] --> G[prep.sinistres] --> H[core.fait_sinistre]",
            "  I[reglements_AAAA_MM.csv] --> J[raw.reglements] --> K[prep.reglements] --> L[core.fait_reglement]",
            "  D --> M[marts.evolution_mensuelle]", "  H --> M", "  L --> M", "  M --> N[app.py : carte Ratio et graphique mensuel]",
            "```", ""]
    (ROOT / "catalogue.md").write_text("\n".join(out), encoding="utf-8")
    lignage()
    print(f"catalogue.md : {len(cols)} colonnes décrites ; images/lignage_ratio.png créé.")
    if manques:
        print("À compléter :", ", ".join(manques))


if __name__ == "__main__":
    main()