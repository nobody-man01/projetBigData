#!/usr/bin/env bash
# Lance toute la démo d'une seule commande : bash scripts/demo.sh  (Ctrl+C arrête tout proprement)
#
#   1. Kafka + MongoDB + mongo-express (Docker)
#   2. données et modèle (seulement s'ils n'existent pas encore)
#   3. scoring Spark, consumer MongoDB, producer (période de test, jamais vue à l'entraînement)
#   4. dashboard sur http://localhost:8501
#
# Prérequis : l'environnement Python du projet activé (pip install -r requirements-spark.txt), Docker lancé.
# Variables utiles : RATE=50 bash scripts/demo.sh   (transactions par seconde, 20 par défaut)
#                    KEEP_DATA=1 bash scripts/demo.sh   (garde les transactions déjà dans MongoDB)
set -euo pipefail
cd "$(dirname "$0")/.."
RATE="${RATE:-20}"
PY="${PYTHON:-python}"
LOGS=logs
mkdir -p "$LOGS"

# Vérification avant de démarrer quoi que ce soit : le Python utilisé a-t-il toutes les bibliothèques ?
if ! $PY -c "import pyspark, streamlit, kafka, pymongo, pandas, plotly" 2>/dev/null; then
  echo "Python utilisé : $(command -v "$PY" || echo "$PY introuvable")"
  echo "Il manque des bibliothèques (pyspark, streamlit, kafka-python, pymongo, pandas ou plotly)."
  echo "Activez l'environnement Python du projet (pip install -r requirements-spark.txt), ou PYTHON=/chemin/python bash scripts/demo.sh"
  exit 1
fi

step() { printf '\n\033[1;33m▶ %s\033[0m\n' "$1"; }

# Sans contrôle des tâches, bash lance les programmes en arrière-plan en ignorant Ctrl+C (SIGINT) : ils ne
# s'arrêteraient pas. Avec set -m, chacun a son propre groupe et reçoit le SIGINT envoyé par cleanup.
set -m
PIDS=()
cleanup() {
  step "Arrêt de la démo"
  for pid in "${PIDS[@]}"; do kill -INT "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  echo "Les conteneurs Docker restent allumés (docker compose down pour les arrêter)."
}
trap cleanup EXIT INT TERM

step "1/4 Démarrage de Kafka et MongoDB"
if docker ps -a --format '{{.Names}}' | grep -q '^momo-kafka-1$'; then
  echo "Le mode cluster est présent (mêmes noms et mêmes ports) : lancez d'abord  bash scripts/cluster.sh down"; exit 1
fi
docker compose up -d
until docker inspect -f '{{.State.Health.Status}}' momo-kafka 2>/dev/null | grep -q healthy; do sleep 2; done
until [ "$(docker inspect -f '{{.State.Status}}' momo-kafka-init 2>/dev/null)" = exited ]; do sleep 2; done   # topic créé

step "2/4 Données et modèle"
[ -f data/transactions.csv ] || $PY -m src.generator.generate_dataset --n 250000 --days 30 --test-days 7 --test-fraud-rate 0.003 --seed 42
[ -f models/metrics.json ] || $PY -m src.ml.train_model --compare --test-data data/transactions_test.csv
# Rejeu de la période de test (jamais vue à l'entraînement) : fichier séparé s'il existe, sinon fin du fichier principal
if [ -f data/transactions_test.csv ]; then REPLAY=(--data data/transactions_test.csv); else
  REPLAY=(--since "$($PY -c "import json; print(json.load(open('models/metrics.json'))['test_period_start'])")"); fi
echo "Rejeu de la période de test : ${REPLAY[*]}"

step "3/4 Scoring Spark, consumer et producer (journaux dans $LOGS/)"
# Kafka ne garde pas ses messages d'un lancement à l'autre (pas de volume) : les positions mémorisées par Spark
# lors d'une démo précédente ne valent plus, on les efface. Les collections MongoDB sont vidées pour que le tableau
# de bord parte de zéro (KEEP_DATA=1 pour les garder) ; le producer rejoue la semaine de test depuis le début.
rm -rf checkpoints/scoring
until docker exec momo-mongo mongosh --quiet --eval 'db.runCommand({ping: 1})' >/dev/null 2>&1; do sleep 1; done
if [ "${KEEP_DATA:-0}" != 1 ]; then
  docker exec momo-mongo mongosh momo_fraud --quiet --eval 'db.transactions.drop(); db.scored_transactions.drop()' >/dev/null
  echo "MongoDB vidé : le tableau de bord part de zéro."
fi
$PY -u -m src.ml.streaming_scoring > "$LOGS/scoring.log" 2>&1 & PIDS+=($!)
$PY -u -m src.ingestion.mongo_consumer > "$LOGS/consumer.log" 2>&1 & PIDS+=($!)
echo "Attente du démarrage de Spark (premier lancement : téléchargement du connecteur Kafka)..."
until grep -q "profils de comptes chargés" "$LOGS/scoring.log"; do
  kill -0 "${PIDS[0]}" 2>/dev/null || { echo "Le scoring s'est arrêté, voir $LOGS/scoring.log"; exit 1; }
  sleep 2
done
sleep 10   # laisse la requête streaming s'abonner au topic avant le premier envoi
$PY -u -m src.ingestion.producer --rate "$RATE" "${REPLAY[@]}" > "$LOGS/producer.log" 2>&1 & PIDS+=($!)

step "4/4 Dashboard : http://localhost:8501  (mongo-express : http://localhost:8081)"
$PY -m streamlit run src/dashboard/app.py
