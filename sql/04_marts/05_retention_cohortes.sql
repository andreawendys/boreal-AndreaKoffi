-- Rétention des contrats par cohorte annuelle de souscription et par produit.
create or replace table marts.retention_cohortes as
with contrats as (
    select contrat_id, produit, year(date_effet) as cohorte, date_resiliation
    from core.dim_contrat
    where not en_quarantaine and year(date_effet) <= 2024
),
grille as (
    select c.*, a.k, make_date(c.cohorte + a.k, 12, 31) as fin_annee
    from contrats c
    cross join (select unnest(range(0, 5)) as k) a
    where c.cohorte + a.k <= 2024
)
select cohorte, produit, k,
       count(*) as contrats,
       count(*) filter (where date_resiliation is null or date_resiliation > fin_annee) as retenus,
       round(100.0 * count(*) filter (where date_resiliation is null or date_resiliation > fin_annee)
             / count(*), 1) as retention_pct
from grille
group by all
order by produit, cohorte, k;