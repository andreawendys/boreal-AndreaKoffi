"""Dashboard Boréal Assurances. Lit uniquement le schéma marts (lecture seule).

Lancement :  streamlit run app.py
"""
import os
from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB = os.environ.get("BOREAL_DB") or str(Path(__file__).resolve().parent / "warehouse" / "boreal.duckdb")
SEUIL = 0.70          # alerte : ratio sinistres/primes au-dessus de 70 %
MOIS_IMMATURES = 3    # derniers mois : sinistres encore en cours de déclaration et de règlement
BLEU, ROUGE, GRIS, VERT, ORANGE, MARINE = "#6d28d9", "#e11d48", "#94a3b8", "#059669", "#f59e0b", "#2e1065"
CARTE = "#ffffff"   # fond des cartes et graphiques

st.set_page_config(page_title="Boréal Assurances", layout="wide")
st.markdown(f"""
<style>
.stApp {{ background: #f4f1fa; font-family: "Trebuchet MS", "Segoe UI", sans-serif; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid #e0d8f2; }}
[data-testid="stMetric"] {{ background: {CARTE}; border-radius: 18px; padding: 14px 20px; border-left: 6px solid {BLEU};
                            box-shadow: 0 2px 8px rgba(46,16,101,.12); }}
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{ background: {CARTE}; border-radius: 18px; padding: 10px;
                            box-shadow: 0 2px 8px rgba(46,16,101,.12); }}
.bandeau {{ background: {CARTE}; border-left: 10px solid {BLEU}; color: {MARINE}; padding: 12px 22px; border-radius: 4px 18px 18px 4px;
            font-size: 1.4rem; font-weight: 700; margin-bottom: 10px; box-shadow: 0 2px 8px rgba(46,16,101,.12); }}
.bandeau span {{ font-size: .85rem; font-weight: 400; color: #6b6480; margin-left: 14px; }}
div[role="radiogroup"] {{ gap: 0; border-bottom: 2px solid #ddd5ee; }}
div[role="radiogroup"] label {{ background: transparent; border: none; border-radius: 0; padding: 6px 22px;
                                border-bottom: 4px solid transparent; margin-bottom: -2px; }}
div[role="radiogroup"] label:has(input:checked) {{ border-bottom: 4px solid {BLEU}; font-weight: 700; }}
div[role="radiogroup"] label > div:first-child {{ display: none; }}
[data-baseweb="select"] > div, [data-testid="stMultiSelect"] > div > div, [data-testid="stSelectbox"] > div > div {{
    background: #e6f4f1 !important; border: 1px solid #0f766e !important; border-radius: 14px !important; }}
[data-baseweb="tag"] {{ background: #0f766e !important; color: #fff !important; border-radius: 14px !important; }}
h2, h3 {{ color: {MARINE}; border-left: 5px solid {ORANGE}; padding-left: 10px; }}
</style>""", unsafe_allow_html=True)


# ---------- accès aux données ----------
@st.cache_resource
def connexion():
    return duckdb.connect(DB, read_only=True)


@st.cache_data
def lire(table):
    return connexion().execute(f"select * from marts.{table}").df()


def pct(x, d=1):
    return "n/d" if pd.isna(x) else f"{x * 100:.{d}f} %".replace(".", ",")


def eur(x):
    return "n/d" if pd.isna(x) else f"{x:,.0f} €".replace(",", " ")


def entier(x):
    return f"{x:,.0f}".replace(",", " ")


def somme(df):
    """Indicateurs d'un ensemble de lignes : on additionne puis on divise."""
    ap, n, p, pr = df.annees_police.sum(), df.nb_sinistres.sum(), df.paye.sum(), df.prime_acquise.sum()
    return {
        "primes": pr, "nb_sinistres": n,
        "frequence": n / ap if ap else float("nan"),
        "cout": p / n if n else float("nan"),
        "prime": pr / ap if ap else float("nan"),
        "ratio": p / pr if pr else float("nan"),
        "resiliation": df.nb_resiliations.sum() / ap if ap else float("nan"),
    }


def variation(a, b):
    return None if pd.isna(a) or pd.isna(b) or b == 0 else (a - b) / b


def delta_pct(a, b):
    v = variation(a, b)
    return None if v is None else f"{v * 100:+.1f} %".replace(".", ",")


