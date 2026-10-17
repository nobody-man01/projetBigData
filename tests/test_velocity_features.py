"""Features de fréquence : même résultat en une fois (entraînement) et par micro-lots (temps réel).

Nécessite pyspark (ignoré dans la CI minimale).
"""
from datetime import datetime, timedelta, timezone

import pytest

pyspark = pytest.importorskip("pyspark")
from pyspark.sql import functions as F  # noqa: E402

from src.ml.features import VELOCITY_HISTORY_S, add_velocity_features  # noqa: E402
from src.ml.spark import get_spark  # noqa: E402

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
# (secondes après T0, expéditeur, destinataire) : une rafale, un fractionnement, de l'activité étalée
EVENTS = [(0, "A", "X"), (20, "A", "Y"), (40, "A", "Z"), (60, "A", "W"),
          (100, "C", "AG"), (160, "C", "AG"), (220, "C", "AG"),
          (0, "S", "R1"), (900, "S", "R2"), (1800, "S", "R3"), (3000, "S", "R4"), (4000, "S", "R5")]


@pytest.fixture(scope="module")
def spark():
    s = get_spark("tests", master="local[1]", conf={"spark.ui.enabled": "false"})
    yield s
    s.stop()


def frame(spark, events):
    rows = [(f"tx{i}", (T0 + timedelta(seconds=t)).isoformat(), s, r, 1000.0)
            for i, (t, s, r) in enumerate(events)]
    return spark.createDataFrame(rows, "transaction_id string, timestamp string, sender_id string, "
                                       "receiver_id string, amount double")


def as_dict(df):
    cols = ["sender_n_10min", "sender_n_1h", "pair_n_10min", "log_sender_amount_10min"]
    return {r["transaction_id"]: tuple(round(r[c], 6) for c in cols) for r in df.collect()}


def test_valeurs_attendues(spark):
    out = as_dict(add_velocity_features(frame(spark, EVENTS)))
    assert out["tx3"][0] == 4          # 4e transfert de A en 1 minute
    assert out["tx6"][2] == 3          # 3e dépôt de C chez le même agent en 2 minutes
    assert out["tx11"][0] == 1         # S : rien dans les 10 dernières minutes...
    assert out["tx11"][1] == 4         # ... mais 4 dans la dernière heure (900, 1800, 3000, 4000 s)


def test_meme_resultat_par_micro_lots(spark):
    full = as_dict(add_velocity_features(frame(spark, EVENTS)))
    df = frame(spark, EVENTS).withColumn("ts_epoch", F.to_timestamp("timestamp").cast("long"))
    ordered = df.orderBy("ts_epoch").collect()
    recent, streamed = None, {}
    for start in range(0, len(ordered), 3):   # micro-lots de 3 transactions, comme le scoring temps réel
        batch = spark.createDataFrame(ordered[start:start + 3], df.schema).withColumn("_new", F.lit(True))
        combined = batch if recent is None else recent.withColumn("_new", F.lit(False)).unionByName(batch)
        streamed.update(as_dict(add_velocity_features(combined).filter("_new")))
        max_ts = combined.agg(F.max("ts_epoch")).first()[0]
        recent = combined.filter(F.col("ts_epoch") >= max_ts - VELOCITY_HISTORY_S).drop("_new")
    assert streamed == full
