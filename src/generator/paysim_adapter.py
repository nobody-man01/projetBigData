"""Adaptateur PaySim -> contrat de données du projet (src/common/schema.py).

PaySim (Kaggle « ealaxi/paysim1 ») est un simulateur de Mobile Money calibré sur de vrais journaux
d'un service africain. On l'utilise comme jeu de RÉFÉRENCE pour entraîner/valider le modèle sur une
base reconnue. Ce fichier le convertit au format du projet.

Usage :
    1. Télécharger PaySim depuis Kaggle (compte gratuit) et placer le CSV dans data/PS_20174392719_1491204439457_log.csv
    2. python -m src.generator.paysim_adapter --max-rows 1000000
       -> écrit data/transactions_paysim.csv, utilisable avec : python -m src.ml.train_model --data data/transactions_paysim.csv

IMPORTANT (à écrire dans le rapport) :
  * Les champs absents de PaySim (opérateur, canal, ville, appareil) sont AJOUTÉS par simulation,
    de façon déterministe à partir de l'identifiant du compte. Ils ne dépendent PAS de la fraude :
    ils ne peuvent donc pas faire fuiter l'étiquette, mais ils n'apportent aucun signal non plus.
  * PaySim n'indique pas de devise : les montants sont gardés tels quels (facteur --scale pour changer).
  * Les lignes de montant nul sont retirées (le contrat exige amount > 0).
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import DATA_DIR
from src.common.schema import CHANNELS, CITIES, FIELDS, OPERATORS

PAYSIM_DEFAULT = DATA_DIR / "PS_20174392719_1491204439457_log.csv"
OUT_DEFAULT = DATA_DIR / "transactions_paysim.csv"
TYPE_MAP = {"PAYMENT": "PAYMENT", "TRANSFER": "TRANSFER", "CASH_OUT": "CASH_OUT",
            "CASH_IN": "CASH_IN", "DEBIT": "CASH_OUT"}  # DEBIT = retrait vers la banque
PAYSIM_COLUMNS = ["step", "type", "amount", "nameOrig", "oldbalanceOrg", "newbalanceOrig",
                  "nameDest", "oldbalanceDest", "newbalanceDest", "isFraud"]


def _stable_bucket(names: pd.Series, k: int, salt: str) -> np.ndarray:
    """Associe chaque identifiant à un entier stable dans [0, k) (même compte -> même valeur, toujours)."""
    return (pd.util.hash_pandas_object(salt + names.astype(str), index=False).values % k).astype(int)


def adapt_paysim(raw: pd.DataFrame, start: datetime = None, scale: float = 1.0, seed: int = 42) -> pd.DataFrame:
    """Convertit un DataFrame PaySim en DataFrame au format FIELDS (mêmes colonnes, même ordre)."""
    missing = [c for c in PAYSIM_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Colonnes PaySim manquantes : {missing}")
    start = start or datetime(2026, 9, 1, tzinfo=timezone.utc)
    df = raw[raw["amount"] > 0].copy()
    df = df[df["type"].isin(TYPE_MAP)]
    rng = np.random.default_rng(seed)
    # step = heure écoulée depuis le début ; on ajoute minutes/secondes pour ne pas avoir 1 000 lignes à la même seconde
    seconds = (df["step"].astype(int) - 1) * 3600 + rng.integers(0, 3600, len(df))
    ts = (pd.Timestamp(start) + pd.to_timedelta(seconds, unit="s")).map(lambda t: t.isoformat())
    out = pd.DataFrame({
        "transaction_id": [f"ps-{i:09d}" for i in range(len(df))],
        "timestamp": ts.values,
        "sender_id": df["nameOrig"].values,
        "receiver_id": df["nameDest"].values,
        "tx_type": df["type"].map(TYPE_MAP).values,
        "amount": (df["amount"] * scale).round().astype(float).values,
        "sender_balance_before": (df["oldbalanceOrg"] * scale).round().values,
        "sender_balance_after": (df["newbalanceOrig"] * scale).round().values,
        "receiver_balance_before": (df["oldbalanceDest"] * scale).round().values,
        "receiver_balance_after": (df["newbalanceDest"] * scale).round().values,
        "is_fraud": df["isFraud"].astype(int).values,
    })
    out = out[out["amount"] > 0]
    # Enrichissement simulé, stable par compte et indépendant de la fraude
    keys = out["sender_id"]
    out["operator"] = np.array(OPERATORS)[_stable_bucket(keys, len(OPERATORS), "op")]
    out["city"] = np.array(CITIES)[_stable_bucket(keys, len(CITIES), "city")]
    out["device_id"] = ["dev-" + f"{b:07d}" for b in _stable_bucket(keys, 10_000_000, "dev")]
    out["channel"] = np.where(out["tx_type"].isin(["CASH_IN", "CASH_OUT"]), "AGENT",
                              np.array(CHANNELS[:2])[_stable_bucket(keys, 2, "chan")])
    return out[list(FIELDS)].reset_index(drop=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--paysim", default=str(PAYSIM_DEFAULT), help="chemin du CSV PaySim")
    p.add_argument("--out", default=str(OUT_DEFAULT))
    p.add_argument("--max-rows", type=int, default=None,
                   help="garde les N premières lignes (PaySim est trié par temps : le taux de fraude est conservé)")
    p.add_argument("--scale", type=float, default=1.0)
    a = p.parse_args()
    if not Path(a.paysim).exists():
        raise SystemExit(f"Fichier introuvable : {a.paysim}\nTélécharge PaySim sur Kaggle (ealaxi/paysim1) "
                         "et place le CSV dans data/ (voir l'en-tête de ce fichier).")
    raw = pd.read_csv(a.paysim, usecols=PAYSIM_COLUMNS, nrows=a.max_rows)
    out = adapt_paysim(raw, scale=a.scale)
    out.to_csv(a.out, index=False)
    print(f"{len(raw)} lignes lues -> {len(out)} transactions écrites dans {a.out} "
          f"(fraudes: {out.is_fraud.sum()}, taux {out.is_fraud.mean():.3%})")


if __name__ == "__main__":
    main()
