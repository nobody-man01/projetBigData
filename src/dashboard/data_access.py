"""Accès MongoDB pour le dashboard. Les pages Streamlit appellent UNIQUEMENT ces fonctions (jamais pymongo directement)."""
import pandas as pd
from pymongo import MongoClient

from config.settings import COL_SCORED, MONGO_DB, MONGO_URI


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
