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

from config.settings import DATASET_PATH, KAFKA_BOOTSTRAP, KAFKA_TOPIC_RAW  # noqa: F401
from src.common.schema import validate_transaction  # noqa: F401


def row_to_message(row: dict) -> dict:
    """Convertit une ligne pandas en dict JSON-sérialisable (types Python natifs : float, int, str).

    À FAIRE par M3 : attention aux numpy.int64 / numpy.float64 qui ne sont pas sérialisables en JSON.
    """
    raise NotImplementedError


def run(rate: float, limit: int = None) -> None:
    raise NotImplementedError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=float, default=20.0, help="transactions par seconde")
    p.add_argument("--limit", type=int, default=None, help="nombre max de transactions")
    a = p.parse_args()
    run(a.rate, a.limit)


if __name__ == "__main__":
    main()
