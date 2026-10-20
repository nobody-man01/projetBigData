"""Figures du rapport, produites à partir des VRAIES données et mesures (aucun chiffre saisi à la main,
sauf les durées d'entraînement, mesurées le 18/10 et consignées dans docs/DECISIONS.md).

Usage:
    python scripts/figures.py            # écrit livrables/figures/*.png et livrables/figures/stats.json

Sources : data/transactions.csv et transactions_test.csv (+ scénarios, pour l'analyse uniquement),
models/metrics*.json (évaluation du modèle), MongoDB scored_transactions (latences mesurées pendant une démo).
Style sobre pour un rapport imprimé : police à empattements, pas de titre dans la figure (la légende du rapport
porte le message), une seule couleur d'accent.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402
from matplotlib.text import Text  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter, ScalarFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import COL_SCORED, DATA_DIR, DATASET_PATH, METRICS_PATH, MONGO_DB, MONGO_URI  # noqa: E402

OUT = ROOT / "livrables" / "figures"
INK, MUTED, GRID = "#1A1A1A", "#555555", "#DDDDDD"
BLUE, GREY, RED = "#1F3A5F", "#A7B1C2", "#B03A2E"
SCENARIOS = {"ATO": "Prise de contrôle", "VELOCITY": "Rafale", "SCAM": "Arnaque",
             "STRUCTURING": "Structuration", "AGENT_SPLIT": "Fractionnement agent"}
FEATURE_LABELS = {
    "amount": "Montant", "log_amount": "Montant (log)", "sender_balance_before": "Solde avant l'opération",
    "hour": "Heure", "is_night": "Opération de nuit", "amount_to_balance_ratio": "Part du solde envoyée",
    "sender_emptied": "Solde vidé", "error_balance_sender": "Écart comptable expéditeur",
    "error_balance_receiver": "Écart comptable destinataire", "has_history": "Compte connu",
    "log_n_tx_hist": "Ancienneté du compte", "amount_vs_avg": "Montant / moyenne du compte",
    "amount_vs_max": "Montant / maximum du compte", "device_is_new": "Nouvel appareil",
    "receiver_is_new": "Nouveau destinataire", "city_is_new": "Ville inhabituelle",
    "sender_n_10min": "Opérations sur 10 min", "log_sender_amount_10min": "Montant envoyé sur 10 min",
    "sender_n_1h": "Opérations sur 1 h", "pair_n_10min": "Même destinataire sur 10 min",
}
FEATURE_LABELS = {k: v.replace("'", "\u2019") for k, v in FEATURE_LABELS.items()}  # apostrophe typographique
# Durées mesurées le 18/10 (commande complète train_model, même machine) : voir docs/DECISIONS.md
DUREES = pd.DataFrame([
    {"jeu": "Nos données\n(200 000 tx)", "mode": "Local (1 JVM, 6 Go)", "s": 258},
    {"jeu": "Nos données\n(200 000 tx)", "mode": "Cluster (2 × 2 cœurs, 1 Go)", "s": 224},
    {"jeu": "PaySim\n(6,36 M tx)", "mode": "Local (1 JVM, 6 Go)", "s": 653},
    {"jeu": "PaySim\n(6,36 M tx)", "mode": "Cluster (2 × 2 cœurs, 1 Go)", "s": 893},
])

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
    "font.size": 11, "axes.edgecolor": MUTED, "axes.linewidth": 0.8, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
    "savefig.dpi": 250, "savefig.bbox": "tight", "legend.frameon": False,
})


class FrFormatter(ScalarFormatter):
    """Graduations au format français : virgule décimale, espace pour les milliers (0,2 ; 15 000)."""

    def __call__(self, x, pos=None):
        s = super().__call__(x, pos).replace(".", ",")
        digits = s.lstrip("−-")
        if digits.isdigit() and len(digits) > 3:
            s = s[: len(s) - len(digits)] + f"{int(digits):,}".replace(",", "\u202f")
        return s


def french(fig) -> None:
    """Format français sur toute la figure : graduations, pourcentages et apostrophes typographiques."""
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            f = axis.get_major_formatter()
            if type(f) is ScalarFormatter:
                axis.set_major_formatter(FrFormatter())
            elif isinstance(f, PercentFormatter):
                axis.set_major_formatter(FuncFormatter(lambda v, _, m=f.xmax: f"{v / m * 100:.0f}\u202f%"))
    for t in fig.findobj(Text):
        if "'" in t.get_text():
            t.set_text(t.get_text().replace("'", "\u2019"))


def save(fig, name: str) -> None:
    french(fig)
    fig.savefig(OUT / f"{name}.png", facecolor="white")
    plt.close(fig)
    print(f"  {name}.png")


def fr(x, d=0):
    """Nombre au format français : 25 000 ; 0,80."""
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


def box(ax, x, y, w, h, title, sub="", lw=1.2):
    ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=INK, lw=lw))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), title, ha="center", va="center", fontsize=11, weight="bold")
    if sub:
        ax.text(x + w / 2, y + h * 0.27, sub, ha="center", va="center", fontsize=9, color=MUTED)


def arrow(ax, x1, y1, x2, y2, label="", dy=1.4):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, lw=1, color=INK))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, ha="center", fontsize=8.5, color=MUTED, style="italic")


def architecture() -> None:
    """Architecture logique : couche temps réel (haut) et couche batch (bas)."""
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.set_xlim(0, 110), ax.set_ylim(0, 44), ax.axis("off")
    ax.text(0.5, 41.5, "Couche temps réel", fontsize=10, weight="bold")
    ax.text(0.5, 14.5, "Couche batch", fontsize=10, weight="bold")
    ax.plot([0.5, 109.5], [17.5, 17.5], color=GRID, lw=1, ls="--")
    y = 25
    box(ax, 1, y, 16, 11, "Producer", "rejoue le CSV")
    box(ax, 23, y, 16, 11, "Apache Kafka", "momo.transactions.raw")
    box(ax, 45, y, 20, 11, "Spark Streaming", "features + forêt aléatoire", lw=2)
    box(ax, 71, y, 16, 11, "MongoDB", "scored_transactions")
    box(ax, 93, y, 16, 11, "Streamlit", "tableau de bord")
    box(ax, 21, 2, 20, 10, "Consumer", "MongoDB transactions")
    box(ax, 45, 2, 20, 10, "Spark MLlib", "profils + entraînement", lw=2)
    arrow(ax, 17.6, y + 5.5, 22.4, y + 5.5, "JSON")
    arrow(ax, 39.6, y + 5.5, 44.4, y + 5.5, "micro-lots")
    arrow(ax, 65.6, y + 5.5, 70.4, y + 5.5, "upsert")
    arrow(ax, 87.6, y + 5.5, 92.4, y + 5.5)
    arrow(ax, 31, y - 0.6, 31, 12.6)
    arrow(ax, 55, 12.6, 55, y - 0.6)
    ax.text(56, 18.6, "profils de comptes + modèle", fontsize=8.5, color=MUTED, style="italic")
    save(fig, "fig_architecture")


def cluster() -> None:
    """Déploiement du mode cluster (docker-compose.cluster.yml)."""
    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 110), ax.set_ylim(0, 46), ax.axis("off")
    ax.add_patch(Rectangle((1, 24), 46, 21, fc="#F4F4F4", ec=MUTED, lw=0.8, ls="--"))
    ax.text(2, 42.7, "Kafka : 3 brokers (KRaft)", fontsize=10, weight="bold")
    for i, x in enumerate((3, 18, 33)):
        box(ax, x, 27, 12, 12, f"kafka-{i + 1}", "broker + contrôleur")
    ax.text(24, 25, "topic : 3 partitions × 3 réplicas, min.insync.replicas = 2", ha="center", fontsize=8.5,
            color=MUTED, style="italic")
    ax.add_patch(Rectangle((52, 24), 57, 21, fc="#F4F4F4", ec=MUTED, lw=0.8, ls="--"))
    ax.text(53, 42.7, "Spark standalone", fontsize=10, weight="bold")
    box(ax, 54, 27, 15, 12, "spark-master", "port 7077, UI 8080")
    box(ax, 73, 27, 16, 12, "spark-worker-1", "2 cœurs, 1,5 Go")
    box(ax, 91, 27, 16, 12, "spark-worker-2", "2 cœurs, 1,5 Go")
    box(ax, 54, 4, 22, 11, "spark-app (driver)", "entraînement, scoring")
    box(ax, 82, 4, 16, 11, "MongoDB", "")
    box(ax, 8, 4, 30, 11, "Machine hôte", "producer, consumer, Streamlit")
    arrow(ax, 23, 15.6, 23, 23.4, "ports 9092 / 9094 / 9096", dy=0)
    arrow(ax, 65, 15.6, 65, 23.4)
    arrow(ax, 76.6, 9.5, 81.4, 9.5)
    arrow(ax, 53.4, 9.5, 38.6, 9.5)
    save(fig, "fig_cluster")


def eda(df: pd.DataFrame, test: pd.DataFrame, stats: dict) -> None:
    """Analyse exploratoire du jeu d'entraînement."""
    local_hour = (pd.to_datetime(df["timestamp"], utc=True, format="ISO8601") + pd.Timedelta(hours=1)).dt.hour
    by_hour = df.assign(h=local_hour).groupby("h").agg(n=("is_fraud", "size"), fraud=("is_fraud", "mean"))
    fig, ax = plt.subplots(figsize=(8, 3.3))
    ax.bar(by_hour.index, by_hour["n"], color=GREY, width=0.8, label="Transactions (axe de gauche)")
    ax.set_xlabel("Heure locale (UTC+1)"), ax.set_ylabel("Transactions"), ax.set_xticks(range(0, 24, 2))
    ax2 = ax.twinx()
    ax2.plot(by_hour.index, by_hour["fraud"] * 100, color=RED, lw=1.8, marker="o", ms=3.5, label="Taux de fraude (axe de droite)")
    ax2.set_ylabel("Taux de fraude (%)"), ax2.grid(False), ax2.spines["right"].set_visible(True)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=9)
    stats.update(fraud_rate_night=float(by_hour.loc[0:4, "fraud"].mean() * 100),
                 fraud_rate_day=float(by_hour.loc[8:19, "fraud"].mean() * 100))
    save(fig, "fig_fraude_heure")

    fig, ax = plt.subplots(figsize=(8, 3.2))
    bins = np.logspace(2, np.log10(df["amount"].max()), 50)
    ax.hist(df.loc[df.is_fraud == 0, "amount"], bins=bins, color=GREY, density=True, label="Transactions normales")
    ax.hist(df.loc[df.is_fraud == 1, "amount"], bins=bins, color=RED, alpha=0.7, density=True, label="Fraudes")
    ax.set_xscale("log"), ax.set_xlabel("Montant (XAF, échelle logarithmique)"), ax.set_ylabel("Densité")
    ax.legend(fontsize=9)
    stats.update(median_amount_normal=float(df.loc[df.is_fraud == 0, "amount"].median()),
                 median_amount_fraud=float(df.loc[df.is_fraud == 1, "amount"].median()))
    save(fig, "fig_montants")

    sc = (pd.read_csv(DATA_DIR / "transactions_scenarios.csv", usecols=["transaction_id", "fraud_scenario"])
          .merge(df.loc[df.is_fraud == 1, ["transaction_id"]], on="transaction_id")["fraud_scenario"]
          .map(SCENARIOS).value_counts().sort_values())
    fig, ax = plt.subplots(figsize=(7, 2.6))
    ax.barh(sc.index, sc.values, color=BLUE, height=0.6)
    for i, v in enumerate(sc.values):
        ax.text(v + 15, i, fr(v), va="center", fontsize=10)
    ax.set_xlabel("Nombre de fraudes (jeu d'entraînement)"), ax.grid(axis="y", visible=False)
    stats["scenarios"] = {k: int(v) for k, v in sc.items()}
    save(fig, "fig_scenarios")


