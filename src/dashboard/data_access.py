"""Accès MongoDB pour le dashboard. Les pages Streamlit appellent UNIQUEMENT ces fonctions (jamais pymongo directement)."""
import json
from functools import lru_cache

import pandas as pd
from pymongo import MongoClient

from config.settings import COL_RAW, COL_SCORED, METRICS_PATH, MONGO_DB, MONGO_URI, PROFILES_PATH


def _col():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)[MONGO_DB][COL_SCORED]


def get_kpis() -> dict:
    """Retourne: total, n_high, n_medium, fraud_rate (part HIGH), amount_at_risk (somme montants HIGH)."""
    col = _col()
    total = col.count_documents({})
    n_high = col.count_documents({"risk_level": "HIGH"})
    n_medium = col.count_documents({"risk_level": "MEDIUM"})
    agg = list(col.aggregate([{"$match": {"risk_level": "HIGH"}},
                              {"$group": {"_id": None, "s": {"$sum": "$amount"}}}]))
    return {
        "total": total, "n_high": n_high, "n_medium": n_medium,
        "fraud_rate": (n_high / total) if total else 0.0,
        "amount_at_risk": agg[0]["s"] if agg else 0.0,
    }


def get_suspicious(limit: int = 200, min_level: str = "MEDIUM", city: str = None, tx_type: str = None) -> pd.DataFrame:
    """Dernières transactions MEDIUM/HIGH (les plus récentes d'abord), filtrables."""
    levels = ["HIGH"] if min_level == "HIGH" else ["MEDIUM", "HIGH"]
    query = {"risk_level": {"$in": levels}}
    if city:
        query["city"] = city
    if tx_type:
        query["tx_type"] = tx_type
    cur = _col().find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    return pd.DataFrame(list(cur))


def get_timeseries(freq: str = "1h") -> pd.DataFrame:
    """Colonnes: bucket, total, n_high. Agrégé par pandas sur les 20 000 dernières transactions."""
    cur = _col().find({}, {"_id": 0, "timestamp": 1, "risk_level": 1}).sort("timestamp", -1).limit(20000)
    df = pd.DataFrame(list(cur))
    if df.empty:
        return pd.DataFrame(columns=["bucket", "total", "n_high"])
    df["bucket"] = pd.to_datetime(df["timestamp"], utc=True).dt.floor(freq)
    df["is_high"] = (df["risk_level"] == "HIGH").astype(int)
    out = df.groupby("bucket").agg(total=("is_high", "size"), n_high=("is_high", "sum")).reset_index()
    return out.sort_values("bucket")


def get_top_risky_accounts(n: int = 10) -> pd.DataFrame:
    """Colonnes: sender_id, n_high, amount_high. Comptes avec le plus de transactions HIGH."""
    pipeline = [
        {"$match": {"risk_level": "HIGH"}},
        {"$group": {"_id": "$sender_id", "n_high": {"$sum": 1}, "amount_high": {"$sum": "$amount"}}},
        {"$sort": {"n_high": -1}}, {"$limit": n},
        {"$project": {"_id": 0, "sender_id": "$_id", "n_high": 1, "amount_high": 1}},
    ]
    return pd.DataFrame(list(_col().aggregate(pipeline)))


# --- Fonctions ajoutées pour les pages Alertes, Performance et Santé du pipeline ---

def ping() -> bool:
    """True si MongoDB répond (sert aux états « hors ligne » des pages)."""
    try:
        MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:
        return False


def explain(tx: dict) -> list:
    """Raisons lisibles d'une alerte, à partir des features conservées par le scoring (3 au maximum)."""
    reasons = []
    if (tx.get("pair_n_10min") or 0) >= 3:
        reasons.append(f"{tx['pair_n_10min']:.0f} opérations vers le même destinataire en 10 min")
    elif (tx.get("sender_n_10min") or 0) >= 4:
        reasons.append(f"{tx['sender_n_10min']:.0f} opérations en 10 min")
    elif (tx.get("sender_n_1h") or 0) >= 4:
        reasons.append(f"{tx['sender_n_1h']:.0f} opérations en 1 h")
    if tx.get("device_is_new") == 1:
        reasons.append("Nouvel appareil pour ce compte")
    if tx.get("receiver_is_new") == 1:
        reasons.append("Destinataire jamais payé")
    ratio = tx.get("amount_vs_avg") or 0
    if ratio >= 3:
        reasons.append(f"Montant ×{ratio:.0f} la moyenne du compte")
    if tx.get("sender_emptied") == 1:
        reasons.append("Solde vidé")
    if tx.get("city_is_new") == 1:
        reasons.append(f"Ville inhabituelle ({tx.get('city', '?')})")
    if tx.get("is_night") == 1:
        reasons.append("En pleine nuit")
    return reasons[:3]


def get_city_stats() -> pd.DataFrame:
    """Colonnes: city, total, n_alerts (MEDIUM+HIGH), alert_rate."""
    pipeline = [
        {"$group": {"_id": "$city", "total": {"$sum": 1},
                    "n_alerts": {"$sum": {"$cond": [{"$in": ["$risk_level", ["MEDIUM", "HIGH"]]}, 1, 0]}}}},
        {"$project": {"_id": 0, "city": "$_id", "total": 1, "n_alerts": 1}},
    ]
    df = pd.DataFrame(list(_col().aggregate(pipeline)))
    if not df.empty:
        df["alert_rate"] = df["n_alerts"] / df["total"]
    return df


