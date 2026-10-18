"""Page « Investigation d'un compte » (lead) : tout ce que l'analyste doit savoir avant d'agir sur un compte.

Utilise UNIQUEMENT src.dashboard.data_access :
  - choix du compte : comptes les plus suspects, numéro saisi, ou lien depuis la page Alertes (?compte=...) ;
  - bilan : transactions, alertes, montant envoyé, score maximal ;
  - habitudes connues (profil calculé par la couche batch) comparées à ce qui se passe pendant le flux ;
  - chronologie des transactions et comptes liés (graphe simple) ;
  - actions simulées « Bloquer » / « Marquer faux positif », avec confirmation (aucune opération réelle).
"""
import math
from datetime import datetime
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.data_access import (account_counterparts, explain, get_account_profile,
                                       get_account_transactions, get_top_risky_accounts, ping)
from src.dashboard.ui.charts import style
from src.dashboard.ui.theme import (COLORS, RISK_LABELS, data_table, format_xaf, fr_num, kpi_card, page_header,
                                    section_header, status_banner)

online = ping()
page_header("Investigation d'un compte", "Historique, comptes liés et décision de l'analyste", live=online)
if not online:
    st.error("MongoDB est injoignable. Lancez `docker compose up -d` puis rechargez la page.")
    st.stop()

# --- Choix du compte : lien depuis Alertes (?compte=...), comptes les plus suspects, ou numéro saisi ---
suspects = get_top_risky_accounts(20)
options = list(suspects["sender_id"]) if not suspects.empty else []
requested = st.query_params.get("compte")
if requested and requested not in options:
    options.insert(0, requested)
if not options:
    st.info("Aucune alerte critique pour l'instant : lancez le producer, ou saisissez un numéro de compte.")
account = st.selectbox("Compte à investiguer", options,
                       index=options.index(requested) if requested else (0 if options else None),
                       accept_new_options=True, placeholder="Numéro de compte (ex. 237600001477)",
                       help="Les 20 comptes avec le plus d'alertes critiques ; vous pouvez aussi saisir un numéro.")
if not account:
    st.stop()
account = str(account).strip()
st.query_params["compte"] = account   # adresse partageable

df = get_account_transactions(account)
if df.empty:
    st.warning(f"Aucune transaction scorée pour le compte {account}.")
    st.stop()

sent = df[df["sender_id"] == account]
received = df[df["receiver_id"] == account]
n_high = int((sent["risk_level"] == "HIGH").sum())
n_medium = int((sent["risk_level"] == "MEDIUM").sum())
profile = get_account_profile(account)
decisions = st.session_state.setdefault("decisions", {})

# --- Bandeau : décision déjà prise, ou état du compte ---
if account in decisions:
    d = decisions[account]
    status_banner(f"Décision de l'analyste : {d['label']} à {d['at']}. "
                  "Action simulée pour la démonstration.", "LOW" if d["action"] == "false_positive" else "HIGH")
elif n_high:
    first = sent.loc[sent["risk_level"] == "HIGH", "timestamp"].min()
    status_banner(f"Compte à risque : {n_high} alertes critiques, la première le {first[8:10]}/{first[5:7]} "
                  f"à {first[11:16]}.", "HIGH")
elif n_medium:
    status_banner(f"Compte à surveiller : {n_medium} transactions au-dessus du seuil « à surveiller ».", "MEDIUM")
else:
    status_banner("Aucune alerte pour ce compte sur la période observée.", "LOW")

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Transactions", fr_num(len(df)), f"{len(sent)} envoyées · {len(received)} reçues")
with c2:
    kpi_card("Alertes critiques", fr_num(n_high), f"+ {n_medium} à surveiller", COLORS["HIGH"] if n_high else None)
with c3:
    kpi_card("Montant envoyé", format_xaf(sent["amount"].sum()), f"reçu : {format_xaf(received['amount'].sum())}")
with c4:
    top_score = float(sent["fraud_score"].max()) if not sent.empty else 0.0
    level = "HIGH" if n_high else "MEDIUM" if n_medium else "LOW"
    kpi_card("Score maximal", fr_num(top_score, 2), RISK_LABELS[level], COLORS[level])

