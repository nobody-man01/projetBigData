"""Identité visuelle du dashboard (voir docs/DESIGN_DASHBOARD.md) : jetons de couleur, CSS et composants.

`app.py` appelle `apply_theme()` une fois par exécution, puis chaque page utilise les composants
(`kpi_card`, `risk_badge`, `data_table`...). Aucune couleur ne doit être écrite en dur dans les pages :
tout passe par COLORS.

Deux palettes : sombre (par défaut, ambiance « centre d'opérations ») et claire (vidéoprojecteur, impression).
Le choix est fait par l'interrupteur « Mode clair » de la barre latérale (st.session_state["light_mode"]).
COLORS renvoie toujours la couleur de la palette active : les pages n'ont rien à changer.
"""
from collections.abc import Mapping
from html import escape
from urllib.parse import urlencode

import streamlit as st

from config.settings import THRESHOLD_HIGH, THRESHOLD_MEDIUM

PALETTES = {
    "dark": {
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
    },
    # Mode clair : mêmes rôles, teintes assombries pour rester lisibles sur fond blanc
    "light": {
        "bg": "#F4F6FA",
        "surface": "#FFFFFF",
        "surface_2": "#EEF2F8",
        "border": "#CBD5E1",
        "text": "#0F172A",
        "muted": "#55627A",
        "accent": "#B45309",
        "HIGH": "#C81E3A",
        "MEDIUM": "#B45309",
        "LOW": "#0F766E",
    },
}

RISK_LABELS = {"HIGH": "Critique", "MEDIUM": "À surveiller", "LOW": "Normal"}


def is_light() -> bool:
    """True si l'utilisateur a choisi le mode clair (False hors de Streamlit, par exemple dans les tests)."""
    try:
        return bool(st.session_state.get("light_mode", False))
    except Exception:
        return False


class _ActivePalette(Mapping):
    """Dictionnaire de couleurs qui suit le mode choisi : COLORS["HIGH"] donne la teinte du mode actif."""

    def _palette(self) -> dict:
        return PALETTES["light" if is_light() else "dark"]

    def __getitem__(self, key: str) -> str:
        return self._palette()[key]

    def __iter__(self):
        return iter(self._palette())

    def __len__(self) -> int:
        return len(self._palette())


COLORS = _ActivePalette()


def _native_overrides(c: dict) -> str:
    """Mode clair : recolore les éléments natifs de Streamlit, configurés en sombre dans .streamlit/config.toml."""
    return f"""
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stMain"] {{
  background: {c['bg']}; color: {c['text']}; }}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label, .stApp label p,
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stSidebarNav"] span, [data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavSeparator"], [data-testid="stNavSectionHeader"] {{ color: {c['text']}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ color: {c['muted']}; }}
[data-testid="stSliderThumbValue"] {{ color: {c['accent']}; }}
[data-testid="stSidebarNavLink"]:hover, [data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: {c['surface_2']}; }}
.react-aria-ComboBox [role="group"], .react-aria-Select button, [data-baseweb="select"] > div,
[data-baseweb="input"], [data-baseweb="input"] input {{
  background: {c['surface']}; color: {c['text']}; border-color: {c['border']}; }}
.react-aria-ComboBox input, .react-aria-Select span {{ color: {c['text']}; }}
.react-aria-ComboBox svg, .react-aria-Select svg, .stTooltipIcon svg {{ color: {c['muted']}; stroke: {c['muted']}; }}
.react-aria-Popover, [role="listbox"], [data-testid="stTooltipContent"] {{
  background: {c['surface']}; color: {c['text']}; border-color: {c['border']}; }}
[role="option"] {{ color: {c['text']}; }}
[data-testid="stRadioOption"]:not([data-selected]) > div > div:first-child {{
  background: {c['surface']}; border-color: {c['muted']}; }}
[role="option"][data-focused], [role="option"][data-selected], [role="option"]:hover {{ background: {c['surface_2']}; }}
[data-testid="stBaseButton-secondary"] {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}
[data-testid="stBaseButton-secondary"]:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
[role="dialog"] {{ background: {c['surface']}; color: {c['text']}; }}
[data-testid="stAlertContainer"] p {{ color: {c['text']}; }}
[data-testid="stMarkdownContainer"] code {{ background: {c['surface_2']}; color: {c['text']}; }}
[data-testid="stMarkdownContainer"] table th, [data-testid="stMarkdownContainer"] table td {{
  color: {c['text']}; border-color: {c['border']}; background: {c['surface']}; }}
"""


