from src.common.schema import FIELDS, validate_transaction
from src.generator.generate_dataset import generate_dataset


def test_generated_rows_respect_contract():
    df = generate_dataset(n=500, fraud_rate=0.05, seed=1)
    assert list(df.columns) == list(FIELDS)
    for rec in df.to_dict("records"):
        rec = {k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}
        assert validate_transaction(rec) == [], rec


def test_fraud_rate_is_reasonable():
    df = generate_dataset(n=5000, fraud_rate=0.02, seed=2)
    assert 0.005 < df["is_fraud"].mean() < 0.05


def test_transaction_ids_unique():
    df = generate_dataset(n=2000, seed=3)
    assert df["transaction_id"].is_unique


def test_validate_rejects_bad_tx():
    assert validate_transaction({}) != []
