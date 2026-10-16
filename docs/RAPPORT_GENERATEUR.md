# Rapport : générateur de données (`src/generator/generate_dataset.py`)

Rédigé par M2 pour la section 2 du rapport (« Données »). Tous les chiffres viennent d'une exécution réelle, reproductible avec :

```bash
python -m src.generator.generate_dataset --n 250000 --days 30 --test-days 7 --test-fraud-rate 0.003 --seed 42
```

## 1. Rôle dans le projet
Le générateur répond au premier point du sujet : *générer un jeu de données simulant des transactions Mobile Money*. Il alimente toute la chaîne :

`generate_dataset.py` → CSV → `producer.py` → **Kafka** → **MongoDB** → **Spark MLlib** → **dashboard Streamlit**

Aucun jeu de données réel de Mobile Money étiqueté n'est public (secret bancaire, données personnelles) : la simulation est une nécessité. PaySim sert de référence externe (voir `docs/DONNEES.md`).

## 2. Mode d'emploi

| Point | Détail |
|---|---|
| Commande de base | `python -m src.generator.generate_dataset --n 200000 --fraud-rate 0.02 --seed 42` |
| Avec jeu de test | `--test-days 7 --test-fraud-rate 0.003` : période de test **après** l'entraînement, mêmes comptes |
| Fraudes non signalées | `--unreported-share 0.3` : 30 % des SCAM / STRUCTURING / AGENT_SPLIT gardent `is_fraud = 0` |
| Sorties | `data/transactions.csv`, `data/transactions_test.csv` (optionnel), chacun avec son `_scenarios.csv` |
| Format | Contrat `src/common/schema.py` (15 colonnes), timestamps en UTC |
| Reproductibilité | Même `--seed` ⇒ mêmes données (vérifié par un test) |

**Trois règles :**
1. Le fichier `_scenarios.csv` (`fraud_scenario`, `event_id`, `reported_at`) sert **uniquement à l'analyse**, jamais à l'entraînement.
2. Évaluer sur la **période postérieure** (`transactions_test.csv`), pas sur un découpage aléatoire.
3. Mesurer avec l'**AUC-PR** et le rappel par scénario, jamais avec l'exactitude : à 0,3 % de fraudes, prédire « jamais de fraude » donne 99,7 %.

## 3. Fonctionnement
1. **Le monde** : clients, agents (dépôt/retrait) et marchands. Chaque client a un profil persistant : ville, montant habituel, appareil, contacts réguliers (85 % chez le même opérateur), usage application ou USSD.
2. **La planification** : chaque événement de fraude, chaque rafale légitime et chaque transaction normale reçoit son instant.
3. **Le rejeu chronologique** : chaque transaction est appliquée aux soldes à son instant exact, sous les règles de l'opérateur (solde suffisant, plafonds KYC de 500 000 XAF par dépense et 1 000 000 XAF par jour).

### Les cinq scénarios de fraude

