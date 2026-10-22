"""Chaîne complète en une commande : chargement, préparation, qualité, cœur, tests, marts.

Un test en échec ou une étape en erreur interrompt tout et déclenche une alerte
(journal warehouse/alertes.log, message à l'écran ).

Utilisation :
  python pipeline/run_all.py                  # recharge tout (rejouable sans doublon)
  python pipeline/run_all.py --mois 2025_07   # ne recharge que le fichier de règlements de ce mois
"""
import argparse
import os
import smtplib
import subprocess
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOURNAL = ROOT / "warehouse" / "journal_pipeline.log"
ALERTES = ROOT / "warehouse" / "alertes.log"
PY = sys.executable


def ecrire(fichier, texte):
    fichier.parent.mkdir(exist_ok=True)
    with open(fichier, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {texte}\n")


def alerter(etape, detail):
    """Alerte en cas d'échec : journal, écran, et e-mail si les variables BOREAL_* sont définies."""
    message = f"ECHEC de l'étape « {etape} » : {detail}"
    ecrire(ALERTES, message)
    print(f"\n*** ALERTE *** {message}\n(voir warehouse/alertes.log)")
    destinataire, hote = os.environ.get("BOREAL_ALERTE_MAIL"), os.environ.get("BOREAL_SMTP_HOTE")
    if destinataire and hote:
        try:
            mail = EmailMessage()
            mail["Subject"], mail["From"], mail["To"] = "Boréal : échec du pipeline", destinataire, destinataire
            mail.set_content(message)
            with smtplib.SMTP(hote, int(os.environ.get("BOREAL_SMTP_PORT", "587"))) as smtp:
                smtp.starttls()
                if os.environ.get("BOREAL_SMTP_UTILISATEUR"):
                    smtp.login(os.environ["BOREAL_SMTP_UTILISATEUR"], os.environ["BOREAL_SMTP_MOT_DE_PASSE"])
                smtp.send_message(mail)
        except Exception as e:  # une alerte qui échoue ne doit pas masquer l'échec d'origine
            ecrire(ALERTES, f"Envoi de l'e-mail impossible : {e}")


def etapes(mois):
    ingest = [PY, "pipeline/ingest.py"] + (["--mois", mois] if mois else [])
    return [
        ("Chargement des sources (brut)", ingest),
        ("Tests de la couche brute", [PY, "tests/test_brut.py"]),
        ("Préparation (types et nettoyage)", [PY, "pipeline/run_sql.py", "02_prep"]),
        ("Contrôles de qualité", [PY, "pipeline/qualite.py"]),
        ("Cœur (modèle en étoile)", [PY, "pipeline/run_sql.py", "03_core"]),
        ("Tests de la couche cœur", [PY, "tests/test_coeur.py"]),
        ("Marts d'analyse", [PY, "pipeline/run_sql.py", "04_marts"]),
    ]


def lancer(mois=None):
    """Exécute la chaîne. Renvoie 0 si tout est passé, 1 sinon."""
    debut = time.time()
    ecrire(JOURNAL, f"DEBUT {'mois ' + mois if mois else 'rechargement complet'}")
    if mois and not list((ROOT / "data" / "sources").rglob(f"reglements_{mois}.csv")):
        alerter("Chargement des sources (brut)", f"fichier reglements_{mois}.csv introuvable dans data/sources")
        ecrire(JOURNAL, "ECHEC fichier introuvable")
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for nom, commande in etapes(mois):
        print(f"\n=== {nom} ===")
        t0 = time.time()
        r = subprocess.run(commande, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(r.stdout, end="")
        if r.returncode != 0:
            fin = (r.stderr or r.stdout).strip().splitlines()[-3:]
            alerter(nom, " | ".join(fin) or f"code {r.returncode}")
            ecrire(JOURNAL, f"ECHEC à l'étape « {nom} »")
            return 1
        ecrire(JOURNAL, f"OK   {nom} ({time.time() - t0:.1f} s)")
    ecrire(JOURNAL, f"FIN  succès en {time.time() - debut:.1f} s")
    print(f"\nPipeline terminé avec succès en {time.time() - debut:.1f} s.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mois", help="mois à recharger, au format AAAA_MM (exemple : 2025_07)")
    sys.exit(lancer(p.parse_args().mois))