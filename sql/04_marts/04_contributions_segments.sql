-- Livrable 3, décomposition : contribution de chaque segment à la variation annuelle du ratio.
-- Contribution = charge du segment / primes du portefeuille, variation d'une année à l'autre.
create or replace table marts.contributions_segments as
with axes as (
    select annee, 'Produit' as axe, produit as modalite, paye, prime_acquise from marts.base_technique
    union all select annee, 'Zone de risque', zone_risque::varchar, paye, prime_acquise from marts.base_technique
    union all select annee, 'Formule', formule, paye, prime_acquise from marts.base_technique
    union all select annee, 'Canal', canal, paye, prime_acquise from marts.base_technique
    union all select annee, 'Tranche d''âge', tranche_age, paye, prime_acquise from marts.base_technique
),
par_segment as (
    select annee, axe, modalite, sum(paye) as paye, sum(prime_acquise) as prime_acquise
    from axes group by all
),
primes_totales as (
    select annee, sum(prime_acquise) as prime_totale from marts.base_technique group by annee
),
poids as (
    select s.*, s.paye / t.prime_totale as part_ratio
    from par_segment s join primes_totales t using (annee)
)
select
    annee, axe, modalite,
    part_ratio,
    part_ratio - lag(part_ratio) over (partition by axe, modalite order by annee) as contribution
from poids;