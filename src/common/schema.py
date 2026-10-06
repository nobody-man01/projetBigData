"""CONTRAT DE DONNÉES : format unique d'une transaction pour tout le projet.

Ne pas modifier sans prévenir le lead (impact sur Kafka, Mongo, Spark, dashboard).
"""
from datetime import datetime

TX_TYPES = ["CASH_IN", "CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME"]
OPERATORS = ["MTN_MOMO", "ORANGE_MONEY"]
CHANNELS = ["USSD", "APP", "AGENT"]
CITIES = ["Douala", "Yaounde", "Bafoussam", "Garoua", "Bamenda", "Bertoua", "Limbe", "Kribi"]

# Champs d'une transaction brute (ce qui circule dans Kafka et est stocké dans `transactions`)
FIELDS = {
    "transaction_id": str,
    "timestamp": str,              # ISO 8601 UTC, ex: 2026-10-06T08:15:30+00:00
    "sender_id": str,
    "receiver_id": str,
    "tx_type": str,                # voir TX_TYPES
    "amount": float,               # en XAF, > 0
    "sender_balance_before": float,
    "sender_balance_after": float,
    "receiver_balance_before": float,
    "receiver_balance_after": float,
    "operator": str,               # voir OPERATORS
    "channel": str,                # voir CHANNELS
    "city": str,                   # voir CITIES
    "device_id": str,
    "is_fraud": int,               # 0/1 : vérité terrain (sert à entraîner/évaluer, jamais comme feature)
}

# Champs ajoutés par le scoring Spark (collection `scored_transactions`)
SCORED_EXTRA = {
    "fraud_score": float,          # probabilité de fraude [0,1]
    "prediction": int,             # 0/1
    "risk_level": str,             # LOW | MEDIUM | HIGH
    "scored_at": str,              # ISO 8601 UTC
}


def validate_transaction(tx: dict) -> list:
    """Retourne la liste des erreurs (liste vide = transaction valide)."""
    errors = []
    for name, typ in FIELDS.items():
        if name not in tx:
            errors.append(f"champ manquant: {name}")
            continue
        value = tx[name]
        if typ is float and isinstance(value, (int, float)) and not isinstance(value, bool):
            continue
        if typ is int and isinstance(value, int) and not isinstance(value, bool):
            continue
        if typ is str and isinstance(value, str):
            continue
        errors.append(f"type invalide pour {name}: attendu {typ.__name__}, reçu {type(value).__name__}")
    if errors:
        return errors
    if tx["tx_type"] not in TX_TYPES:
        errors.append(f"tx_type inconnu: {tx['tx_type']}")
    if tx["operator"] not in OPERATORS:
        errors.append(f"operator inconnu: {tx['operator']}")
    if tx["channel"] not in CHANNELS:
        errors.append(f"channel inconnu: {tx['channel']}")
    if tx["amount"] <= 0:
        errors.append("amount doit être > 0")
    if tx["is_fraud"] not in (0, 1):
        errors.append("is_fraud doit valoir 0 ou 1")
    try:
        datetime.fromisoformat(tx["timestamp"])
    except ValueError:
        errors.append("timestamp non ISO 8601")
    return errors
