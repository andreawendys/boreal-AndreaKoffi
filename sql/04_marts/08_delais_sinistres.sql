-- Délais de gestion par sinistre (en jours).
-- Combien de jours prennent la déclaration, le premier règlement et la clôture ?

create or replace table marts.delais_sinistres as
with paiements as (
    select sinistre_id, min(date_paiement) as premier, max(date_paiement) as dernier
    from core.fait_reglement
    group by 1
)
select s.sinistre_id, g.produit, g.garantie, s.statut,
       case when s.date_declaration >= s.date_survenance
            then date_diff('day', s.date_survenance, s.date_declaration) end as delai_declaration,
       date_diff('day', s.date_declaration, p.premier) as delai_premier_reglement,
       case when s.statut = 'CLOTURE' then date_diff('day', s.date_declaration, p.dernier) end as delai_cloture
from core.fait_sinistre s
join core.dim_garantie g on g.garantie_id = s.garantie_id
left join paiements p on p.sinistre_id = s.sinistre_id
where not s.contrat_en_quarantaine;