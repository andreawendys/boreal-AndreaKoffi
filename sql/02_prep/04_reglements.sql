-- Préparation des règlements : typage et fusion des deux libellés de montant.
-- coalesce prend la première valeur non vide : montant (63 fichiers) ou montant_eur (mars 2024).
-- Les paiements en double sont conservés ici : ils sont traités par les règles de qualité.
create or replace table prep.reglements as
select
    cast(paiement_id as integer)    as paiement_id,
    cast(sinistre_id as integer)    as sinistre_id,
    try_cast(date_paiement as date) as date_paiement,
    coalesce(try_cast(montant as double), try_cast(montant_eur as double)) as montant,
    _source_file,
    _loaded_at
from raw.reglements;