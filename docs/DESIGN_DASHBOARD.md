# Direction de design du dashboard : « Centre d'opérations anti-fraude »

Objectif : un produit, pas un TP. Un jury doit se dire « c'est un vrai outil d'analyste », et un autre groupe ne doit pas pouvoir obtenir ça avec un simple « fais-moi un dashboard Streamlit ».

## Concept
Un SOC (centre d'opérations de sécurité) pour la fraude Mobile Money au Cameroun : sombre, dense mais lisible, orienté action. L'analyste doit comprendre en 3 secondes : *y a-t-il un problème, où, et sur quel compte agir ?*

## Identité visuelle (jetons de design, dans `src/dashboard/ui/theme.py`)
| Jeton | Valeur | Usage |
|---|---|---|
| fond | `#0A0E17` | page |
| surface | `#121929` | cartes |
| bordure | `#1F2A44` | séparations fines (1 px) |
| texte / texte atténué | `#E6EAF2` / `#8A94AD` | |
| accent | `#FFB020` | éléments interactifs, focus |
| critique (HIGH) | `#FF4D5E` | alertes |
| attention (MEDIUM) | `#FFB020` | |
| normal (LOW) | `#2DD4BF` | |
Polices : Inter (texte) + JetBrains Mono (chiffres, identifiants), via Google Fonts injecté en CSS. Chiffres tabulaires. Pas de palette arc-en-ciel : un seul accent, les couleurs de risque réservées au risque. Ne pas imiter les marques MTN/Orange.

## Écrans
1. **Vue d'ensemble (Command Center)** : bandeau d'état global (« Système nominal / Activité suspecte »), 4 cartes KPI avec mini-courbe (sparkline) et variation vs période précédente, flux d'activité en direct, courbe transactions vs alertes avec seuils annotés.
2. **Carte du risque** : carte du Cameroun (pydeck/plotly) des 8 villes, taille = volume, couleur = taux d'alertes, survol détaillé.
3. **Alertes** : liste type « boîte de réception » triée par gravité ; chaque alerte = carte avec badge de risque, jauge de score, montant, parcours expéditeur → destinataire, **les 3 raisons principales** (« solde vidé à 98 % », « nuit », « nouvel appareil »). Clic = panneau de détail.
4. **Investigation d'un compte** : historique du compte, chronologie, comptes liés (graphe simple), actions fictives (Bloquer / Marquer faux positif) avec confirmation.
5. **Performance du modèle** : matrice de confusion, courbe précision-rappel, importance des features, seuil réglable avec impact immédiat sur nombre d'alertes et fraudes manquées (curseur = intérêt métier fort).
6. **Architecture / Santé du pipeline** : débit msg/s, latence de bout en bout, retard Kafka, état de chaque composant. Montre la maîtrise Big Data.

## Techniques pour dépasser le Streamlit par défaut
- Un module `ui/theme.py` unique : CSS injecté via `st.markdown(..., unsafe_allow_html=True)`, masquer le menu/pied de page par défaut, cartes avec bordures fines et ombres douces, grille cohérente (espacement multiple de 8 px).
- Composants maison réutilisables : `kpi_card`, `risk_badge`, `score_gauge`, `alert_card`, `section_header`.
- Graphiques Plotly avec thème sombre custom commun (`ui/charts.py`) : pas de grille lourde, annotations directes plutôt que légendes, info-bulles riches.
- Rafraîchissement fluide : `st.fragment(run_every=...)` pour ne recharger que les blocs vivants, sans clignotement de page.
- Animations discrètes en CSS (pulsation d'un point « LIVE », apparition douce des nouvelles alertes).
- Navigation personnalisée (`st.navigation` / `st.Page`) avec icônes, filtres globaux persistants dans `st.session_state`.
- Mode démo : bouton qui lance une rafale de fraudes pour montrer le système réagir en direct devant le jury.

## Critères d'acceptation
- Aucune zone « par défaut Streamlit » visible ; cohérence totale des couleurs/espacements.
- Chaque graphique a un titre qui énonce le message (« Les alertes explosent la nuit »), pas juste le nom de la variable.
- États vide / erreur / chargement soignés. Lisible en 1280 px.
- Capture d'écran de chaque écran validée par le lead avant fusion.
