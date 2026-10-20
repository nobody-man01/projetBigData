"""Courbe précision-rappel : chaque point doit être exact pour la règle « alerte si score >= seuil ».

Nécessite pyspark (train_model l'importe) : ignoré dans la CI minimale.
"""
import numpy as np
import pytest

pytest.importorskip("pyspark")
from src.ml.train_model import pr_curve  # noqa: E402


def test_points_exacts_meme_avec_scores_egaux():
    rng = np.random.default_rng(0)
    y = (rng.random(2000) < 0.02).astype(int)
    score = np.round(rng.random(2000) * 0.6 + y * 0.4, 2)    # arrondi : beaucoup de scores égaux
    for p in pr_curve(y, score):
        alert = score >= p["threshold"]
        tp = int((alert & (y == 1)).sum())
        assert p["precision"] == pytest.approx(tp / alert.sum())
        assert p["recall"] == pytest.approx(tp / y.sum())


def test_un_point_par_fraude_retrouvee():
    y = np.array([0, 1, 0, 0, 1, 0, 1, 0, 0, 0])
    score = np.linspace(1, 0.1, 10)                           # scores tous différents
    recalls = {round(p["recall"], 6) for p in pr_curve(y, score, n_extra=2)}
    assert {round(1 / 3, 6), round(2 / 3, 6), 1.0} <= recalls      # les trois fraudes ont chacune leur point