def serie_mensuelle(df):
    """Série mensuelle de chaque indicateur (on additionne puis on divise)."""
    m = df.groupby("mois")[["annees_police", "nb_sinistres", "paye", "prime_acquise", "nb_resiliations"]].sum()
    m = m.reindex(pd.date_range(m.index.min(), m.index.max(), freq="MS"), fill_value=0)
    return pd.DataFrame({
        "ratio": m.paye / m.prime_acquise,
        "frequence": m.nb_sinistres / m.annees_police,
        "cout": m.paye / m.nb_sinistres,
        "resiliation": m.nb_resiliations / m.annees_police,
        "prime": m.prime_acquise / m.annees_police,
    })


def zone_immature(fig, dernier):
    debut = dernier - pd.DateOffset(months=MOIS_IMMATURES - 1)
    fig.add_vrect(x0=debut, x1=dernier + pd.DateOffset(days=30), fillcolor=GRIS, opacity=0.18, line_width=0,
                  annotation_text="mois immatures", annotation_position="top left")


def mise_en_forme(fig, titre, hauteur=380):
    fig.update_layout(title=dict(text=titre.replace(" Piste :", "<br>Piste :"), font=dict(size=15, color=MARINE)),
                      template="plotly_white", paper_bgcolor=CARTE, plot_bgcolor=CARTE, height=hauteur, font=dict(family="Trebuchet MS, Segoe UI, sans-serif"),
                      margin=dict(l=10, r=10, t=85, b=10), legend=dict(orientation="h", y=-0.18))
    return fig


def graphique(fig, titre, hauteur=380):
    st.plotly_chart(mise_en_forme(fig, titre, hauteur), width="stretch")


# ---------- données ----------
mens = lire("evolution_mensuelle").copy()
mens["mois"] = pd.to_datetime(mens["mois"])
base = lire("base_technique")
dernier_mois = mens["mois"].max()
fin_donnees = dernier_mois + pd.offsets.MonthEnd(0)

# ---------- en-tête et navigation (en haut de page) ----------
bandeau = st.empty()   # rempli plus bas, une fois la période choisie connue
page = st.radio("Page", ["Synthèse", "Risque et clientèle", "Suivi de la chaîne"],
                horizontal=True, label_visibility="collapsed")

# ---------- filtres communs (valables pour toutes les pages) ----------
st.sidebar.markdown("### Réglages")
mois_liste = list(pd.date_range(mens["mois"].min(), dernier_mois, freq="MS"))
debut, fin = st.sidebar.select_slider("Fenêtre de temps", options=mois_liste, value=(mois_liste[0], mois_liste[-1]),
                                      format_func=lambda d: d.strftime("%m/%Y"),
                                      help="Mois de survenance des sinistres et d'exposition des contrats.")
produits = st.sidebar.multiselect("Produits", sorted(mens["produit"].unique()), default=sorted(mens["produit"].unique()))
zones = st.sidebar.multiselect("Zones de risque", sorted(mens["zone_risque"].unique()), default=sorted(mens["zone_risque"].unique()))
canaux = st.sidebar.multiselect("Canaux de vente", sorted(mens["canal"].unique()), default=sorted(mens["canal"].unique()))
st.sidebar.divider()
exclure = st.sidebar.toggle(f"Écarter les {MOIS_IMMATURES} derniers mois", value=False,
                            help="Les sinistres récents ne sont pas encore tous déclarés ni payés : le ratio des derniers mois "
                                 "est sous-estimé. Désactivé, les chiffres sont ceux du dossier.")
hors_exc = st.sidebar.toggle("Mettre de côté le sinistre exceptionnel (> 1 M€)", value=False,
                             help="Retire un dossier de 2,5 M€ (22 % du payé) qui fausse les moyennes. "
                                  "Désactivé, les chiffres sont ceux du dossier. Concerne la page Synthèse.")

limite = dernier_mois - pd.DateOffset(months=MOIS_IMMATURES) if exclure else dernier_mois
fin_eff = min(fin, limite)
bandeau.markdown(f'<div class="bandeau">Boréal · tableau de bord IARD<span>du {debut:%m/%Y} au {fin_eff:%m/%Y}</span></div>',
                 unsafe_allow_html=True)

