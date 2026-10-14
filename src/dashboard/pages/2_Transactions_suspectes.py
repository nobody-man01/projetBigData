"""MEMBRE 6 (tenu par le lead) : page « Alertes » — investiguer les transactions suspectes.

Utilise UNIQUEMENT src.dashboard.data_access :
  - filtres latéraux : niveau (MEDIUM+/HIGH), ville, type de transaction ;
  - boîte de réception des alertes (cartes triées par date, avec les raisons principales) ;
  - répartition des alertes HIGH par ville et par type ;
  - top 10 des comptes à risque.
"""
import plotly.express as px
import streamlit as st

from src.common.schema import CITIES, TX_TYPES
from src.dashboard.data_access import explain, get_suspicious, get_top_risky_accounts, ping
from src.dashboard.ui.charts import style
from src.dashboard.ui.theme import COLORS, alert_card, format_xaf, page_header, section_header

online = ping()
page_header("Alertes", "Transactions suspectes à investiguer, les plus récentes d'abord", live=online)
if not online:
    st.error("MongoDB est injoignable. Lancez `docker compose up -d` puis rechargez la page.")
    st.stop()

with st.sidebar:
    st.subheader("Filtres")
    level = st.radio("Niveau minimum", ["MEDIUM", "HIGH"], index=1,
                     format_func=lambda v: "À surveiller et critiques" if v == "MEDIUM" else "Critiques seulement")
    city = st.selectbox("Ville", ["Toutes"] + CITIES)
    tx_type = st.selectbox("Type de transaction", ["Tous"] + TX_TYPES)


@st.fragment(run_every=5)
def live_alerts():
    """Bloc rafraîchi toutes les 5 s sans recharger la page."""
    df = get_suspicious(limit=300, min_level=level,
                        city=None if city == "Toutes" else city,
                        tx_type=None if tx_type == "Tous" else tx_type)
    if df.empty:
        st.info("Aucune alerte pour ces filtres. Lancez le producer pour alimenter le flux.")
        return

    left, right = st.columns([3, 2], gap="large")
    with left:
        section_header("Boîte de réception", f"{len(df)} alertes, les 8 plus récentes en détail")
        for tx in df.head(8).to_dict(orient="records"):
            alert_card(tx, explain(tx))
    with right:
        high = df[df["risk_level"] == "HIGH"]
        if not high.empty:
            by_city = high.groupby("city").size().sort_values().reset_index(name="alertes")
            top_city = by_city.iloc[-1]
            section_header("Où frappe la fraude ?",
                           f"{top_city['city']} concentre {top_city['alertes']} alertes critiques")
            fig = px.bar(by_city, x="alertes", y="city", orientation="h",
                         color_discrete_sequence=[COLORS["HIGH"]])
            st.plotly_chart(style(fig, 260).update_layout(showlegend=False, yaxis_title=None,
                                                          xaxis_title=None), use_container_width=True)

            by_type = high.groupby("tx_type").size().sort_values().reset_index(name="alertes")
            section_header("Par type d'opération",
                           f"Les {by_type.iloc[-1]['tx_type']} dominent les alertes critiques")
            fig = px.bar(by_type, x="alertes", y="tx_type", orientation="h",
                         color_discrete_sequence=[COLORS["accent"]])
            st.plotly_chart(style(fig, 200).update_layout(showlegend=False, yaxis_title=None,
                                                          xaxis_title=None), use_container_width=True)

    section_header("Toutes les alertes", "Score de fraude, montant et parcours de chaque transaction")
    table = df[["timestamp", "risk_level", "fraud_score", "amount", "tx_type", "sender_id",
                "receiver_id", "city", "channel"]].copy()
    table["timestamp"] = table["timestamp"].str[:19].str.replace("T", " ")
    st.dataframe(
        table, hide_index=True, use_container_width=True, height=320,
        column_config={
            "timestamp": "Date", "risk_level": "Niveau", "tx_type": "Type", "city": "Ville",
            "channel": "Canal", "sender_id": "Expéditeur", "receiver_id": "Destinataire",
            "fraud_score": st.column_config.ProgressColumn("Score", min_value=0.0, max_value=1.0, format="%.2f"),
            "amount": st.column_config.NumberColumn("Montant (XAF)", format="%d"),
        },
    )


live_alerts()

section_header("Top 10 des comptes à risque", "Comptes émetteurs avec le plus d'alertes critiques : à bloquer en priorité")
top = get_top_risky_accounts(10)
if top.empty:
    st.info("Aucun compte avec une alerte critique pour l'instant.")
else:
    top["amount_high"] = top["amount_high"].map(format_xaf)
    st.dataframe(top.rename(columns={"sender_id": "Compte", "n_high": "Alertes critiques",
                                     "amount_high": "Montant en jeu"}),
                 hide_index=True, use_container_width=True)
