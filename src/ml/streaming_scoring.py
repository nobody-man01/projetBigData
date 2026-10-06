"""Scoring temps réel : Kafka -> Spark Structured Streaming (PipelineModel) -> MongoDB `scored_transactions`.

Usage:
    python -m src.ml.streaming_scoring
Prérequis: docker compose up -d, modèle entraîné (src.ml.train_model), producer actif.
"""
from datetime import datetime, timezone

from pymongo import MongoClient, ReplaceOne
from pyspark.ml import PipelineModel
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from config.settings import (CHECKPOINT_DIR, COL_SCORED, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW,
                             MODEL_PATH, MONGO_DB, MONGO_URI, SPARK_KAFKA_PACKAGE,
                             THRESHOLD_HIGH, THRESHOLD_MEDIUM)
from src.ml.features import TX_SCHEMA, add_features

DROP_COLS = ["features", "rawPrediction", "probability"]


def main():
    spark = (SparkSession.builder.appName("momo-fraud-scoring").master("local[*]")
             .config("spark.jars.packages", SPARK_KAFKA_PACKAGE)
             .config("spark.sql.shuffle.partitions", "4").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    model = PipelineModel.load(str(MODEL_PATH))

    raw = (spark.readStream.format("kafka")
           .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
           .option("subscribe", KAFKA_TOPIC_RAW)
           .option("startingOffsets", "latest")
           .option("failOnDataLoss", "false").load())

    parsed = (raw.select(F.from_json(F.col("value").cast("string"), TX_SCHEMA).alias("tx"))
              .select("tx.*").filter(F.col("transaction_id").isNotNull()))

    scored = model.transform(add_features(parsed))
    scored = (scored
              .withColumn("fraud_score", vector_to_array("probability")[1])
              .withColumn("prediction", F.col("prediction").cast("int"))
              .withColumn("risk_level",
                          F.when(F.col("fraud_score") >= THRESHOLD_HIGH, "HIGH")
                           .when(F.col("fraud_score") >= THRESHOLD_MEDIUM, "MEDIUM")
                           .otherwise("LOW")))
    # On ne garde que les colonnes du contrat (schema.FIELDS + SCORED_EXTRA) + features utiles à l'explication
    keep = [f.name for f in TX_SCHEMA.fields] + ["fraud_score", "prediction", "risk_level",
                                                 "amount_to_balance_ratio", "sender_emptied", "is_night"]
    scored = scored.select(*keep)

    def write_batch(batch_df, batch_id: int):
        rows = [r.asDict() for r in batch_df.collect()]
        if not rows:
            return
        now = datetime.now(timezone.utc).isoformat()
        for r in rows:
            r["scored_at"] = now
        client = MongoClient(MONGO_URI)
        try:
            # Upsert sur transaction_id => idempotent si Spark rejoue un micro-batch
            client[MONGO_DB][COL_SCORED].bulk_write(
                [ReplaceOne({"transaction_id": r["transaction_id"]}, r, upsert=True) for r in rows])
        finally:
            client.close()
        print(f"[batch {batch_id}] {len(rows)} transactions scorées, "
              f"{sum(1 for r in rows if r['risk_level'] == 'HIGH')} à risque élevé")

    (scored.writeStream.foreachBatch(write_batch)
     .option("checkpointLocation", str(CHECKPOINT_DIR))
     .trigger(processingTime="5 seconds").start().awaitTermination())


if __name__ == "__main__":
    main()
