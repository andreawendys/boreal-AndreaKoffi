-- Fait règlement. Grain : un paiement.
-- Les copies de paiements rejouées dans un autre mois (règle Q07) sont exclues et restent en quarantaine.
create or replace table core.fait_reglement as
select
    r.paiement_id,
    r.sinistre_id,
    r.date_paiement,
    r.montant,
    r._source_file
from prep.reglements r
where not exists (
    select 1 from qualite.quarantaine q
    where q.regle_id = 'Q07'
      and q.cle = r.paiement_id::varchar
      and q.detail = r._source_file
);
