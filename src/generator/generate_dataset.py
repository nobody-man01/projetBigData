"""Générateur de transactions Mobile Money simulées (version v0 fonctionnelle, à enrichir par M2).

Usage:
    python -m src.generator.generate_dataset --n 200000 --fraud-rate 0.02 --seed 42

Scénarios de fraude v0 (M2 doit en ajouter, cf. docs/TACHES.md) :
  1. DRAIN      : TRANSFER/CASH_OUT qui vide presque tout le solde de l'expéditeur
  2. NIGHT_BIG  : gros montant entre 00h et 04h
"""
import argparse
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config.settings import DATA_DIR, DATASET_PATH
from src.common.schema import CHANNELS, CITIES, FIELDS, OPERATORS, TX_TYPES


def _msisdn(rng: np.random.Generator, n_accounts: int) -> str:
    return f"2376{rng.integers(0, n_accounts):08d}"


def generate_dataset(n: int = 100_000, fraud_rate: float = 0.02, seed: int = 42,
                     n_accounts: int = 20_000, start: datetime = None) -> pd.DataFrame:
    """Retourne un DataFrame respectant exactement src.common.schema.FIELDS (mêmes noms de colonnes)."""
    rng = np.random.default_rng(seed)
    start = start or datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        ts = start + timedelta(seconds=int(i * 30 * 24 * 3600 / n) + int(rng.integers(0, 30)))
        is_fraud = int(rng.random() < fraud_rate)
        tx_type = str(rng.choice(TX_TYPES, p=[0.20, 0.30, 0.25, 0.20, 0.05]))
        sender_before = float(rng.lognormal(mean=11, sigma=1.0))  # ~60k XAF médian
        if is_fraud:
            tx_type = str(rng.choice(["TRANSFER", "CASH_OUT"]))
            amount = round(sender_before * rng.uniform(0.9, 1.0), 2)
            if rng.random() < 0.5:  # NIGHT_BIG
                ts = ts.replace(hour=int(rng.integers(0, 4)))
        else:
            amount = round(min(float(rng.lognormal(8.5, 1.0)), sender_before), 2) or 100.0
        amount = max(amount, 100.0)
        sender_before = max(sender_before, amount)
        receiver_before = float(rng.lognormal(10.5, 1.0))
        debit = tx_type in ("CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME")
        sender_after = sender_before - amount if debit else sender_before + amount
        receiver_after = receiver_before + amount if tx_type in ("TRANSFER", "PAYMENT") else receiver_before
        rows.append({
            "transaction_id": str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | i)),
            "timestamp": ts.isoformat(),
            "sender_id": _msisdn(rng, n_accounts),
            "receiver_id": _msisdn(rng, n_accounts),
            "tx_type": tx_type,
            "amount": amount,
            "sender_balance_before": round(sender_before, 2),
            "sender_balance_after": round(sender_after, 2),
            "receiver_balance_before": round(receiver_before, 2),
            "receiver_balance_after": round(receiver_after, 2),
            "operator": str(rng.choice(OPERATORS, p=[0.55, 0.45])),
            "channel": str(rng.choice(CHANNELS, p=[0.45, 0.25, 0.30])),
            "city": str(rng.choice(CITIES, p=[0.30, 0.25, 0.10, 0.08, 0.07, 0.05, 0.08, 0.07])),
            "device_id": f"dev-{rng.integers(0, n_accounts * 2):07d}",
            "is_fraud": is_fraud,
        })
    return pd.DataFrame(rows, columns=list(FIELDS))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200_000)
    p.add_argument("--fraud-rate", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=str(DATASET_PATH))
    a = p.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = generate_dataset(a.n, a.fraud_rate, a.seed)
    df.to_csv(a.out, index=False)
    print(f"{len(df)} transactions écrites dans {a.out} (fraudes: {df.is_fraud.sum()})")


if __name__ == "__main__":
    main()
