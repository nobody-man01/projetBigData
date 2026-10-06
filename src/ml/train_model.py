"""Entraînement du modèle de détection de fraude avec Spark MLlib.

Usage:
    python -m src.ml.train_model --data data/transactions.csv

Sortie: un PipelineModel sauvegardé dans models/fraud_pipeline + métriques affichées (AUC-PR, AUC-ROC, F1, matrice de confusion).
Choix: RandomForest + pondération des classes (jeu de données très déséquilibré), split temporel.
"""
import argparse

from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from config.settings import DATASET_PATH, MODEL_PATH
from src.ml.features import CATEGORICAL_COLS, NUMERIC_COLS, TX_SCHEMA, add_features


def build_pipeline() -> Pipeline:
    indexers = [StringIndexer(inputCol=c, outputCol=f"{c}_idx", handleInvalid="keep") for c in CATEGORICAL_COLS]
    encoder = OneHotEncoder(
        inputCols=[f"{c}_idx" for c in CATEGORICAL_COLS],
        outputCols=[f"{c}_ohe" for c in CATEGORICAL_COLS],
        handleInvalid="keep",
    )
    assembler = VectorAssembler(
        inputCols=NUMERIC_COLS + [f"{c}_ohe" for c in CATEGORICAL_COLS],
        outputCol="features",
        handleInvalid="keep",
    )
    rf = RandomForestClassifier(
        featuresCol="features", labelCol="is_fraud", weightCol="class_weight",
        numTrees=100, maxDepth=8, seed=42,
    )
    return Pipeline(stages=[*indexers, encoder, assembler, rf])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(DATASET_PATH))
    p.add_argument("--model-out", default=str(MODEL_PATH))
    a = p.parse_args()

    spark = SparkSession.builder.appName("momo-fraud-train").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    df = spark.read.csv(a.data, header=True, schema=TX_SCHEMA)
    df = add_features(df).withColumn("ts", F.to_timestamp("timestamp"))

    # Split temporel : on entraîne sur le passé, on teste sur le futur (réaliste pour un système temps réel)
    df = df.withColumn("ts_epoch", F.col("ts").cast("long"))
    cutoff = df.approxQuantile("ts_epoch", [0.8], 0.01)[0]
    train, test = df.filter(F.col("ts_epoch") <= cutoff), df.filter(F.col("ts_epoch") > cutoff)

    # Pondération : poids inversement proportionnel à la fréquence de la classe
    n, n_fraud = train.count(), train.filter("is_fraud = 1").count()
    w_fraud = (n - n_fraud) / max(n_fraud, 1)
    train = train.withColumn("class_weight", F.when(F.col("is_fraud") == 1, w_fraud).otherwise(1.0))
    print(f"train={n} fraudes={n_fraud} poids_fraude={w_fraud:.1f}")

    model = build_pipeline().fit(train)
    pred = model.transform(test)

    auc_pr = BinaryClassificationEvaluator(labelCol="is_fraud", metricName="areaUnderPR").evaluate(pred)
    auc_roc = BinaryClassificationEvaluator(labelCol="is_fraud", metricName="areaUnderROC").evaluate(pred)
    f1 = MulticlassClassificationEvaluator(labelCol="is_fraud", metricName="f1").evaluate(pred)
    print(f"AUC-PR={auc_pr:.4f}  AUC-ROC={auc_roc:.4f}  F1={f1:.4f}")
    pred.groupBy("is_fraud", "prediction").count().orderBy("is_fraud", "prediction").show()

    model.write().overwrite().save(a.model_out)
    print(f"Modèle sauvegardé: {a.model_out}")
    spark.stop()


if __name__ == "__main__":
    main()
