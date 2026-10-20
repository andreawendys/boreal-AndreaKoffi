-- -- Livrable 3, indicateurs techniques : base technique du portefeuille.
-- Grain : année × produit × zone × formule × canal × tranche d'âge.
-- Les sinistres sont rattachés à leur année de survenance.
--  les autres (contrat en quarantaine, sinistre hors période de couverture) sont écartés de la base.
create or replace table marts.base_technique as
with exposition as (
    select
        e.annee,
        e.contrat_id,
        c.produit,
        s.zone_risque,
        c.formule,
        c.canal_distribution as canal,
        cl.tranche_age,
        e.annees_police,
        e.prime_acquise,
        (year(c.date_resiliation) = e.annee and c.date_resiliation <= date '2025-06-30')::int as resilie
    from core.fait_exposition e
    join core.dim_contrat c using (contrat_id)
    join core.dim_segment_risque s using (segment_id)
    join core.dim_client cl using (client_id)
),
sinistres as (
    select
        year(date_survenance) as annee,
        contrat_id,
        count(*) filter (where statut in ('OUVERT', 'CLOTURE')) as nb_retenus,
        count(*) filter (where statut = 'SANS_SUITE') as nb_sans_suite,
        count(*) filter (where statut = 'REJETE') as nb_rejetes,
        coalesce(sum(montant_regle), 0) as paye,
        coalesce(sum(greatest(reserve_initiale - montant_regle, 0)) filter (where statut = 'OUVERT'), 0) as reserve_restante
    from core.fait_sinistre
    where not contrat_en_quarantaine
    group by 1, 2
)
select
    e.annee, e.produit, e.zone_risque, e.formule, e.canal, e.tranche_age,
    count(*) as nb_contrats,
    sum(e.annees_police) as annees_police,
    sum(e.prime_acquise) as prime_acquise,
    sum(e.resilie) as nb_resiliations,
    coalesce(sum(s.nb_retenus), 0) as nb_sinistres,
    coalesce(sum(s.nb_sans_suite), 0) as nb_sans_suite,
    coalesce(sum(s.nb_rejetes), 0) as nb_rejetes,
    coalesce(sum(s.paye), 0) as paye,
    coalesce(sum(s.reserve_restante), 0) as reserve_restante
from exposition e
left join sinistres s on s.contrat_id = e.contrat_id and s.annee = e.annee
group by all;