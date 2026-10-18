"""Scoring temps réel : Kafka -> Spark Structured Streaming (PipelineModel) -> MongoDB `scored_transactions`.

Usage:
    python -m src.ml.streaming_scoring
Prérequis: docker compose up -d, modèle entraîné (src.ml.train_model), producer actif.

Chaque micro-lot (toutes les 5 s) est traité dans `score_batch` :
  1. on y ajoute la dernière heure de transactions déjà vues (gardée en mémoire entre les lots) ;
  2. on calcule les features de fréquence avec la MÊME fonction qu'à l'entraînement (add_velocity_features) ;
  3. on joint les profils de comptes (couche batch), on applique le modèle, on écrit dans MongoDB (upsert).
"""
from datetime import datetime, timezone

from pymongo import MongoClient, ReplaceOne
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from config.settings import (CHECKPOINT_DIR, COL_SCORED, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW,
                             MODEL_PATH, MONGO_DB, MONGO_URI, PROFILES_PATH, SPARK_KAFKA_PACKAGE,
                             THRESHOLD_HIGH, THRESHOLD_MEDIUM)
from src.ml.spark import get_spark
from src.ml.features import (TX_SCHEMA, VELOCITY_COLS, VELOCITY_HISTORY_S, add_features,
                             add_velocity_features)

# Colonnes écrites dans MongoDB : contrat (schema.FIELDS + SCORED_EXTRA) + features utiles à l'explication
EXPLAIN_COLS = ["amount_to_balance_ratio", "sender_emptied", "is_night", "amount_vs_avg", "device_is_new",
                "receiver_is_new", "city_is_new", *VELOCITY_COLS]


def main():
    spark = get_spark("momo-fraud-scoring", conf={"spark.jars.packages": SPARK_KAFKA_PACKAGE,
                                                  "spark.sql.shuffle.partitions": "4"})
    model = PipelineModel.load(str(MODEL_PATH))
    # Profils de comptes calculés en batch par train_model : table statique jointe à chaque micro-lot
    profiles = spark.read.parquet(str(PROFILES_PATH)).cache()
    print(f"{profiles.count()} profils de comptes chargés")

    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
           .option("subscribe", KAFKA_TOPIC_RAW)
           .option("startingOffsets", "latest")
           .option("failOnDataLoss", "false").load())

    # sent_at (ajouté par le producer) ne fait pas partie du contrat : il sert à mesurer la latence
    message_schema = StructType(TX_SCHEMA.fields + [StructField("sent_at", StringType())])
    parsed = (raw.select(F.from_json(F.col("value").cast("string"), message_schema).alias("tx"))
              .select("tx.*").filter(F.col("transaction_id").isNotNull()))

    state = {"recent": None}   # dernière heure de transactions déjà scorées (historique des fenêtres)

    def score_batch(batch_df, batch_id: int):
        batch = (batch_df.dropDuplicates(["transaction_id"])
                 .withColumn("ts_epoch", F.to_timestamp("timestamp").cast("long"))
                 .withColumn("_new", F.lit(True)))
        if batch.isEmpty():
            return
        recent = state["recent"]
        combined = batch if recent is None else recent.withColumn("_new", F.lit(False)).unionByName(batch)
        combined = combined.dropDuplicates(["transaction_id"]).localCheckpoint()

        feats = add_velocity_features(combined).filter("_new").drop("_new")
        scored = (model.transform(add_features(feats, profiles))
                  .withColumn("fraud_score", vector_to_array("probability")[1])
                  .withColumn("prediction", F.col("prediction").cast("int"))
                  .withColumn("risk_level",
                              F.when(F.col("fraud_score") >= THRESHOLD_HIGH, "HIGH")
                               .when(F.col("fraud_score") >= THRESHOLD_MEDIUM, "MEDIUM")
                               .otherwise("LOW"))
                  .select(*[f.name for f in TX_SCHEMA.fields], "sent_at", "fraud_score", "prediction",
                          "risk_level", *EXPLAIN_COLS))
        rows = [r.asDict() for r in scored.collect()]

        # Mise à jour de l'historique : on ne garde que la dernière heure (temps des transactions)
        max_ts = combined.agg(F.max("ts_epoch")).first()[0]
        new_recent = (combined.filter(F.col("ts_epoch") >= max_ts - VELOCITY_HISTORY_S)
                      .drop("_new").localCheckpoint())
        state["recent"] = new_recent

        now = datetime.now(timezone.utc)
        for r in rows:
            r["scored_at"] = now.isoformat()
            # Latence de bout en bout : envoi par le producer -> écriture du score dans MongoDB
            if r.get("sent_at"):
                r["latency_ms"] = (now - datetime.fromisoformat(r["sent_at"])).total_seconds() * 1000
        client = MongoClient(MONGO_URI)
        try:
            # Upsert sur transaction_id => idempotent si Spark rejoue un micro-lot
            client[MONGO_DB][COL_SCORED].bulk_write(
                [ReplaceOne({"transaction_id": r["transaction_id"]}, r, upsert=True) for r in rows])
        finally:
            client.close()
        print(f"[batch {batch_id}] {len(rows)} transactions scorées, "
              f"{sum(1 for r in rows if r['risk_level'] == 'HIGH')} à risque élevé "
              f"(historique : {new_recent.count()} transactions)")

    (parsed.writeStream.foreachBatch(score_batch)
     .option("checkpointLocation", str(CHECKPOINT_DIR))
     .trigger(processingTime="5 seconds").start().awaitTermination())


if __name__ == "__main__":
    main()