def get_pipeline_stats(window_s: int = 60) -> dict:
    """Débit et latence mesurés sur les transactions scorées récemment (champs scored_at et latency_ms)."""
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[MONGO_DB]
    cur = db[COL_SCORED].find({"latency_ms": {"$exists": True}}, {"_id": 0, "scored_at": 1, "latency_ms": 1}
                              ).sort("scored_at", -1).limit(5000)
    df = pd.DataFrame(list(cur))
    stats = {"n_raw": db[COL_RAW].estimated_document_count(),
             "n_scored": db[COL_SCORED].estimated_document_count(),
             "throughput": 0.0, "latency_p50": None, "latency_p95": None, "latency_series": pd.DataFrame()}
    if df.empty:
        return stats
    df["scored_at"] = pd.to_datetime(df["scored_at"], utc=True, format="ISO8601")
    recent = df[df["scored_at"] >= df["scored_at"].max() - pd.Timedelta(seconds=window_s)]
    stats["throughput"] = len(recent) / window_s
    stats["latency_p50"] = float(df["latency_ms"].quantile(0.5))
    stats["latency_p95"] = float(df["latency_ms"].quantile(0.95))
    stats["latency_series"] = (df.set_index("scored_at")["latency_ms"].resample("10s")
                               .agg(["median", "count"]).dropna().reset_index())
    return stats


def load_model_metrics() -> dict:
    """Métriques du dernier entraînement (models/metrics.json), ou {} si le modèle n'est pas entraîné."""
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text())


# --- Page « Investigation d'un compte » et curseur de seuil ---

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def get_account_transactions(account_id: str, limit: int = 2000) -> pd.DataFrame:
    """Transactions scorées où le compte est émetteur OU destinataire, de la plus ancienne à la plus récente."""
    query = {"$or": [{"sender_id": account_id}, {"receiver_id": account_id}]}
    cur = _col().find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
    df = pd.DataFrame(list(cur))
    return df.iloc[::-1].reset_index(drop=True) if not df.empty else df


@lru_cache(maxsize=2)
def _profiles(mtime: float) -> pd.DataFrame:
    """Table des profils (couche batch), relue seulement si le fichier change (nouvel entraînement)."""
    return pd.read_parquet(PROFILES_PATH).set_index("p_sender_id")


def get_account_profile(account_id: str) -> dict:
    """Habitudes du compte calculées en batch par train_model (models/account_profiles), ou {} si inconnu.

    Clés : n_tx, avg_amount, max_amount, devices, receivers, cities (listes).
    """
    if not PROFILES_PATH.exists():
        return {}
    files = list(PROFILES_PATH.glob("*.parquet"))
    mtime = max((f.stat().st_mtime for f in files), default=0.0)
    table = _profiles(mtime)
    if account_id not in table.index:
        return {}
    p = table.loc[account_id]
    return {"n_tx": int(p["p_n_tx"]), "avg_amount": float(p["p_avg_amount"]), "max_amount": float(p["p_max_amount"]),
            "devices": list(p["p_devices"]), "receivers": list(p["p_receivers"]), "cities": list(p["p_cities"])}


def account_counterparts(df: pd.DataFrame, account_id: str) -> pd.DataFrame:
    """Comptes en relation avec `account_id` dans `df` (sans accès à MongoDB, testable).

    Colonnes : counterpart, direction (Envoyé / Reçu / Les deux), n, amount, max_score, worst_level, first_ts.
    """
    if df.empty:
        return pd.DataFrame(columns=["counterpart", "direction", "n", "amount", "max_score", "worst_level", "first_ts"])
    sent = df["sender_id"] == account_id
    links = df.assign(counterpart=df["receiver_id"].where(sent, df["sender_id"]),
                      direction=sent.map({True: "Envoyé", False: "Reçu"}),
                      risk_rank=df["risk_level"].map(RISK_ORDER).fillna(0))
    out = links.groupby("counterpart").agg(
        n=("transaction_id", "size"), amount=("amount", "sum"), max_score=("fraud_score", "max"),
        risk_rank=("risk_rank", "max"), first_ts=("timestamp", "min"),
        directions=("direction", lambda d: "Les deux" if d.nunique() > 1 else d.iloc[0]),
    ).reset_index()
    out["worst_level"] = out["risk_rank"].map({v: k for k, v in RISK_ORDER.items()})
    out = out.rename(columns={"directions": "direction"}).drop(columns="risk_rank")
    return out.sort_values(["max_score", "amount"], ascending=False).reset_index(drop=True)


def threshold_options(metrics: dict, min_threshold: float = 0.05) -> list:
    """Seuils dont on connaît les chiffres EXACTS sur la période de test, du plus bas au plus haut.

    Chaque point de la courbe précision-rappel enregistrée par train_model est exact pour la règle
    « alerte si score >= seuil » ; on y ajoute les deux seuils de la configuration (0,50 et 0,80).
    Chaque option : threshold, caught, missed, false_alerts, precision, recall.
    """
    n_fraud = metrics["n_test_fraud"]
    options = {}
    for key in ("at_high", "at_medium"):  # prioritaires si deux seuils s'affichent pareil (0,80 et 0,8 ...)
        m = metrics.get(key)
        if m:
            options[round(m["threshold"], 2)] = {"threshold": m["threshold"], "caught": m["tp"], "missed": m["fn"],
                                                 "false_alerts": m["fp"], "precision": m["precision"],
                                                 "recall": m["recall"]}
    for p in metrics.get("pr_curve", []):
        key = round(p["threshold"], 2)
        if p["threshold"] < min_threshold or key in options or p["precision"] <= 0:
            continue
        caught = round(p["recall"] * n_fraud)
        alerts = round(caught / p["precision"])
        options[key] = {"threshold": p["threshold"], "caught": caught, "missed": n_fraud - caught,
                        "false_alerts": alerts - caught, "precision": p["precision"], "recall": p["recall"]}
    return [options[k] for k in sorted(options)]
