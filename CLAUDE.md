# Projet : détection de fraude Mobile Money (Groupe 7)

Pipeline Big Data temps réel : **Générateur → Kafka → MongoDB → Spark MLlib → Streamlit**. Objectif : un rendu de niveau expert Big Data, propre, justifié, démontrable.

## Qui est qui
- **Lead** : `codeur.enigma@gmail.com` (M1). Il garde les parties complexes (`src/ml/`, intégration) et finit/améliore les modules de ses 6 équipiers quand ils sont incomplets. Les équipiers sont débutants : tout doit être très lisible, commenté, avec consignes claires.
- Répartition des modules : `docs/TACHES.md`. Équipe et comptes GitHub : `docs/EQUIPE.md`.

## Architecture et contrats (ne pas casser)
- Contrat de données : `src/common/schema.py` (`FIELDS`, `SCORED_EXTRA`). Toute modification doit être annoncée et répercutée partout (producer, consumer, Spark `TX_SCHEMA`, dashboard, tests).
- Configuration : uniquement `config/settings.py` (jamais de valeur en dur).
- Features Spark : une seule fonction `add_features` (`src/ml/features.py`) partagée entraînement/streaming.
- Dashboard : les pages ne lisent MongoDB que via `src/dashboard/data_access.py`.
- Idempotence : upsert sur `transaction_id` partout.
- Kafka topic `momo.transactions.raw` ; Mongo : `transactions` (brut), `scored_transactions` (scoré).

## Commandes
```bash
docker compose up -d
python -m src.generator.generate_dataset --n 200000
python -m src.ml.train_model
python -m src.ml.streaming_scoring
python -m src.ingestion.mongo_consumer
python -m src.ingestion.producer --rate 20
streamlit run src/dashboard/app.py
pytest -q
```

## Règles de travail
1. **Planifier avant de coder** pour toute tâche non triviale ; vérifier en exécutant (tests, vrai lancement), jamais « ça devrait marcher ».
2. Utiliser les **sous-agents** de `.claude/agents/` pour les tâches spécialisées et pour relire son propre travail.
3. Un fichier = un propriétaire. Ne pas réécrire le module d'un équipier sans raison : compléter, corriger, expliquer dans le message de commit.
4. Branches `feature/<prenom>-<module>`, Pull Requests vers `main`, commits `feat|fix|docs|test(...)`. Jamais de push direct sur `main` sauf demande explicite du lead.
5. Code en Python 3.10+, docstrings et commentaires en français, noms de variables en anglais.
6. Aucun secret dans le dépôt (`.env` est ignoré ; jetons via variables d'environnement).
7. Les métriques du modèle doivent être honnêtes : split temporel, AUC-PR, pas d'accuracy sur classes déséquilibrées, pas de fuite de la colonne `is_fraud` dans les features.
8. Justifier chaque choix technologique (le rapport en dépend) : noter les décisions importantes dans `docs/DECISIONS.md` (une ligne : décision, alternatives, raison).

## Niveau de qualité attendu
- Tout lancement à froid fonctionne en suivant le README.
- Le dashboard doit être exceptionnel visuellement : voir `docs/DESIGN_DASHBOARD.md`.
- Livrables finaux (code, rapport Word/PDF, PowerPoint de soutenance) : cahier des charges dans `docs/LIVRABLES.md`. Aucun chiffre ni capture inventés ; rien ne doit paraître « généré » ; vérifier chaque page/diapositive rendue en image.
- Une démo de bout en bout doit tenir en 5 minutes devant un jury.

## État d'avancement (mettre à jour à chaque jalon, 5 lignes max)
- Fait : squelette, générateur v0, modules ML v1 (non testés avec Spark réel), data_access.
- À faire : valider train_model en réel, producer, consumer, pages dashboard, générateur enrichi, rapport.
