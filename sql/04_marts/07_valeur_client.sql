-- Valeur observée par client : primes acquises moins sinistres payés.
create or replace table marts.valeur_client as
with primes as (
    select c.client_id,
           count(distinct e.contrat_id) as nb_contrats,
           count(distinct c.produit) as nb_produits,
           sum(e.annees_police) as annees_police,
           sum(e.prime_acquise) as primes_acquises
    from core.fait_exposition e
    join core.dim_contrat c on c.contrat_id = e.contrat_id
    group by 1
),
sinistres as (
    select c.client_id, count(*) as nb_sinistres, sum(coalesce(s.montant_regle, 0)) as paye
    from core.fait_sinistre s
    join core.dim_contrat c on c.contrat_id = s.contrat_id
    where s.statut in ('OUVERT', 'CLOTURE') and not s.contrat_en_quarantaine
    group by 1
)
select p.client_id, d.tranche_age, d.region, d.csp,
       p.nb_contrats, p.nb_produits, p.annees_police, p.primes_acquises,
       coalesce(s.nb_sinistres, 0) as nb_sinistres,
       coalesce(s.paye, 0) as paye,
       p.primes_acquises - coalesce(s.paye, 0) as valeur
from primes p
join core.dim_client d on d.client_id = p.client_id
left join sinistres s on s.client_id = p.client_id;