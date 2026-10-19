-- Dimension contrat : tous les contrats sont conservés pour garder l'intégrité avec les sinistres.
-- Les contrats mis en quarantaine (règles Q08 et Q19) sont repérés par un indicateur et un motif.
create or replace table core.dim_contrat as
select
    c.contrat_id,
    p.client_id_survivant as client_id,
    s.segment_id,
    c.produit,
    c.formule,
    c.canal_distribution,
    c.date_effet,
    c.date_resiliation,
    c.franchise,
    c.prime_annuelle,
    q.cle is not null as en_quarantaine,
    q.motif as motif_quarantaine
from prep.contrats c
join core.pont_client_survivant p on p.client_id = c.client_id
join core.dim_segment_risque s
  on s.produit = c.produit and s.zone_risque = c.zone_risque
 and s.classe_risque = case
        when c.produit = 'AUTO' and c.bonus_malus < 0.8 then 'Bonus fort'
        when c.produit = 'AUTO' and c.bonus_malus < 1 then 'Bonus'
        when c.produit = 'AUTO' then 'Malus'
        when c.surface_m2 < 60 then 'Petite surface'
        when c.surface_m2 < 100 then 'Surface moyenne'
        else 'Grande surface' end
left join qualite.quarantaine q
  on q.table_source = 'prep.contrats' and q.cle = c.contrat_id::varchar;