mens_calc = mens.copy()
if hors_exc:
    mens_calc["paye"] = mens_calc["paye"] - mens_calc["paye_exceptionnel"]
    mens_calc["nb_sinistres"] = mens_calc["nb_sinistres"] - mens_calc["nb_exceptionnels"]
filtre_df = mens_calc[mens_calc["produit"].isin(produits) & mens_calc["zone_risque"].isin(zones) & mens_calc["canal"].isin(canaux)]
if filtre_df.empty:
    st.warning("Rien à afficher avec ces réglages.")
    st.stop()

periode = filtre_df[(filtre_df.mois >= debut) & (filtre_df.mois <= fin_eff)]
precedente = filtre_df[(filtre_df.mois >= debut - pd.DateOffset(years=1)) & (filtre_df.mois <= fin_eff - pd.DateOffset(years=1))]
if debut - pd.DateOffset(years=1) < mens["mois"].min():
    precedente = precedente.iloc[0:0]   # pas de données un an avant le début : aucune comparaison
k, k1 = somme(periode), somme(precedente)
immature_inclus = (not exclure) and fin_eff >= dernier_mois - pd.DateOffset(months=MOIS_IMMATURES - 1)

# =============================================================== PORTEFEUILLE
if page == "Synthèse":
    st.title("Synthèse du portefeuille")
    st.caption(f"Situation au {fin_donnees:%d/%m/%Y}. Chaque variation est mesurée face à la même période de l'année précédente, lorsqu'elle existe.")
    if k["ratio"] > SEUIL:
        st.error(f"Seuil franchi : le ratio sinistres/primes atteint {pct(k['ratio'])} (limite fixée à {pct(SEUIL, 0)}).")
    else:
        st.success(f"Situation saine : ratio sinistres/primes à {pct(k['ratio'])}, en dessous de la limite de {pct(SEUIL, 0)}.")
    if immature_inclus:
        st.info(f"Attention, les {MOIS_IMMATURES} derniers mois sont intégrés alors qu'ils sont incomplets : leur ratio paraît trop bas.")

    actifs = periode[periode.mois == periode.mois.max()].contrats_actifs.sum()
    actifs_n1 = precedente[precedente.mois == precedente.mois.max()].contrats_actifs.sum() if len(precedente) else float("nan")
    c = st.columns(3)
    c[0].metric("Primes acquises", eur(k["primes"]), delta_pct(k["primes"], k1["primes"]) if len(precedente) else None,
                help="Prime annuelle × années-police, sur la période.")
    c[1].metric("Contrats actifs", entier(actifs), delta_pct(actifs, actifs_n1),
                help="Contrats en vigueur le dernier mois de la période.")
    c[2].metric("Ratio sinistres/primes", pct(k["ratio"]),
                None if pd.isna(k1["ratio"]) else f"{(k['ratio'] - k1['ratio']) * 100:+.1f} pts".replace(".", ","),
                delta_color="inverse", help="Sinistres payés ÷ primes acquises. Plus il est bas, plus le portefeuille est rentable. Seuil de 70 % = hypothèse de travail : frais de gestion et commissions (absents des sources) pèsent en général 25 à 30 % des primes.")
    c = st.columns(3)
    c[0].metric("Fréquence", pct(k["frequence"], 2), delta_pct(k["frequence"], k1["frequence"]), delta_color="inverse",
                help="Sinistres retenus ÷ années-police.")
    c[1].metric("Coût moyen", eur(k["cout"]), delta_pct(k["cout"], k1["cout"]), delta_color="inverse",
                help="Montant payé ÷ sinistres retenus.")
    c[2].metric("Taux de résiliation", pct(k["resiliation"]), delta_pct(k["resiliation"], k1["resiliation"]), delta_color="inverse",
                help="Résiliations ÷ années-police.")

    s = serie_mensuelle(filtre_df)

    # Graphique 1 : évolution mensuelle comparée à l'année précédente
    st.subheader("Tendance mois par mois")
    noms = {"ratio": "Ratio sinistres/primes", "frequence": "Fréquence", "cout": "Coût moyen",
            "resiliation": "Taux de résiliation"}
    ind = st.selectbox("Indicateur suivi", list(noms), format_func=noms.get)
    fmt = ".1%" if ind in ("ratio", "resiliation") else (".2%" if ind == "frequence" else ",.0f")
    cour = s[ind][(s.index >= debut) & (s.index <= fin_eff)]
    prec = s[ind].shift(12)[cour.index]
    f1 = go.Figure()
    f1.add_scatter(x=cour.index, y=prec, name="Année précédente", line=dict(color=GRIS, width=2, dash="dot"),
                   hovertemplate="%{x|%m/%Y}<br>Année précédente : %{y:" + fmt + "}<extra></extra>")
    f1.add_scatter(x=cour.index, y=cour, name="Année en cours", line=dict(color=BLEU, width=3),
                   hovertemplate="%{x|%m/%Y}<br>Mois : %{y:" + fmt + "}<extra></extra>")
    if ind == "ratio":
        f1.add_hline(y=SEUIL, line_dash="dash", line_color=ROUGE, annotation_text=f"Seuil d'alerte {SEUIL:.0%}")
    if immature_inclus:
        zone_immature(f1, dernier_mois)
    f1.update_yaxes(tickformat=fmt, rangemode="tozero")
    mois_alerte = int((cour > SEUIL).sum()) if ind == "ratio" else None
    if ind == "ratio":
        titre1 = (f"Limite de {SEUIL:.0%} franchie sur {mois_alerte} mois (sur {len(cour)}) : "
                  + ("repérer les mois et segments responsables" if mois_alerte else "rien ne justifie de toucher aux tarifs"))
    else:
        v1, v0 = cour.dropna(), prec.dropna()
        titre1 = (f"{noms[ind]} {'plus élevé(e)' if v1.mean() > v0.mean() else 'plus bas(se)'} que l'an dernier sur la fenêtre choisie"
                  if len(v1) and len(v0) else f"{noms[ind]} mensuel")
    graphique(f1, titre1)

    # Graphique : prime moyenne mensuelle
    st.subheader("Prix moyen d'un contrat")
    pm = s["prime"][(s.index >= debut) & (s.index <= fin_eff)]
    pm_prec = s["prime"].shift(12)[pm.index]
    fp = go.Figure()
    fp.add_scatter(x=pm.index, y=pm_prec, name="Année précédente", line=dict(color=GRIS, width=2, dash="dot"),
                   hovertemplate="%{x|%m/%Y}<br>Année précédente : %{y:,.0f} €<extra></extra>")
    fp.add_scatter(x=pm.index, y=pm, name="Prime moyenne", line=dict(color=ORANGE, width=3), mode="lines+markers",
                   hovertemplate="%{x|%m/%Y}<br>Prime moyenne : %{y:,.0f} €<extra></extra>")
    fp.update_yaxes(ticksuffix=" €", rangemode="tozero")
    pm_ok = pm.dropna()
    if len(pm_ok) > 1:
        ecart = (pm_ok.iloc[-1] - pm_ok.iloc[0]) / pm_ok.iloc[0]
        titre_p = (f"La prime moyenne passe de {eur(pm_ok.iloc[0])} à {eur(pm_ok.iloc[-1])} ({ecart * 100:+.1f} %".replace(".", ",")
                   + ") : le prix est stable, il n'explique pas l'évolution du ratio" if abs(ecart) < 0.05
                   else f"La prime moyenne passe de {eur(pm_ok.iloc[0])} à {eur(pm_ok.iloc[-1])} ({ecart * 100:+.1f} %".replace(".", ",")
                   + ") : le prix pèse sur le ratio")
    else:
        titre_p = "Prime moyenne mensuelle"
    graphique(fp, titre_p, 330)

    # Graphique 2 : marge technique par segment
    st.subheader("Rentabilité par segment")
    axes_marge = {"Produit": ("produit", ""), "Zone de risque": ("zone_risque", "la zone "), "Canal": ("canal", "le canal ")}
    axe_m = st.selectbox("Découper par", list(axes_marge), help="Marge technique = primes acquises − sinistres payés, sur la période choisie.")
    col_m, prefixe = axes_marge[axe_m]
    gm = periode.assign(zone_risque=periode.zone_risque.astype(str)).groupby(col_m)[["prime_acquise", "paye"]].sum()
    gm["marge"] = gm.prime_acquise - gm.paye
    gm["ratio"] = gm.paye / gm.prime_acquise
    gm = gm.sort_values("marge")
    fm2 = go.Figure(go.Bar(x=gm.marge, y=gm.index.astype(str), orientation="h",
                           marker_color=[VERT if m >= 0 else ROUGE for m in gm.marge],
                           customdata=gm[["prime_acquise", "paye", "ratio"]].values,
                           hovertemplate="%{y}<br>Marge : %{x:,.0f} €<br>Primes : %{customdata[0]:,.0f} €<br>"
                                         "Sinistres payés : %{customdata[1]:,.0f} €<br>Ratio : %{customdata[2]:.1%}<extra></extra>"))
    fm2.add_vline(x=0, line_color=GRIS)
    fm2.update_xaxes(title="Marge technique (€)")

    def meur(x):
        return (f"{x / 1e6:.1f} M€" if abs(x) >= 1e6 else f"{x / 1e3:.0f} k€").replace(".", ",")

    if len(gm) > 1:
        haut, bas = gm.index[-1], gm.index[0]
        action = ("contrôler d'abord l'effet d'un gros sinistre avant de modifier les prix" if gm.ratio.iloc[0] > SEUIL
                  else "suivre son ratio, encore sous la limite")
        titre_m = (f"{prefixe.capitalize()}{haut} est la plus rentable ({meur(gm.marge.iloc[-1])}) tandis que {prefixe}{bas} l'est le moins "
                   f"({meur(gm.marge.iloc[0])}). Piste : {action}")
    else:
        titre_m = "Marge technique par segment"
    graphique(fm2, titre_m, 260 + 40 * len(gm))

    # Graphique 3 : le levier qui bouge le plus vs N-1
    st.subheader("Les moteurs de variation du ratio")
    if len(precedente):
        ka, kb, comparaison = k, k1, "la période choisie vs la même période un an plus tôt"
    else:   # pas d'année précédente disponible : on compare les 12 derniers mois aux 12 mois d'avant
        fin_ref = min(fin_eff, dernier_mois - pd.DateOffset(months=MOIS_IMMATURES))
        ka = somme(filtre_df[(filtre_df.mois > fin_ref - pd.DateOffset(months=12)) & (filtre_df.mois <= fin_ref)])
        kb = somme(filtre_df[(filtre_df.mois > fin_ref - pd.DateOffset(months=24)) & (filtre_df.mois <= fin_ref - pd.DateOffset(months=12))])
        comparaison = f"les 12 mois à fin {fin_ref:%m/%Y} vs les 12 mois précédents"
    leviers = {
        "la fréquence": (variation(ka["frequence"], kb["frequence"]), "des sinistres", "renforcer la prévention et la sélection des risques"),
        "le coût moyen": (variation(ka["cout"], kb["cout"]), "du coût", "contrôler les gros sinistres et les barèmes d'indemnisation"),
        "la prime moyenne": (variation(ka["prime"], kb["prime"]), "des primes", "réviser la tarification"),
    }
    leviers = {n: v for n, v in leviers.items() if v[0] is not None}
    if leviers:
        # une hausse de la fréquence ou du coût dégrade le ratio ; une hausse de la prime l'améliore
        def defavorable(nom, var):
            return var > 0 if nom != "la prime moyenne" else var < 0
        fl2 = go.Figure(go.Bar(
            x=[v[0] * 100 for v in leviers.values()], y=list(leviers), orientation="h",
            marker_color=[ROUGE if defavorable(n, v[0]) else VERT for n, v in leviers.items()],
            hovertemplate="%{y} : %{x:+.1f} % vs la période de comparaison<extra></extra>"))
        fl2.add_vline(x=0, line_color=GRIS)
        fl2.update_xaxes(title="Variation vs la période de comparaison (%)", ticksuffix=" %")
        n_max = max(leviers, key=lambda n: abs(leviers[n][0]))
        var_max, _, action = leviers[n_max]
        if defavorable(n_max, var_max):
            titre_l = f"{n_max.capitalize()} pèse le plus ({var_max * 100:+.0f} %) et tire le ratio vers le haut. Piste : {action}"
        else:
            titre_l = f"{n_max.capitalize()} pèse le plus ({var_max * 100:+.0f} %) et améliore le ratio. Piste : conforter cette évolution"
        graphique(fl2, titre_l, 300)
        st.caption(f"Base de comparaison : {comparaison}. En rouge, ce qui dégrade le ratio ; en vert, ce qui l'améliore. "
                   "Ratio = fréquence × coût moyen ÷ prime moyenne.")
    else:
        st.info("Historique insuffisant pour établir une comparaison.")

