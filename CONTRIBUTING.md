# Workflow Git (simple)

## Une seule fois : installer le projet
1. Accepter l'invitation au dépôt (e-mail ou https://github.com/nobody-man01/projetBigData/invitations).
2. `git clone https://github.com/nobody-man01/projetBigData.git` puis `cd projetBigData`
3. `python -m venv .venv && source .venv/bin/activate` (Windows : `.venv\Scripts\activate`) puis `pip install -r requirements.txt`
4. `cp .env.example .env`
5. `pytest -q` : tout doit passer avant de commencer.

## À chaque tâche
1. Avant de travailler : `git checkout main && git pull`
2. Créer sa branche : `git checkout -b feature/<prenom>-<module>` (ex. `feature/awa-producer`)
3. Travailler **uniquement dans ses fichiers** (voir `docs/TACHES.md` et son Issue sur GitHub), lancer `pytest -q`
4. `git add <fichiers> && git commit -m "feat(producer): envoi CSV vers Kafka"`
5. `git push -u origin feature/<prenom>-<module>` puis ouvrir une **Pull Request** vers `main`
6. Les tests se lancent automatiquement sur la Pull Request (coche verte attendue). Le lead relit et fusionne.

Format des commits : `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`.

## À ne jamais faire
- Pousser directement sur `main` (c'est bloqué de toute façon).
- Ajouter des données (`data/*.csv`), un modèle, le dossier `.venv/` ou le fichier `.env` : ils restent sur votre machine (déjà ignorés par git).
- Mettre un mot de passe ou un jeton dans un fichier.
- Utiliser `git add .` sans relire `git status` avant.