def model_figures(m: dict, stats: dict) -> None:
    """Apport des features, choix de l'algorithme, courbe PR, matrice de confusion, importance, scénarios."""
    variants = [("Transaction seule", "metrics_sans_profils_sans_frequence"), ("+ profils", "metrics_sans_frequence"),
                ("+ fréquence", "metrics_sans_profils"), ("Profils + fréquence", "metrics")]
    abl = []
    for label, f in variants:
        path = METRICS_PATH.with_name(f"{f}.json")
        if path.exists():
            mm = json.loads(path.read_text())
            abl.append({"label": label, "auc_pr": mm["auc_pr"], "precision_high": mm["at_high"]["precision"],
                        "recall_high": mm["at_high"]["recall"], "alerts": mm["at_medium"]["alerts_per_1000"]})
    if abl:
        a = pd.DataFrame(abl)
        fig, ax = plt.subplots(figsize=(7.2, 2.8))
        ax.barh(a["label"], a["auc_pr"], color=[GREY] * (len(a) - 1) + [BLUE], height=0.6)
        for i, v in enumerate(a["auc_pr"]):
            ax.text(v + 0.01, i, fr(v, 2), va="center", fontsize=10)
        ax.set_xlim(0, 1), ax.set_xlabel("AUC-PR sur la période de test"), ax.invert_yaxis(), ax.grid(axis="y", visible=False)
        stats["ablation"] = abl
        save(fig, "fig_ablation")

    if m.get("comparison"):
        comp = pd.DataFrame(m["comparison"]).sort_values("auc_pr_validation")
        fig, ax = plt.subplots(figsize=(7, 2.2))
        ax.barh(comp["label"], comp["auc_pr_validation"], color=[BLUE if x == m["algo"] else GREY for x in comp["algo"]], height=0.55)
        for i, v in enumerate(comp["auc_pr_validation"]):
            ax.text(v + 0.01, i, fr(v, 3), va="center", fontsize=10)
        ax.set_xlim(0, 1), ax.set_xlabel("AUC-PR sur la tranche de validation"), ax.grid(axis="y", visible=False)
        save(fig, "fig_comparaison")

    pr = pd.DataFrame(m["pr_curve"])
    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    ax.plot(pr["recall"], pr["precision"], color=BLUE, lw=2)
    ax.axhline(m["fraud_rate_test"], color=MUTED, ls="--", lw=0.8)
    ax.text(0.02, m["fraud_rate_test"] + 0.02, "classement au hasard", color=MUTED, fontsize=9)
    for key, label, off in (("at_high", "seuil 0,80", (-150, 18)), ("at_medium", "seuil 0,50", (-150, -30))):
        t = m[key]
        ax.scatter(t["recall"], t["precision"], s=30, color=INK, zorder=3)
        ax.annotate(f"{label} : rappel {fr(t['recall'] * 100)} %, précision {fr(t['precision'] * 100)} %",
                    (t["recall"], t["precision"]), xytext=off, textcoords="offset points", fontsize=9,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
    ax.set_xlim(0, 1.02), ax.set_ylim(0, 1.02)
    ax.set_xlabel("Rappel (part des fraudes détectées)"), ax.set_ylabel("Précision (part d'alertes justifiées)")
    save(fig, "fig_courbe_pr")

    t = m["at_high"]
    mat = np.array([[t["tn"], t["fp"]], [t["fn"], t["tp"]]])
    fig, ax = plt.subplots(figsize=(4.2, 3.4))
    ax.imshow(np.zeros_like(mat), cmap="Greys", vmin=0, vmax=1), ax.grid(False)
    for (i, j), v in np.ndenumerate(mat):
        ax.text(j, i, fr(v), ha="center", va="center", fontsize=14, weight="bold" if i == j else "normal")
    ax.set_xticks([0, 1], ["Prédit normal", "Prédit fraude"]), ax.set_yticks([0, 1], ["Normal", "Fraude"])
    ax.set_ylabel("Réalité")
    for x in (-0.5, 0.5, 1.5):
        ax.axhline(x, color=INK, lw=0.8), ax.axvline(x, color=INK, lw=0.8)
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "fig_confusion")

    imp = pd.DataFrame(m["feature_importances"]).head(10).iloc[::-1]
    if not imp.empty:
        def lab(f):
            for p, l in (("tx_type_ohe_", "Type"), ("channel_ohe_", "Canal"), ("operator_ohe_", "Opérateur")):
                if f.startswith(p):
                    return f"{l} : {f[len(p):]}"
            return FEATURE_LABELS.get(f, f)
        fig, ax = plt.subplots(figsize=(7, 3.8))
        ax.barh([lab(f) for f in imp["feature"]], imp["importance"], color=BLUE, height=0.6)
        ax.set_xlabel("Importance dans la forêt aléatoire"), ax.grid(axis="y", visible=False)
        save(fig, "fig_importance")

    if m.get("by_scenario"):
        sc = pd.DataFrame([{"s": SCENARIOS.get(k, k), "n": v["n"], "high": v["recall_high"], "med": v["recall_medium"]}
                           for k, v in m["by_scenario"].items()]).sort_values("med")
        fig, ax = plt.subplots(figsize=(7, 3.0))
        y = np.arange(len(sc))
        ax.barh(y + 0.19, sc["med"], height=0.36, color=GREY, label="seuil 0,50")
        ax.barh(y - 0.19, sc["high"], height=0.36, color=BLUE, label="seuil 0,80")
        for i, (h, md) in enumerate(zip(sc["high"], sc["med"])):
            ax.text(md + 0.01, i + 0.19, f"{fr(md * 100)} %", va="center", fontsize=9)
            ax.text(h + 0.01, i - 0.19, f"{fr(h * 100)} %", va="center", fontsize=9)
        ax.set_yticks(y, [f"{s} (n = {n})" for s, n in zip(sc["s"], sc["n"])]), ax.set_xlim(0, 1.12)
        ax.xaxis.set_major_formatter(PercentFormatter(1.0)), ax.grid(axis="y", visible=False)
        ax.legend(loc="lower right", fontsize=9)
        save(fig, "fig_rappel_scenarios")


