"""Point d'entrée du dashboard. Lancer : streamlit run src/dashboard/app.py

Navigation personnalisée : chaque page est un fichier de src/dashboard/pages/ (un propriétaire par fichier).
"""
import sys
from pathlib import Path

import streamlit as st

# Permet `from src... import` quel que soit le dossier depuis lequel streamlit est lancé
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard.ui.theme import apply_theme  # noqa: E402

st.set_page_config(page_title="MoMo Fraud Ops – Groupe 7", page_icon="🛡️", layout="wide")

# Mode clair ou sombre : choisi par l'interrupteur de la barre latérale, ou par l'adresse (?theme=clair),
# ce qui permet aux liens entre pages (alerte -> investigation) de garder le mode choisi.
if "light_mode" not in st.session_state:
    st.session_state["light_mode"] = st.query_params.get("theme") == "clair"
apply_theme()

PAGES = Path(__file__).parent / "pages"
nav = st.navigation({
    "Surveillance": [
        st.Page(PAGES / "1_Indicateurs.py", title="Vue d'ensemble", icon=":material/monitoring:",
                url_path="vue-ensemble", default=True),
        st.Page(PAGES / "2_Transactions_suspectes.py", title="Alertes", icon=":material/notifications_active:",
                url_path="alertes"),
        st.Page(PAGES / "5_Investigation_compte.py", title="Investigation d'un compte",
                icon=":material/person_search:", url_path="investigation"),
    ],
    "Système": [
        st.Page(PAGES / "3_Performance_modele.py", title="Performance du modèle", icon=":material/insights:",
                url_path="performance"),
        st.Page(PAGES / "4_Sante_pipeline.py", title="Santé du pipeline", icon=":material/lan:",
                url_path="pipeline"),
    ],
})
with st.sidebar:
    st.toggle("Mode clair", key="light_mode", help="Fond clair, plus lisible au vidéoprojecteur")
    st.caption("Détection de fraude Mobile Money en temps réel · Kafka → Spark → MongoDB")
nav.run()