# =============================================================== TECHNIQUE ET CLIENTS
elif page == "Risque et clientèle":
    st.title("Risque et clientèle")
    annees = range(debut.year, fin_eff.year + 1)
    b = base[base.annee.isin(annees) & base.produit.isin(produits) & base.zone_risque.isin(zones) & base.canal.isin(canaux)]
    st.caption("Les filtres s'appliquent aux années entières couvertes par la période. La décomposition porte sur le portefeuille entier ; "
               "les cohortes se filtrent par produit ; les clients ne dépendent ni de la zone ni du canal.")

    # Ratio par segment
    st.subheader("Comparaison des segments")
    axes = {"Zone de risque": "zone_risque", "Formule": "formule", "Canal": "canal", "Tranche d'âge": "tranche_age", "Produit": "produit"}
    axe = st.selectbox("Regrouper par", list(axes), help="Ratio = sinistres payés ÷ primes acquises, calculé sur la sélection.")
    g = b.assign(zone_risque=b.zone_risque.astype(str)).groupby(axes[axe])[["annees_police", "nb_sinistres", "paye", "prime_acquise"]].sum()
    g["ratio"] = g.paye / g.prime_acquise
    g["frequence"] = g.nb_sinistres / g.annees_police
    g["cout"] = g.paye / g.nb_sinistres
    g = g.sort_values("ratio")
    fs = go.Figure(go.Bar(x=g.ratio, y=g.index.astype(str), orientation="h", marker_color=[ROUGE if r > SEUIL else BLEU for r in g.ratio],
                          customdata=g[["frequence", "cout", "prime_acquise"]].values,
                          hovertemplate="%{y}<br>Ratio : %{x:.1%}<br>Fréquence : %{customdata[0]:.2%}<br>"
                                        "Coût moyen : %{customdata[1]:,.0f} €<br>Primes : %{customdata[2]:,.0f} €<extra></extra>"))
    fs.add_vline(x=SEUIL, line_dash="dash", line_color=ROUGE)
    fs.update_xaxes(tickformat=".0%")
    titre = (f"{axe} : « {g.index[-1]} » est le segment le plus coûteux ({pct(g.ratio.iloc[-1], 0)}), à traiter en premier"
             if len(g) else "Aucune donnée")
    graphique(fs, titre, 300 + 25 * len(g))

    # Décomposition
    st.subheader("Pourquoi le ratio a bougé, année après année")
    st.caption("Lecture : 1 point = 1 € de sinistres en plus (ou en moins) pour 100 € de primes. Le ratio vaut fréquence × coût moyen ÷ prime moyenne ; "
               "la prime moyenne étant presque stable, son effet est proche de zéro.")
    ev = lire("evolution_annuelle").dropna(subset=["effet_frequence"])
    ev = ev.assign(libelle=ev.annee.astype(str) + ev.annee_incomplete.map({True: " (partielle)", False: ""}))
    fd = go.Figure()
    for col, nom, couleur in [("effet_frequence", "Fréquence", ORANGE), ("effet_cout", "Coût moyen", ROUGE), ("effet_prime", "Prime moyenne", VERT)]:
        fd.add_bar(x=ev.libelle, y=ev[col] * 100, name=nom, marker_color=couleur,
                   hovertemplate="%{x}<br>" + nom + " : %{y:+.1f} points de ratio<extra></extra>")
    fd.add_scatter(x=ev.libelle, y=ev.variation_ratio * 100, name="Variation totale", mode="markers",
                   marker=dict(color=MARINE, size=11, symbol="diamond"),
                   hovertemplate="%{x}<br>Variation du ratio : %{y:+.1f} points<extra></extra>")
    fd.update_layout(barmode="relative")
    fd.update_yaxes(title="Points de ratio")
    complet = ev[~ev.annee_incomplete]
    if len(complet):
        d = complet.iloc[-1]
        eff = {"de la fréquence": d.effet_frequence, "du coût moyen": d.effet_cout, "de la prime moyenne": d.effet_prime}
        moteur = max(eff, key=lambda n: abs(eff[n]))
        titre = f"Sur {int(d.annee)}, le ratio bouge de {d.variation_ratio * 100:+.0f} points, principalement sous l'effet {moteur}".replace(".", ",")
    else:
        titre = "Décomposition du ratio"
    graphique(fd, titre, 380)

    # Rétention : matrice par cohorte
    st.subheader("Fidélité des contrats par cohorte")
    coh = lire("retention_cohortes")
    coh = coh[coh["produit"].isin(produits)].groupby(["cohorte", "k"])[["contrats", "retenus"]].sum().reset_index()
    coh["retention"] = coh.retenus / coh.contrats
    mat = coh.pivot(index="cohorte", columns="k", values="retention")
    fh = go.Figure(go.Heatmap(xgap=3, ygap=3, z=mat.values * 100, x=[f"{int(c)} an(s)" for c in mat.columns], y=mat.index.astype(str),
                              colorscale="Purples", zmin=0, zmax=100, text=mat.apply(lambda col: col.map(lambda v: "" if pd.isna(v) else f"{v * 100:.0f} %")).values, texttemplate="%{text}",
                              hovertemplate="Cohorte %{y}<br>%{x} après souscription : %{z:.1f} % des contrats conservés<extra></extra>",
                              colorbar=dict(title="%")))
    fh.update_yaxes(autorange="reversed", title="Cohorte")
    pooled = coh.groupby("k")[["contrats", "retenus"]].sum()
    pooled = pooled.retenus / pooled.contrats
    titre = (f"Après {int(pooled.index[-1])} ans, un contrat sur deux seulement subsiste : renforcer la fidélisation dès la 1re année"
             if len(pooled) and pooled.iloc[-1] < 0.6 else "Proportion de contrats encore actifs, par année de souscription")
    graphique(fh, titre, 380)

    # Valeur client
    st.subheader("Qui crée la valeur ?")
    vc0 = lire("valeur_client")
    tranches = st.multiselect("Âge des clients", sorted(vc0.tranche_age.dropna().unique()),
                              default=sorted(vc0.tranche_age.dropna().unique()),
                              help="Valeur = primes acquises − sinistres payés, sur toute la période.")
    vc = vc0[vc0.tranche_age.isin(tranches)].sort_values("valeur", ascending=False).reset_index(drop=True)
    if len(vc):
        cum = vc.valeur.cumsum() / vc.valeur.sum()
        x = (vc.index + 1) / len(vc)
        top10 = cum.iloc[int(len(vc) * 0.10) - 1] if len(vc) >= 10 else float("nan")
        neg = int((vc.valeur < 0).sum())
        fv = go.Figure(go.Scatter(x=x, y=cum, line=dict(color=BLEU, width=3), showlegend=False,
                                  hovertemplate="%{x:.0%} des clients<br>= %{y:.0%} de la valeur<extra></extra>"))
        fv.add_hline(y=1, line_dash="dot", line_color=GRIS)
        fv.update_xaxes(tickformat=".0%", title="Part des clients, du plus au moins rentable")
        fv.update_yaxes(tickformat=".0%", title="Part cumulée de la valeur")
        v1, v2 = st.columns([2, 1])
        with v1:
            graphique(fv, f"{pct(top10, 0)} de la valeur vient de 10 % des clients, alors que {entier(neg)} clients en font perdre : fidéliser en priorité les meilleurs", 400)
        v2.metric("Valeur totale", eur(vc.valeur.sum()), help="Primes acquises − sinistres payés, tous clients de la sélection.")
        v2.metric("Clients à valeur négative", entier(neg), help="Sinistres payés supérieurs aux primes acquises.")
        v2.metric("Perte cumulée de ces clients", eur(vc.loc[vc.valeur < 0, "valeur"].sum()))

