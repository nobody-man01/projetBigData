"""MEMBRE 3 : Producer Kafka. Rejoue le dataset CSV vers le topic Kafka comme un flux temps réel.

Usage attendu:
    python -m src.ingestion.producer --rate 20          # 20 transactions/seconde
    python -m src.ingestion.producer --rate 100 --limit 5000

À FAIRE (voir docs/TACHES.md, fiche M3) :
  - lire config.settings.DATASET_PATH avec pandas (par paquets de 10 000 lignes, pas tout en mémoire)
  - valider chaque ligne avec src.common.schema.validate_transaction (ignorer + compter les invalides)
  - envoyer chaque transaction en JSON (UTF-8) sur config.settings.KAFKA_TOPIC_RAW
    avec key=transaction_id (bytes), via kafka-python KafkaProducer
  - respecter le débit --rate (time.sleep), afficher un compteur toutes les 5 secondes
  - flush() proprement à la fin ou sur Ctrl+C
"""
import argparse
import json
import logging
import math
import threading
import time

import numpy as np
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from config.settings import DATASET_PATH, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW
from src.common.schema import FIELDS, validate_transaction

CHUNK_SIZE = 10_000
REPORT_EVERY_S = 5.0
FLUSH_TIMEOUT_S = 30
MAX_LOGGED_INVALID = 5

log = logging.getLogger("producer")

# Compteur d'échecs d'envoi, mis à jour depuis le thread réseau de kafka-python.
_errors = 0
_errors_lock = threading.Lock()


def _to_native(value):
    """Convertit une valeur pandas/numpy en type Python natif sérialisable en JSON."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # NaN / inf ne sont pas du JSON valide
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def row_to_message(row: dict) -> dict:
    """Convertit une ligne pandas en dict JSON-sérialisable (types Python natifs : float, int, str)."""
    return {str(k): _to_native(v) for k, v in row.items()}


def _validation_errors(message: dict) -> list:
    """Retourne la liste des erreurs de validation (liste vide = transaction valide)."""
    try:
        return validate_transaction(message)
    except Exception as exc:  # une ligne corrompue ne doit jamais arrêter le flux
        return [f"exception de validation: {exc}"]


def _serialize_key(key) -> bytes:
    return str(key).encode("utf-8")


def _serialize_value(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")


def _on_send_error(exc) -> None:
    global _errors
    with _errors_lock:
        _errors += 1
    log.error("Échec d'envoi Kafka : %s", exc)


def _iter_rows():
    """Génère les lignes du CSV une par une, en lisant par paquets pour limiter la mémoire."""
    # Les colonnes texte du contrat (ids, ville...) sont lues en str : sans cela, pandas
    # transformerait un identifiant numérique en entier et la validation le rejetterait.
    dtypes = {name: str for name, typ in FIELDS.items() if typ is str}
    for chunk in pd.read_csv(DATASET_PATH, chunksize=CHUNK_SIZE, dtype=dtypes):
        yield from chunk.to_dict("records")


def run(rate: float, limit: int = None) -> None:
    if rate <= 0:
        raise ValueError("--rate doit être strictement positif")

    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            key_serializer=_serialize_key,
            value_serializer=_serialize_value,
            acks="all",
            retries=5,
            linger_ms=20,
            batch_size=32 * 1024,
        )
    except NoBrokersAvailable:
        log.error("Aucun broker Kafka joignable sur %s", KAFKA_BOOTSTRAP)
        raise SystemExit(1)

    sent = 0
    invalid = 0
    start = last_report = time.monotonic()

    try:
        for row in _iter_rows():
            if limit is not None and sent >= limit:
                break

            message = row_to_message(row)
            errors = _validation_errors(message)
            if errors:
                invalid += 1
                if invalid <= MAX_LOGGED_INVALID:
                    log.warning("Transaction invalide ignorée : %s", errors)
                continue

            producer.send(
                KAFKA_TOPIC_RAW, key=message["transaction_id"], value=message
            ).add_errback(_on_send_error)
            sent += 1

            # Contrôle du débit : on vise l'heure théorique du n-ième message.
            delay = start + sent / rate - time.monotonic()
            if delay > 0:
                time.sleep(delay)

            now = time.monotonic()
            if now - last_report >= REPORT_EVERY_S:
                log.info(
                    "envoyés=%d invalides=%d erreurs=%d débit=%.1f/s",
                    sent, invalid, _errors, sent / (now - start),
                )
                last_report = now
    except KeyboardInterrupt:
        log.warning("Interruption demandée : arrêt propre en cours")
    finally:
        producer.flush(timeout=FLUSH_TIMEOUT_S)
        producer.close()
        elapsed = max(time.monotonic() - start, 1e-9)
        log.info(
            "TERMINÉ envoyés=%d invalides=%d erreurs=%d durée=%.1fs débit moyen=%.1f/s",
            sent, invalid, _errors, elapsed, sent / elapsed,
        )


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=float, default=20.0, help="transactions par seconde")
    p.add_argument("--limit", type=int, default=None, help="nombre max de transactions")
    a = p.parse_args()
    run(a.rate, a.limit)


if __name__ == "__main__":
    main()