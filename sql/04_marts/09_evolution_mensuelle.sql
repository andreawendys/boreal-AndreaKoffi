-- Évolution mensuelle du portefeuille (alimente le dashboard).
create or replace table marts.evolution_mensuelle as
with mois as (
    select m::date as debut, (m + interval 1 month - interval 1 day)::date as fin
    from generate_series(date '2020-01-01', date '2025-06-01', interval 1 month) as t(m)
),
expo as (
    select m.debut as mois, m.fin as fin_mois, e.date_debut, e.date_fin, c.prime_annuelle,
           date_diff('day', greatest(e.date_debut, m.debut), least(e.date_fin, m.fin)) + 1 as jours
    from core.fait_exposition e
    join mois m on year(m.debut) = e.annee and e.date_debut <= m.fin and e.date_fin >= m.debut
    join core.dim_contrat c on c.contrat_id = e.contrat_id
),
expo_mois as (
    select mois,
           count(*) filter (where date_debut <= fin_mois and date_fin >= fin_mois) as contrats_actifs,
           sum(cast(jours as double) / date_diff('day', make_date(year(mois), 1, 1), make_date(year(mois) + 1, 1, 1))) as annees_police,
           sum(prime_annuelle * jours / date_diff('day', make_date(year(mois), 1, 1), make_date(year(mois) + 1, 1, 1))) as primes_acquises
    from expo
    group by 1
),
sin as (
    select date_trunc('month', s.date_survenance)::date as mois,
           count(*) as nb_sinistres, sum(coalesce(s.montant_regle, 0)) as paye
    from core.fait_sinistre s
    where s.statut in ('OUVERT', 'CLOTURE') and not s.contrat_en_quarantaine
      and exists (select 1 from core.fait_exposition e
                  where e.contrat_id = s.contrat_id and e.annee = year(s.date_survenance))
    group by 1
),
res as (
    select date_trunc('month', date_resiliation)::date as mois, count(*) as nb_resiliations
    from core.dim_contrat
    where not en_quarantaine and date_resiliation <= date '2025-06-30'
    group by 1
),
base as (
    select e.mois, year(e.mois) as annee, month(e.mois) as mois_num,
           e.contrats_actifs, e.annees_police, e.primes_acquises,
           coalesce(s.nb_sinistres, 0) as nb_sinistres, coalesce(s.paye, 0) as paye,
           coalesce(r.nb_resiliations, 0) as nb_resiliations
    from expo_mois e
    left join sin s on s.mois = e.mois
    left join res r on r.mois = e.mois
),
ind as (
    select *,
           nb_sinistres / annees_police as frequence,
           paye / nullif(nb_sinistres, 0) as cout_moyen,
           primes_acquises / annees_police as prime_moyenne,
           paye / primes_acquises as ratio_sp,
           nb_resiliations / annees_police as taux_resiliation
    from base
)
select *,
       lag(primes_acquises, 12) over (order by mois) as primes_acquises_n1,
       lag(frequence, 12) over (order by mois) as frequence_n1,
       lag(cout_moyen, 12) over (order by mois) as cout_moyen_n1,
       lag(prime_moyenne, 12) over (order by mois) as prime_moyenne_n1,
       lag(ratio_sp, 12) over (order by mois) as ratio_sp_n1,
       lag(taux_resiliation, 12) over (order by mois) as taux_resiliation_n1
from ind
order by mois;