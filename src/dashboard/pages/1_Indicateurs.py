"""MEMBRE 5 : page « Vue d'ensemble » — le risque en un coup d'œil.

Utilise UNIQUEMENT src.dashboard.data_access :
  - bandeau d'état global ;
  - 4 indicateurs : transactions analysées, alertes critiques, taux d'alerte, montant à risque (XAF) ;
  - courbe transactions vs alertes critiques par heure ;
  - rafraîchissement automatique toutes les 5 s ;
  - états « aucune donnée » et « MongoDB injoignable ».
"""
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_access import get_kpis, get_timeseries, ping
from src.dashboard.ui.charts import style
from src.dashboard.ui.theme import COLORS, format_xaf, fr_pct, kpi_card, page_header, section_header, status_banner

online = ping()
page_header("Vue d'ensemble", "Surveillance en temps réel des transactions Mobile Money", live=online)
if not online:
    st.error("MongoDB est injoignable. Lancez `docker compose up -d` puis rechargez la page.")
    st.stop()


@st.fragment(run_every=5)
def overview():
    """Bloc rafraîchi toutes les 5 s sans recharger la page."""
    k = get_kpis()
    if k["total"] == 0:
        st.info("Aucune transaction scorée pour l'instant. Lancez le scoring Spark puis le producer.")
        return

    if k["n_high"] == 0:
        status_banner("Système nominal : aucune alerte critique.", "LOW")
    else:
        status_banner(f"Activité suspecte : {k['n_high']} alertes critiques à traiter "
                      f"({format_xaf(k['amount_at_risk'])} en jeu).", "HIGH")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Transactions analysées", f"{k['total']:,}".replace(",", " "), "scorées par le modèle")
    with c2:
        kpi_card("Alertes critiques", f"{k['n_high']:,}".replace(",", " "),
                 f"+ {k['n_medium']} à surveiller", COLORS["HIGH"])
    with c3:
        kpi_card("Taux d'alerte", fr_pct(k["fraud_rate"], 1), "part des transactions critiques")
    with c4:
        kpi_card("Montant à risque", format_xaf(k["amount_at_risk"]), "somme des alertes critiques",
                 COLORS["accent"])

    ts = get_timeseries("1h")
    if not ts.empty:
        peak = ts.loc[ts["n_high"].idxmax()]
        section_header("Transactions et alertes par heure",
                       f"Pic d'alertes critiques le {peak['bucket']:%d/%m à %Hh} ({int(peak['n_high'])} alertes)")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=ts["bucket"], y=ts["total"], name="Transactions",
                             marker_color=COLORS["border"]))
        fig.add_trace(go.Scatter(x=ts["bucket"], y=ts["n_high"], name="Alertes critiques", yaxis="y2",
                                 mode="lines+markers", line=dict(color=COLORS["HIGH"], width=2.5)))
        fig.update_layout(yaxis=dict(title="transactions"),
                          yaxis2=dict(title="alertes", overlaying="y", side="right", showgrid=False, tickmode="auto",
                                      tickformat="d",
                                      color=COLORS["HIGH"], rangemode="tozero"))
        st.plotly_chart(style(fig, 340), use_container_width=True, theme=None,
                    config={"displayModeBar": False})


overview()
