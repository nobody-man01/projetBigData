"""Entraînement du modèle de détection de fraude avec Spark MLlib.

Usage:
    python -m src.ml.train_model                      # forêt aléatoire, données data/transactions.csv
    python -m src.ml.train_model --compare            # compare 3 algorithmes sur une tranche de validation
    python -m src.ml.train_model --data data/transactions_paysim.csv

Découpage TEMPOREL (on apprend sur le passé, on évalue sur le futur, comme en production) :
    [0 % ─ 50 %]   historique : sert uniquement à calculer les profils de comptes
    [50 % ─ 80 %]  entraînement (dont 70-80 % en validation avec --compare)
    [80 % ─ 100 %] test : profils recalculés sur tout ce qui précède (0-80 %), comme en production

Sorties (dossier models/) :
    fraud_pipeline/     le PipelineModel Spark
    account_profiles/   les profils de comptes (0-80 %), joints au flux par le scoring temps réel
    metrics.json        toutes les métriques, réutilisées telles quelles par le rapport
"""
import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from pyspark.ml import Pipeline
from pyspark.ml.classification import GBTClassifier, LogisticRegression, RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StandardScaler, StringIndexer, VectorAssembler
from pyspark.ml.functions import vector_to_array
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from config.settings import (DATA_DIR, MODEL_PATH, PROFILES_PATH, METRICS_PATH, DATASET_PATH,
                             THRESHOLD_HIGH, THRESHOLD_MEDIUM)
from src.ml.features import CATEGORICAL_COLS, NUMERIC_COLS, TX_SCHEMA, add_features, build_profiles

ALGOS = {
    "logreg": "Régression logistique",
    "rf": "Forêt aléatoire",
    "gbt": "Gradient boosting (GBT)",
}


def build_pipeline(algo: str = "rf") -> Pipeline:
    """Encodage des colonnes catégorielles + assemblage des features + classifieur pondéré."""
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
    stages = [*indexers, encoder, assembler]
    if algo == "logreg":
        stages.append(StandardScaler(inputCol="features", outputCol="scaled"))
        clf = LogisticRegression(featuresCol="scaled", labelCol="is_fraud", weightCol="class_weight",
                                 maxIter=100, regParam=0.01)
    elif algo == "gbt":
        clf = GBTClassifier(featuresCol="features", labelCol="is_fraud", weightCol="class_weight",
                            maxIter=60, maxDepth=6, seed=42)
    else:
        clf = RandomForestClassifier(featuresCol="features", labelCol="is_fraud", weightCol="class_weight",
                                     numTrees=100, maxDepth=10, seed=42)
    return Pipeline(stages=[*stages, clf])


def with_class_weight(df):
    """Poids inversement proportionnel à la fréquence de la classe (les fraudes sont rares)."""
    n, n_fraud = df.count(), df.filter("is_fraud = 1").count()
    w_fraud = (n - n_fraud) / max(n_fraud, 1)
    return df.withColumn("class_weight", F.when(F.col("is_fraud") == 1, w_fraud).otherwise(1.0)), n, n_fraud


def auc_pr(pred) -> float:
    return BinaryClassificationEvaluator(labelCol="is_fraud", metricName="areaUnderPR").evaluate(pred)


def threshold_metrics(y: np.ndarray, score: np.ndarray, threshold: float) -> dict:
    """Précision / rappel / volume d'alertes si l'on alerte au-dessus du seuil."""
    alert = score >= threshold
    tp, fp = int((alert & (y == 1)).sum()), int((alert & (y == 0)).sum())
    fn, tn = int((~alert & (y == 1)).sum()), int((~alert & (y == 0)).sum())
    return {
        "threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": tp / max(tp + fp, 1), "recall": tp / max(tp + fn, 1),
        "alerts_per_1000": 1000 * (tp + fp) / max(len(y), 1),
    }


def pr_curve(y: np.ndarray, score: np.ndarray, n_points: int = 200) -> list:
    """Points (seuil, précision, rappel) de la courbe précision-rappel, pour les figures du rapport."""
    order = np.argsort(-score)
    y_sorted, s_sorted = y[order], score[order]
    tp = np.cumsum(y_sorted)
    precision = tp / np.arange(1, len(y) + 1)
    recall = tp / max(y.sum(), 1)
    idx = np.unique(np.linspace(0, len(y) - 1, n_points).astype(int))
    return [{"threshold": float(s_sorted[i]), "precision": float(precision[i]), "recall": float(recall[i])}
            for i in idx]


