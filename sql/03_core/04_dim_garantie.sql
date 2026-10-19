-- Dimension garantie : une ligne par couple (produit, garantie), car VOL existe en auto et en habitation.
create or replace table core.dim_garantie as
select
    row_number() over (order by produit, garantie) as garantie_id,
    produit,
    garantie
from (select distinct c.produit, s.garantie
      from prep.sinistres s join prep.contrats c using (contrat_id));
