# Architecture

```mermaid
flowchart LR
    G[Générateur Python<br/>data/transactions.csv] --> P[Producer Kafka]
    P -->|JSON| K[(Kafka<br/>momo.transactions.raw)]
    K --> C[Consumer Python]
    C --> M1[(MongoDB<br/>transactions)]
    K --> S[Spark Structured Streaming<br/>+ modèle MLlib]
    S --> M2[(MongoDB<br/>scored_transactions)]
    M2 --> D[Dashboard Streamlit]
    G -.entraînement.-> T[Spark MLlib<br/>train_model.py]
    T -.PipelineModel.-> S
```

## Contrat d'interfaces
| Interface | Format |
|---|---|
| Topic Kafka | `momo.transactions.raw`, clé = `transaction_id`, valeur = JSON (champs de `schema.FIELDS`) |
| Mongo `transactions` | transactions brutes (écrit par le consumer), index unique `transaction_id` |
| Mongo `scored_transactions` | transaction + `fraud_score`, `prediction`, `risk_level`, `scored_at` (écrit par Spark) |
| Dashboard | lit uniquement `scored_transactions`, via `src/dashboard/data_access.py` |

## Pourquoi deux collections ?
Découplage : le stockage brut (historique, audit) ne dépend pas du scoring. Si le modèle change, on peut rescorer l'historique.

## Garanties
- **Idempotence** : upserts sur `transaction_id` côté consumer et côté Spark (rejeu sans doublon).
- **Pas de décalage train/serve** : `add_features` est partagée entre l'entraînement et le streaming.
- **Déséquilibre des classes** : pondération des classes, métrique AUC-PR (pas l'accuracy).
- **Split temporel** : on entraîne sur le passé et on teste sur le futur.

## Limites assumées (à citer dans le rapport)
Mono-broker Kafka, Spark en mode local, pas de features d'historique par compte (fenêtres glissantes) : pistes d'amélioration.
