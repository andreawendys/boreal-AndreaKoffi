-- Livrable 3, indicateurs techniques : un tableau par axe d'analyse, toutes années confondues.
-- Chaque indicateur est calculé en sommant la base puis en divisant (jamais en moyennant des ratios).
create or replace table marts.indicateurs as
with axes as (
    select 'Portefeuille' as axe, 'Ensemble' as modalite, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
    union all select 'Produit', produit, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
    union all select 'Zone de risque', zone_risque::varchar, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
    union all select 'Formule', formule, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
    union all select 'Canal', canal, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
    union all select 'Tranche d''âge', tranche_age, * exclude (annee, produit, zone_risque, formule, canal, tranche_age) from marts.base_technique
)
select
    axe,
    modalite,
    sum(annees_police) as annees_police,
    sum(nb_sinistres) as nb_sinistres,
    sum(nb_sinistres) / sum(annees_police) as frequence,
    sum(paye) / sum(nb_sinistres) as cout_moyen,
    sum(prime_acquise) / sum(annees_police) as prime_moyenne,
    sum(paye) / sum(prime_acquise) as ratio_paye,
    (sum(paye) + sum(reserve_restante)) / sum(prime_acquise) as ratio_avec_reserve,
    sum(nb_resiliations) / sum(annees_police) as taux_resiliation,
    sum(reserve_restante) as reserve_restante,
    sum(nb_sans_suite) as nb_sans_suite,
    sum(nb_rejetes) as nb_rejetes
from axes
group by axe, modalite;