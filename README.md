# 🛡️ Détection de fraude Mobile Money – Groupe 7

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

## Démarrage complet (ordre des commandes, un terminal chacune)
```bash
pip install -r requirements.txt && cp .env.example .env
docker compose up -d                                   # Kafka + MongoDB + mongo-express
python -m src.generator.generate_dataset --n 200000    # crée data/transactions.csv (voir docs/DONNEES.md pour PaySim)
python -m src.ml.train_model                           # entraîne et sauvegarde le modèle
python -m src.ml.streaming_scoring                     # terminal 1 : scoring temps réel
python -m src.ingestion.mongo_consumer                 # terminal 2 : stockage brut
python -m src.ingestion.producer --rate 20             # terminal 3 : flux de transactions
streamlit run src/dashboard/app.py                     # terminal 4 : dashboard
```
Prérequis : Python 3.10+, Java 11 ou 17 (pour Spark), Docker.
