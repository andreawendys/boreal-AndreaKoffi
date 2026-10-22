# Boréal Assurances : Construire la chaîne de données et analyse du portefeuille IARD

Nous avons réalisé un pipeline en couches (brut, préparation, cœur, marts) sur DuckDB, orchestré en Python, avec un dashboard Streamlit.

## Exécution en 5 commandes (PowerShell, depuis la racine du dépôt)

Prérequis : Python 3.10+ ; les fichiers sources du sujet sont dans `data/sources`.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python pipeline/run_all.py
streamlit run app.py
```

La commande 4 enchaîne : chargement des sources (brut), tests du brut, préparation, contrôles de qualité, cœur,tests du cœur, marts. Un test en échec interrompt la chaîne et déclenche une alerte.
Fermer le dashboard avant de relancer le pipeline : DuckDB n'autorise pas l'écriture pendant qu'il lit.

## Recharger un mois

```powershell
python pipeline/run_all.py --mois 2025_07
```

Rejouable sans doublon : les lignes du fichier sont remplacées, jamais ajoutées en double.
Un fichier déjà chargé avec la même empreinte est ignoré.

## Exécution mensuelle déclenchée par l'arrivée d'un fichier

`pipeline/declencheur.py` compare les fichiers `reglements_AAAA_MM.csv` de `data/sources` à ceux déjà chargés dans `raw.reglements`. Pour chaque nouveau fichier, il lance la chaîne complète pour ce mois.

```powershell
python pipeline/declencheur.py --une-fois   # une vérification
python pipeline/declencheur.py              # surveillance continue (toutes les 60 secondes)
```

Planification Windows : vérification chaque jour à 6 h ; la chaîne ne démarre que si un nouveau fichier est arrivé.

```powershell
$p = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute "$p\.venv\Scripts\python.exe" -Argument "pipeline\declencheur.py --une-fois" -WorkingDirectory $p
$declencheur = New-ScheduledTaskTrigger -Daily -At 6:00AM
Register-ScheduledTask -TaskName "Boreal pipeline" -Action $action -Trigger $declencheur
```

## Alertes et journaux

- `warehouse/journal_pipeline.log` : une ligne par étape exécutée.
- `warehouse/alertes.log` : une ligne par échec (étape en cause, message d'erreur), avec un message à l'écran.


## Contenu du dépôt

| Dossier ou fichier | Rôle |
|---|---|
| `data/sources` | Fichiers sources du sujet (non versionnés) |
| `sql/01_raw` à `sql/04_marts` | Requêtes de chaque couche : brut, préparation, cœur, marts |
| `pipeline/ingest.py` | Chargement des sources dans la couche brute |
| `pipeline/qualite.py` | 23 règles de qualité, anomalies, quarantaine |
| `pipeline/run_sql.py` | Exécution des requêtes SQL d'une couche |
| `pipeline/run_all.py` | Chaîne complète, tests bloquants, alertes |
| `pipeline/declencheur.py` | Déclenchement à l'arrivée d'un nouveau fichier |
| `pipeline/catalogue.py` | Génération du catalogue et du schéma de lignage |
| `tests/` | Tests des couches brute et cœur |
| `warehouse/` | Entrepôt DuckDB, journal et alertes |
| `app.py` | Dashboard : trois pages et une page de définitions |
| `catalogue.md` | Catalogue des données (chaque table et chaque colonne) |
| `images/` | Schéma de lignage et captures |

## Tests

```powershell
python tests/test_brut.py
python tests/test_coeur.py
```

Un test en échec renvoie un code d'erreur et interrompt la chaîne.

## Documentation

`python pipeline/catalogue.py` régénère `catalogue.md` et `images/lignage_ratio.png`
(lignage du ratio sinistres/primes, des fichiers sources au dashboard).