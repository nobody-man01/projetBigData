# Livrables finaux : cahier des charges

Trois livrables, tous cohérents entre eux (mêmes chiffres, mêmes schémas, même identité visuelle) :
1. **Le code** : dépôt propre, démarrage à froid fonctionnel.
2. **Le rapport** : `livrables/Rapport_Groupe7.docx` + export PDF.
3. **Le PowerPoint de soutenance** : `livrables/Presentation_Groupe7.pptx` + export PDF de secours.

Règle d'or : **aucun chiffre ni capture inventés**. Tout provient d'une exécution réelle (métriques du modèle, latence, débit, captures du vrai dashboard). Une mesure manquante se mesure, elle ne s'invente pas.

## Identité visuelle commune
Reprendre la palette de `docs/DESIGN_DASHBOARD.md` (fond sombre `#0A0E17`, accent ambre `#FFB020`, risque rouge `#FF4D5E`, normal turquoise `#2DD4BF`) pour les schémas et le PowerPoint, afin que dashboard, rapport et slides forment un seul produit. Polices : Inter (ou Calibri si Inter indisponible), JetBrains Mono pour le code. Pas de logos de marques (MTN, Orange).

## 1. Le rapport (≈ 25 à 35 pages)
Structure : voir `docs/RAPPORT_PLAN.md`. Exigences de qualité :
- Page de garde soignée, résumé exécutif d'une page (problème, solution, résultats chiffrés), table des matières, liste des figures, numérotation des pages.
- Chaque section commence par la question à laquelle elle répond et finit par ce qu'il faut en retenir.
- **Schémas vectoriels propres** (architecture, flux de données, pipeline ML) rendus depuis Mermaid/Graphviz/matplotlib en haute résolution, légendés et numérotés. Pas de capture floue.
- **Tableaux comparatifs** des choix (Kafka vs RabbitMQ, MongoDB vs HBase vs Hive, Spark vs scikit-learn, Streamlit vs Grafana) avec critères explicites et décision argumentée.
- Résultats ML : matrice de confusion, courbe précision-rappel, importance des features, discussion honnête des limites (données simulées, mono-broker).
- Captures du vrai dashboard (voir `docs/DESIGN_DASHBOARD.md`), annotées.
- Annexes : guide de déploiement, répartition du travail par membre, glossaire des termes Big Data.
- Relecture orthographique complète, style homogène, aucune phrase creuse.

## 2. Le PowerPoint (≈ 12 à 15 diapositives, 15 min)
Récit : **problème → solution → architecture → démo → résultats → limites → perspectives**.
1. Titre · 2. Le problème (chiffres sourcés, impact) · 3. Notre solution en une image · 4. Architecture (schéma animé étape par étape) · 5. Les données et les scénarios de fraude · 6. Pourquoi ces technologies (comparatif visuel, pas un mur de texte) · 7. Le modèle (features clés, démarche) · 8. Résultats (graphiques lisibles, message dans le titre) · 9. **Démo live** (plan B : vidéo enregistrée du dashboard) · 10. Latence et passage à l'échelle · 11. Limites et honnêteté · 12. Perspectives (Hive/HBase, cluster, alertes) · 13. L'équipe et la répartition · 14. Conclusion · 15. Questions (avec diapositives d'annexe prêtes pour les questions probables).
Exigences de design :
- **Un message par diapositive**, énoncé dans le titre (« 98 % des fraudes détectées en moins de 5 s »), pas un intitulé de rubrique.
- Peu de texte (6 lignes max), grands visuels, hiérarchie typographique claire, marges et alignements rigoureux, même grille sur toutes les diapositives.
- Schémas natifs et éditables quand c'est possible ; captures nettes du dashboard ; icônes cohérentes (un seul jeu).
- Palette et polices de l'identité commune. Pas de modèles génériques reconnaissables, pas de dégradés criards, pas de clipart.
- **Notes du présentateur** sur chaque diapositive (ce qu'on dit, qui parle, durée), pour que même un débutant puisse présenter.
- Transitions sobres. Rendre chaque diapositive en image et la vérifier visuellement : aucun débordement, aucun texte coupé, contraste correct.

## 3. Le dépôt de code
- `README.md` : démarrage à froid en moins de 10 commandes, vérifié sur machine propre.
- Arborescence nette, pas de fichiers morts, `pytest` vert, `.env.example` à jour, pas de secrets.
- Un script `make demo` (ou `scripts/demo.sh`) qui lance toute la démo.

## Contrôle qualité final (avant rendu)
- Relecture indépendante par l'agent `qa-reviewer` + vérification croisée des chiffres entre code, rapport et diapositives.
- Répétition chronométrée de la soutenance avec le plan B vidéo prêt.
- Export PDF du rapport et du PowerPoint ouverts et vérifiés page par page.