def feature_importances(model, pred) -> list:
    """Importance de chaque feature (forêt aléatoire / GBT), avec les noms lisibles des colonnes."""
    clf = model.stages[-1]
    if not hasattr(clf, "featureImportances"):
        return []
    attrs = pred.schema["features"].metadata["ml_attr"]["attrs"]
    names = {a["idx"]: a["name"] for group in attrs.values() for a in group}
    imp = clf.featureImportances.toArray()
    ranked = sorted(((names.get(i, str(i)), float(v)) for i, v in enumerate(imp)), key=lambda t: -t[1])
    return [{"feature": n, "importance": v} for n, v in ranked if v > 0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default=str(DATASET_PATH))
    p.add_argument("--algo", choices=list(ALGOS), default="rf")
    p.add_argument("--compare", action="store_true", help="compare les 3 algorithmes (validation 70-80 %%)")
    a = p.parse_args()

    spark = (SparkSession.builder.appName("momo-fraud-train").master("local[*]")
             .config("spark.driver.memory", "6g").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    df = (spark.read.csv(a.data, header=True, schema=TX_SCHEMA)
          .withColumn("ts_epoch", F.to_timestamp("timestamp").cast("long")).cache())
    q50, q70, q80 = df.approxQuantile("ts_epoch", [0.5, 0.7, 0.8], 0.001)
    history, test_history = df.filter(F.col("ts_epoch") <= q50), df.filter(F.col("ts_epoch") <= q80)
    train_raw = df.filter((F.col("ts_epoch") > q50) & (F.col("ts_epoch") <= q80))
    test_raw = df.filter(F.col("ts_epoch") > q80)

    profiles_train = build_profiles(history).cache()
    profiles_test = build_profiles(test_history).cache()

    comparison = []
    if a.compare:
        fit_part = add_features(train_raw.filter(F.col("ts_epoch") <= q70), profiles_train)
        valid = add_features(train_raw.filter(F.col("ts_epoch") > q70), profiles_train)
        fit_part, _, _ = with_class_weight(fit_part)
        for algo, label in ALGOS.items():
            score = auc_pr(build_pipeline(algo).fit(fit_part).transform(valid))
            comparison.append({"algo": algo, "label": label, "auc_pr_validation": score})
            print(f"  {label:28s} AUC-PR validation = {score:.4f}")
        a.algo = max(comparison, key=lambda r: r["auc_pr_validation"])["algo"]
        print(f"Algorithme retenu : {ALGOS[a.algo]}")

    train, n_train, n_fraud = with_class_weight(add_features(train_raw, profiles_train))
    print(f"Entraînement : {n_train} transactions dont {n_fraud} fraudes ({ALGOS[a.algo]})")
    model = build_pipeline(a.algo).fit(train)

    pred = model.transform(add_features(test_raw, profiles_test))
    pred = pred.withColumn("fraud_score", vector_to_array("probability")[1])
    roc = BinaryClassificationEvaluator(labelCol="is_fraud", metricName="areaUnderROC").evaluate(pred)
    pr = auc_pr(pred)

    # Analyse détaillée côté pandas (≈ 40 000 lignes de test)
    res = pred.select("transaction_id", "is_fraud", "fraud_score").toPandas()
    y, score = res["is_fraud"].to_numpy(), res["fraud_score"].to_numpy()
    by_scenario = {}
    scenarios_path = DATA_DIR / "transactions_scenarios.csv"
    if scenarios_path.exists():  # uniquement pour l'analyse (jamais pour l'entraînement)
        sc = pd.read_csv(scenarios_path).dropna()
        res = res.merge(sc, on="transaction_id", how="left")
        for name, g in res[res["is_fraud"] == 1].groupby("fraud_scenario"):
            by_scenario[name] = {
                "n": int(len(g)),
                "recall_high": float((g["fraud_score"] >= THRESHOLD_HIGH).mean()),
                "recall_medium": float((g["fraud_score"] >= THRESHOLD_MEDIUM).mean()),
            }

    metrics = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": a.data, "algo": a.algo, "algo_label": ALGOS[a.algo],
        "n_rows": int(df.count()), "n_train": n_train, "n_train_fraud": n_fraud,
        "n_test": int(len(y)), "n_test_fraud": int(y.sum()),
        "test_period_start": datetime.fromtimestamp(q80, timezone.utc).isoformat(),
        "auc_pr": pr, "auc_roc": roc, "fraud_rate_test": float(y.mean()),
        "at_high": threshold_metrics(y, score, THRESHOLD_HIGH),
        "at_medium": threshold_metrics(y, score, THRESHOLD_MEDIUM),
        "by_scenario": by_scenario,
        "comparison": comparison,
        "feature_importances": feature_importances(model, pred),
        "pr_curve": pr_curve(y, score),
    }
    print(f"AUC-PR={pr:.4f}  AUC-ROC={roc:.4f}  (taux de fraude test {y.mean():.2%})")
    for key in ("at_high", "at_medium"):
        m = metrics[key]
        print(f"  seuil {m['threshold']:.2f} : précision {m['precision']:.1%}, rappel {m['recall']:.1%}, "
              f"{m['alerts_per_1000']:.1f} alertes / 1000 tx")
    for name, s in by_scenario.items():
        print(f"  {name:9s} rappel HIGH {s['recall_high']:.1%}  MEDIUM+ {s['recall_medium']:.1%}  (n={s['n']})")

    model.write().overwrite().save(str(MODEL_PATH))
    profiles_test.write.mode("overwrite").parquet(str(PROFILES_PATH))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Modèle, profils et métriques sauvegardés dans {MODEL_PATH.parent}")
    spark.stop()


if __name__ == "__main__":
    main()
