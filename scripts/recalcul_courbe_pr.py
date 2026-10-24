"""Recalcule la courbe précision-rappel de models/metrics.json avec le modèle déjà entraîné, sans réentraîner.

Les versions de train_model antérieures au 20/10 n'enregistraient que 200 points pris à pas constant : la courbe
n'avait presque aucun point entre un rappel de 0 et de 0,8. Ce script rejoue exactement l'évaluation de
train_model (période de test séparée, fenêtres de fréquence, profils sauvegardés), vérifie que les scores redonnent
les mêmes chiffres aux seuils 0,50 et 0,80, puis remplace uniquement le champ pr_curve.

Usage : python scripts/recalcul_courbe_pr.py [--test-data data/transactions_test.csv]
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyspark.ml import PipelineModel  # noqa: E402
from pyspark.ml.functions import vector_to_array  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from config.settings import DATASET_PATH, METRICS_PATH, MODEL_PATH, PROFILES_PATH, THRESHOLD_HIGH, THRESHOLD_MEDIUM  # noqa: E402
from src.ml.features import TX_SCHEMA, VELOCITY_HISTORY_S, add_features, add_velocity_features  # noqa: E402
from src.ml.spark import get_spark  # noqa: E402
from src.ml.train_model import BROADCAST_MAX_PROFILES, pr_curve, threshold_metrics  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(DATASET_PATH))
    p.add_argument("--test-data", default=str(ROOT / "data" / "transactions_test.csv"))
    a = p.parse_args()
    metrics = json.loads(METRICS_PATH.read_text())

    spark = get_spark("momo-fraud-courbe-pr", conf={"spark.driver.memory": os.getenv("SPARK_DRIVER_MEMORY", "4g")})
    read = lambda f: spark.read.csv(f, header=True, schema=TX_SCHEMA).withColumn("ts_epoch", F.to_timestamp("timestamp").cast("long"))  # noqa: E731
    raw, test_only = read(a.data), read(a.test_data)
    # Même construction que train_model : la dernière heure du jeu principal sert d'historique aux fenêtres du test
    test_start = test_only.agg(F.min("ts_epoch")).first()[0]
    tail = raw.filter(F.col("ts_epoch") >= test_start - VELOCITY_HISTORY_S).withColumn("_test", F.lit(False))
    test_raw = (add_velocity_features(tail.unionByName(test_only.withColumn("_test", F.lit(True))))
                .filter("_test").drop("_test"))
    profiles = spark.read.parquet(str(PROFILES_PATH))
    bc = profiles.count() <= BROADCAST_MAX_PROFILES

    model = PipelineModel.load(str(MODEL_PATH))
    pred = model.transform(add_features(test_raw, profiles, bc)).withColumn("fraud_score", vector_to_array("probability")[1])
    res = pred.select("is_fraud", "fraud_score").toPandas()
    y, score = res["is_fraud"].to_numpy(), res["fraud_score"].to_numpy()
    spark.stop()

    # Contrôle : les scores doivent redonner exactement les chiffres enregistrés à l'entraînement
    for key, thr in (("at_high", THRESHOLD_HIGH), ("at_medium", THRESHOLD_MEDIUM)):
        now, saved = threshold_metrics(y, score, thr), metrics[key]
        if any(now[k] != saved[k] for k in ("tp", "fp", "fn", "tn")):
            raise SystemExit(f"Scores différents de l'entraînement au seuil {thr} : {now} au lieu de {saved}. Rien n'est modifié.")
    metrics["pr_curve"] = pr_curve(y, score)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Courbe précision-rappel recalculée : {len(metrics['pr_curve'])} points, chiffres aux seuils identiques.")


if __name__ == "__main__":
    main()
