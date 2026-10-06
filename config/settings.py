"""Configuration centrale. TOUS les modules importent d'ici (jamais de valeur en dur ailleurs)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv optionnel
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[1]
if load_dotenv:
    load_dotenv(ROOT / ".env")

# --- Kafka ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "momo.transactions.raw")
SPARK_KAFKA_PACKAGE = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1"

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "momo_fraud")
COL_RAW = "transactions"            # écrit par M4 (consumer)
COL_SCORED = "scored_transactions"  # écrit par le lead (Spark), lu par le dashboard

# --- Fichiers ---
DATA_DIR = ROOT / "data"
DATASET_PATH = DATA_DIR / "transactions.csv"
MODEL_PATH = ROOT / "models" / "fraud_pipeline"
CHECKPOINT_DIR = ROOT / "checkpoints" / "scoring"

# --- Seuils de risque (appliqués sur la probabilité de fraude) ---
THRESHOLD_HIGH = 0.80
THRESHOLD_MEDIUM = 0.50
