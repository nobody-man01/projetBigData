# Décisions techniques (une ligne par décision : décision, alternatives, raison)

| Date | Décision | Alternatives écartées | Raison |
|---|---|---|---|
| 2026-10-06 | Données : PaySim pour entraîner/valider + générateur v1 pour la démo, même format via adaptateur | Générateur seul ; PaySim seul ; données réelles | Aucune donnée réelle publique ; PaySim est une référence citée (crédibilité) ; le générateur apporte le contexte camerounais et la démo en direct |
| 2026-10-06 | Générateur v1 : comptes persistants, XAF entiers, 3 scénarios de fraude dont un très difficile (SCAM), cas normaux trompeurs | Tirages indépendants par transaction (v0) | La v0 donnait des fraudes triviales (100 % de soldes vidés) et des montants irréalistes (centimes) : des métriques gonflées n'auraient aucune valeur |
| 2026-10-06 | `add_features` : l'erreur de solde du destinataire tient compte du CASH_IN (l'agent donne du e-money) | Formule unique pour tous les types | Sinon un signal faux est créé pour tous les dépôts |
