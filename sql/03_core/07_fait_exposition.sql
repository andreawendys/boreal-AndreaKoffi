-- Fait exposition. Grain : un contrat par année civile couverte.
-- Exposition en années-police = jours couverts / nombre de jours de l'année civile (365 ou 366),
-- bornée à la date d'extraction (30/06/2025). Une année entière couverte vaut donc exactement 1.
create or replace table core.fait_exposition as
with bornes as (
    select
        c.contrat_id,
        y.annee,
        greatest(c.date_effet, make_date(y.annee, 1, 1)) as date_debut,
        least(coalesce(c.date_resiliation, date '2025-06-30'), date '2025-06-30',
              make_date(y.annee, 12, 31)) as date_fin,
        c.prime_annuelle
    from core.dim_contrat c
    cross join (select distinct annee from core.dim_date) y
    where not c.en_quarantaine
)
select
    contrat_id,
    annee,
    date_debut,
    date_fin,
    date_diff('day', date_debut, date_fin) + 1 as jours_couverture,
    (date_diff('day', date_debut, date_fin) + 1)
        / (date_diff('day', make_date(annee, 1, 1), make_date(annee, 12, 31)) + 1) as annees_police,
    prime_annuelle * (date_diff('day', date_debut, date_fin) + 1)
        / (date_diff('day', make_date(annee, 1, 1), make_date(annee, 12, 31)) + 1) as prime_acquise
from bornes
where date_fin >= date_debut;
