"""MEMBRE 4 : Consumer Kafka -> MongoDB (stockage des transactions brutes dans `transactions`).

Usage attendu:
    python -m src.ingestion.mongo_consumer

À FAIRE (voir docs/TACHES.md, fiche M4) :
  - créer les index au démarrage via ensure_indexes() :
      transaction_id (unique), timestamp, sender_id
  - consommer config.settings.KAFKA_TOPIC_RAW (group_id="mongo-writer") avec kafka-python KafkaConsumer
  - écrire en lots (bulk) de 200 messages max ou toutes les 2 s, avec upsert sur transaction_id
    (si le même message arrive 2 fois, il ne doit PAS y avoir de doublon)
  - convertir le champ timestamp (str) en datetime avant stockage
  - afficher un compteur de messages écrits, fermer proprement sur Ctrl+C
"""
from config.settings import COL_RAW, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW, MONGO_DB, MONGO_URI  # noqa: F401


def ensure_indexes(collection) -> None:
    raise NotImplementedError


def run() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    run()
