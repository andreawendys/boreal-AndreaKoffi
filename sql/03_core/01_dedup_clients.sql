-- Déduplication des clients.
-- Clé de rapprochement : email_hash (empreinte de l'adresse e-mail), seul identifiant stable et renseigné.
-- Règle de survie : on conserve le plus petit client_id du groupe ; les autres sont rattachés à lui.
create or replace table core.pont_client_survivant as
select
    client_id,
    min(client_id) over (partition by email_hash) as client_id_survivant,
    email_hash,
    client_id <> min(client_id) over (partition by email_hash) as est_doublon
from prep.clients;
