# Plan du rapport (à compléter par M7, relu par M1)

1. **Contexte et problématique** : Mobile Money en Afrique, enjeux de fraude, pourquoi le Big Data (volume, vitesse, variété).
2. **Données** : génération, schéma (`schema.py`), scénarios de fraude, déséquilibre des classes, analyse exploratoire.
3. **Architecture** : schéma (`ARCHITECTURE.md`), rôle de chaque composant, flux de bout en bout.
4. **Justification des choix technologiques** (tableau comparatif avec critères) :
   - Kafka vs RabbitMQ / ingestion par fichiers
   - MongoDB vs HBase vs Hive (schéma flexible, requêtes d'agrégation, latence de lecture du dashboard)
   - Spark MLlib vs scikit-learn (passage à l'échelle, streaming unifié)
   - Streamlit vs Grafana / Power BI
5. **Modèle** : features, algorithme, pondération des classes, split temporel, métriques (AUC-PR, rappel sur la classe fraude), matrice de confusion, importance des features.
6. **Dashboard** : captures d'écran et usages pour un analyste fraude.
7. **Résultats et limites** : performance, latence de bout en bout, limites (mono-broker, données simulées).
8. **Perspectives** : features par compte en fenêtres glissantes, cluster Kafka/Spark, Hive/HBase pour l'historique long, alertes temps réel (SMS).
9. **Annexes** : répartition du travail, instructions de déploiement.
