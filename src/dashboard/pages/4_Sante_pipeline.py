"""Page « Santé du pipeline » (lead) : débit et latence de bout en bout, mesurés en direct.

Latence = du moment où le producer envoie la transaction dans Kafka jusqu'à l'écriture du score dans MongoDB.
"""
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_access import get_pipeline_stats, ping
from src.dashboard.ui.charts import style
from src.dashboard.ui.theme import COLORS, fr_num, kpi_card, page_header, section_header, status_banner

online = ping()
page_header("Santé du pipeline", "Producer → Kafka → Spark Structured Streaming → MongoDB → dashboard", live=online)
if not online:
    st.error("MongoDB est injoignable. Lancez `docker compose up -d` puis rechargez la page.")
    st.stop()


@st.fragment(run_every=5)
def live_health():
    """Indicateurs rafraîchis toutes les 5 s."""
    s = get_pipeline_stats()
    if s["latency_p50"] is None:
        status_banner("En attente de transactions scorées : lancez le scoring Spark puis le producer.", "MEDIUM")
        return
    p95 = s["latency_p95"] / 1000
    if s["throughput"] == 0:
        status_banner("Flux à l'arrêt : aucune transaction scorée dans la dernière minute.", "MEDIUM")
    else:
        status_banner(f"Pipeline opérationnel : {fr_num(s['throughput'], 1)} transactions scorées par seconde, "
                      f"95 % en moins de {fr_num(p95, 1)} s.", "LOW")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Débit", f"{fr_num(s['throughput'], 1)} tx/s", "transactions scorées, dernière minute")
    with c2:
        kpi_card("Latence médiane", f"{fr_num(s['latency_p50'] / 1000, 1)} s", "envoi Kafka → score dans MongoDB")
    with c3:
        kpi_card("Latence p95", f"{fr_num(p95, 1)} s", "95 % des transactions plus rapides")
    with c4:
        kpi_card("Volumes", f"{s['n_scored']:,}".replace(",", " "),
                 f"scorées · {s['n_raw']:,} brutes stockées".replace(",", " "))

    series = s["latency_series"]
    if not series.empty:
        section_header("Latence de bout en bout", "Le scoring Spark travaille par micro-lots de 5 s : "
                                                  "c'est lui qui fixe la latence")
        fig = go.Figure(go.Scatter(x=series["scored_at"], y=series["median"] / 1000, mode="lines+markers",
                                   name="Latence médiane (s)", line=dict(color=COLORS["accent"], width=2)))
        fig.update_yaxes(title="secondes", rangemode="tozero")
        st.plotly_chart(style(fig, 300), use_container_width=True)


live_health()

section_header("Architecture", "Chaque composant est remplaçable et passe à l'échelle horizontalement")
st.markdown(
    "| Étape | Technologie | Rôle |\n|---|---|---|\n"
    "| Ingestion | Apache Kafka (topic `momo.transactions.raw`) | Tampon durable entre producteurs et consommateurs |\n"
    "| Stockage brut | MongoDB `transactions` | Historique complet, upsert idempotent sur `transaction_id` |\n"
    "| Scoring | Spark Structured Streaming + MLlib | Features + profils de comptes + modèle, micro-lots de 5 s |\n"
    "| Résultats | MongoDB `scored_transactions` | Lu par ce dashboard |\n"
)