# =============================================================== EXPLOITATION
elif page == "Suivi de la chaîne":
    st.title("État de la chaîne de données")
    ex = lire("exploitation")
    ex["horodatage"] = pd.to_datetime(ex["horodatage"])
    ch, rg, ts = (ex[ex.rubrique == r] for r in ("CHARGEMENT", "REGLE", "TEST"))
    echecs = int((~ts.statut.isin({"OK", "PASS"})).sum())
    c = st.columns(4)
    c[0].metric("Données à jour au", f"{pd.to_datetime(ex.derniere_date_donnee).max():%d/%m/%Y}",
                help="Date la plus récente dans les sources importées.")
    c[1].metric("Dernier import", f"{ch.horodatage.max():%d/%m/%Y}")
    c[2].metric("Contrôles réussis", f"{len(ts) - echecs} / {len(ts)}", help="Tests des couches brute et cœur.")
    c[3].metric("Règles activées", f"{int((rg.valeur > 0).sum())} / {len(rg)}",
                help="Règles de qualité qui ont détecté au moins une ligne anormale.")
    if echecs:
        st.error("Un contrôle est en échec : les chiffres ne doivent pas être diffusés tant que ce n'est pas corrigé.")
    else:
        st.success("Tous les contrôles sont au vert : les chiffres peuvent être diffusés.")

    st.subheader("Derniers imports par source")
    st.dataframe(ch[["element", "detail", "valeur", "statut", "horodatage"]].rename(
        columns={"element": "Source", "detail": "Fichiers", "valeur": "Lignes chargées", "statut": "Statut", "horodatage": "Chargé le"}),
        hide_index=True, width="stretch")

    st.subheader("Les 10 règles qui écartent le plus de lignes")
    anom = rg[rg.valeur > 0].nlargest(10, "valeur").sort_values("valeur")
    libelles = anom.element + " · " + anom.detail.str.slice(0, 38)
    fr = go.Figure(go.Bar(x=anom.valeur, y=libelles, orientation="h", marker_color=ORANGE, customdata=anom[["detail", "statut"]].values,
                          hovertemplate="%{y} : %{x:,.0f} lignes<br>%{customdata[0]}<br>Traitement : %{customdata[1]}<extra></extra>"))
    if len(anom):
        top = anom.iloc[-1]
        titre = f"{top.element} concentre le plus de lignes concernées ({entier(top.valeur)}) : traiter cette anomalie à la source en priorité"
    else:
        titre = "Aucune ligne écartée"
    graphique(fr, titre, 300 + 26 * len(anom))

    st.subheader("Catalogue des règles de qualité")
    st.dataframe(rg[["element", "detail", "valeur", "statut"]].rename(
        columns={"element": "Règle", "detail": "Description", "valeur": "Lignes signalées ou rejetées", "statut": "Gravité / traitement"}),
        hide_index=True, width="stretch")

    st.subheader("Contrôles automatisés")
    st.dataframe(ts[["element", "detail", "statut", "horodatage"]].rename(
        columns={"element": "Test", "detail": "Description", "statut": "Résultat", "horodatage": "Exécuté le"}),
        hide_index=True, width="stretch")

    st.subheader("Rapidité de traitement des sinistres")
    dl = lire("delais_sinistres")
    dl = dl[dl["produit"].isin(produits)]
    etapes = {"delai_declaration": "Survenance → déclaration", "delai_premier_reglement": "Déclaration → 1er règlement",
              "delai_cloture": "Déclaration → clôture (dernier règlement)"}
    etape = st.selectbox("Phase du dossier", list(etapes), index=1, format_func=etapes.get)
    t = dl.groupby("garantie")[etape].agg(mediane="median", p90=lambda x: x.quantile(0.9), dossiers="count").sort_values("p90")
    fl = go.Figure()
    fl.add_bar(y=t.index.astype(str), x=t.mediane, orientation="h", name="Médiane", marker_color=BLEU,
               hovertemplate="%{y}<br>Médiane : %{x:.0f} jours<extra></extra>")
    fl.add_bar(y=t.index.astype(str), x=t.p90, orientation="h", name="90e centile", marker_color=ROUGE,
               hovertemplate="%{y}<br>9 dossiers sur 10 en moins de %{x:.0f} jours<extra></extra>")
    fl.update_layout(barmode="group")
    fl.update_xaxes(title="Jours")
    titre = (f"« {t.index[-1]} » est la garantie la plus lente : 1 dossier sur 10 dépasse {t.p90.iloc[-1]:.0f} jours, fixer un délai cible"
             if len(t) else "Délais")
    graphique(fl, titre, 260 + 40 * len(t))
    st.caption("Délai de clôture approché par la date du dernier règlement des dossiers clôturés (aucune date de clôture dans les sources).")
