-- Livrable 3, décomposition : évolution annuelle du ratio sinistres/primes.
-- Ratio = fréquence × coût moyen / prime moyenne ; variation répartie par moyennes logarithmiques.
create or replace table marts.evolution_annuelle as
with annuel as (
    select
        annee,
        sum(annees_police) as expo,
        sum(nb_sinistres) as n,
        sum(paye) as s,
        sum(reserve_restante) as reserve,
        sum(prime_acquise) as p
    from marts.base_technique
    group by annee
),
exceptionnels as (
    -- Sinistres exceptionnels : plus d'un million d'euros payés.
    select year(f.date_survenance) as annee, sum(f.montant_regle) as s_exc, count(*) as n_exc
    from core.fait_sinistre f
    where f.montant_regle > 1000000 and f.statut in ('OUVERT', 'CLOTURE') and not f.contrat_en_quarantaine
    group by 1
),
ouverts as (
    select year(date_survenance) as annee,
           count(*) filter (where statut = 'OUVERT') as nb_ouverts,
           count(*) filter (where statut in ('OUVERT', 'CLOTURE')) as nb_retenus
    from core.fait_sinistre where not contrat_en_quarantaine group by 1
),
ratios as (
    select
        a.annee, a.expo, a.n, a.s, a.p, a.reserve,
        a.n / a.expo as frequence,
        a.s / a.n as cout_moyen,
        a.p / a.expo as prime_moyenne,
        a.s / a.p as ratio,
        (a.s + a.reserve) / a.p as ratio_avec_reserve,
        (a.s - coalesce(e.s_exc, 0)) / a.p as ratio_hors_exceptionnel,
        o.nb_ouverts::double / o.nb_retenus as part_dossiers_ouverts,
        a.annee = 2025 as annee_incomplete
    from annuel a
    left join exceptionnels e using (annee)
    left join ouverts o using (annee)
),
avec_precedent as (
    select *,
        lag(expo) over w as expo_prec, lag(frequence) over w as frequence_prec,
        lag(cout_moyen) over w as cout_prec, lag(prime_moyenne) over w as prime_prec,
        lag(ratio) over w as ratio_prec, lag(s) over w as s_prec, lag(p) over w as p_prec
    from ratios
    window w as (order by annee)
),
poids as (
    select *,
        -- Moyennes logarithmiques, poids de la décomposition.
        case when ratio = ratio_prec then ratio else (ratio - ratio_prec) / ln(ratio / ratio_prec) end as l_ratio,
        case when s = s_prec then s else (s - s_prec) / ln(s / s_prec) end as l_s,
        case when p = p_prec then p else (p - p_prec) / ln(p / p_prec) end as l_p
    from avec_precedent
)
select
    annee, annee_incomplete, expo as annees_police, n as nb_sinistres, s as paye, p as prime_acquise,
    frequence, cout_moyen, prime_moyenne, ratio, ratio_avec_reserve, ratio_hors_exceptionnel, part_dossiers_ouverts,
    ratio - ratio_prec as variation_ratio,
    l_ratio * ln(frequence / frequence_prec) as effet_frequence,
    l_ratio * ln(cout_moyen / cout_prec) as effet_cout,
    -l_ratio * ln(prime_moyenne / prime_prec) as effet_prime,
    s - s_prec as variation_sinistres,
    l_s * ln(expo / expo_prec) as sinistres_effet_volume,
    l_s * ln(frequence / frequence_prec) as sinistres_effet_frequence,
    l_s * ln(cout_moyen / cout_prec) as sinistres_effet_cout,
    p - p_prec as variation_primes,
    l_p * ln(expo / expo_prec) as primes_effet_volume,
    l_p * ln(prime_moyenne / prime_prec) as primes_effet_prime
from poids;