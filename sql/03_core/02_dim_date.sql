-- Dimension date : un jour par ligne, de la première date d'effet à la date d'extraction.
create or replace table core.dim_date as
select
    d::date as date_jour,
    year(d) as annee,
    quarter(d) as trimestre,
    month(d) as mois,
    strftime(d, '%Y-%m') as annee_mois,
    isodow(d) as jour_semaine
from generate_series(date '2020-01-01', date '2025-06-30', interval 1 day) as t(d);
