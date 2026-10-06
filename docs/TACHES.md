# Répartition des tâches – Groupe 7

Chaque membre travaille **dans ses propres fichiers** (aucun conflit Git) et respecte le contrat `src/common/schema.py`.
Chaque fiche peut être copiée-collée telle quelle à l'équipier concerné.

| Membre | Rôle | Fichiers à lui | Difficulté | Dépend de |
|---|---|---|---|---|
| **M1 (Lead)** | Features, modèle MLlib, scoring streaming, intégration, Docker | `src/ml/*`, `docker-compose.yml` | Élevée | tous |
| **M2** | Générateur de données réaliste | `src/generator/generate_dataset.py` | Facile | — |
| **M3** | Producer Kafka | `src/ingestion/producer.py` | Facile | M2 (CSV) |
| **M4** | Consumer Kafka → MongoDB | `src/ingestion/mongo_consumer.py` | Facile | M3 |
| **M5** | Dashboard : page Indicateurs | `src/dashboard/pages/1_Indicateurs.py` | Facile | `data_access.py` |
| **M6** | Dashboard : page Transactions suspectes | `src/dashboard/pages/2_Transactions_suspectes.py` | Facile | `data_access.py` |
| **M7** | Documentation, tests, rapport, présentation | `docs/*`, `tests/*`, `notebooks/*` | Facile | tous |

## Règles communes
1. `git pull` avant de commencer, branche `feature/<prenom>-<module>`, Pull Request vers `main` (voir `CONTRIBUTING.md`).
2. Jamais de valeur en dur (adresse Kafka, nom de collection...) : tout est dans `config/settings.py`.
3. Respecter les noms de champs de `src/common/schema.py`.
4. Chaque fonction a une docstring. Code lisible > code malin.
5. Lancer `pytest` avant chaque Pull Request.

---

## Fiche M2 – Générateur de données réaliste
**Objectif** : produire `data/transactions.csv` (≥ 200 000 lignes, ~2 % de fraudes) qui ressemble à du vrai Mobile Money camerounais.
**Fichier** : `src/generator/generate_dataset.py` (une version v0 fonctionne déjà, à améliorer).
**À faire** :
1. Lancer la v0 : `python -m src.generator.generate_dataset --n 200000` et regarder le CSV.
2. Ajouter ces scénarios de fraude (colonne `is_fraud = 1`), un par fonction `_scenario_xxx` :
   - **Prise de contrôle de compte** : nouveau `device_id` jamais vu pour ce `sender_id`, puis TRANSFER qui vide le solde.
   - **Rafale (velocity)** : un même `sender_id` fait 5 à 10 petites transactions en moins de 2 minutes vers des receveurs différents.
   - **Montant atypique** : montant 10 à 50 fois supérieur à la moyenne de l'expéditeur.
3. Rendre les transactions normales plus réalistes : plus d'activité en journée (7h–21h), montants arrondis (500, 1000, 5000 XAF) fréquents.
4. Garder **exactement** les colonnes de `schema.FIELDS`.
**Terminé quand** : `pytest tests/test_schema_and_generator.py` passe et le taux de fraude est entre 1 % et 4 %.

## Fiche M3 – Producer Kafka
**Objectif** : envoyer les transactions du CSV dans Kafka, comme un flux en direct.
**Fichier** : `src/ingestion/producer.py` (squelette + instructions dans le fichier).
**À faire** : implémenter `row_to_message` et `run` en suivant la liste « À FAIRE » du fichier.
**Test manuel** : `docker compose up -d`, puis `python -m src.ingestion.producer --rate 20 --limit 200`, puis vérifier avec :
`docker exec momo-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic momo.transactions.raw --from-beginning --max-messages 5`
**Terminé quand** : les messages JSON apparaissent dans la console et le débit demandé est respecté.

## Fiche M4 – Consumer Kafka → MongoDB
**Objectif** : stocker chaque transaction reçue dans MongoDB, sans doublon.
**Fichier** : `src/ingestion/mongo_consumer.py`.
**À faire** : implémenter `ensure_indexes` et `run` (liste « À FAIRE » dans le fichier).
**Test manuel** : producer actif + consumer actif, puis ouvrir http://localhost:8081 (mongo-express) → base `momo_fraud` → collection `transactions`. Relancer le producer : le nombre de documents ne doit pas doubler.
**Terminé quand** : les documents sont dans Mongo, avec un index unique sur `transaction_id`.

## Fiche M5 – Dashboard : Indicateurs
**Objectif** : donner une vue d'ensemble du risque en un coup d'œil.
**Fichier** : `src/dashboard/pages/1_Indicateurs.py`. Les fonctions de données existent déjà dans `src/dashboard/data_access.py`.
**À faire** : liste « À FAIRE » dans le fichier. Lancer avec `streamlit run src/dashboard/app.py`.
**Astuce** : tant que le scoring n'est pas prêt, demander au lead quelques documents de test dans `scored_transactions`.
**Terminé quand** : 4 indicateurs + une courbe s'affichent, et la page ne plante pas quand la base est vide.

## Fiche M6 – Dashboard : Transactions suspectes
**Objectif** : permettre à un analyste d'investiguer les alertes.
**Fichier** : `src/dashboard/pages/2_Transactions_suspectes.py`.
**À faire** : liste « À FAIRE » dans le fichier.
**Terminé quand** : filtres fonctionnels, tableau lisible avec couleurs par niveau de risque, top 10 comptes.

## Fiche M7 – Documentation, tests, rapport
**Objectif** : que le rendu final soit propre et argumenté (c'est ce qui fait la différence devant le jury).
**À faire** :
1. `docs/RAPPORT_PLAN.md` : compléter chaque section du plan (surtout « Justification des choix : Kafka vs RabbitMQ, MongoDB vs HBase/Hive, Spark vs Pandas, Streamlit vs Grafana »).
2. `notebooks/01_exploration.ipynb` : analyse exploratoire du CSV (répartition fraude/normal, montants, heures, villes) avec 5 graphiques commentés.
3. Captures d'écran de chaque étape du pipeline qui fonctionne (Kafka, Mongo, dashboard) dans `docs/img/`.
4. Compléter les tests dans `tests/` (ex. test du `data_access` avec une base vide).
5. Préparer la présentation (10 à 12 diapositives) à partir de `docs/ARCHITECTURE.md`.
**Terminé quand** : le plan du rapport est entièrement rempli et le notebook s'exécute de bout en bout.

## Fiche M1 – Lead (vous)
- `src/ml/features.py`, `train_model.py`, `streaming_scoring.py` (déjà écrits en v1, à valider et améliorer : tuning, comparaison RF / GBT / régression logistique, importance des features).
- Intégration finale et test de bout en bout (voir `README.md`, section « Démarrage complet »).
- Revue des Pull Requests des équipiers.