def durees() -> None:
    """Durées d'entraînement : une machine contre le cluster (mesures du 18/10)."""
    fig, ax = plt.subplots(figsize=(7, 2.9))
    jeux = DUREES["jeu"].unique()
    x = np.arange(len(jeux))
    for k, (mode, color) in enumerate((("Local (1 JVM, 6 Go)", GREY), ("Cluster (2 × 2 cœurs, 1 Go)", BLUE))):
        vals = [DUREES[(DUREES.jeu == j) & (DUREES["mode"] == mode)]["s"].iloc[0] for j in jeux]
        ax.bar(x + (k - 0.5) * 0.36, vals, width=0.36, color=color, label=mode)
        for xi, v in zip(x, vals):
            ax.text(xi + (k - 0.5) * 0.36, v + 12, f"{v} s", ha="center", fontsize=9)
    ax.set_xticks(x, jeux), ax.set_ylabel("Durée de l'entraînement (s)"), ax.grid(axis="x", visible=False)
    ax.legend(fontsize=9, loc="upper left")
    save(fig, "fig_durees")


def latency(stats: dict) -> None:
    """Distribution des latences de bout en bout mesurées pendant une démonstration réelle."""
    try:
        from pymongo import MongoClient
        cur = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)[MONGO_DB][COL_SCORED].find(
            {"latency_ms": {"$exists": True}}, {"_id": 0, "latency_ms": 1})
        lat = pd.Series([d["latency_ms"] for d in cur]) / 1000
    except Exception as exc:  # MongoDB éteint : pas de figure de latence
        print(f"  (latence ignorée : {exc.__class__.__name__})")
        return
    if lat.empty:
        return
    stats.update(latency_n=int(len(lat)), latency_p50=float(lat.median()), latency_p95=float(lat.quantile(0.95)),
                 latency_min=float(lat.min()), latency_max=float(lat.max()))
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.hist(lat, bins=30, color=GREY, edgecolor="white", linewidth=0.4)
    for q, ls, lbl in ((0.5, "-", "médiane"), (0.95, "--", "95e centile")):
        v = lat.quantile(q)
        ax.axvline(v, color=INK, lw=1, ls=ls)
        ax.text(v, ax.get_ylim()[1] * 0.93, f" {lbl} : {fr(v, 1)} s", fontsize=9)
    ax.set_xlabel("Latence de bout en bout (s) : envoi dans Kafka → score dans MongoDB"), ax.set_ylabel("Transactions")
    save(fig, "fig_latence")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    previous = json.loads((OUT / "stats.json").read_text()) if (OUT / "stats.json").exists() else {}
    df = pd.read_csv(DATASET_PATH)
    test = pd.read_csv(DATA_DIR / "transactions_test.csv")
    m = json.loads(METRICS_PATH.read_text())
    stats = {"n_transactions": int(len(df)), "n_fraud": int(df["is_fraud"].sum()), "fraud_rate": float(df["is_fraud"].mean()),
             "n_test": int(len(test)), "n_test_fraud": int(test["is_fraud"].sum()),
             "n_senders": int(df["sender_id"].nunique()), "period_start": str(df["timestamp"].min()),
             "period_end": str(df["timestamp"].max()), "test_end": str(test["timestamp"].max()),
             "by_type": df.groupby("tx_type")["is_fraud"].agg(["size", "mean"]).round(4).to_dict("index")}
    print("Figures :")
    architecture()
    cluster()
    eda(df, test, stats)
    model_figures(m, stats)
    durees()
    latency(stats)
    if "latency_n" not in stats and "latency_n" in previous:
        # MongoDB éteint ou vidé : on garde les latences mesurées lors de la dernière démonstration
        stats.update({k: v for k, v in previous.items() if k.startswith("latency_")})
        print("  latences reprises de la mesure précédente (stats.json)")
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False, default=float))
    print(f"Statistiques : {OUT / 'stats.json'}")


if __name__ == "__main__":
    main()
