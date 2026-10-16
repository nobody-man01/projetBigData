# Stratégie de données

Aucun jeu de données réel de Mobile Money avec étiquettes de fraude n'est public (secret bancaire, données personnelles). Le projet utilise donc deux sources simulées aux rôles distincts :

| Source | Rôle | Pourquoi |
|---|---|---|
| **PaySim** (Kaggle `ealaxi/paysim1`, ≈ 6,36 M de transactions, ≈ 0,13 % de fraudes) | Entraîner et valider le modèle | Simulateur reconnu, calibré sur de vrais journaux d'un service de Mobile Money africain : les métriques sont comparables à la littérature |
| **Générateur** (`src/generator/generate_dataset.py`) | Alimenter la démo en direct | Contexte camerounais (XAF, 8 villes, MTN/Orange), comptes persistants, scénarios de fraude variés |

Les deux produisent exactement le même format (`src/common/schema.py`) : le reste du pipeline ne sait pas laquelle des deux il lit.

## Générateur : ce qui le rend réaliste
- Comptes persistants (profil : ville, montant habituel, appareil, contacts, opérateur), activité très inégale.
- Montants en XAF entiers, souvent ronds ; creux d'activité la nuit ; agents et marchands distincts des clients ; soldes comptablement cohérents.
- Plafonds KYC (hypothèses) imposés à toutes les dépenses des clients, fraudeurs compris : 500 000 XAF par dépense, 1 000 000 XAF par jour (heure locale).
- 85 % des contacts réguliers d'un client sont chez le même opérateur : les transferts inter-opérateurs sont minoritaires (≈ 16 %).
- 5 scénarios de fraude de difficulté différente :
  - **ATO** : prise de contrôle, appareil inconnu, mule qui retire aussitôt ;
  - **VELOCITY** : 5 à 10 petits transferts en moins de 3 minutes (≈ 95 s en médiane) ;
  - **SCAM** : la victime envoie elle-même, depuis son appareil habituel (très difficile à repérer) ;
  - **STRUCTURING** : blanchiment, 5 à 9 transferts juste sous le seuil de contrôle de 100 000 XAF, étalés sur ≈ 2 h, depuis l'appareil habituel de la mule ;
  - **AGENT_SPLIT** : fraude d'agent, un dépôt fractionné en 5 à 10 petits dépôts (même client, même agent, en quelques minutes) pour toucher plus de commissions.
- Cas normaux trompeurs : vidages de solde légitimes, grosses dépenses, changement de téléphone, déplacements, activité de nuit, téléphone partagé, virement vers un futur compte mule, **rafales légitimes** (paie, tontine, remboursements : 4 à 10 transferts rapprochés vers des contacts habituels).
- `data/transactions_scenarios.csv` donne le scénario de chaque fraude (et `LEGIT_BURST` pour les rafales légitimes), un `event_id` et `reported_at`, pour l'analyse uniquement (jamais pour l'entraînement). L'`event_id` permet de séparer entraînement et test **par événement**.

### Signalement des fraudes (étiquettes retardées)
- `reported_at` : date de la plainte ou de la découverte. Délai médian : ATO ≈ 6 h, VELOCITY ≈ 1 jour, SCAM ≈ 2 jours, STRUCTURING ≈ 7 jours, AGENT_SPLIT ≈ 10 jours. Sert à simuler un réentraînement réaliste (on n'entraîne que sur les fraudes déjà signalées à une date donnée).
- `--unreported-share` (défaut 0) : part des SCAM / STRUCTURING / AGENT_SPLIT **jamais signalés**. Ces lignes ont `is_fraud = 0` dans le CSV, comme dans la réalité, mais gardent leur vrai scénario dans le fichier de scénarios pour mesurer le vrai rappel.

### Choix qui empêchent une détection triviale
- Sans rafales légitimes, la règle « ≥ 5 transferts en 2 minutes » trouvait 100 % des VELOCITY sans aucune fausse alerte.
- Les fraudeurs sont peu « mémorisables » : beaucoup de mules, qui reçoivent aussi des transferts légitimes ; appareils neufs ou partagés ; victimes tirées avec la même loi d'activité que les autres clients.

### Garanties de cohérence comptable
- Chaque ligne, fraude comprise, est jouée à son instant exact : l'ordre du fichier est l'ordre réel des soldes (la chaîne « solde après → solde avant » est cohérente pour chaque compte).
- Aucun argent n'est créé hors transaction : en VELOCITY et STRUCTURING, la mule est alimentée par un vrai dépôt ; en ATO, elle retire une part de ce qu'elle vient réellement de recevoir. Un agent ne donne jamais plus d'e-money qu'il n'en a.
- Seules exceptions, volontaires : 0,2 % d'erreurs de journalisation sur le solde après de l'émetteur.
- Timestamps écrits en UTC (contrat `schema.py`) ; l'activité est simulée en heure locale (UTC+1) : la nuit locale 0h–5h correspond à 23h–4h UTC.
- `device_id` = hash salé par la seed : un numéro séquentiel trahirait les appareils créés en cours de route, donc les fraudes.

## Jeu de test réaliste (taux de fraude faible)
Le taux de 2 % aide l'entraînement mais dépasse largement le réel (≈ 0,1 à 0,5 %). Pour évaluer dans des conditions réalistes :

```bash
python -m src.generator.generate_dataset --n 250000 --days 30 --test-days 7 --test-fraud-rate 0.003
```

- `--n` est le total, réparti au prorata des jours (ici ≈ 203 000 lignes d'entraînement, ≈ 47 000 de test).
- La période de test vient **après** l'entraînement, avec les **mêmes comptes** et des soldes continus : c'est un vrai split temporel.
- Fichiers produits : `data/transactions.csv` (entraînement) et `data/transactions_test.csv`, chacun avec son `_scenarios.csv`.
- Avec 0,3 % de fraudes, prévoir assez de lignes de test (≥ 40 000, soit ≈ 120 fraudes) pour que précision et rappel soient stables. Rapporter l'AUC-PR, pas l'exactitude.

## Difficulté mesurée sur une version antérieure (3 scénarios, sans plafonds ; à re-mesurer)
200 000 transactions, 2 % de fraudes, split temporel 80/20, modèle de référence scikit-learn.
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
