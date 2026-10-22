"""Rigueur statistique : intervalles de confiance, tests de comparaison, queue des coûts."""

import duckdb
import numpy as np
from scipy.stats import chi2, binomtest, mannwhitneyu

con = duckdb.connect("warehouse/boreal.duckdb", read_only=True)
rng = np.random.default_rng(42)

AXES = {"Produit": "produit", "Zone de risque": "zone_risque", "Formule": "formule",
        "Canal": "canal", "Tranche d'âge": "tranche_age"}
FILTRE_SINISTRES = "s.statut in ('OUVERT', 'CLOTURE') and not s.contrat_en_quarantaine"


def ic_poisson(k, expo, niveau=0.95):
    """Intervalle exact de Poisson pour un nombre d'événements k sur une exposition."""
    a = 1 - niveau
    bas = chi2.ppf(a / 2, 2 * k) / 2 / expo if k > 0 else 0.0
    haut = chi2.ppf(1 - a / 2, 2 * k + 2) / 2 / expo
    return bas, haut


def ic_bootstrap(x, n=5000):
    """Intervalle de la moyenne par rééchantillonnage."""
    moyennes = rng.choice(x, (n, len(x))).mean(axis=1)
    return np.percentile(moyennes, [2.5, 97.5])


def donnees(col):
    return con.execute(f"""
        select {col}::varchar, sum(annees_police), sum(nb_sinistres), sum(nb_resiliations)
        from marts.base_technique group by 1 order by 1""").fetchall()


def intervalles(indice, titre):
    print(f"\n{titre}")
    print(f"{'':20}{indice:>15}{'IC 95 % (bas - haut)':>26}")
    pos = 2 if indice.startswith("Fréquence") else 3
    total = con.execute("select sum(annees_police), sum(nb_sinistres), sum(nb_resiliations) "
                        "from marts.base_technique").fetchone()
    expo, k = total[0], total[pos - 1]
    bas, haut = ic_poisson(k, expo)
    print(f"\n{'Portefeuille':20}{k / expo * 100:>15.2f}{f'{bas * 100:.2f} - {haut * 100:.2f}':>26}")
    for nom, col in AXES.items():
        print(f"\n{nom}")
        for ligne in donnees(col):
            expo, k = ligne[1], ligne[pos]
            bas, haut = ic_poisson(k, expo)
            print(f"{ligne[0]:20}{k / expo * 100:>15.2f}{f'{bas * 100:.2f} - {haut * 100:.2f}':>26}")


def comparer(titre, col, m1, m2, pos):
    """Test binomial exact : comparaison de deux taux de Poisson."""
    d = {ligne[0]: (ligne[1], ligne[pos]) for ligne in donnees(col)}
    (e1, x1), (e2, x2) = d[m1], d[m2]
    p = binomtest(x1, x1 + x2, e1 / (e1 + e2)).pvalue
    print(f"{titre}: {m1} {x1 / e1 * 100:.2f} % contre {m2} {x2 / e2 * 100:.2f} %  ->  p-value = {p:.2e}")


