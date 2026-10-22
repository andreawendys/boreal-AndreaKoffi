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
BLEU, ROUGE, GRIS, VERT, ORANGE, MARINE = "#1f5fa8", "#c0392b", "#8a8f98", "#2e8b57", "#e08e0b", "#14213d"

st.set_page_config(page_title="Boréal Assurances", layout="wide")
st.markdown(f"""
<style>
.stApp {{ background: #eef1f5; }}
[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid #dde2e8; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMetric"] {{ background: #fff; border-radius: 10px; padding: 14px 18px; border-top: 4px solid {BLEU};
                            box-shadow: 0 1px 4px rgba(0,0,0,.12); }}
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{ background: #fff; border-radius: 10px; padding: 8px;
                            box-shadow: 0 1px 4px rgba(0,0,0,.12); }}
.bandeau {{ background: linear-gradient(90deg, {MARINE}, {BLEU}); color: #fff; padding: 14px 22px; border-radius: 10px;
            font-size: 1.5rem; font-weight: 600; margin-bottom: 8px; }}
.bandeau span {{ font-size: .9rem; font-weight: 400; opacity: .85; margin-left: 14px; }}
div[role="radiogroup"] {{ gap: 8px; }}
div[role="radiogroup"] label {{ background: #fff; border: 1px solid #cfd6de; border-radius: 20px; padding: 4px 16px; }}
[data-baseweb="select"] > div, [data-testid="stMultiSelect"] > div > div, [data-testid="stSelectbox"] > div > div {{
    background: #dde3ea !important; border: 1px solid #c3ccd6 !important; }}
h2, h3 {{ color: {MARINE}; }}
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
    })


def zone_immature(fig, dernier):
    debut = dernier - pd.DateOffset(months=MOIS_IMMATURES - 1)
    fig.add_vrect(x0=debut, x1=dernier + pd.DateOffset(days=30), fillcolor=GRIS, opacity=0.18, line_width=0,
                  annotation_text="mois immatures", annotation_position="top left")


def mise_en_forme(fig, titre, hauteur=380):
    fig.update_layout(title=dict(text=titre, font=dict(size=15, color=MARINE)), template="plotly_white", height=hauteur,
                      margin=dict(l=10, r=10, t=60, b=10), legend=dict(orientation="h", y=-0.18))
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
page = st.radio("Page", ["Portefeuille", "Technique et clients", "Exploitation", "Définitions"],
                horizontal=True, label_visibility="collapsed")

# ---------- filtres communs (valables pour toutes les pages) ----------
st.sidebar.markdown("### Filtres")
mois_liste = list(pd.date_range(mens["mois"].min(), dernier_mois, freq="MS"))
debut, fin = st.sidebar.select_slider("Période", options=mois_liste, value=(mois_liste[0], mois_liste[-1]),
                                      format_func=lambda d: d.strftime("%m/%Y"),
                                      help="Mois de survenance des sinistres et d'exposition des contrats.")
produits = st.sidebar.multiselect("Produit", sorted(mens["produit"].unique()), default=sorted(mens["produit"].unique()))
zones = st.sidebar.multiselect("Zone de risque", sorted(mens["zone_risque"].unique()), default=sorted(mens["zone_risque"].unique()))
canaux = st.sidebar.multiselect("Canal de distribution", sorted(mens["canal"].unique()), default=sorted(mens["canal"].unique()))
st.sidebar.divider()
exclure = st.sidebar.checkbox(f"Exclure les {MOIS_IMMATURES} derniers mois", value=False,
                              help="Les sinistres récents ne sont pas encore tous déclarés ni payés : le ratio des derniers mois "
                                   "est sous-estimé. Décoché, les chiffres sont ceux du dossier.")
hors_exc = st.sidebar.checkbox("Hors sinistre exceptionnel (> 1 M€)", value=False,
                               help="Retire un dossier de 2,5 M€ (22 % du payé) qui fausse les moyennes. "
                                    "Décoché, les chiffres sont ceux du dossier. S'applique à la page Portefeuille.")

limite = dernier_mois - pd.DateOffset(months=MOIS_IMMATURES) if exclure else dernier_mois
fin_eff = min(fin, limite)
bandeau.markdown(f'<div class="bandeau">Boréal Assurances<span>Période choisie : {debut:%m/%Y} à {fin_eff:%m/%Y}</span></div>',
                 unsafe_allow_html=True)

mens_calc = mens.copy()
if hors_exc:
    mens_calc["paye"] = mens_calc["paye"] - mens_calc["paye_exceptionnel"]
    mens_calc["nb_sinistres"] = mens_calc["nb_sinistres"] - mens_calc["nb_exceptionnels"]
filtre_df = mens_calc[mens_calc["produit"].isin(produits) & mens_calc["zone_risque"].isin(zones) & mens_calc["canal"].isin(canaux)]
if filtre_df.empty:
    st.warning("Aucune donnée pour cette sélection.")
    st.stop()

periode = filtre_df[(filtre_df.mois >= debut) & (filtre_df.mois <= fin_eff)]
precedente = filtre_df[(filtre_df.mois >= debut - pd.DateOffset(years=1)) & (filtre_df.mois <= fin_eff - pd.DateOffset(years=1))]
if debut - pd.DateOffset(years=1) < mens["mois"].min():
    precedente = precedente.iloc[0:0]   # pas de données un an avant le début : aucune comparaison
k, k1 = somme(periode), somme(precedente)
immature_inclus = (not exclure) and fin_eff >= dernier_mois - pd.DateOffset(months=MOIS_IMMATURES - 1)

# =============================================================== PORTEFEUILLE
if page == "Portefeuille":
    st.title("Pilotage du portefeuille")
    st.caption(f"Données arrêtées au {fin_donnees:%d/%m/%Y}. Les écarts comparent à la même période un an plus tôt, quand elle existe.")
    if k["ratio"] > SEUIL:
        st.error(f"Alerte : ratio sinistres/primes de {pct(k['ratio'])}, au-dessus du seuil de {pct(SEUIL, 0)}.")
    else:
        st.success(f"Ratio sinistres/primes de {pct(k['ratio'])}, sous le seuil d'alerte de {pct(SEUIL, 0)}.")
    if immature_inclus:
        st.info(f"Les {MOIS_IMMATURES} derniers mois sont inclus mais incomplets : leur ratio est sous-estimé.")

    actifs = periode[periode.mois == periode.mois.max()].contrats_actifs.sum()
    actifs_n1 = precedente[precedente.mois == precedente.mois.max()].contrats_actifs.sum() if len(precedente) else float("nan")
    c = st.columns(3)
    c[0].metric("Primes acquises", eur(k["primes"]), delta_pct(k["primes"], k1["primes"]) if len(precedente) else None,
                help="Prime annuelle × années-police, sur la période.")
    c[1].metric("Contrats actifs", entier(actifs), delta_pct(actifs, actifs_n1),
                help="Contrats en vigueur le dernier mois de la période.")
    c[2].metric("Ratio sinistres/primes", pct(k["ratio"]),
                None if pd.isna(k1["ratio"]) else f"{(k['ratio'] - k1['ratio']) * 100:+.1f} pts".replace(".", ","),
                delta_color="inverse", help="Sinistres payés ÷ primes acquises. Plus il est bas, plus le portefeuille est rentable.")
    c = st.columns(3)
    c[0].metric("Fréquence", pct(k["frequence"], 2), delta_pct(k["frequence"], k1["frequence"]), delta_color="inverse",
                help="Sinistres retenus ÷ années-police.")
    c[1].metric("Coût moyen", eur(k["cout"]), delta_pct(k["cout"], k1["cout"]), delta_color="inverse",
                help="Montant payé ÷ sinistres retenus.")
    c[2].metric("Taux de résiliation", pct(k["resiliation"]), delta_pct(k["resiliation"], k1["resiliation"]), delta_color="inverse",
                help="Résiliations ÷ années-police.")

    s = serie_mensuelle(filtre_df)

    # Graphique 1 : évolution mensuelle comparée à l'année précédente
    st.subheader("Évolution mensuelle")
    noms = {"ratio": "Ratio sinistres/primes", "frequence": "Fréquence", "cout": "Coût moyen",
            "resiliation": "Taux de résiliation"}
    ind = st.selectbox("Indicateur", list(noms), format_func=noms.get)
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
        titre1 = (f"{mois_alerte} mois sur {len(cour)} dépassent le seuil de {SEUIL:.0%} : "
                  + ("identifier les mois et segments en cause" if mois_alerte else "aucun mois ne justifie une action tarifaire"))
    else:
        v1, v0 = cour.dropna(), prec.dropna()
        titre1 = (f"{noms[ind]} : {'en hausse' if v1.mean() > v0.mean() else 'en baisse'} vs l'année précédente sur la période"
                  if len(v1) and len(v0) else f"{noms[ind]} mensuel")
    graphique(f1, titre1)

    # Graphique 2 : marge technique par segment
    st.subheader("Où le portefeuille gagne ou perd de l'argent")
    axes_marge = {"Produit": ("produit", ""), "Zone de risque": ("zone_risque", "la zone "), "Canal": ("canal", "le canal ")}
    axe_m = st.selectbox("Segment", list(axes_marge), help="Marge technique = primes acquises − sinistres payés, sur la période choisie.")
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
        action = ("revoir sa tarification ou sa sélection des risques" if gm.ratio.iloc[0] > SEUIL
                  else "surveiller son ratio, il reste sous le seuil d'alerte")
        titre_m = (f"{prefixe.capitalize()}{haut} rapporte le plus ({meur(gm.marge.iloc[-1])}) et {prefixe}{bas} le moins "
                   f"({meur(gm.marge.iloc[0])}). Action : {action}")
    else:
        titre_m = "Marge technique par segment"
    graphique(fm2, titre_m, 260 + 40 * len(gm))

    # Graphique 3 : le levier qui bouge le plus vs N-1
    st.subheader("Ce qui fait bouger le ratio")
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
            titre_l = f"Le levier qui bouge le plus est {n_max} ({var_max * 100:+.0f} %), et il dégrade le ratio. Action : {action}"
        else:
            titre_l = f"Le levier qui bouge le plus est {n_max} ({var_max * 100:+.0f} %), et il améliore le ratio. Action : consolider cette tendance"
        graphique(fl2, titre_l.replace(".", ","), 300)
        st.caption(f"Comparaison : {comparaison}. Rouge = évolution défavorable au ratio, vert = favorable. "
                   "Ratio = fréquence × coût moyen ÷ prime moyenne.")
    else:
        st.info("Pas assez d'historique pour comparer cette sélection.")

# =============================================================== TECHNIQUE ET CLIENTS
elif page == "Technique et clients":
    st.title("Technique et clients")
    annees = range(debut.year, fin_eff.year + 1)
    b = base[base.annee.isin(annees) & base.produit.isin(produits) & base.zone_risque.isin(zones) & base.canal.isin(canaux)]
    st.caption("Les filtres s'appliquent aux années entières couvertes par la période. La décomposition porte sur le portefeuille entier ; "
               "les cohortes se filtrent par produit ; les clients ne dépendent ni de la zone ni du canal.")

    # Ratio par segment
    st.subheader("Ratio sinistres/primes par segment")
    axes = {"Zone de risque": "zone_risque", "Formule": "formule", "Canal": "canal", "Tranche d'âge": "tranche_age", "Produit": "produit"}
    axe = st.selectbox("Axe d'analyse", list(axes), help="Ratio = sinistres payés ÷ primes acquises, calculé sur la sélection.")
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
    titre = (f"{axe} : « {g.index[-1]} » est le segment le moins rentable ({pct(g.ratio.iloc[-1], 0)}), à surveiller en priorité"
             if len(g) else "Aucune donnée")
    graphique(fs, titre, 300 + 25 * len(g))

    # Décomposition
    st.subheader("Décomposition de l'évolution du ratio")
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
        titre = f"En {int(d.annee)}, le ratio varie de {d.variation_ratio * 100:+.0f} points, surtout à cause {moteur}".replace(".", ",")
    else:
        titre = "Décomposition du ratio"
    graphique(fd, titre, 380)

    # Rétention : matrice par cohorte
    st.subheader("Matrice de rétention par cohorte")
    coh = lire("retention_cohortes")
    coh = coh[coh["produit"].isin(produits)].groupby(["cohorte", "k"])[["contrats", "retenus"]].sum().reset_index()
    coh["retention"] = coh.retenus / coh.contrats
    mat = coh.pivot(index="cohorte", columns="k", values="retention")
    fh = go.Figure(go.Heatmap(z=mat.values * 100, x=[f"{int(c)} an(s)" for c in mat.columns], y=mat.index.astype(str),
                              colorscale="Blues", zmin=0, zmax=100, text=mat.apply(lambda col: col.map(lambda v: "" if pd.isna(v) else f"{v * 100:.0f} %")).values, texttemplate="%{text}",
                              hovertemplate="Cohorte %{y}<br>%{x} après souscription : %{z:.1f} % des contrats conservés<extra></extra>",
                              colorbar=dict(title="%")))
    fh.update_yaxes(autorange="reversed", title="Cohorte")
    pooled = coh.groupby("k")[["contrats", "retenus"]].sum()
    pooled = pooled.retenus / pooled.contrats
    titre = (f"Un contrat sur deux seulement est encore là après {int(pooled.index[-1])} ans : agir sur la rétention dès la 1re année"
             if len(pooled) and pooled.iloc[-1] < 0.6 else "Part des contrats conservés, par cohorte de souscription")
    graphique(fh, titre, 380)

    # Valeur client
    st.subheader("Concentration de la valeur client")
    vc0 = lire("valeur_client")
    tranches = st.multiselect("Tranche d'âge des clients", sorted(vc0.tranche_age.dropna().unique()),
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
            graphique(fv, f"10 % des clients font {pct(top10, 0)} de la valeur ; {entier(neg)} clients en détruisent : cibler la fidélisation sur les premiers", 400)
        v2.metric("Valeur totale", eur(vc.valeur.sum()), help="Primes acquises − sinistres payés, tous clients de la sélection.")
        v2.metric("Clients à valeur négative", entier(neg), help="Sinistres payés supérieurs aux primes acquises.")
        v2.metric("Perte cumulée de ces clients", eur(vc.loc[vc.valeur < 0, "valeur"].sum()))

# =============================================================== EXPLOITATION
elif page == "Exploitation":
    st.title("Exploitation de la chaîne de données")
    ex = lire("exploitation")
    ex["horodatage"] = pd.to_datetime(ex["horodatage"])
    ch, rg, ts = (ex[ex.rubrique == r] for r in ("CHARGEMENT", "REGLE", "TEST"))
    echecs = int((~ts.statut.isin({"OK", "PASS"})).sum())
    c = st.columns(4)
    c[0].metric("Fraîcheur des données", f"{pd.to_datetime(ex.derniere_date_donnee).max():%d/%m/%Y}",
                help="Date la plus récente présente dans les sources chargées.")
    c[1].metric("Dernier chargement", f"{ch.horodatage.max():%d/%m/%Y}")
    c[2].metric("Tests réussis", f"{len(ts) - echecs} / {len(ts)}", help="Tests des couches brute et cœur.")
    c[3].metric("Règles déclenchées", f"{int((rg.valeur > 0).sum())} / {len(rg)}",
                help="Règles de qualité qui ont détecté au moins une ligne anormale.")
    if echecs:
        st.error("Au moins un test échoue : ne pas diffuser les chiffres avant correction.")
    else:
        st.success("Tous les tests passent : les chiffres sont diffusables.")

    st.subheader("Dernier chargement par source")
    st.dataframe(ch[["element", "detail", "valeur", "statut", "horodatage"]].rename(
        columns={"element": "Source", "detail": "Fichiers", "valeur": "Lignes chargées", "statut": "Statut", "horodatage": "Chargé le"}),
        hide_index=True, width="stretch")

    st.subheader("Top 10 des règles avec le plus de lignes signalées ou rejetées")
    anom = rg[rg.valeur > 0].nlargest(10, "valeur").sort_values("valeur")
    libelles = anom.element + " · " + anom.detail.str.slice(0, 38)
    fr = go.Figure(go.Bar(x=anom.valeur, y=libelles, orientation="h", marker_color=BLEU, customdata=anom[["detail", "statut"]].values,
                          hovertemplate="%{y} : %{x:,.0f} lignes<br>%{customdata[0]}<br>Traitement : %{customdata[1]}<extra></extra>"))
    if len(anom):
        top = anom.iloc[-1]
        titre = f"{top.element} concentre le plus de lignes concernées ({entier(top.valeur)}) : traiter cette anomalie à la source en priorité"
    else:
        titre = "Aucune ligne rejetée"
    graphique(fr, titre, 300 + 26 * len(anom))

    st.subheader("Détail de toutes les règles appliquées")
    st.dataframe(rg[["element", "detail", "valeur", "statut"]].rename(
        columns={"element": "Règle", "detail": "Description", "valeur": "Lignes signalées ou rejetées", "statut": "Gravité / traitement"}),
        hide_index=True, width="stretch")

    st.subheader("Résultats des tests")
    st.dataframe(ts[["element", "detail", "statut", "horodatage"]].rename(
        columns={"element": "Test", "detail": "Description", "statut": "Résultat", "horodatage": "Exécuté le"}),
        hide_index=True, width="stretch")

    st.subheader("Délais de gestion des sinistres par garantie")
    dl = lire("delais_sinistres")
    dl = dl[dl["produit"].isin(produits)]
    etapes = {"delai_declaration": "Survenance → déclaration", "delai_premier_reglement": "Déclaration → 1er règlement",
              "delai_cloture": "Déclaration → clôture (dernier règlement)"}
    etape = st.selectbox("Étape", list(etapes), index=1, format_func=etapes.get)
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

# =============================================================== DÉFINITIONS
else:
    st.title("Définitions des indicateurs")
    st.markdown(f"""
| Indicateur | Définition |
|---|---|
| **Années-police** | Jours de couverture d'un contrat dans l'année ÷ nombre de jours de l'année. Un contrat couvert toute l'année vaut 1. |
| **Primes acquises** | Prime annuelle × années-police. |
| **Contrats actifs** | Contrats en vigueur le dernier mois de la période. |
| **Sinistres retenus** | Dossiers au statut OUVERT ou CLOTURE. Les rejetés et sans suite sont exclus. |
| **Montant payé** | Somme des règlements des sinistres retenus, rattachés au mois de survenance. |
| **Fréquence** | Sinistres retenus ÷ années-police. |
| **Coût moyen** | Montant payé ÷ sinistres retenus. |
| **Prime moyenne** | Primes acquises ÷ années-police. |
| **Ratio sinistres/primes** | Montant payé ÷ primes acquises. Alerte au-dessus de {SEUIL:.0%}. Il vaut fréquence × coût moyen ÷ prime moyenne. |
| **Taux de résiliation** | Résiliations ÷ années-police. |
| **Marge technique** | Primes acquises − sinistres payés, avant frais de gestion et commissions. |
| **Décomposition du ratio** | Part de la variation annuelle du ratio due à la fréquence, au coût moyen et à la prime moyenne, en points de ratio. |
| **Rétention** | Part des contrats d'une cohorte encore en vigueur au 31/12, k années après la souscription. |
| **Valeur client** | Primes acquises − sinistres payés du client, sur la période. |
| **Délai de clôture** | Date du dernier règlement − date de déclaration, pour les dossiers clôturés (approximation). |

**Seuil d'alerte de 70 %** : c'est une hypothèse de travail. Les sources ne contiennent ni frais de gestion ni commissions. En assurance dommages, ces frais
représentent généralement 25 à 30 % des primes : quand les sinistres dépassent 70 % des primes, le résultat technique tombe autour de l'équilibre,
puis devient négatif. Le portefeuille (56 %) laisse environ 44 points pour couvrir ces frais.

**Mois immatures** : les {MOIS_IMMATURES} derniers mois sont incomplets (sinistres non encore déclarés ni payés). Leur ratio est sous-estimé.
L'option du menu de gauche permet de les exclure ; décochée, les chiffres sont ceux du dossier.

**Sinistre exceptionnel** : un dossier de plus de 1 M€ (2,5 M€, 22 % du payé total). L'option « hors sinistre exceptionnel » le retire pour lire la tendance sous-jacente.

**Périmètre** : 51 contrats en quarantaine (prime nulle ou date de résiliation incohérente) sont exclus de tous les indicateurs.
Données arrêtées au {fin_donnees:%d/%m/%Y}.
""")