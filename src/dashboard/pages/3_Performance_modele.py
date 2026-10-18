"""Page « Performance du modèle » (lead) : chiffres du dernier entraînement (models/metrics.json).

Tous les chiffres viennent de l'évaluation réelle sur la période de test (les 20 % les plus récents).
Le curseur de seuil montre le compromis métier : plus d'alertes = moins de fraudes manquées.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_access import load_model_metrics
from src.dashboard.ui.charts import style
from src.dashboard.ui.theme import COLORS, fr_num, fr_pct, kpi_card, page_header, section_header

SCENARIOS = {"ATO": "Prise de contrôle", "VELOCITY": "Rafale", "SCAM": "Arnaque"}
FEATURE_LABELS = {
    "amount": "Montant", "log_amount": "Montant (log)", "sender_balance_before": "Solde avant opération",
    "hour": "Heure", "is_night": "Opération de nuit", "amount_to_balance_ratio": "Part du solde envoyée",
    "sender_emptied": "Solde vidé", "error_balance_sender": "Incohérence solde expéditeur",
    "error_balance_receiver": "Incohérence solde destinataire", "has_history": "Compte connu",
    "log_n_tx_hist": "Ancienneté du compte (nb d'opérations)", "amount_vs_avg": "Montant / moyenne du compte",
    "amount_vs_max": "Montant / maximum du compte", "device_is_new": "Nouvel appareil",
    "receiver_is_new": "Nouveau destinataire", "city_is_new": "Ville inhabituelle",
    "sender_n_10min": "Opérations sur 10 min", "log_sender_amount_10min": "Montant envoyé sur 10 min",
    "sender_n_1h": "Opérations sur 1 h", "pair_n_10min": "Même destinataire sur 10 min",
}


def feature_label(name: str) -> str:
    """Nom lisible d'une feature (les colonnes encodées deviennent « Type : TRANSFER »)."""
    for prefix, label in (("tx_type_ohe_", "Type"), ("channel_ohe_", "Canal"), ("operator_ohe_", "Opérateur")):
        if name.startswith(prefix):
            return f"{label} : {name[len(prefix):]}"
    return FEATURE_LABELS.get(name, name)

m = load_model_metrics()
page_header("Performance du modèle", "Évaluation honnête sur des transactions futures, jamais vues à l'entraînement",
            live=bool(m))
if not m:
    st.info("Aucun modèle entraîné. Lancez `python -m src.ml.train_model --compare`.")
    st.stop()

high, medium = m["at_high"], m["at_medium"]
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("AUC-PR", fr_num(m["auc_pr"], 2), f"hasard = {fr_num(m['fraud_rate_test'], 3)} (taux de fraude)")
with c2:
    kpi_card("Fraudes détectées", fr_pct(medium["recall"]), f"seuil {fr_num(medium['threshold'], 2)} (à surveiller et plus)",
             COLORS["LOW"])
with c3:
    kpi_card("Précision des alertes critiques", fr_pct(high["precision"]),
             f"seuil {fr_num(high['threshold'], 2)} : {high['tp']} vraies / {high['fp']} fausses")
with c4:
    kpi_card("Volume d'alertes", fr_pct(medium["alerts_per_1000"] / 1000, 1), "des transactions signalées (seuil 0,50)")

curve = pd.DataFrame(m["pr_curve"])
left, right = st.columns(2, gap="large")
with left:
    section_header("Choisir le seuil d'alerte", "Déplacez le curseur : chaque fraude rattrapée coûte des fausses alertes")
    threshold = st.slider("Seuil de score", 0.05, 0.95, float(high["threshold"]), 0.05)
    point = curve.iloc[(curve["threshold"] - threshold).abs().argmin()]
    n_fraud = m["n_test_fraud"]
    caught = round(point["recall"] * n_fraud)
    alerts = round(caught / point["precision"]) if point["precision"] > 0 else 0
    a, b, c = st.columns(3)
    with a:
        kpi_card("Fraudes rattrapées", f"{caught}", f"sur {n_fraud} ({fr_pct(point['recall'])})", COLORS["LOW"])
    with b:
        kpi_card("Fraudes manquées", f"{n_fraud - caught}", "passent sous le seuil", COLORS["HIGH"])
    with c:
        kpi_card("Fausses alertes", f"{alerts - caught}", f"précision {fr_pct(point['precision'])}")

    fig = go.Figure(go.Scatter(x=curve["recall"], y=curve["precision"], mode="lines", name="Courbe PR",
                               line=dict(color=COLORS["accent"], width=2.5)))
    fig.add_trace(go.Scatter(x=[point["recall"]], y=[point["precision"]], mode="markers", name="Seuil choisi",
                             marker=dict(color=COLORS["text"], size=11, line=dict(color=COLORS["accent"], width=2))))
    fig.update_xaxes(title="Rappel (part des fraudes détectées)", range=[0, 1.02])
    fig.update_yaxes(title="Précision (part d'alertes justes)", range=[0, 1.02])
    st.plotly_chart(style(fig, 300), use_container_width=True)

with right:
    imp = pd.DataFrame(m["feature_importances"]).head(10).iloc[::-1]
    imp["feature"] = imp["feature"].map(feature_label)
    if not imp.empty:
        section_header("Ce qui trahit un fraudeur", f"« {imp.iloc[-1]['feature']} » est le signal le plus utilisé")
        fig = px.bar(imp, x="importance", y="feature", orientation="h", color_discrete_sequence=[COLORS["accent"]])
        st.plotly_chart(style(fig, 330).update_layout(showlegend=False, xaxis_title=None, yaxis_title=None),
                        use_container_width=True)

    if m.get("by_scenario"):
        sc = pd.DataFrame([{"Scénario": SCENARIOS.get(k, k), "Rappel": v["recall_medium"], "n": v["n"]}
                           for k, v in m["by_scenario"].items()]).sort_values("Rappel")
        hardest = sc.iloc[0]
        section_header("Détection par scénario", f"{hardest['Scénario']} reste le plus difficile "
                                                 f"({fr_pct(hardest['Rappel'])} détectées)")
        fig = px.bar(sc, x="Rappel", y="Scénario", orientation="h", text=sc["Rappel"].map(fr_pct),
                     color_discrete_sequence=[COLORS["LOW"]])
        fig.update_xaxes(range=[0, 1.05], tickformat=".0%")
        st.plotly_chart(style(fig, 200).update_layout(showlegend=False, xaxis_title=None, yaxis_title=None),
                        use_container_width=True)

if m.get("comparison"):
    section_header("Pourquoi cet algorithme ?",
                   f"{m['algo_label']} obtient la meilleure AUC-PR sur la période de validation")
    comp = pd.DataFrame(m["comparison"])[["label", "auc_pr_validation"]]
    st.dataframe(comp.rename(columns={"label": "Algorithme", "auc_pr_validation": "AUC-PR (validation)"}),
                 hide_index=True, use_container_width=True,
                 column_config={"AUC-PR (validation)": st.column_config.NumberColumn(format="%.3f")})

st.caption(f"Entraîné le {m['created_at'][:16].replace('T', ' ')} UTC · {m['n_train']} transactions "
           f"d'entraînement · test : {m['n_test']} transactions à partir du {m['test_period_start'][:10]}")
