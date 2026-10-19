-- Dimension client : survivants uniquement (type 1, voir la justification dans le rapport).
create or replace table core.dim_client as
select
    c.client_id,
    c.date_naissance,
    date_diff('year', c.date_naissance, date '2025-06-30') as age,
    case
        when c.date_naissance is null then 'Inconnu'
        when date_diff('year', c.date_naissance, date '2025-06-30') < 25 then '< 25 ans'
        when date_diff('year', c.date_naissance, date '2025-06-30') < 40 then '25-39 ans'
        when date_diff('year', c.date_naissance, date '2025-06-30') < 60 then '40-59 ans'
        else '60 ans et +'
    end as tranche_age,
    c.region,
    c.csp,
    c.consent_marketing
from prep.clients c
join core.pont_client_survivant p using (client_id)
where not p.est_doublon;
