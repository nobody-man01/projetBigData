# Workflow Git (simple)

1. `git clone <url-du-depot>` puis `cd momo-fraud-detection`
2. `python -m venv .venv && source .venv/bin/activate` puis `pip install -r requirements.txt`
3. `cp .env.example .env`
4. Avant de travailler : `git checkout main && git pull`
5. Créer sa branche : `git checkout -b feature/<prenom>-<module>` (ex. `feature/awa-producer`)
6. Travailler **uniquement dans ses fichiers** (voir `docs/TACHES.md`), lancer `pytest`
7. `git add <fichiers> && git commit -m "feat(producer): envoi CSV vers Kafka"`
8. `git push -u origin feature/<prenom>-<module>` puis ouvrir une **Pull Request** vers `main`
9. Le lead relit et fusionne. Ne jamais pousser directement sur `main`.

Format des commits : `feat(...)`, `fix(...)`, `docs(...)`, `test(...)`.
