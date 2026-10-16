import numpy as np

from src.common.schema import FIELDS, validate_transaction
from src.generator.generate_dataset import (CONTROL_THRESHOLD, DAILY_CAP, KINDS, TX_CAP,
                                            UNREPORTABLE_KINDS, _generate, generate_dataset)
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
    assert set(scen.loc[df["is_fraud"] == 1, "fraud_scenario"]) == set(KINDS)


def _local_day(df):
    return pd.to_datetime(df["timestamp"]).dt.tz_convert("Africa/Douala").dt.date


def test_kyc_caps_are_respected():
    df = generate_dataset(n=30000, seed=11)
    debit = df["tx_type"].isin(["CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME"]) & df["sender_id"].str.startswith("2376")
    assert (df.loc[debit, "amount"] <= TX_CAP).all()
    daily = df[debit].groupby([df.loc[debit, "sender_id"], _local_day(df[debit])])["amount"].sum()
    assert (daily <= DAILY_CAP).all()


def test_new_scenarios_have_their_signature():
    df, scen = _generate(60000, 0.03, 12, None, 30, None)
    st = scen["fraud_scenario"] == "STRUCTURING"
    assert st.any() and (df.loc[st, "amount"] < CONTROL_THRESHOLD).all()
    assert (df.loc[st, "amount"] >= 0.8 * CONTROL_THRESHOLD).mean() > 0.9     # juste sous le seuil
    ag = scen["fraud_scenario"] == "AGENT_SPLIT"
    assert ag.any() and (df.loc[ag, "tx_type"] == "CASH_IN").all()
    pairs = df[ag].groupby(scen.loc[ag, "event_id"])[["sender_id", "receiver_id"]].nunique()
    assert (pairs == 1).all().all()                                          # même client, même agent


def test_reporting_delay_and_unreported_frauds():
    df, scen = _generate(30000, 0.03, 13, None, 30, None, unreported_share=1.0)
    fraud = ~scen["fraud_scenario"].isin(["", "LEGIT_BURST"])
    hidden = fraud & scen["fraud_scenario"].isin(UNREPORTABLE_KINDS)
    assert (df.loc[hidden, "is_fraud"] == 0).all() and (scen.loc[hidden, "reported_at"] == "").all()
    shown = fraud & ~hidden
    assert (df.loc[shown, "is_fraud"] == 1).all()
    assert (pd.to_datetime(scen.loc[shown, "reported_at"]) > pd.to_datetime(df.loc[shown, "timestamp"])).all()


def test_transfers_mostly_stay_within_operator():
    df = generate_dataset(n=20000, seed=14)
    op = dict(zip(df["sender_id"], df["operator"]))
    tr = df[(df["tx_type"] == "TRANSFER") & df["receiver_id"].isin(op)]
    assert (tr["receiver_id"].map(op) == tr["operator"]).mean() > 0.7


def test_balance_chain_is_consistent_per_account():
    df = generate_dataset(n=20000, seed=15)
    side = pd.concat([
        pd.DataFrame({"acct": df["sender_id"], "before": df["sender_balance_before"],
                      "after": df["sender_balance_after"], "i": df.index}),
        pd.DataFrame({"acct": df["receiver_id"], "before": df["receiver_balance_before"],
                      "after": df["receiver_balance_after"], "i": df.index}),
    ]).sort_values(["acct", "i"])
    prev_after = side.groupby("acct")["after"].shift()
    breaks = (side["before"] != prev_after) & prev_after.notna()
    assert breaks.mean() < 0.005          # seules les rares erreurs de journalisation volontaires (0,2 %)


def test_timestamps_are_utc():
    df = generate_dataset(n=1000, seed=8)
    assert df["timestamp"].str.endswith("+00:00").all()   # contrat : ISO 8601 UTC


def test_device_ids_do_not_reveal_creation_order():
    df = generate_dataset(n=5000, seed=9)
    assert df["device_id"].str.fullmatch(r"dev-[0-9a-f]{12}").all()
    # Avant : appareils neufs numérotés après tous les autres -> rang de tri proche de 1 pour les fraudes
    rank = pd.Series(df["device_id"].unique()).rank(pct=True)
    rank.index = df["device_id"].unique()
    fraud_only = df.groupby("device_id")["is_fraud"].min() == 1
    assert 0.3 < rank[fraud_only[fraud_only].index].mean() < 0.7


def test_test_period_has_its_own_fraud_rate():
    df = generate_dataset(n=40000, fraud_rate=0.02, seed=10, days=30, test_days=10, test_fraud_rate=0.003)
    split = pd.Timestamp("2026-09-01T00:00:00+01:00") + pd.Timedelta(days=30)
    is_test = pd.to_datetime(df["timestamp"]) >= split
    assert 0.2 < is_test.mean() < 0.3                      # ~10/40 des lignes
    assert 0.015 < df.loc[~is_test, "is_fraud"].mean() < 0.025
    assert df.loc[is_test, "is_fraud"].mean() < 0.006
    # mêmes comptes dans les deux périodes (vrai split temporel, pas un autre monde)
    assert df.loc[is_test, "sender_id"].isin(df.loc[~is_test, "sender_id"]).mean() > 0.9


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