# --- Habitudes connues (couche batch) contre activité observée dans le flux ---
left, right = st.columns([3, 2], gap="large")
with right:
    chips = lambda values, known=None: "".join(  # noqa: E731
        f'<span class="chip{" new" if known is not None and v not in known else ""}">{escape(str(v))}</span>'
        for v in values) or "–"
    devices_now = list(dict.fromkeys(sent["device_id"])) if not sent.empty else []
    cities_now = list(dict.fromkeys(sent["city"])) if not sent.empty else []
    if profile:
        new_devices = [d for d in devices_now if d not in profile["devices"]]
        new_receivers = sent.loc[~sent["receiver_id"].isin(profile["receivers"]), "receiver_id"].nunique()
        section_header("Habitudes connues et écarts",
                       f"{len(new_devices)} appareil(s) jamais vu(s) avant, {new_receivers} nouveau(x) destinataire(s)"
                       if devices_now else "Aucune transaction envoyée pendant la période observée")
        st.markdown(
            '<div class="facts">'
            f'<span class="k">Historique (batch)</span><span class="v">{profile["n_tx"]} opérations envoyées</span>'
            f'<span class="k">Montant habituel</span><span class="v">moyenne {format_xaf(profile["avg_amount"])}, '
            f'maximum {format_xaf(profile["max_amount"])}</span>'
            f'<span class="k">Appareils connus</span><span class="v">{chips(profile["devices"])}</span>'
            f'<span class="k">Villes connues</span><span class="v">{chips(profile["cities"])}</span>'
            f'<span class="k">Destinataires connus</span><span class="v">{len(profile["receivers"])} comptes</span>'
            f'<span class="k">Appareils observés</span><span class="v">{chips(devices_now, profile["devices"])}</span>'
            f'<span class="k">Villes observées</span><span class="v">{chips(cities_now, profile["cities"])}</span>'
            '</div>', unsafe_allow_html=True)
        st.caption("En rouge : ce qui n'apparaît pas dans l'historique du compte (profil calculé en batch).")
    else:
        section_header("Habitudes connues et écarts", "Compte sans historique : il n'a rien envoyé avant la période")
        st.markdown(
            '<div class="facts">'
            f'<span class="k">Appareils observés</span><span class="v">{chips(devices_now)}</span>'
            f'<span class="k">Villes observées</span><span class="v">{chips(cities_now)}</span>'
            '</div>', unsafe_allow_html=True)

with left:
    first_alert = sent.loc[sent["risk_level"] == "HIGH", "timestamp"].min() if n_high else None
    section_header("Chronologie",
                   f"Les alertes critiques commencent le {first_alert[8:10]}/{first_alert[5:7]} à {first_alert[11:16]}"
                   if first_alert else "Montant et niveau de risque de chaque transaction du compte")
    t = df.assign(ts=pd.to_datetime(df["timestamp"], utc=True, format="ISO8601"),
                  is_sent=df["sender_id"] == account)
    t["hover"] = [
        f"{r.tx_type} {'vers' if r.is_sent else 'de'} {r.receiver_id if r.is_sent else r.sender_id}<br>"
        f"{format_xaf(r.amount)} · score {fr_num(r.fraud_score, 2)}<br>{' · '.join(explain(r._asdict())) or '—'}"
        for r in t.itertuples()]
    fig = go.Figure()
    for lvl in ("LOW", "MEDIUM", "HIGH"):
        part = t[t["is_sent"] & (t["risk_level"] == lvl)]
        if not part.empty:
            fig.add_trace(go.Scatter(x=part["ts"], y=part["amount"], mode="markers", name=f"Envoyée · {RISK_LABELS[lvl].lower()}",
                                     marker=dict(color=COLORS[lvl], size=12 if lvl == "HIGH" else 9,
                                                 line=dict(color=COLORS["bg"], width=1)),
                                     hovertext=part["hover"], hoverinfo="text"))
    part = t[~t["is_sent"]]
    if not part.empty:
        fig.add_trace(go.Scatter(x=part["ts"], y=part["amount"], mode="markers", name="Reçue",
                                 marker=dict(symbol="circle-open", size=10, line=dict(width=2),
                                             color=[COLORS[lv] for lv in part["risk_level"]]),
                                 hovertext=part["hover"], hoverinfo="text"))
    fig.update_yaxes(type="log", title="montant (XAF)")
    st.plotly_chart(style(fig, 300), use_container_width=True, theme=None,
                    config={"displayModeBar": False})

