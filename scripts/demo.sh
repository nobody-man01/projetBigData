#!/usr/bin/env bash
# Lance toute la démo d'une seule commande : bash scripts/demo.sh  (Ctrl+C arrête tout proprement)
#
#   1. Kafka + MongoDB + mongo-express (Docker)
#   2. données et modèle (seulement s'ils n'existent pas encore)
#   3. scoring Spark, consumer MongoDB, producer (période de test, jamais vue à l'entraînement)
#   4. dashboard sur http://localhost:8501
#
# Variables utiles : RATE=50 bash scripts/demo.sh   (transactions par seconde, 20 par défaut)
set -euo pipefail
cd "$(dirname "$0")/.."
RATE="${RATE:-20}"
PY="${PYTHON:-python}"
LOGS=logs
mkdir -p "$LOGS"

step() { printf '\n\033[1;33m▶ %s\033[0m\n' "$1"; }

PIDS=()
cleanup() {
  step "Arrêt de la démo"
  for pid in "${PIDS[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  echo "Les conteneurs Docker restent allumés (docker compose down pour les arrêter)."
}
trap cleanup EXIT INT TERM

step "1/4 Démarrage de Kafka et MongoDB"
docker compose up -d
until docker inspect -f '{{.State.Health.Status}}' momo-kafka 2>/dev/null | grep -q healthy; do sleep 2; done

step "2/4 Données et modèle"
[ -f data/transactions.csv ] || $PY -m src.generator.generate_dataset --n 200000
[ -f models/metrics.json ] || $PY -m src.ml.train_model --compare
SINCE=$($PY -c "import json; print(json.load(open('models/metrics.json'))['test_period_start'])")
echo "Rejeu des transactions à partir du $SINCE (période de test)"

step "3/4 Scoring Spark, consumer et producer (journaux dans $LOGS/)"
$PY -u -m src.ml.streaming_scoring > "$LOGS/scoring.log" 2>&1 & PIDS+=($!)
$PY -u -m src.ingestion.mongo_consumer > "$LOGS/consumer.log" 2>&1 & PIDS+=($!)
echo "Attente du démarrage de Spark (premier lancement : téléchargement du connecteur Kafka)..."
until grep -q "profils de comptes chargés" "$LOGS/scoring.log"; do
  kill -0 "${PIDS[0]}" 2>/dev/null || { echo "Le scoring s'est arrêté, voir $LOGS/scoring.log"; exit 1; }
  sleep 2
done
sleep 10   # laisse la requête streaming s'abonner au topic avant le premier envoi
$PY -u -m src.ingestion.producer --rate "$RATE" --since "$SINCE" > "$LOGS/producer.log" 2>&1 & PIDS+=($!)

step "4/4 Dashboard : http://localhost:8501  (mongo-express : http://localhost:8081)"
$PY -m streamlit run src/dashboard/app.py
