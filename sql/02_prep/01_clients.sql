-- Préparation des clients : typage et conversion des dates. Aucune ligne n'est supprimée ici.
create or replace table prep.clients as
select
    cast(client_id as integer)                     as client_id,
    try_strptime(date_naissance, '%d/%m/%Y')::date as date_naissance,
    region,
    csp,
    cast(consent_marketing as integer) = 1         as consent_marketing,
    email_hash,
    _source_file,
    _loaded_at
from raw.clients;