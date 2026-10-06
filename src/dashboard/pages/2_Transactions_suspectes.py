"""MEMBRE 6 : page « Transactions suspectes ».

À FAIRE (voir docs/TACHES.md, fiche M6) — utiliser UNIQUEMENT src.dashboard.data_access :
  - filtres latéraux : niveau (MEDIUM+/HIGH), ville (src.common.schema.CITIES), type de transaction
  - tableau st.dataframe des transactions suspectes (colonnes utiles, fraud_score en barre de progression,
    ligne colorée selon risk_level)
  - histogramme (plotly) de la répartition par ville et par tx_type des alertes HIGH
  - tableau « Top 10 comptes à risque » -> get_top_risky_accounts()
"""
import streamlit as st

from config.settings import THRESHOLD_HIGH, THRESHOLD_MEDIUM  # noqa: F401
from src.common.schema import CITIES, TX_TYPES  # noqa: F401
from src.dashboard.data_access import get_suspicious, get_top_risky_accounts  # noqa: F401

st.title("🚨 Transactions suspectes")
st.info("TODO M6 : implémenter cette page.")
