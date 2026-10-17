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
    # Comparaison avec l'historique du compte (profil calculé par build_profiles)
    "has_history", "log_n_tx_hist", "amount_vs_avg", "amount_vs_max",
    "device_is_new", "receiver_is_new", "city_is_new",
]
# Features issues des profils de comptes (retirées par train_model --sans-profils, pour mesurer leur apport)
PROFILE_COLS = ["has_history", "log_n_tx_hist", "amount_vs_avg", "amount_vs_max",
                "device_is_new", "receiver_is_new", "city_is_new"]


def build_profiles(history: DataFrame) -> DataFrame:
    """Profil de chaque compte émetteur, calculé sur l'historique (couche « batch » de l'architecture).

    N'utilise jamais `is_fraud` : en production, l'historique n'est pas étiqueté.
    Le profil est figé pendant le streaming et recalculé périodiquement (ex. chaque nuit).
    """
    return history.groupBy(F.col("sender_id").alias("p_sender_id")).agg(
        F.count("*").alias("p_n_tx"),
        F.avg("amount").alias("p_avg_amount"),
        F.max("amount").alias("p_max_amount"),
        F.collect_set("device_id").alias("p_devices"),
        F.collect_set("receiver_id").alias("p_receivers"),
        F.collect_set("city").alias("p_cities"),
    )


def _add_profile_features(df: DataFrame, profiles: DataFrame) -> DataFrame:
    """Compare la transaction aux habitudes du compte (jointure flux / table statique, possible en streaming)."""
    known = F.col("p_n_tx").isNotNull()

    def is_new(values_col: str, value_col: str):
        # 1 si le compte a un historique et que la valeur n'y figure pas ; 0 sinon (pas d'historique = inconnu)
        return F.when(known & ~F.array_contains(values_col, F.col(value_col)), 1.0).otherwise(0.0)

    return (
        df.join(F.broadcast(profiles), df["sender_id"] == profiles["p_sender_id"], "left")
        .withColumn("has_history", F.when(known, 1.0).otherwise(0.0))
        .withColumn("log_n_tx_hist", F.log1p(F.coalesce(F.col("p_n_tx"), F.lit(0)).cast("double")))
        .withColumn("amount_vs_avg", F.coalesce(F.col("amount") / F.col("p_avg_amount"), F.lit(1.0)))
        .withColumn("amount_vs_max", F.coalesce(F.col("amount") / F.col("p_max_amount"), F.lit(1.0)))
        .withColumn("device_is_new", is_new("p_devices", "device_id"))
        .withColumn("receiver_is_new", is_new("p_receivers", "receiver_id"))
        .withColumn("city_is_new", is_new("p_cities", "city"))
        .drop("p_sender_id", "p_n_tx", "p_avg_amount", "p_max_amount", "p_devices", "p_receivers", "p_cities")
    )


def add_features(df: DataFrame, profiles: DataFrame) -> DataFrame:
    """Ajoute les features dérivées. Fonctionne en batch ET en streaming (pas de fenêtre ni d'agrégat sur le flux)."""
    ts = F.to_timestamp("timestamp")
    debit_types = ["CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME"]
    df = _add_profile_features(df, profiles)
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
            # Au dépôt (CASH_IN) l'agent « donne » du e-money : son solde baisse au lieu de monter.
            F.when(
                F.col("tx_type") == "CASH_IN",
                F.col("receiver_balance_before") - F.col("amount") - F.col("receiver_balance_after"),
            ).otherwise(F.col("receiver_balance_before") + F.col("amount") - F.col("receiver_balance_after")),
        )
    )
