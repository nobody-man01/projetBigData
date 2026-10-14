"""Thème Plotly commun : fond transparent, grille légère, polices et couleurs du dashboard."""
import plotly.graph_objects as go

from src.dashboard.ui.theme import COLORS


def style(fig: go.Figure, height: int = 320) -> go.Figure:
    """Applique le style sombre commun à une figure Plotly et la renvoie."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=COLORS["text"], size=12),
        hoverlabel=dict(bgcolor=COLORS["surface_2"], bordercolor=COLORS["border"],
                        font=dict(family="JetBrains Mono, monospace", color=COLORS["text"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )
    fig.update_xaxes(showgrid=False, linecolor=COLORS["border"], tickcolor=COLORS["border"],
                     color=COLORS["muted"], zeroline=False)
    fig.update_yaxes(gridcolor=COLORS["border"], gridwidth=1, color=COLORS["muted"], zeroline=False)
    return fig
