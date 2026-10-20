# Détection de fraude Mobile Money – Groupe 7

Pipeline Big Data temps réel : **Générateur → Kafka → MongoDB → Spark MLlib → Streamlit**.

## Structure
```
config/settings.py        configuration centrale
src/common/schema.py      contrat de données (format d'une transaction)
src/generator/            M2  génération des données
src/ingestion/            M3 producer Kafka, M4 consumer -> MongoDB
src/ml/                   M1  features, entraînement, scoring streaming
src/dashboard/            M5/M6 pages Streamlit, data_access.py partagé
docs/                     architecture, tâches, plan du rapport
tests/                    tests automatiques
```
Répartition : `docs/TACHES.md`. Workflow Git : `CONTRIBUTING.md`. Architecture : `docs/ARCHITECTURE.md`.

## Démarrage rapide (nouvel équipier)
```bash
git clone https://github.com/nobody-man01/projetBigData.git && cd projetBigData
python -m venv .venv && source .venv/bin/activate     # ou activez votre environnement du cours
pip install -r requirements.txt && cp .env.example .env
pytest -q                                              # doit afficher « passed »
```
Ensuite : lire sa fiche dans `docs/TACHES.md` (ou son Issue sur GitHub) et suivre `CONTRIBUTING.md`.

## Démo en une commande
```bash
bash scripts/demo.sh          # Docker, modèle si absent, scoring, consumer, producer puis dashboard
```
Dashboard : http://localhost:8501 · mongo-express : http://localhost:8081 · journaux : `logs/`.

## Mode cluster (Kafka 3 brokers + Spark 1 master / 2 workers)
```bash
docker compose down                 # le mode simple et le mode cluster utilisent les mêmes ports
bash scripts/cluster.sh up          # construit l'image Spark au premier lancement (quelques minutes)
bash scripts/cluster.sh train       # entraînement sur le cluster (suivi : http://localhost:8080)
bash scripts/cluster.sh demo        # scoring sur le cluster, flux et dashboard sur la machine
bash scripts/cluster.sh panne       # arrêt d'un broker pendant le flux : aucune transaction perdue
bash scripts/cluster.sh down
```
Détails et mesures : `notebooks/05_cluster.ipynb`. PaySim (6,36 millions de transactions) : `notebooks/06_paysim.ipynb`.

## Démarrage complet (ordre des commandes, un terminal chacune)
```bash
pip install -r requirements-spark.txt && cp .env.example .env   # inclut Spark
docker compose up -d                                   # Kafka + MongoDB + mongo-express
# septembre (entraînement, 2 % de fraudes) + semaine de test séparée à 0,3 % de fraudes (voir docs/DONNEES.md)
python -m src.generator.generate_dataset --n 250000 --days 30 --test-days 7 --test-fraud-rate 0.003 --seed 42
python -m src.ml.train_model --compare --test-data data/transactions_test.csv   # compare 3 algorithmes, sauvegarde modèle + métriques
python -m src.ml.streaming_scoring                     # terminal 1 : scoring temps réel
python -m src.ingestion.mongo_consumer                 # terminal 2 : stockage brut
python -m src.ingestion.producer --rate 20 --data data/transactions_test.csv   # terminal 3 : rejoue la semaine de test
streamlit run src/dashboard/app.py                     # terminal 4 : dashboard
```
Prérequis : Python 3.10+ et Docker. Pour la partie ML seulement : Spark 3.5 (Java 11/17) ou Spark 4.x (Java 17+).
Vous pouvez réutiliser votre environnement Python du cours : `pip install -r requirements.txt` n'ajoute que ce qui manque, sans imposer de version de Spark.
