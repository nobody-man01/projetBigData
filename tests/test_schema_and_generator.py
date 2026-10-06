import numpy as np

from src.common.schema import FIELDS, validate_transaction
from src.generator.generate_dataset import _generate, generate_dataset
from src.generator.paysim_adapter import adapt_paysim
import pandas as pd


def _records(df):
    for rec in df.to_dict("records"):
        yield {k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}


def test_generated_rows_respect_contract():
    df = generate_dataset(n=500, fraud_rate=0.05, seed=1)
    assert list(df.columns) == list(FIELDS)
    for rec in _records(df):
        assert validate_transaction(rec) == [], rec


def test_fraud_rate_is_reasonable():
    df = generate_dataset(n=5000, fraud_rate=0.02, seed=2)
    assert 0.01 < df["is_fraud"].mean() < 0.03


def test_transaction_ids_unique():
    df = generate_dataset(n=2000, seed=3)
    assert df["transaction_id"].is_unique


def test_same_seed_gives_same_data():
    a = generate_dataset(n=1500, seed=7)
    b = generate_dataset(n=1500, seed=7)
    assert a.equals(b)


def test_amounts_look_like_xaf():
    df = generate_dataset(n=5000, seed=4)
    assert (df["amount"] % 1 == 0).all()                 # pas de centimes en franc CFA
    assert (df["amount"] % 500 == 0).mean() > 0.4        # beaucoup de montants ronds


def test_accounts_have_history_and_night_is_quiet():
    df = generate_dataset(n=20000, seed=5)
    assert len(df) / df["sender_id"].nunique() > 5       # plusieurs transactions par compte
    hours = pd.to_datetime(df["timestamp"]).dt.hour
    legit = df["is_fraud"] == 0
    assert (hours[legit] < 5).mean() < 0.08              # peu d'activité normale la nuit


def test_fraud_is_not_trivially_separable():
    df, scen = _generate(30000, 0.02, 6, None, 30, None)
    debit = df["tx_type"].isin(["CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME"])
    ratio = df["amount"] / df["sender_balance_before"].clip(lower=1)
    emptied_normal = ((ratio >= 0.9) & debit & (df["is_fraud"] == 0)).sum()
    emptied_fraud = ((ratio >= 0.9) & debit & (df["is_fraud"] == 1)).sum()
    assert emptied_normal > 0 and (df["is_fraud"] == 1).sum() > emptied_fraud   # des cas normaux ressemblent à des fraudes
    assert set(scen[df["is_fraud"] == 1]) == {"ATO", "VELOCITY", "SCAM"}


def test_paysim_adapter_matches_contract():
    raw = pd.DataFrame({
        "step": [1, 1, 2, 3], "type": ["PAYMENT", "TRANSFER", "CASH_OUT", "TRANSFER"],
        "amount": [9839.64, 181.0, 181.0, 0.0],
        "nameOrig": ["C1", "C2", "C2", "C3"], "oldbalanceOrg": [170136.0, 181.0, 181.0, 50.0],
        "newbalanceOrig": [160296.36, 0.0, 0.0, 50.0], "nameDest": ["M1", "C9", "C8", "C7"],
        "oldbalanceDest": [0.0, 0.0, 21182.0, 0.0], "newbalanceDest": [0.0, 0.0, 0.0, 0.0],
        "isFraud": [0, 1, 1, 1],
    })
    out = adapt_paysim(raw)
    assert list(out.columns) == list(FIELDS)
    assert len(out) == 3                                  # la ligne de montant 0 est retirée
    for rec in _records(out):
        assert validate_transaction(rec) == [], rec
    # l'enrichissement est stable : même compte -> même ville / appareil
    again = adapt_paysim(raw)
    assert out["city"].tolist() == again["city"].tolist()
    assert out.loc[out.sender_id == "C2", "device_id"].nunique() == 1
