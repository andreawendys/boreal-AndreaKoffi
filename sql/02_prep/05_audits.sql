-- Préparation des audits : typage. Aucune ligne n'est supprimée ici.
create or replace table prep.audits as
select
    cast(sinistre_id as integer)          as sinistre_id,
    try_cast(date_audit as date)          as date_audit,
    cast(fraude_confirmee as integer) = 1 as fraude_confirmee,
    _source_file,
    _loaded_at
from raw.audits;