# --- Comptes liés ---
links = account_counterparts(df, account)
left, right = st.columns([3, 2], gap="large")
with left:
    risky = int((links["worst_level"] == "HIGH").sum())
    section_header("Comptes liés", f"{len(links)} contrepartie(s), dont {risky} liée(s) à des alertes critiques")
    shown = links.head(16)
    fig = go.Figure()
    xs, ys = [], []
    for i in range(len(shown)):
        angle = 2 * math.pi * i / max(len(shown), 1) + math.pi / 2
        xs.append(math.cos(angle))
        ys.append(math.sin(angle))
    for lvl in ("LOW", "MEDIUM", "HIGH"):   # arêtes regroupées par niveau de risque (une couleur par trace)
        ex, ey = [], []
        for x, y, w in zip(xs, ys, shown["worst_level"]):
            if w == lvl:
                ex += [0, x, None]
                ey += [0, y, None]
        if ex:
            fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", hoverinfo="skip", showlegend=False,
                                     line=dict(color=COLORS[lvl], width=2.5 if lvl == "HIGH" else 1.5)))
    size = [14 + 10 * math.log10(1 + a / 1000) for a in shown["amount"]]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", showlegend=False, text=[f"…{c[-6:]}" for c in shown["counterpart"]],
        textposition="top center", textfont=dict(size=11, color=COLORS["muted"]),
        marker=dict(size=size, color=[COLORS[w] for w in shown["worst_level"]], line=dict(color=COLORS["bg"], width=1.5)),
        hovertext=[f"{r.counterpart}<br>{r.direction} · {r.n} transaction(s) · {format_xaf(r.amount)}"
                   f"<br>score max {fr_num(r.max_score, 2)}" for r in shown.itertuples()], hoverinfo="text"))
    fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers", showlegend=False, hovertext=[f"{account} (compte investigué)"],
                             marker=dict(size=26, color=COLORS["surface_2"], line=dict(color=COLORS["accent"], width=3)),
                             hoverinfo="text"))
    fig.update_xaxes(visible=False, range=[-1.4, 1.4])
    fig.update_yaxes(visible=False, range=[-1.35, 1.35], scaleanchor="x")
    st.plotly_chart(style(fig, 340), use_container_width=True, theme=None,
                    config={"displayModeBar": False})
    if len(links) > len(shown):
        st.caption(f"Les {len(shown)} contreparties les plus risquées sont affichées sur {len(links)}.")

with right:
    section_header("Contreparties", "Cliquer sur un compte pour l'investiguer à son tour")
    data_table(links, [("counterpart", "Compte", "account"), ("n", "Opér.", "int"), ("amount", "Montant", "xaf"),
                       ("worst_level", "Risque", "risk")], max_height=300)

# --- Décision de l'analyste (simulée) ---
ACTIONS = {"block": "compte bloqué", "false_positive": "alertes marquées comme faux positif"}


@st.dialog("Confirmer la décision")
def confirm(action: str) -> None:
    """Fenêtre de confirmation : la décision n'est enregistrée qu'après un second clic."""
    if action == "block":
        st.markdown(f"Bloquer le compte **{account}** ? Les retraits et transferts sortants seraient suspendus "
                    "en attendant la vérification du client.")
    else:
        st.markdown(f"Marquer les alertes du compte **{account}** comme **faux positif** ? Elles serviraient "
                    "d'exemples « normaux » au prochain réentraînement.")
    st.caption("Démonstration : aucune opération n'est envoyée à l'opérateur.")
    ok, cancel = st.columns(2)
    if ok.button("Confirmer", type="primary", use_container_width=True):
        decisions[account] = {"action": action, "label": ACTIONS[action], "at": datetime.now().strftime("%H:%M")}
        st.rerun()
    if cancel.button("Annuler", use_container_width=True):
        st.rerun()


section_header("Décision", "Actions simulées : elles restent dans cette session du tableau de bord")
b1, b2, b3 = st.columns([1, 1, 2])
if b1.button("Bloquer le compte", icon=":material/block:", use_container_width=True, disabled=account in decisions):
    confirm("block")
if b2.button("Marquer faux positif", icon=":material/check_circle:", use_container_width=True,
             disabled=account in decisions):
    confirm("false_positive")
if account in decisions and b3.button("Annuler la décision", icon=":material/undo:"):
    decisions.pop(account)
    st.rerun()

# --- Détail des transactions ---
section_header("Transactions du compte", "Les plus récentes d'abord ; raisons affichées pour les transactions à risque")
table = df.iloc[::-1].copy()
table["sens"] = (table["sender_id"] == account).map({True: "Envoyée", False: "Reçue"})
table["contrepartie"] = table["receiver_id"].where(table["sender_id"] == account, table["sender_id"])
table["raisons"] = [" · ".join(explain(r)) if r.get("risk_level") != "LOW" else ""
                    for r in table.to_dict(orient="records")]
data_table(table, [("timestamp", "Date", "date"), ("sens", "Sens", "text"), ("tx_type", "Type", "text"),
                   ("amount", "Montant", "xaf"), ("contrepartie", "Contrepartie", "account"), ("city", "Ville", "text"),
                   ("device_id", "Appareil", "mono"), ("fraud_score", "Score", "score"),
                   ("risk_level", "Niveau", "risk"), ("raisons", "Raisons", "wrap")], max_height=380)
