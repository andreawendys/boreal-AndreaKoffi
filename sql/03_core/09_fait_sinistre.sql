-- Fait sinistre. Grain : un sinistre.
-- Les sinistres de contrats mis en quarantaine sont gardés et repérés par contrat_en_quarantaine.
create or replace table core.fait_sinistre as
select
    s.sinistre_id,
    s.contrat_id,
    g.garantie_id,
    s.date_survenance,
    s.date_declaration,
    s.statut,
    s.reserve_initiale,
    coalesce(r.montant_regle, 0) as montant_regle,
    coalesce(r.nb_reglements, 0) as nb_reglements,
    a.fraude_confirmee,
    c.en_quarantaine as contrat_en_quarantaine
from prep.sinistres s
join core.dim_contrat c using (contrat_id)
join core.dim_garantie g on g.produit = c.produit and g.garantie = s.garantie
left join (select sinistre_id, sum(montant) as montant_regle, count(*) as nb_reglements
           from core.fait_reglement group by sinistre_id) r using (sinistre_id)
left join prep.audits a using (sinistre_id);
