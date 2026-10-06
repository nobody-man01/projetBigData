"""Schéma Spark + ingénierie de features, PARTAGÉS entre l'entraînement et le scoring streaming.

Une seule fonction `add_features` garantit qu'il n'y a pas de décalage train/serve.
"""
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (DoubleType, IntegerType, StringType, StructField,
                               StructType)

TX_SCHEMA = StructType([
    StructField("transaction_id", StringType()),
    StructField("timestamp", StringType()),
    StructField("sender_id", StringType()),
    StructField("receiver_id", StringType()),
    StructField("tx_type", StringType()),
    StructField("amount", DoubleType()),
    StructField("sender_balance_before", DoubleType()),
    StructField("sender_balance_after", DoubleType()),
    StructField("receiver_balance_before", DoubleType()),
    StructField("receiver_balance_after", DoubleType()),
    StructField("operator", StringType()),
    StructField("channel", StringType()),
    StructField("city", StringType()),
    StructField("device_id", StringType()),
    StructField("is_fraud", IntegerType()),
])

CATEGORICAL_COLS = ["tx_type", "channel", "operator"]
NUMERIC_COLS = [
    "amount", "log_amount", "sender_balance_before", "hour", "is_night",
    "amount_to_balance_ratio", "sender_emptied", "error_balance_sender",
    "error_balance_receiver",
]


def add_features(df: DataFrame) -> DataFrame:
    """Ajoute les features dérivées. Fonctionne en batch ET en streaming (aucune fenêtre/agrégat global)."""
    ts = F.to_timestamp("timestamp")
    debit_types = ["CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME"]
    return (
        df
        .withColumn("hour", F.hour(ts).cast("double"))
        .withColumn("is_night", F.when(F.col("hour") < 5, 1.0).otherwise(0.0))
        .withColumn("log_amount", F.log1p("amount"))
        .withColumn(
            "amount_to_balance_ratio",
            F.col("amount") / F.greatest(F.col("sender_balance_before"), F.lit(1.0)),
        )
        .withColumn(
            "sender_emptied",
            F.when(F.col("sender_balance_after") <= 0.01 * F.col("sender_balance_before"), 1.0).otherwise(0.0),
        )
        # Incohérences comptables (très discriminantes dans la littérature, ex. dataset PaySim)
        .withColumn(
            "error_balance_sender",
            F.when(
                F.col("tx_type").isin(debit_types),
                F.col("sender_balance_before") - F.col("amount") - F.col("sender_balance_after"),
            ).otherwise(F.col("sender_balance_before") + F.col("amount") - F.col("sender_balance_after")),
        )
        .withColumn(
            "error_balance_receiver",
            F.col("receiver_balance_before") + F.col("amount") - F.col("receiver_balance_after"),
        )
    )
