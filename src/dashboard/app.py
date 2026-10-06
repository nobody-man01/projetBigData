"""Page d'accueil du dashboard. Lancer: streamlit run src/dashboard/app.py
Les pages sont dans src/dashboard/pages/ (une par membre, aucun conflit Git)."""
import streamlit as st

st.set_page_config(page_title="Détection de fraude Mobile Money", page_icon="🛡️", layout="wide")
st.title("🛡️ Détection de fraude – Mobile Money (Groupe 7)")
st.markdown(
    "Pipeline temps réel : **Kafka → Spark MLlib → MongoDB → Streamlit**.\n\n"
    "Utilisez le menu à gauche : *Indicateurs* (vue d'ensemble) et *Transactions suspectes* (détail)."
)