def prime_et_ratio():
    """Prime moyenne et ratio S/P : bootstrap par contrat (les indicateurs sont des rapports de sommes)."""
    cols = [c[0] for c in con.execute("select * from core.fait_exposition limit 0").description]
    manque = [c for c in ("contrat_id", "annee", "annees_police", "prime_acquise") if c not in cols]
    if manque:
        raise SystemExit(f"Colonnes absentes de core.fait_exposition : {manque}. Colonnes disponibles : {cols}")

    rows = con.execute(f"""
        with expo as (
            select contrat_id, sum(annees_police) as ap, sum(prime_acquise) as pr
            from core.fait_exposition group by 1),
        sin as (
            select s.contrat_id, sum(coalesce(s.montant_regle, 0)) as paye
            from core.fait_sinistre s
            join core.fait_exposition e on e.contrat_id = s.contrat_id and e.annee = year(s.date_survenance)
            where {FILTRE_SINISTRES} group by 1)
        select e.contrat_id, c.produit::varchar, c.formule::varchar, c.canal_distribution::varchar,
               e.ap, e.pr, coalesce(sin.paye, 0)
        from expo e
        join core.dim_contrat c on c.contrat_id = e.contrat_id
        left join sin on sin.contrat_id = e.contrat_id""").fetchall()
    ids = np.array([r[0] for r in rows])
    produit, formule, canal = (np.array([r[i] for r in rows]) for i in (1, 2, 3))
    ap, pr, paye = (np.array([r[i] for r in rows], dtype=float) for i in (4, 5, 6))

    gros = con.execute(f"select contrat_id, montant_regle from core.fait_sinistre s where {FILTRE_SINISTRES} "
                       "order by montant_regle desc limit 1").fetchone()
    paye_h = paye.copy()
    paye_h[ids == gros[0]] -= gros[1]

    def boot(masque, paye_v, n=2000, lot=200):
        a, p, s = ap[masque], pr[masque], paye_v[masque]
        prime, ratio = [], []
        for _ in range(n // lot):
            idx = rng.integers(0, len(a), (lot, len(a)))
            sa, sp, ss = a[idx].sum(axis=1), p[idx].sum(axis=1), s[idx].sum(axis=1)
            prime.append(sp / sa)
            ratio.append(ss / sp)
        return [np.percentile(np.concatenate(v), [2.5, 97.5]) for v in (prime, ratio)]

    print("\nPrime moyenne et ratio sinistres/primes, intervalle de confiance à 95 % (bootstrap par contrat)")
    print(f"{'':32}{'Prime moy. €':>13}{'IC 95 %':>16}{'Ratio S/P %':>13}{'IC 95 %':>18}")
    tout = np.ones(len(ap), bool)
    groupes = [("Portefeuille", tout, paye), ("Portefeuille hors exceptionnel", tout, paye_h)]
    for nom, vals in (("Produit", produit), ("Formule", formule), ("Canal", canal)):
        groupes += [(f"{nom} {v}", vals == v, paye) for v in sorted(set(vals))]
    for nom, masque, paye_v in groupes:
        ic_prime, ic_ratio = boot(masque, paye_v)
        prime = pr[masque].sum() / ap[masque].sum()
        ratio = paye_v[masque].sum() / pr[masque].sum()
        print(f"{nom:32}{prime:>13,.0f}{f'{ic_prime[0]:,.0f} - {ic_prime[1]:,.0f}':>16}"
              f"{ratio * 100:>13.1f}{f'{ic_ratio[0] * 100:.1f} - {ic_ratio[1] * 100:.1f}':>18}")


def couts():
    rows = con.execute(f"""
        select coalesce(s.montant_regle, 0), c.produit::varchar, c.canal_distribution::varchar
        from core.fait_sinistre s
        join core.dim_contrat c on c.contrat_id = s.contrat_id
        where {FILTRE_SINISTRES}""").fetchall()
    montant = np.array([r[0] for r in rows], dtype=float)
    produit = np.array([r[1] for r in rows])
    canal = np.array([r[2] for r in rows])
    print(f"\nSinistres retenus : {len(montant)}, coût moyen : {montant.mean():,.0f} €")

    print("\nCoût moyen par sinistre, intervalle de confiance à 95 % (bootstrap)")
    print(f"{'':28}{'Sinistres':>10}{'Coût moyen €':>14}{'IC 95 % (bas - haut)':>24}")
    groupes = [("Portefeuille", np.ones(len(montant), bool)),
               ("Portefeuille hors exceptionnel", montant < montant.max())]
    groupes += [(f"Produit {p}", produit == p) for p in sorted(set(produit))]
    groupes += [(f"Canal {c}", canal == c) for c in sorted(set(canal))]
    for nom, masque in groupes:
        x = montant[masque]
        bas, haut = ic_bootstrap(x)
        print(f"{nom:28}{len(x):>10}{x.mean():>14,.0f}{f'{bas:,.0f} - {haut:,.0f}':>24}")

    print("\nCoût : WEB contre AGENT (test de Mann-Whitney)")
    w, a = montant[canal == "WEB"], montant[canal == "AGENT"]
    p = mannwhitneyu(w, a, alternative="two-sided").pvalue
    print(f"Médiane WEB {np.median(w):,.0f} €, médiane AGENT {np.median(a):,.0f} €  ->  p-value = {p:.4f}")
    w2, a2 = w[w < montant.max()], a[a < montant.max()]
    print(f"Hors sinistre exceptionnel : p-value = {mannwhitneyu(w2, a2).pvalue:.4f}")

    print("\nQueue des coûts")
    for q in (50, 75, 90, 95, 99):
        print(f"Quantile {q:>2} % : {np.percentile(montant, q):>12,.0f} €")
    print(f"Maximum        : {montant.max():>12,.0f} €")
    print(f"Coût moyen / médiane : {montant.mean() / np.median(montant):.1f}")
    tri = np.sort(montant)[::-1]
    for part in (0.01, 0.05, 0.10):
        k = int(round(len(tri) * part))
        print(f"Les {part:.0%} sinistres les plus chers ({k}) portent {tri[:k].sum() / tri.sum():.1%} des paiements")
    print(f"Le plus gros sinistre porte {tri[0] / tri.sum():.1%} des paiements")


if __name__ == "__main__":
    intervalles("Fréquence %", "Fréquence des sinistres, intervalle de confiance à 95 %")
    intervalles("Résiliation %", "Taux de résiliation, intervalle de confiance à 95 %")
    prime_et_ratio()
    print("\nTests de comparaison")
    comparer("Fréquence, zone 1 contre zone 5", "zone_risque", "1", "5", 2)
    comparer("Résiliation, WEB contre AGENT", "canal", "WEB", "AGENT", 3)
    couts()