def _css(c: dict, light: bool) -> str:
    """Feuille de style complète pour une palette donnée."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stText {{ font-family: 'Inter', sans-serif; }}
#MainMenu, footer, header [data-testid="stToolbar"] {{ visibility: hidden; }}
/* Le bouton qui rouvre la barre latérale est rangé dans la barre d'outils masquée : on le garde visible */
[data-testid="stExpandSidebarButton"] {{ visibility: visible; }}
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] span,
[data-testid="stExpandSidebarButton"] svg {{ color: {c['muted']} !important; }}
[data-testid="stExpandSidebarButton"]:hover span {{ color: {c['accent']} !important; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1400px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
{_native_overrides(c) if light else ""}
.soc-header {{ display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid {c['border']}; padding-bottom: 12px; margin-bottom: 20px; }}
.soc-header h1 {{ font-size: 1.55rem; font-weight: 700; margin: 0; color: {c['text']}; }}
.soc-header p {{ margin: 2px 0 0; color: {c['muted']}; font-size: 0.9rem; }}

.live {{ display: inline-flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem; color: {c['muted']}; letter-spacing: 0.08em; }}
.live .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {c['LOW']};
  box-shadow: 0 0 0 0 {c['LOW']}; animation: pulse 2s infinite; }}
.live.off .dot {{ background: {c['muted']}; animation: none; }}
@keyframes pulse {{ 0% {{ box-shadow: 0 0 0 0 {c['LOW']}99; }}
  70% {{ box-shadow: 0 0 0 8px {c['LOW']}00; }} 100% {{ box-shadow: 0 0 0 0 {c['LOW']}00; }} }}

.status {{ border: 1px solid {c['border']}; border-left-width: 4px; border-radius: 8px;
  padding: 12px 16px; margin-bottom: 20px; background: {c['surface']}; font-weight: 500; color: {c['text']}; }}

.kpi {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
  padding: 16px 18px; height: 100%; }}
.kpi .label {{ color: {c['muted']}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }}
.kpi .value {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums;
  font-size: 1.9rem; font-weight: 600; margin-top: 6px; color: {c['text']}; }}
.kpi .hint {{ color: {c['muted']}; font-size: 0.8rem; margin-top: 4px; }}

.section {{ margin: 28px 0 10px; }}
.section h3 {{ font-size: 1.05rem; font-weight: 600; margin: 0; color: {c['text']}; }}
.section p {{ color: {c['muted']}; font-size: 0.85rem; margin: 2px 0 0; }}

.badge {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.72rem;
  font-weight: 600; letter-spacing: 0.04em; border: 1px solid; }}
.mono {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}

.alert-card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 10px; animation: fadein .4s ease; color: {c['text']}; }}
@keyframes fadein {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: none; }} }}
.alert-card .row {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
.alert-card .amount {{ font-family: 'JetBrains Mono', monospace; font-size: 1.15rem; font-weight: 600; }}
.alert-card .path {{ font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: {c['muted']}; }}
.alert-card .reasons {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }}
.reason {{ background: {c['surface_2']}; border: 1px solid {c['border']}; border-radius: 6px;
  padding: 2px 8px; font-size: 0.75rem; color: {c['text']}; }}
.gauge {{ height: 6px; border-radius: 3px; background: {c['border']}; margin-top: 10px; overflow: hidden; }}
.gauge > div {{ height: 100%; border-radius: 3px; }}

a.acct {{ color: inherit; text-decoration: none; border-bottom: 1px dotted {c['muted']}; }}
a.acct:hover {{ color: {c['accent']}; border-bottom-color: {c['accent']}; }}

.soc-table-wrap {{ border: 1px solid {c['border']}; border-radius: 8px; overflow: auto; background: {c['surface']}; }}
table.soc-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; color: {c['text']}; }}
table.soc-table th {{ position: sticky; top: 0; background: {c['surface_2']}; color: {c['muted']};
  text-align: left; font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 8px 10px; border-bottom: 1px solid {c['border']}; white-space: nowrap; }}
table.soc-table td {{ padding: 7px 10px; border-bottom: 1px solid {c['border']}; white-space: nowrap; }}
table.soc-table tr:last-child td {{ border-bottom: none; }}
table.soc-table td.num {{ text-align: right; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}
table.soc-table td.mono {{ font-family: 'JetBrains Mono', monospace; }}
table.soc-table td.wrap {{ white-space: normal; min-width: 220px; color: {c['muted']}; }}
.mini-gauge {{ display: inline-block; width: 64px; height: 6px; border-radius: 3px; background: {c['border']};
  vertical-align: middle; margin-right: 8px; overflow: hidden; }}
.mini-gauge > span {{ display: block; height: 100%; }}

.facts {{ display: grid; grid-template-columns: max-content 1fr; gap: 6px 14px; font-size: 0.85rem;
  background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 14px 16px; color: {c['text']}; }}
.facts .k {{ color: {c['muted']}; }}
.facts .v {{ font-family: 'JetBrains Mono', monospace; overflow-wrap: anywhere; }}
.chip {{ display: inline-block; background: {c['surface_2']}; border: 1px solid {c['border']}; border-radius: 6px;
  padding: 1px 7px; margin: 0 4px 4px 0; font-size: 0.75rem; }}
.chip.new {{ border-color: {c['HIGH']}; color: {c['HIGH']}; }}

[data-testid="stSidebar"] {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
</style>
"""


