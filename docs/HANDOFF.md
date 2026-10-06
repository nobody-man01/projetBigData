# HANDOFF – état du projet (à coller dans Gemini pour continuer de façon cohérente)

**Projet** : détection de fraude Mobile Money, Groupe 7 (7 membres). Stack imposée : Kafka, MongoDB, Spark MLlib, Streamlit.
**Pipeline** : générateur CSV → producer Kafka → topic `momo.transactions.raw` → (a) consumer → Mongo `transactions` ; (b) Spark Structured Streaming + PipelineModel → Mongo `scored_transactions` → dashboard Streamlit.

## Conventions à respecter (ne pas changer sans raison)
- Python 3.10+, lancement en modules : `python -m src.<paquet>.<module>` depuis la racine.
- Toute configuration dans `config/settings.py`. Contrat de données dans `src/common/schema.py` (champs `FIELDS` + `SCORED_EXTRA`).
- Un fichier par membre (pas de conflits Git). Dashboard : pages dans `src/dashboard/pages/`, accès Mongo uniquement via `src/dashboard/data_access.py`.
- Features Spark : une seule fonction `add_features` (`src/ml/features.py`), utilisée à l'entraînement ET en streaming.
- Upserts sur `transaction_id` partout (idempotence). Docstrings en français.

## Fait
- Squelette complet : `docker-compose.yml` (Kafka KRaft 3.8, Mongo 7, mongo-express), config, schéma + validation, README, CONTRIBUTING, docs (ARCHITECTURE, TACHES, RAPPORT_PLAN).
- Générateur v0 fonctionnel (`generate_dataset.py`), 4 tests pytest qui passent.
- Lead (`src/ml/`) : `features.py`, `train_model.py` (RandomForest pondéré, split temporel à 80 %, AUC-PR/ROC/F1), `streaming_scoring.py` (Kafka → modèle → upsert Mongo via foreachBatch). **Écrits et compilés mais jamais exécutés** (PySpark indisponible dans l'environnement de Claude).
- `data_access.py` du dashboard (KPIs, suspects, série temporelle, top comptes) écrit, non testé avec une vraie base.
- Squelettes avec consignes détaillées : `producer.py` (M3), `mongo_consumer.py` (M4), pages dashboard (M5, M6).

## Reste à faire (ordre conseillé)
1. **Valider en local** : `docker compose up -d`, générer le CSV, `python -m src.ml.train_model`, corriger les éventuelles erreurs Spark (premier test réel).
2. M3 et M4 implémentent producer et consumer (fiches dans `docs/TACHES.md`).
3. Tester `streaming_scoring.py` avec producer actif (vérifier `scored_transactions` dans mongo-express, http://localhost:8081).
4. M5 et M6 construisent les pages Streamlit.
5. M2 enrichit le générateur (3 scénarios de fraude + réalisme) ; ré-entraîner ensuite.
6. Lead : comparer RF / GBT / régression logistique, importance des features, ajuster `THRESHOLD_HIGH/MEDIUM`.
7. M7 : rapport (`RAPPORT_PLAN.md`), notebook d'exploration, captures, présentation.
8. Intégration finale, test de bout en bout, mise au propre.

## Points d'attention connus
- Dépôt GitHub : la session Claude n'a pas pu accéder au dépôt (liste vide). Copier le dossier `momo-fraud-detection/` dans le dépôt puis `git add . && git commit && git push`.
- Spark a besoin de Java 11/17 et télécharge le package Kafka (`spark-sql-kafka-0-10_2.12:3.5.1`) au premier lancement (internet requis).
- Si le streaming ne reçoit rien : vérifier que `startingOffsets` est `latest` (le producer doit tourner APRÈS le démarrage du scoring) ou passer à `earliest`.
- Le générateur v0 est volontairement simple : le modèle peut y obtenir des scores artificiellement élevés (fraudes = soldes vidés). Ne pas présenter ces métriques telles quelles avant l'enrichissement par M2.