| Scénario | Comportement | Ce qui le trahit |
|---|---|---|
| **ATO** (prise de contrôle) | Appareil inconnu, souvent de nuit et d'une autre ville ; la victime est vidée vers une mule qui retire aussitôt | Appareil et ville inhabituels (historique nécessaire) |
| **VELOCITY** | Une mule envoie 5 à 10 petits transferts en ≈ 94 s (médiane) | Le rythme, mais des rafales légitimes lui ressemblent |
| **SCAM** (arnaque) | La victime envoie elle-même un gros montant, depuis son appareil habituel | Presque rien : le plus difficile, comme dans la réalité |
| **STRUCTURING** (blanchiment) | 5 à 9 transferts juste sous le seuil de contrôle (médiane 92 000 XAF pour un seuil de 100 000), étalés sur ≈ 2 h | La répétition de montants proches du seuil |
| **AGENT_SPLIT** (fraude d'agent) | Un dépôt fractionné en 5 à 10 petits dépôts, même client et même agent, en ≈ 7 min | La répétition de la même paire client/agent |

## 4. Résultats mesurés (seed 42)

| | Entraînement (30 jours) | Test (7 jours) |
|---|---|---|
| Transactions | 203 141 | 46 566 |
| Taux de fraude (visé) | 1,99 % (2 %) | 0,30 % (0,3 %) |
| Lignes de fraude | 4 034 | 142 |
| Rafales légitimes (pièges, `is_fraud = 0`) | 2 010 lignes | 490 lignes |

Répartition des lignes de fraude à l'entraînement : ATO 1 159 (28,7 %), VELOCITY 1 125 (27,9 %), SCAM 837 (20,7 %), AGENT_SPLIT 462 (11,5 %), STRUCTURING 451 (11,2 %).

Autres mesures sur l'entraînement :
- 16 627 émetteurs distincts, soit ≈ 12 transactions par émetteur.
- Montant médian : 6 500 XAF pour une transaction normale, 22 000 XAF pour une fraude.
- 66,8 % de montants ronds (multiples de 500 XAF).
- 84,1 % des transferts entre clients restent chez le même opérateur.
- Délai médian de signalement : ATO 5,9 h, VELOCITY 22,5 h, SCAM 47,4 h, STRUCTURING 212 h, AGENT_SPLIT 221 h.

Génération : 46 s et ≈ 530 Mo de mémoire pour 250 000 lignes. Qualité : 16 tests automatisés (`tests/test_schema_and_generator.py`).

## 5. Points forts
- **Réalisme local** : XAF entiers et souvent ronds, 8 villes du Cameroun, MTN et Orange, rythme jour/nuit en heure locale, agents et marchands, plafonds KYC.
- **Comptes persistants** : chaque client a un historique cohérent, ce qui permet les variables d'historique au cœur d'une détection en temps réel.
- **Cohérence comptable vérifiée** : la chaîne « solde après → solde avant » est cohérente pour chaque compte, à part 0,2 % d'erreurs de journalisation volontaires. Aucun argent n'est créé hors transaction : les mules sont financées par de vrais dépôts.
- **Détection non triviale par construction** : rafales légitimes, vidages de solde légitimes, changements de téléphone, voyages et téléphones partagés ressemblent à des fraudes.
- **Pas de fuite d'étiquette connue** : `device_id` hachés, erreurs de solde indépendantes de la fraude, scénarios dans un fichier séparé.
- **Évaluation honnête** : période de test postérieure à taux réaliste, `event_id` pour découper par événement, `reported_at` et `--unreported-share` pour simuler des étiquettes tardives ou manquantes.
- **Maintenable** : paramètres regroupés en tête de fichier, chaque type de transaction validé, 16 tests.

## 6. Limites (à assumer)
- **Hypothèses non calibrées** : distributions, plafonds, seuil de contrôle et délais de signalement sont plausibles mais ne viennent pas de données d'un opérateur.
- **Taux de 2 % à l'entraînement** : choix volontaire pour avoir assez d'exemples ; il est paramétrable (`--fraud-rate`) et l'évaluation se fait à 0,3 %.
- **Peu d'événements rares au test** : à 0,3 %, le jeu de test ne contient que 2 événements STRUCTURING et 4 AGENT_SPLIT. Le rappel par scénario n'y est pas significatif ; il faut augmenter `--n` ou mesurer le rappel par scénario sur l'entraînement en validation temporelle.
- **Pas de frais de transaction ni de SIM swap** : il faudrait une nouvelle colonne, donc modifier le contrat de données (décision du lead).
- **Fraudes déjà exécutées dans le CSV** : le générateur ne simule pas le blocage (transaction refusée, argent sauvé, fraudeur qui réessaie). Un mode direct relié au scoring serait nécessaire (voir § 7).
- **Nombre de lignes approximatif** : 249 707 lignes pour 250 000 demandées (−0,12 %), car les transactions sans solde suffisant ou au-delà des plafonds sont annulées, comme en réalité.
- **Performance** : la boucle Python ligne par ligne suffit pour quelques centaines de milliers de lignes ; PaySim couvre les gros volumes.

## 7. Ce qui est attendu des autres membres

| Qui | Attendu | Pourquoi |
|---|---|---|
| **M1 (lead, ML)** | Variables d'historique par compte dans `features.py` : appareil ou ville jamais vus, nombre de transferts sur 2 min, dépôts répétés vers le même agent, transferts juste sous 100 000 XAF sur 24 h | Sans historique, ATO, STRUCTURING et AGENT_SPLIT sont presque invisibles : le réalisme du générateur n'est pas exploité |
| **M1** | Re-mesurer le tableau de difficulté de `docs/DONNEES.md` (mesuré sur une version à 3 scénarios) | Règle des livrables : aucun chiffre périmé |
| **M1** | Régler la session Spark sur `Africa/Douala` (ou décaler `is_night`) | Les timestamps sont en UTC : `hour < 5` correspond à 1h–6h en heure locale |
| **M1** | Décider si l'entraînement utilise `--unreported-share` et `reported_at` | Choix de méthodologie du modèle |
| **Lead** | Décider d'ajouter des colonnes au contrat (`hours_since_sim_swap`, `fee`) | Le contrat est partagé par Kafka, MongoDB, Spark et le dashboard |
| **M1 + M3** | Mode direct (`--live`) : émission en continu vers Kafka et retour des décisions de blocage | Montrer le blocage en temps réel et l'argent sauvé |
| **M3** | Rejouer `transactions.csv` (et `transactions_test.csv` pour la démo à taux réaliste) ; ne jamais envoyer les fichiers `_scenarios.csv` | Ce sont des fichiers d'analyse, pas des données de production |
| **M4** | Indexer `sender_id` + `timestamp` dans MongoDB | Les variables d'historique lisent les transactions récentes d'un compte |
| **M7** | Reprendre ce rapport dans la section 2 et les § 4 à 6 dans « Résultats et limites » | Cohérence entre code, rapport et diapositives |
