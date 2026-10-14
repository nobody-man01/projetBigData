"""Identité visuelle du dashboard (voir docs/DESIGN_DASHBOARD.md) : jetons de couleur, CSS et composants.

Chaque page appelle `apply_theme()` en premier, puis utilise les composants (`kpi_card`, `risk_badge`...).
Aucune couleur ne doit être écrite en dur dans les pages : tout passe par COLORS.
"""
from html import escape

import streamlit as st

COLORS = {
    "bg": "#0A0E17",
    "surface": "#121929",
    "surface_2": "#18213A",
    "border": "#1F2A44",
    "text": "#E6EAF2",
    "muted": "#8A94AD",
    "accent": "#FFB020",
    "HIGH": "#FF4D5E",
    "MEDIUM": "#FFB020",
    "LOW": "#2DD4BF",
}

RISK_LABELS = {"HIGH": "Critique", "MEDIUM": "À surveiller", "LOW": "Normal"}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stText {{ font-family: 'Inter', sans-serif; }}
#MainMenu, footer, header [data-testid="stToolbar"] {{ visibility: hidden; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}

.soc-header {{ display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid {COLORS['border']}; padding-bottom: 12px; margin-bottom: 20px; }}
.soc-header h1 {{ font-size: 1.55rem; font-weight: 700; margin: 0; color: {COLORS['text']}; }}
.soc-header p {{ margin: 2px 0 0; color: {COLORS['muted']}; font-size: 0.9rem; }}

.live {{ display: inline-flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem; color: {COLORS['muted']}; letter-spacing: 0.08em; }}
.live .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {COLORS['LOW']};
  box-shadow: 0 0 0 0 {COLORS['LOW']}; animation: pulse 2s infinite; }}
.live.off .dot {{ background: {COLORS['muted']}; animation: none; }}
@keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 rgba(45,212,191,.6); }}
  70% {{ box-shadow: 0 0 0 8px rgba(45,212,191,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(45,212,191,0); }} }}

.status {{ border: 1px solid {COLORS['border']}; border-left-width: 4px; border-radius: 8px;
  padding: 12px 16px; margin-bottom: 20px; background: {COLORS['surface']}; font-weight: 500; }}

.kpi {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 10px;
  padding: 16px 18px; height: 100%; }}
.kpi .label {{ color: {COLORS['muted']}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }}
.kpi .value {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums;
  font-size: 1.9rem; font-weight: 600; margin-top: 6px; color: {COLORS['text']}; }}
.kpi .hint {{ color: {COLORS['muted']}; font-size: 0.8rem; margin-top: 4px; }}

.section {{ margin: 28px 0 10px; }}
.section h3 {{ font-size: 1.05rem; font-weight: 600; margin: 0; color: {COLORS['text']}; }}
.section p {{ color: {COLORS['muted']}; font-size: 0.85rem; margin: 2px 0 0; }}

.badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.72rem;
  font-weight: 600; letter-spacing: 0.04em; border: 1px solid; }}
.mono {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}

.alert-card {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 10px; animation: fadein .4s ease; }}
@keyframes fadein {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
.alert-card .row {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
.alert-card .amount {{ font-family: 'JetBrains Mono', monospace; font-size: 1.15rem; font-weight: 600; }}
.alert-card .path {{ font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: {COLORS['muted']}; }}
.alert-card .reasons {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.reason {{ background: {COLORS['surface_2']}; border: 1px solid {COLORS['border']}; border-radius: 6px;
  padding: 2px 8px; font-size: 0.75rem; color: {COLORS['text']}; }}
.gauge {{ height: 6px; border-radius: 3px; background: {COLORS['border']}; margin-top: 10px; overflow: hidden; }}
.gauge > div {{ height: 100%; border-radius: 3px; }}

[data-testid="stSidebar"] {{ background: {COLORS['surface']}; border-right: 1px solid {COLORS['border']}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {COLORS['border']}; border-radius: 8px; }}
</style>
"""


def apply_theme() -> None:
    """Injecte le CSS commun. À appeler une fois en haut de chaque page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str, live: bool = True) -> None:
    """En-tête de page : titre, sous-titre et indicateur LIVE (vert si le flux est actif)."""
    state = "" if live else " off"
    label = "LIVE" if live else "HORS LIGNE"
    st.markdown(
        f'<div class="soc-header"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>'
        f'<div class="live{state}"><span class="dot"></span>{label}</div></div>',
        unsafe_allow_html=True,
    )


def status_banner(message: str, level: str = "LOW") -> None:
    """Bandeau d'état global, coloré selon le niveau de risque."""
    st.markdown(f'<div class="status" style="border-left-color:{COLORS[level]}">{escape(message)}</div>',
                unsafe_allow_html=True)


def kpi_card(label: str, value: str, hint: str = "", color: str = None) -> None:
    """Carte d'indicateur : libellé, valeur en chiffres tabulaires, ligne d'explication."""
    style = f' style="color:{color}"' if color else ""
    st.markdown(
        f'<div class="kpi"><div class="label">{escape(label)}</div>'
        f'<div class="value"{style}>{escape(value)}</div><div class="hint">{escape(hint)}</div></div>',
        unsafe_allow_html=True,
    )


def section_header(title: str, message: str = "") -> None:
    """Titre de section ; `message` énonce ce qu'il faut retenir du bloc."""
    st.markdown(f'<div class="section"><h3>{escape(title)}</h3><p>{escape(message)}</p></div>',
                unsafe_allow_html=True)


def risk_badge(level: str) -> str:
    """Badge HTML coloré pour un niveau de risque (HIGH / MEDIUM / LOW)."""
    c = COLORS.get(level, COLORS["muted"])
    return (f'<span class="badge" style="color:{c};border-color:{c};background:{c}1A">'
            f'{escape(RISK_LABELS.get(level, level))}</span>')


def alert_card(tx: dict, reasons: list) -> None:
    """Carte d'alerte : badge, montant, parcours expéditeur -> destinataire, jauge de score, raisons."""
    level = tx.get("risk_level", "LOW")
    score = float(tx.get("fraud_score", 0.0))
    color = COLORS.get(level, COLORS["muted"])
    reasons_html = "".join(f'<span class="reason">{escape(r)}</span>' for r in reasons)
    st.markdown(
        f'<div class="alert-card" style="border-left:3px solid {color}">'
        f'<div class="row"><div>{risk_badge(level)} '
        f'<span class="path">{escape(str(tx.get("tx_type", "")))} · {escape(str(tx.get("city", "")))} · '
        f'{escape(str(tx.get("timestamp", ""))[:16].replace("T", " "))}</span></div>'
        f'<div class="amount">{format_xaf(tx.get("amount", 0))}</div></div>'
        f'<div class="row" style="margin-top:6px"><span class="path">{escape(str(tx.get("sender_id", "")))} → '
        f'{escape(str(tx.get("receiver_id", "")))}</span>'
        f'<span class="mono" style="color:{color}">score {score:.2f}</span></div>'
        f'<div class="gauge"><div style="width:{score * 100:.0f}%;background:{color}"></div></div>'
        f'<div class="reasons">{reasons_html}</div></div>',
        unsafe_allow_html=True,
    )


def format_xaf(amount) -> str:
    """Montant en francs CFA, avec espaces comme séparateurs de milliers : 1 250 000 XAF."""
    return f"{float(amount or 0):,.0f} XAF".replace(",", " ")
