-- Rétention selon le statut de détention (multi ou mono) à la fin de l'année du premier contrat du client.
create or replace table marts.retention_multidetention as
with contrats as (
    select client_id, contrat_id, produit, year(date_effet) as annee, date_effet, date_resiliation
    from core.dim_contrat
    where not en_quarantaine
),
premiers as (
    select client_id, min(annee) as cohorte
    from contrats
    group by 1
    having min(annee) <= 2024
),
statut as (
    select c.client_id, p.cohorte,
           case when count(distinct c.produit) = 2 then 'MULTI' else 'MONO' end as statut
    from contrats c
    join premiers p on p.client_id = c.client_id and c.annee = p.cohorte
    group by 1, 2
),
annees as (select unnest(range(0, 5)) as k),
suivi_client as (
    select s.statut, s.cohorte, a.k,
           exists (select 1 from contrats c
                   where c.client_id = s.client_id
                     and c.date_effet <= make_date(s.cohorte + a.k, 12, 31)
                     and (c.date_resiliation is null
                          or c.date_resiliation > make_date(s.cohorte + a.k, 12, 31))) as ok
    from statut s
    cross join annees a
    where s.cohorte + a.k <= 2024
),
suivi_contrat as (
    select s.statut, s.cohorte, a.k,
           (c.date_resiliation is null
            or c.date_resiliation > make_date(s.cohorte + a.k, 12, 31)) as ok
    from contrats c
    join statut s on s.client_id = c.client_id and c.annee = s.cohorte
    cross join annees a
    where s.cohorte + a.k <= 2024
)
select 'CLIENT' as niveau, statut, cohorte, k,
       count(*) as effectif,
       count(*) filter (where ok) as retenus,
       round(100.0 * count(*) filter (where ok) / count(*), 1) as retention_pct
from suivi_client
group by statut, cohorte, k
union all
select 'CONTRAT', statut, cohorte, k,
       count(*),
       count(*) filter (where ok),
       round(100.0 * count(*) filter (where ok) / count(*), 1)
from suivi_contrat
group by statut, cohorte, k
order by 1, 2, 3, 4;