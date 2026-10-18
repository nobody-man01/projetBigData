#!/usr/bin/env bash
# Mode cluster : Kafka à 3 brokers + Spark standalone (1 master, 2 workers). Voir docker-compose.cluster.yml.
#
#   bash scripts/cluster.sh up        démarre le cluster (construit l'image Spark au premier lancement)
#   bash scripts/cluster.sh train     entraîne le modèle SUR le cluster (arguments passés à train_model)
#   bash scripts/cluster.sh demo      scoring sur le cluster + consumer, producer et dashboard sur la machine
#   bash scripts/cluster.sh panne     arrête un broker Kafka 60 s pendant le flux, puis le relance
#   bash scripts/cluster.sh etat      état des brokers, du topic et des workers
#   bash scripts/cluster.sh down      arrête le cluster
#
# Le mode simple (docker-compose.yml, scripts/demo.sh) utilise les mêmes ports : arrêtez l'un avant l'autre.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.cluster.yml)
PY="${PYTHON:-python}"
RATE="${RATE:-20}"
TOPIC=momo.transactions.raw
# Depuis la machine hôte, les trois brokers répondent sur trois ports différents
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092,localhost:9094,localhost:9096
mkdir -p logs

step() { printf '\n\033[1;33m▶ %s\033[0m\n' "$1"; }
topic() { docker exec momo-kafka-1 /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka-1:19092 --describe --topic "$TOPIC"; }
workers() { curl -s localhost:8080/json/ | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"Spark : {d['aliveworkers']} workers, {d['cores']} cœurs, {d['memory']} Mo\")"; }

case "${1:-}" in
  up)
    if docker ps -a --format '{{.Names}}' | grep -q '^momo-kafka$'; then
      echo "Le mode simple est présent (mêmes noms et mêmes ports) : lancez d'abord  docker compose down"; exit 1
    fi
    step "Démarrage du cluster"
    HOST_UID=$(id -u) HOST_GID=$(id -g) "${COMPOSE[@]}" up -d --build
    until [ "$(docker inspect -f '{{.State.Status}}' momo-kafka-init 2>/dev/null)" = exited ]; do sleep 3; done
    topic
    until curl -s localhost:8080/json/ | grep -q '"aliveworkers" : 2'; do sleep 2; done
    workers
    echo "Interface Spark : http://localhost:8080"
    ;;
  train)
    shift
    [ $# -eq 0 ] && set -- --algo rf
    step "Entraînement sur le cluster Spark (suivi : http://localhost:8080)"
    time docker exec momo-spark-app python3 -u -m src.ml.train_model "$@" --test-data data/transactions_test.csv
    ;;
  demo)
    PIDS=()
    trap 'step "Arrêt"; for p in "${PIDS[@]}"; do kill -INT "$p" 2>/dev/null || true; done;
          docker exec momo-spark-app pkill -INT -f streaming_scoring || true; wait 2>/dev/null || true' EXIT INT TERM
    step "Scoring Spark Streaming sur le cluster (journal : logs/scoring_cluster.log)"
    rm -rf checkpoints/scoring   # les positions Kafka du mode simple ne valent pas pour ce cluster
    docker exec momo-spark-app sh -c 'python3 -u -m src.ml.streaming_scoring > logs/scoring_cluster.log 2>&1' & PIDS+=($!)
    until grep -q "profils de comptes chargés" logs/scoring_cluster.log 2>/dev/null; do sleep 2; done
    sleep 45   # premiers micro-lots lents (JVM, modèle) : on laisse le scoring se lancer avant le flux
    step "Consumer et producer sur la machine, reliés aux 3 brokers"
    $PY -u -m src.ingestion.mongo_consumer > logs/consumer.log 2>&1 & PIDS+=($!)
    $PY -u -m src.ingestion.producer --rate "$RATE" --data data/transactions_test.csv > logs/producer.log 2>&1 & PIDS+=($!)
    step "Dashboard : http://localhost:8501"
    $PY -m streamlit run src/dashboard/app.py
    ;;
  panne)
    step "État avant la panne"; topic
    step "Arrêt du broker kafka-2 pendant 60 s"
    docker stop momo-kafka-2 >/dev/null
    sleep 5; topic
    echo "Le flux continue : les partitions dont kafka-2 était leader ont un nouveau leader parmi les réplicas synchrones."
    sleep 55
    step "Redémarrage de kafka-2"
    docker start momo-kafka-2 >/dev/null
    until docker inspect -f '{{.State.Health.Status}}' momo-kafka-2 | grep -q healthy; do sleep 2; done
    sleep 10; topic
    ;;
  etat)
    "${COMPOSE[@]}" ps --format 'table {{.Name}}\t{{.Status}}'
    topic; workers
    ;;
  down)
    "${COMPOSE[@]}" down   # supprime les conteneurs, garde les données (volumes)
    ;;
  *)
    sed -n '2,10p' "$0"; exit 1
    ;;
esac
