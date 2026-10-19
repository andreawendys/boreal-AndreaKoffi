-- Préparation des sinistres : typage. Aucune ligne n'est supprimée ici.
create or replace table prep.sinistres as
select
    cast(sinistre_id as integer)          as sinistre_id,
    cast(contrat_id as integer)           as contrat_id,
    try_cast(date_survenance as date)     as date_survenance,
    try_cast(date_declaration as date)    as date_declaration,
    garantie,
    statut,
    try_cast(reserve_initiale as double)  as reserve_initiale,
    _source_file,
    _loaded_at
from raw.sinistres;