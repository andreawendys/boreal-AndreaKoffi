-- Préparation des contrats : typage. Aucune ligne n'est supprimée ici.
-- try_cast donne NULL si la valeur est illisible, au lieu de faire échouer la requête.
create or replace table prep.contrats as
select
    cast(contrat_id as integer)          as contrat_id,
    cast(client_id as integer)           as client_id,
    produit,
    try_cast(date_effet as date)         as date_effet,
    try_cast(date_resiliation as date)   as date_resiliation,
    formule,
    canal_distribution,
    cast(zone_risque as integer)         as zone_risque,
    try_cast(franchise as double)        as franchise,
    try_cast(bonus_malus as double)      as bonus_malus,
    try_cast(puissance_cv as double)     as puissance_cv,
    try_cast(surface_m2 as double)       as surface_m2,
    try_cast(prime_annuelle as double)   as prime_annuelle,
    _source_file,
    _loaded_at
from raw.contrats;