def apply_theme() -> None:
    """Injecte le CSS du mode actif (sombre ou clair). Appelée par app.py à chaque exécution."""
    light = is_light()
    st.markdown(_css(PALETTES["light" if light else "dark"], light), unsafe_allow_html=True)


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


def account_link(account_id) -> str:
    """Lien HTML vers la page « Investigation » de ce compte (le mode clair est conservé dans l'adresse)."""
    params = {"compte": str(account_id)}
    if is_light():
        params["theme"] = "clair"
    return (f'<a class="acct" href="investigation?{urlencode(params)}" target="_self" '
            f'title="Investiguer ce compte">{escape(str(account_id))}</a>')


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
        f'<div class="row" style="margin-top:6px"><span class="path">{account_link(tx.get("sender_id", ""))} → '
        f'{account_link(tx.get("receiver_id", ""))}</span>'
        f'<span class="mono" style="color:{color}">score {fr_num(score, 2)}</span></div>'
        f'<div class="gauge"><div style="width:{score * 100:.0f}%;background:{color}"></div></div>'
        f'<div class="reasons">{reasons_html}</div></div>',
        unsafe_allow_html=True,
    )


def _cell(value, kind: str) -> tuple:
    """Contenu HTML et classe CSS d'une cellule selon son type d'affichage."""
    if value is None or (isinstance(value, float) and value != value):  # None ou NaN
        return "", ""
    if kind == "xaf":
        return escape(format_xaf(value)), "num"
    if kind == "int":
        return escape(fr_num(value)), "num"
    if kind == "score":
        level = "HIGH" if value >= THRESHOLD_HIGH else "MEDIUM" if value >= THRESHOLD_MEDIUM else "LOW"
        return (f'<span class="mini-gauge"><span style="width:{float(value) * 100:.0f}%;background:{COLORS[level]}">'
                f'</span></span>{fr_num(value, 2)}', "num")
    if kind.startswith("dec"):
        return escape(fr_num(value, int(kind[3:] or 2))), "num"
    if kind == "risk":
        return risk_badge(str(value)), ""
    if kind == "account":
        return account_link(value), "mono"
    if kind == "date":
        return escape(str(value)[:19].replace("T", " ")), "mono"
    if kind == "html":
        return str(value), ""  # contenu déjà construit et échappé par la page
    return escape(str(value)), {"mono": "mono", "wrap": "wrap"}.get(kind, "")


def data_table(df, columns: list, max_height: int = None) -> None:
    """Tableau HTML aux couleurs du thème (remplace st.dataframe, dont les couleurs ne suivent pas le mode clair).

    columns : liste de (colonne, titre, type) ; types : text, wrap (texte long), mono, int, xaf, dec2, score, risk,
    account, date, html.
    max_height : hauteur maximale en pixels (défilement, en-tête fixe).
    """
    head = "".join(f"<th>{escape(title)}</th>" for _, title, _ in columns)
    rows = []
    for rec in df.to_dict(orient="records"):
        cells = []
        for key, _, kind in columns:
            html, cls = _cell(rec.get(key), kind)
            cells.append(f'<td class="{cls}">{html}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    style = f' style="max-height:{max_height}px"' if max_height else ""
    st.markdown(f'<div class="soc-table-wrap"{style}><table class="soc-table"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div>', unsafe_allow_html=True)


def fr_num(x, decimals: int = 0) -> str:
    """Nombre au format français : virgule décimale, espace fine pour les milliers (0,80 ; 1 250)."""
    return f"{float(x):,.{decimals}f}".replace(",", " ").replace(".", ",")


def fr_pct(ratio, decimals: int = 0) -> str:
    """Pourcentage au format français à partir d'une proportion : 0.452 -> « 45 % »."""
    return f"{fr_num(float(ratio) * 100, decimals)} %"


def format_xaf(amount) -> str:
    """Montant en francs CFA, avec espaces comme séparateurs de milliers : 1 250 000 XAF."""
    return f"{float(amount or 0):,.0f} XAF".replace(",", " ")
