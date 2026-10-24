"""Tests sans MongoDB : comptes liés (page Investigation), seuils exacts (page Performance), palettes de couleurs.

Ignorés automatiquement si pymongo ou streamlit ne sont pas installés (CI minimale).
"""
import pandas as pd
import pytest

pytest.importorskip("pymongo")
pytest.importorskip("streamlit")

from src.dashboard.data_access import account_counterparts, threshold_options  # noqa: E402
from src.dashboard.ui.theme import COLORS, PALETTES  # noqa: E402

TX = pd.DataFrame([
    {"transaction_id": "t1", "timestamp": "2026-10-01T01:30:12+00:00", "sender_id": "V", "receiver_id": "M",
     "amount": 48000.0, "fraud_score": 0.98, "risk_level": "HIGH"},
    {"transaction_id": "t2", "timestamp": "2026-10-01T01:32:45+00:00", "sender_id": "V", "receiver_id": "M",
     "amount": 21500.0, "fraud_score": 0.97, "risk_level": "HIGH"},
    {"transaction_id": "t3", "timestamp": "2026-10-01T09:00:00+00:00", "sender_id": "A", "receiver_id": "V",
     "amount": 5000.0, "fraud_score": 0.10, "risk_level": "LOW"},
    {"transaction_id": "t4", "timestamp": "2026-10-01T10:00:00+00:00", "sender_id": "V", "receiver_id": "A",
     "amount": 2000.0, "fraud_score": 0.60, "risk_level": "MEDIUM"},
])


def test_contreparties_agregees_par_compte():
    links = account_counterparts(TX, "V").set_index("counterpart")
    assert list(links.index) == ["M", "A"]                      # la plus risquée d'abord
    assert links.loc["M", "n"] == 2 and links.loc["M", "amount"] == 69500.0
    assert links.loc["M", "direction"] == "Envoyé" and links.loc["M", "worst_level"] == "HIGH"
    assert links.loc["A", "direction"] == "Les deux"            # A a payé V et V a payé A
    assert links.loc["A", "worst_level"] == "MEDIUM"            # le pire niveau des deux transactions


def test_contreparties_vide():
    assert account_counterparts(TX.iloc[0:0], "V").empty


METRICS = {
    "n_test_fraud": 10,
    "at_high": {"threshold": 0.8, "tp": 6, "fp": 4, "fn": 4, "precision": 0.6, "recall": 0.6},
    "at_medium": {"threshold": 0.5, "tp": 8, "fp": 12, "fn": 2, "precision": 0.4, "recall": 0.8},
    # points de la courbe : chaque point est exact (alerte si score >= seuil)
    "pr_curve": [{"threshold": 0.95, "precision": 1.0, "recall": 0.1},
                 {"threshold": 0.801, "precision": 6 / 9, "recall": 0.6},
                 {"threshold": 0.3, "precision": 0.25, "recall": 0.9},
                 {"threshold": 0.01, "precision": 0.1, "recall": 1.0}],
}


def test_seuils_exacts_et_tries():
    options = threshold_options(METRICS)
    seuils = [round(o["threshold"], 2) for o in options]
    assert seuils == sorted(seuils) and 0.01 not in seuils     # sous min_threshold : ignoré
    by = {round(o["threshold"], 2): o for o in options}
    assert by[0.8]["false_alerts"] == 4 and by[0.8]["caught"] == 6   # 0,801 s'affiche 0,80 : la config l'emporte
    assert by[0.3]["caught"] == 9 and by[0.3]["false_alerts"] == 27  # 9 vraies sur 36 alertes
    assert by[0.95]["missed"] == 9


def test_fausses_alertes_croissent_quand_le_seuil_baisse():
    options = threshold_options(METRICS)
    fausses = [o["false_alerts"] for o in options]
    assert fausses == sorted(fausses, reverse=True)


def test_palettes_completes_et_mode_sombre_par_defaut():
    assert set(PALETTES["dark"]) == set(PALETTES["light"])
    assert COLORS["bg"] == PALETTES["dark"]["bg"]             # hors Streamlit : mode sombre
