# Décisions techniques (une ligne par décision : décision, alternatives, raison)

| Date | Décision | Alternatives écartées | Raison |
|---|---|---|---|
| 2026-10-06 | Données : PaySim pour entraîner/valider + générateur v1 pour la démo, même format via adaptateur | Générateur seul ; PaySim seul ; données réelles | Aucune donnée réelle publique ; PaySim est une référence citée (crédibilité) ; le générateur apporte le contexte camerounais et la démo en direct |
| 2026-10-06 | Générateur v1 : comptes persistants, XAF entiers, 3 scénarios de fraude dont un très difficile (SCAM), cas normaux trompeurs | Tirages indépendants par transaction (v0) | La v0 donnait des fraudes triviales (100 % de soldes vidés) et des montants irréalistes (centimes) : des métriques gonflées n'auraient aucune valeur |
| 2026-10-06 | `add_features` : l'erreur de solde du destinataire tient compte du CASH_IN (l'agent donne du e-money) | Formule unique pour tous les types | Sinon un signal faux est créé pour tous les dépôts |
| 2026-10-14 | Features d'historique par compte (appareils, destinataires, villes, montant moyen) calculées en batch puis jointes au flux (jointure flux / table statique) | Agrégats en fenêtres glissantes dans le streaming ; features de la seule transaction | Les trois scénarios de fraude se définissent par rapport aux habitudes du compte : AUC-PR 0,39 → 0,80 sur la période de test. Architecture de type Lambda (couche batch + couche temps réel), simple et sans état dans le streaming |
| 2026-10-14 | Découpage temporel en 3 tranches : profils 0-50 %, entraînement 50-80 %, test 80-100 % (profils recalculés sur 0-80 %) | Découpage aléatoire ; profils calculés sur tout le jeu | Évite toute fuite du futur vers le passé ; reproduit la situation de production |
| 2026-10-14 | Gradient boosting (GBT) retenu | Régression logistique (AUC-PR validation 0,60), forêt aléatoire (0,72) | Meilleure AUC-PR sur la tranche de validation 70-80 % (0,82), choisie sans regarder le test |
| 2026-10-14 | Latence mesurée par un horodatage `sent_at` ajouté par le producer | Estimation théorique | Chiffre réel pour le rapport ; le micro-lot de 5 s de Spark domine la latence (médiane ≈ 5,6 s) |
