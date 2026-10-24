"""Configuration centrale. TOUS les modules importent d'ici (jamais de valeur en dur ailleurs)."""
import os
from importlib.metadata import PackageNotFoundError, version
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


def _spark_kafka_package() -> str:
    """Connecteur Kafka adapté au Spark installé (Spark 3.x : Scala 2.12, Spark 4.x : Scala 2.13)."""
    try:
        spark_version = version("pyspark")
    except PackageNotFoundError:
        try:  # pyspark fourni par l'installation de Spark (image Docker du cluster) et non par pip
            import pyspark
            spark_version = pyspark.__version__
        except ImportError:  # Spark non installé (équipiers hors ML, CI)
            spark_version = "3.5.1"
    scala = "2.13" if int(spark_version.split(".")[0]) >= 4 else "2.12"
    return f"org.apache.spark:spark-sql-kafka-0-10_{scala}:{spark_version}"


SPARK_KAFKA_PACKAGE = os.getenv("SPARK_KAFKA_PACKAGE") or _spark_kafka_package()
# local[*] : Spark sur cette machine ; spark://spark-master:7077 : cluster (docker-compose.cluster.yml)
SPARK_MASTER = os.getenv("SPARK_MASTER", "local[*]")

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "momo_fraud")
COL_RAW = "transactions"            # écrit par M4 (consumer)
COL_SCORED = "scored_transactions"  # écrit par le lead (Spark), lu par le dashboard

# --- Fichiers ---
DATA_DIR = ROOT / "data"
DATASET_PATH = DATA_DIR / "transactions.csv"
MODEL_PATH = ROOT / "models" / "fraud_pipeline"
PROFILES_PATH = ROOT / "models" / "account_profiles"   # profils de comptes (couche batch)
METRICS_PATH = ROOT / "models" / "metrics.json"        # métriques du dernier entraînement
CHECKPOINT_DIR = ROOT / "checkpoints" / "scoring"
# Intervalle des micro-lots du scoring temps réel (fixe une bonne part de la latence)
TRIGGER_INTERVAL = os.getenv("TRIGGER_INTERVAL", "5 seconds")

# --- Seuils de risque (appliqués sur la probabilité de fraude) ---
THRESHOLD_HIGH = 0.80
THRESHOLD_MEDIUM = 0.50
