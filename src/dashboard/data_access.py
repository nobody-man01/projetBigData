"""Accès MongoDB pour le dashboard. Les pages Streamlit appellent UNIQUEMENT ces fonctions (jamais pymongo directement)."""
import json

import pandas as pd
from pymongo import MongoClient

from config.settings import COL_RAW, COL_SCORED, METRICS_PATH, MONGO_DB, MONGO_URI


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
