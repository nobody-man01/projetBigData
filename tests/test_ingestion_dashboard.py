"""Tests sans Kafka ni MongoDB en marche : conversions du producer/consumer et raisons d'alerte.

Ignorés automatiquement si kafka-python ou pymongo ne sont pas installés (CI minimale).
"""
import json
from datetime import datetime

import numpy as np
import pytest

from src.common.schema import FIELDS, validate_transaction

pytest.importorskip("kafka")
pytest.importorskip("pymongo")

from src.dashboard.data_access import explain  # noqa: E402
from src.ingestion.mongo_consumer import to_document  # noqa: E402
from src.ingestion.producer import row_to_message  # noqa: E402

ROW = {
    "transaction_id": "tx-1", "timestamp": "2026-10-06T08:15:30+00:00", "sender_id": "237600000001",
    "receiver_id": "237600000002", "tx_type": "TRANSFER", "amount": np.float64(5000.0),
    "sender_balance_before": np.float64(20000.0), "sender_balance_after": np.float64(15000.0),
    "receiver_balance_before": np.float64(0.0), "receiver_balance_after": np.float64(5000.0),
    "operator": "MTN_MOMO", "channel": "APP", "city": "Douala", "device_id": "dev-1", "is_fraud": np.int64(0),
}


def test_row_to_message_types_natifs_et_json():
    msg = row_to_message(ROW)
    assert set(msg) == set(FIELDS)
    assert type(msg["amount"]) is float and type(msg["is_fraud"]) is int
    assert validate_transaction(msg) == []
    json.dumps(msg)  # ne doit pas lever d'erreur (numpy non sérialisable)


def test_to_document_convertit_le_timestamp():
    doc = to_document(row_to_message(ROW))
    assert isinstance(doc["timestamp"], datetime)
    assert doc["transaction_id"] == "tx-1"


def test_explain_donne_au_plus_trois_raisons():
    tx = {"device_is_new": 1, "receiver_is_new": 1, "amount_vs_avg": 12.0, "sender_emptied": 1, "is_night": 1}
    reasons = explain(tx)
    assert len(reasons) == 3
    assert reasons[0] == "Nouvel appareil pour ce compte"
    assert explain({}) == []
    assert explain({"pair_n_10min": 6.0})[0] == "6 opérations vers le même destinataire en 10 min"
