"""MEMBRE 5 : page « Indicateurs de risque ».

À FAIRE (voir docs/TACHES.md, fiche M5) — utiliser UNIQUEMENT src.dashboard.data_access :
  - 4 cartes st.metric : Total transactions, Alertes HIGH, Taux de fraude (%), Montant à risque (XAF)
  - courbe temporelle (plotly) : total vs n_high par heure  -> get_timeseries()
  - bouton / case « Rafraîchir automatiquement (5 s) »
  - gérer le cas « aucune donnée » (st.info) et « MongoDB injoignable » (st.error)
"""
import streamlit as st

from src.dashboard.data_access import get_kpis, get_timeseries  # noqa: F401

st.title("📊 Indicateurs de risque")
st.info("TODO M5 : implémenter cette page.")
