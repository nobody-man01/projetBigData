# Stratégie de données

Aucun jeu de données réel de Mobile Money avec étiquettes de fraude n'est public (secret bancaire, données personnelles). Le projet utilise donc deux sources simulées aux rôles distincts :

| Source | Rôle | Pourquoi |
|---|---|---|
| **PaySim** (Kaggle `ealaxi/paysim1`, ≈ 6,36 M de transactions, ≈ 0,13 % de fraudes) | Entraîner et valider le modèle | Simulateur reconnu, calibré sur de vrais journaux d'un service de Mobile Money africain : les métriques sont comparables à la littérature |
| **Générateur v1** (`src/generator/generate_dataset.py`) | Alimenter la démo en direct | Contexte camerounais (XAF, 8 villes, MTN/Orange), comptes persistants, scénarios de fraude variés |

Les deux produisent exactement le même format (`src/common/schema.py`) : le reste du pipeline ne sait pas laquelle des deux il lit.

## Générateur v1 : ce qui le rend réaliste
- Comptes persistants (profil : ville, montant habituel, appareil, contacts, opérateur), activité très inégale.
- Montants en XAF entiers, souvent ronds ; creux d'activité la nuit ; agents et marchands distincts des clients ; soldes comptablement cohérents.
- 3 scénarios de fraude de difficulté différente : **ATO** (prise de contrôle, appareil inconnu, mule qui retire aussitôt), **VELOCITY** (5 à 10 petits transferts en 2 minutes), **SCAM** (la victime envoie elle-même, depuis son appareil habituel : très difficile à repérer).
- Cas normaux trompeurs : vidages de solde légitimes, grosses dépenses, changement de téléphone, déplacements, activité de nuit.
- `data/transactions_scenarios.csv` donne le scénario de chaque fraude, pour l'analyse uniquement (jamais pour l'entraînement).

## Difficulté mesurée (200 000 transactions, 2 % de fraudes, split temporel 80/20, modèle de référence scikit-learn)
| Variables utilisées | AUC-PR | AUC-ROC |
|---|---|---|
| Seulement la transaction (équivalent de `features.py` actuel) | 0,43 | 0,97 |
| + historique du compte (nouvel appareil, nouvelle ville, rafale récente) | 0,77 | 0,98 |

Rappel par scénario si l'on signale les 2 % de transactions les plus risquées : sans historique ATO 66 %, VELOCITY 44 %, SCAM 17 % ; avec historique ATO 90 %, VELOCITY 96 %, SCAM 13 %.
Ces chiffres viennent d'un modèle scikit-learn de contrôle, pas de Spark MLlib : ils servent à vérifier que les données ne sont pas triviales. Les vrais résultats du projet seront ceux de `train_model.py`.

**Conséquence pour `src/ml/` (à faire par le lead / `ml-engineer`)** : ajouter des variables d'historique par compte est le gain le plus fort. En streaming, cela demande un état par compte (Spark `applyInPandasWithState`/`mapGroupsWithState`, ou lecture de l'historique récent dans MongoDB). C'est un excellent point technique pour le rapport.

## Utiliser PaySim
1. Télécharger le jeu sur Kaggle (compte gratuit) : fichier `PS_20174392719_1491204439457_log.csv`, à placer dans `data/` (ignoré par git, ≈ 470 Mo).
2. `python -m src.generator.paysim_adapter --max-rows 1000000`
3. `python -m src.ml.train_model --data data/transactions_paysim.csv`

L'adaptateur ajoute par simulation l'opérateur, le canal, la ville et l'appareil (absents de PaySim), de façon stable par compte et indépendante de la fraude : ils n'apportent donc ni fuite d'étiquette ni signal. À écrire tel quel dans le rapport.

## Limites à assumer dans le rapport
Les deux sources sont simulées ; les taux de fraude et les comportements sont des hypothèses ; les résultats ne prouvent pas la performance sur des données réelles d'un opérateur.
