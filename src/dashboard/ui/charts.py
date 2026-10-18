"""Thème Plotly commun : fond transparent, grille légère, polices et couleurs du dashboard (mode sombre ou clair).

Les pages affichent les figures avec st.plotly_chart(..., theme=None) : sinon le thème natif de Streamlit,
configuré en sombre, écraserait ces couleurs en mode clair.
"""
import plotly.graph_objects as go

from src.dashboard.ui.theme import COLORS


def style(fig: go.Figure, height: int = 320) -> go.Figure:
    """Applique le style commun (couleurs du mode actif) à une figure Plotly et la renvoie."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=COLORS["text"], size=12),
        hoverlabel=dict(bgcolor=COLORS["surface_2"], bordercolor=COLORS["border"],
                        font=dict(family="JetBrains Mono, monospace", color=COLORS["text"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(color=COLORS["text"])),
        showlegend=True,
        modebar=dict(orientation="v", bgcolor="rgba(0,0,0,0)", color=COLORS["muted"], activecolor=COLORS["accent"]),
    )
    fig.update_xaxes(automargin=True, showgrid=False, linecolor=COLORS["border"], tickcolor=COLORS["border"],
                     color=COLORS["muted"], zeroline=False)
    fig.update_yaxes(automargin=True, gridcolor=COLORS["border"], gridwidth=1, color=COLORS["muted"], zeroline=False)
    return fig
