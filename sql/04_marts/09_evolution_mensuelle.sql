-- Livrable 5 : évolution mensuelle du portefeuille, alimentation du dashboard.
-- Quelle est la situation mois par mois, par produit, zone et canal ?

create or replace table marts.evolution_mensuelle as
with mois as (
    select m::date as debut, last_day(m::date) as fin
    from generate_series(date '2020-01-01', date '2025-06-01', interval 1 month) t(m)
),
exposition as (
    select
        mo.debut as mois,
        c.produit,
        s.zone_risque,
        c.canal_distribution as canal,
        c.contrat_id,
        greatest(date_diff('day', greatest(c.date_effet, mo.debut),
                 least(coalesce(c.date_resiliation, date '2025-06-30'), date '2025-06-30', mo.fin)) + 1, 0) as jours,
        date_diff('day', make_date(year(mo.debut), 1, 1), make_date(year(mo.debut), 12, 31)) + 1 as jours_annee,
        c.prime_annuelle,
        (c.date_resiliation between mo.debut and least(mo.fin, date '2025-06-30'))::int as resilie
    from mois mo
    cross join core.dim_contrat c
    join core.dim_segment_risque s using (segment_id)
    where not c.en_quarantaine
),
expo as (
    select
        mois, produit, zone_risque, canal,
        count(*) filter (where jours > 0) as contrats_actifs,
        sum(jours / jours_annee) as annees_police,
        sum(prime_annuelle * jours / jours_annee) as prime_acquise,
        sum(resilie) as nb_resiliations
    from exposition
    group by all
),
sin as (
    select
        date_trunc('month', f.date_survenance)::date as mois,
        c.produit, s.zone_risque, c.canal_distribution as canal,
        count(*) as nb_sinistres,
        sum(f.montant_regle) as paye,
        count(*) filter (where f.montant_regle > 1000000) as nb_exceptionnels,
        sum(f.montant_regle) filter (where f.montant_regle > 1000000) as paye_exceptionnel,
        sum(greatest(f.reserve_initiale - f.montant_regle, 0)) filter (where f.statut = 'OUVERT') as reserve_restante
    from core.fait_sinistre f
    join core.dim_contrat c using (contrat_id)
    join core.dim_segment_risque s using (segment_id)
    -- comme la base technique : seuls les sinistres d'une année où le contrat a une exposition
    join core.fait_exposition x on x.contrat_id = f.contrat_id and x.annee = year(f.date_survenance)
    where not f.contrat_en_quarantaine and f.statut in ('OUVERT', 'CLOTURE')
    group by all
)
select
    e.mois, year(e.mois) as annee, month(e.mois) as mois_num,
    e.produit, e.zone_risque, e.canal,
    e.contrats_actifs, e.annees_police, e.prime_acquise, e.nb_resiliations,
    coalesce(s.nb_sinistres, 0) as nb_sinistres,
    coalesce(s.paye, 0) as paye,
    coalesce(s.nb_exceptionnels, 0) as nb_exceptionnels,
    coalesce(s.paye_exceptionnel, 0) as paye_exceptionnel,
    coalesce(s.reserve_restante, 0) as reserve_restante
from expo e
left join sin s using (mois, produit, zone_risque, canal);