"""MEMBRE 4 : Consumer Kafka -> MongoDB (stockage des transactions brutes dans `transactions`).

Usage:
    python -m src.ingestion.mongo_consumer

Fonctionnement :
  - crée les index au démarrage : transaction_id (unique), timestamp, sender_id ;
  - consomme config.settings.KAFKA_TOPIC_RAW (group_id="mongo-writer") ;
  - écrit en lots de 200 messages max ou toutes les 2 s, avec upsert sur transaction_id
    (si le même message arrive deux fois, il n'y a PAS de doublon) ;
  - convertit le champ timestamp (texte ISO 8601) en datetime avant stockage ;
  - affiche un compteur et se ferme proprement sur Ctrl+C.
"""
import json
import time
from datetime import datetime

from kafka import KafkaConsumer
from pymongo import ASCENDING, MongoClient, ReplaceOne

from config.settings import COL_RAW, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW, MONGO_DB, MONGO_URI

BATCH_SIZE = 200
FLUSH_EVERY_S = 2.0


def ensure_indexes(collection) -> None:
    """Index unique sur transaction_id (anti-doublon) + index de recherche sur timestamp et sender_id."""
    collection.create_index([("transaction_id", ASCENDING)], unique=True)
    collection.create_index([("timestamp", ASCENDING)])
    collection.create_index([("sender_id", ASCENDING)])


def to_document(message: dict) -> dict:
    """Prépare une transaction pour MongoDB : timestamp texte -> datetime (requêtes par date possibles)."""
    doc = dict(message)
    doc["timestamp"] = datetime.fromisoformat(doc["timestamp"])
    return doc


def write_batch(collection, batch: list) -> int:
    """Upsert du lot sur transaction_id. Retourne le nombre de documents écrits."""
    if not batch:
        return 0
    collection.bulk_write(
        [ReplaceOne({"transaction_id": d["transaction_id"]}, d, upsert=True) for d in batch],
        ordered=False,
    )
    return len(batch)


def run() -> None:
    """Boucle principale : lit Kafka, regroupe en lots, écrit dans MongoDB."""
    client = MongoClient(MONGO_URI)
    collection = client[MONGO_DB][COL_RAW]
    ensure_indexes(collection)
    consumer = KafkaConsumer(
        KAFKA_TOPIC_RAW,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="mongo-writer",
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    print(f"Lecture de '{KAFKA_TOPIC_RAW}' -> MongoDB {MONGO_DB}.{COL_RAW} (Ctrl+C pour arrêter)")
    batch, written, last_flush = [], 0, time.monotonic()
    try:
        while True:
            # poll rend la main au plus tard après 500 ms, même sans message : on peut vider le lot à temps
            for records in consumer.poll(timeout_ms=500).values():
                for record in records:
                    batch.append(to_document(record.value))
            if len(batch) >= BATCH_SIZE or (batch and time.monotonic() - last_flush >= FLUSH_EVERY_S):
                written += write_batch(collection, batch)
                print(f"  {written} transactions écrites")
                batch, last_flush = [], time.monotonic()
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        written += write_batch(collection, batch)
        consumer.close()
        client.close()
        print(f"Terminé : {written} transactions écrites au total.")


if __name__ == "__main__":
    run()
