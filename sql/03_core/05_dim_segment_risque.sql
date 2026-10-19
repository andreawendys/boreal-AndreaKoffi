-- Dimension segment de risque : produit, classe de risque propre au produit et zone de risque.
-- Auto : classe selon le bonus-malus. Habitation : classe selon la surface.
create or replace table core.dim_segment_risque as
with classes as (
    select distinct
        produit,
        zone_risque,
        case
            when produit = 'AUTO' and bonus_malus < 0.8 then 'Bonus fort'
            when produit = 'AUTO' and bonus_malus < 1 then 'Bonus'
            when produit = 'AUTO' then 'Malus'
            when surface_m2 < 60 then 'Petite surface'
            when surface_m2 < 100 then 'Surface moyenne'
            else 'Grande surface'
        end as classe_risque
    from prep.contrats
)
select row_number() over (order by produit, classe_risque, zone_risque) as segment_id,
       produit, classe_risque, zone_risque
from classes;
