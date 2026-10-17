"""Générateur de transactions Mobile Money simulées (contexte camerounais, XAF, MTN / Orange).

Comptes persistants avec un profil (ville, montant habituel, appareil, contacts), soldes cohérents,
rythme jour/nuit en heure locale, plafonds KYC (500 000 XAF par dépense, 1 000 000 par jour). Scénarios :
  * ATO         : prise de contrôle (appareil inconnu, souvent de nuit), mule qui retire aussitôt ;
  * VELOCITY    : 5 à 10 petits transferts en moins de 3 minutes vers des inconnus ;
  * SCAM        : la victime envoie elle-même un gros montant, depuis son appareil habituel ;
  * STRUCTURING : blanchiment, transferts répétés juste sous le seuil de contrôle (100 000 XAF) ;
  * AGENT_SPLIT : un agent fractionne un dépôt en petits dépôts pour toucher plus de commissions.
Des cas normaux trompeurs (rafales légitimes, vidages de solde, changement de téléphone...) évitent
une détection triviale. Justification détaillée des choix : docs/DONNEES.md et docs/RAPPORT_GENERATEUR.md.

Usage :
    python -m src.generator.generate_dataset --n 200000 --fraud-rate 0.02 --seed 42
    python -m src.generator.generate_dataset --n 250000 --days 30 --test-days 7 --test-fraud-rate 0.003

Sorties (timestamps en UTC, contrat src/common/schema.py) :
  * data/transactions.csv (+ data/transactions_test.csv si --test-days > 0) ;
  * *_scenarios.csv : transaction_id, fraud_scenario (un des KINDS, LEGIT_BURST ou vide), event_id
    (-1 hors événement), reported_at (date de signalement, vide si jamais signalée).
    Pour l'analyse UNIQUEMENT, jamais pour l'entraînement.
Option --unreported-share : une part des SCAM / STRUCTURING / AGENT_SPLIT n'est jamais signalée
(is_fraud = 0 dans le CSV, comme dans la réalité) ; le vrai scénario reste dans *_scenarios.csv.
"""
import argparse
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config.settings import DATA_DIR, DATASET_PATH
from src.common.schema import CITIES, FIELDS, OPERATORS

# --------------------------------------------------------------------------------------------
# Paramètres (tous regroupés ici : on les justifie dans le rapport, on les change ici seulement)
# --------------------------------------------------------------------------------------------
# Fuseau horaire local (Cameroun / zone CEMAC : UTC+1) : sert à placer les heures d'activité.
LOCAL_TZ = timezone(timedelta(hours=1))
# Début de la période simulée (minuit heure locale). Les timestamps sont ÉCRITS en UTC (contrat schema.py).
DEFAULT_START = datetime(2026, 9, 1, tzinfo=LOCAL_TZ)

# Probabilité d'activité par heure locale (0h..23h) : creux la nuit, pic matinée et soirée.
HOUR_WEIGHTS = np.array([0.3, 0.15, 0.1, 0.1, 0.2, 0.6, 1.6, 3.0, 4.0, 4.6, 4.8, 5.2,
                         5.6, 5.2, 4.6, 4.6, 5.0, 5.6, 6.0, 5.0, 3.6, 2.2, 1.1, 0.6])
HOUR_P = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()
# Les fraudes automatisées visent plutôt la nuit (forte pondération de 0h à 6h, creux en journée,
# remontée de 17h à minuit).
NIGHT_WEIGHTS = np.array([4, 4, 4, 3.5, 3, 1.5, 0.8] + [0.4] * 10 + [0.8, 1.5, 3, 3.5, 4, 4, 4],
                         dtype=float)
FRAUD_HOUR_P = 0.5 * HOUR_P + 0.5 * (NIGHT_WEIGHTS / NIGHT_WEIGHTS.sum())

CITY_P = np.array([0.30, 0.25, 0.10, 0.08, 0.07, 0.05, 0.08, 0.07])
TYPE_P = {"CASH_IN": 0.22, "CASH_OUT": 0.27, "TRANSFER": 0.28, "PAYMENT": 0.15, "AIRTIME": 0.08}
# Types où l'émetteur PERD de l'argent. CASH_IN (dépôt) n'y est pas : le client y gagne.
DEBIT_TYPES = ("CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME")
AIRTIME_AMOUNTS = np.array([100, 200, 500, 1000, 2000, 5000])

KINDS = ["ATO", "VELOCITY", "SCAM", "STRUCTURING", "AGENT_SPLIT"]
KIND_P = [0.40, 0.10, 0.40, 0.05, 0.05]   # probabilités PAR ÉVÉNEMENT (pas par ligne)
MULTI_ROW_KINDS = ("VELOCITY", "STRUCTURING", "AGENT_SPLIT")   # au moins 5 lignes, sinon cela n'a pas de sens
FUNDED_KINDS = ("VELOCITY", "STRUCTURING")   # la mule dépose d'abord en agent de quoi financer l'événement

# Plafonds réglementaires (hypothèses d'un compte KYC standard), appliqués à TOUTES les dépenses d'un client
TX_CAP = 500_000          # montant maximal d'une dépense
DAILY_CAP = 1_000_000     # total maximal des dépenses d'un client sur une journée (heure locale)
# Seuil de vérification renforcée (hypothèse) : le blanchiment STRUCTURING fractionne juste en dessous
CONTROL_THRESHOLD = 100_000

# Signalement des fraudes : délai médian (heures) entre la dernière ligne et la plainte / la découverte.
REPORT_DELAY_H = {"ATO": 6, "VELOCITY": 24, "SCAM": 48, "STRUCTURING": 24 * 7, "AGENT_SPLIT": 24 * 10}
# Scénarios qui peuvent ne JAMAIS être signalés (honte de la victime, ou pas de victime consciente)
UNREPORTABLE_KINDS = ("SCAM", "STRUCTURING", "AGENT_SPLIT")
# Colonnes du fichier de scénarios (analyse uniquement, jamais pour l'entraînement)
SCENARIO_COLS = ["fraud_scenario", "event_id", "reported_at"]

ACTIVITY_CAP = 30.0       # plafond du poids d'activité (≈ 10 x la moyenne) : pas de « client » à 5 000 tx
N_RING_DEVICES = 40       # appareils du réseau frauduleux
P_FRESH_DEVICE = 0.5      # part des fraudes faites avec un appareil NEUF (jamais vu nulle part)
P_SHARED_DEVICE = 0.008   # part des transactions normales faites depuis un appareil « du réseau » (cybercafé, prêt)
P_SECOND_DEVICE = 0.012   # part des transactions normales faites depuis un 2e appareil connu
P_PHONE_CHANGE = 0.0004   # changement de téléphone légitime
MULE_LEGIT_SHARE = 0.03   # part des transferts normaux « aléatoires » reçus par un futur compte mule
LEGIT_BURST_SHARE = 0.01  # part des lignes qui sont des rafales LÉGITIMES (paie, tontine, remboursements)
SAME_OPERATOR_SHARE = 0.85  # part des contacts réguliers chez le même opérateur (transferts inter-opérateurs rares)

assert len(HOUR_WEIGHTS) == 24 and len(NIGHT_WEIGHTS) == 24, "il faut exactement 24 poids horaires"
assert len(CITIES) == len(CITY_P), "CITY_P doit avoir une probabilité par ville de schema.CITIES"
assert len(OPERATORS) == 2, "les probabilités d'opérateur (0.55 / 0.45) supposent 2 opérateurs"


def _round_amount(x: float, u: float) -> int:
    """Arrondit un montant comme le font les gens : souvent à 100, 500 ou 1 000 près."""
    x = max(float(x), 100.0)
    if u < 0.55:
        step = 1000 if x >= 10_000 else 500 if x >= 2_000 else 100
    elif u < 0.80:
        step = 500 if x >= 5_000 else 100
    else:
        step = 1
    # round(x/step)*step : multiple de step proche de x (donc de 100 sauf si u est dans [0.8, 1[)
    return int(max(100, round(x / step) * step))


class _World:
    """État des comptes (soldes, profils) pendant la génération."""

    def __init__(self, rng: np.random.Generator, n_customers: int):
        self.rng = rng
        self.n = n_customers
        self.n_agents = max(10, n_customers // 40)
        self.n_merch = max(10, n_customers // 40)
        total = self.n + self.n_agents + self.n_merch
        self.balance = np.concatenate([
            rng.lognormal(np.log(45_000), 1.0, self.n).clip(500, 8_000_000),
            rng.lognormal(np.log(2_000_000), 0.5, self.n_agents),
            rng.lognormal(np.log(1_500_000), 0.6, self.n_merch),
        ]).round()
        assert len(self.balance) == total
        w = np.minimum(rng.pareto(1.5, self.n) + 1.0, ACTIVITY_CAP)   # activité inégale mais plafonnée
        self.p_sender = w / w.sum()
        self._cdf = np.cumsum(self.p_sender)
        self.typical = rng.lognormal(np.log(6_000), 0.8, self.n)      # montant habituel du compte
        self.home_city = rng.choice(len(CITIES), self.n, p=CITY_P)
        self.operator = rng.choice(len(OPERATORS), self.n, p=[0.55, 0.45])
        self.app_user = rng.random(self.n) < 0.35
        self.device = np.arange(self.n)                          # appareil principal (numéro 0..n-1)
        # 2e appareil connu de s : n + s (plage n..2n-1). Les appareils neufs partent donc de 2n+1.
        self.next_device = self.n * 2
        by_op = [np.flatnonzero(self.operator == k) for k in range(len(OPERATORS))]
        self.contacts = []
        for s in range(self.n):
            m = int(rng.integers(3, 9))
            same = rng.random(m) < SAME_OPERATOR_SHARE    # surtout des contacts du même opérateur
            self.contacts.append(np.where(same, rng.choice(by_op[self.operator[s]], m), rng.integers(0, self.n, m)))
        # Les mules sont des clients ordinaires (elles ont une activité normale) : plus nombreuses qu'en v1.
        self.mules = rng.choice(self.n, max(20, self.n // 150), replace=False)
        self.ring_devices = [self.new_device() for _ in range(N_RING_DEVICES)]

    def new_device(self) -> int:
        self.next_device += 1
        return self.next_device

    def acct_id(self, i: int) -> str:
        if i < self.n:
            return f"2376{i:08d}"
        if i < self.n + self.n_agents:
            return f"2377{i - self.n:08d}"
        return f"2378{i - self.n - self.n_agents:08d}"

    def sample_customer(self) -> int:
        """Tire un client avec la MÊME loi d'activité que les émetteurs normaux (pas uniformément)."""
        i = int(np.searchsorted(self._cdf, self.rng.random(), side="right"))
        return min(i, self.n - 1)

    def pick_mule(self, exclude: int = -1) -> int:
        """Tire une mule au hasard, différente de `exclude`."""
        while True:
            m = int(self.rng.choice(self.mules))
            if m != exclude:
                return m

    def agent(self, min_balance: float = 0.0) -> int:
        """Tire un agent. Pour un dépôt, on cherche (8 essais max) un agent qui a assez d'e-money :
        le client va simplement voir un autre agent si le premier n'a plus de liquidités."""
        best = -1
        for _ in range(8):
            a = self.n + int(self.rng.integers(0, self.n_agents))
            if self.balance[a] >= min_balance:
                return a
            if best < 0 or self.balance[a] > self.balance[best]:
                best = a
        return best

    def merchant(self) -> int:
        return self.n + self.n_agents + int(self.rng.integers(0, self.n_merch))


def _fraud_device(rng: np.random.Generator, world: _World) -> int:
    """Appareil d'une fraude : neuf (jamais vu) ou issu du réseau frauduleux."""
    if rng.random() < P_FRESH_DEVICE:
        return world.new_device()
    return int(rng.choice(world.ring_devices))


def _plan_event(rng: np.random.Generator, world: _World, eid: int, kind: str, k: int,
                day_lo: int, day_hi: int, unreported_share: float = 0.0) -> dict:
    """Prépare TOUT ce qui ne dépend pas des soldes : acteurs, appareil, ville, instants de chaque ligne.
    Les montants qui dépendent des soldes sont calculés plus tard, au moment exact de la ligne."""
    # Les fraudes « humaines » ou discrètes suivent le rythme normal ; les automatisées visent la nuit.
    hour_p = HOUR_P if kind in ("SCAM", "STRUCTURING", "AGENT_SPLIT") else FRAUD_HOUR_P
    t = int(rng.integers(day_lo, day_hi)) * 86400 + int(rng.choice(24, p=hour_p)) * 3600 + int(rng.integers(0, 3600))
    gap_low, gap_high = {"ATO": (20, 150), "VELOCITY": (5, 25), "SCAM": (60, 600),
                         "STRUCTURING": (300, 2400), "AGENT_SPLIT": (20, 120)}[kind]
    offsets, step = [], 0
    for _ in range(k):
        offsets.append(step)                     # instant de chaque ligne, en secondes après t
        step += int(rng.integers(gap_low, gap_high))
    # Signalement : plainte ou découverte après un délai ; certains scénarios ne sont jamais signalés.
    reported = not (kind in UNREPORTABLE_KINDS and rng.random() < unreported_share)
    delay = int(REPORT_DELAY_H[kind] * 3600 * rng.lognormal(0, 0.8))
    ev = {"id": eid, "kind": kind, "k": k, "t": t, "offsets": offsets, "got": 0.0,
          "reported": reported, "reported_t": t + offsets[-1] + delay if reported else None}

    if kind == "ATO":
        victim = world.sample_customer()
        ev.update(
            victim=victim,
            mule=world.pick_mule(exclude=victim),
            device=_fraud_device(rng, world),
            city=int(rng.integers(0, len(CITIES))) if rng.random() < 0.6 else int(world.home_city[victim]),
            channel="USSD" if rng.random() < 0.6 else "APP",
        )
    elif kind == "VELOCITY":
        mule = world.pick_mule()
        receivers = []
        for _ in range(k):
            r = int(rng.integers(0, world.n))
            receivers.append((r + 1) % world.n if r == mule else r)
        ev.update(
            mule=mule,
            device=_fraud_device(rng, world),
            city=int(rng.integers(0, len(CITIES))),
            amounts=[_round_amount(rng.uniform(5_000, 40_000), 0.3) for _ in range(k)],
            receivers=receivers,
            t_fund=max(0, t - int(rng.integers(600, 7200))),   # dépôt de la mule, 10 min à 2 h avant
        )
    elif kind == "SCAM":
        victim = world.sample_customer()
        dest = world.pick_mule(exclude=victim) if rng.random() < 0.5 else int(rng.integers(0, world.n))
        if dest == victim:
            dest = (victim + 1) % world.n
        ev.update(victim=victim, dest=dest)
    elif kind == "STRUCTURING":
        # Blanchiment : une mule fractionne une grosse somme en transferts JUSTE SOUS le seuil de contrôle,
        # vers plusieurs comptes, depuis son propre appareil, aux heures normales : discret ligne par ligne.
        mule = world.pick_mule()
        receivers = []
        for _ in range(k):
            r = world.pick_mule(exclude=mule) if rng.random() < 0.6 else int(rng.integers(0, world.n))
            receivers.append((r + 1) % world.n if r == mule else r)
        ev.update(
            mule=mule,
            receivers=receivers,
            # min(...) : l'arrondi à 1 000 près ne doit pas faire atteindre le seuil
            amounts=[min(_round_amount(rng.uniform(0.85, 0.999) * CONTROL_THRESHOLD, rng.uniform(0.3, 1.0)),
                         CONTROL_THRESHOLD - 500) for _ in range(k)],
            t_fund=max(0, t - int(rng.integers(1800, 4 * 3600))),   # dépôt de la mule, 30 min à 4 h avant
        )
    else:  # AGENT_SPLIT
        # Fraude d'agent : un dépôt client est fractionné en k petits dépôts pour toucher k commissions.
        # Le client et l'agent sont habituels : seul le motif (même paire, rapprochés) trahit la fraude.
        customer = world.sample_customer()
        total = max(20_000.0, float(world.typical[customer]) * rng.uniform(3, 10))
        parts = rng.dirichlet(np.full(k, 3.0)) * total
        ev.update(customer=customer, agent=world.agent(total),
                  amounts=[_round_amount(p, 0.3) for p in parts])
    return ev


def _plan_burst(rng: np.random.Generator, world: _World, bid: int, k: int, days: int) -> dict:
    """Rafale LÉGITIME : un client envoie k petits transferts rapprochés (paie, tontine, remboursements),
    depuis son appareil et sa ville habituels, surtout vers ses contacts, aux heures d'activité normales."""
    t = int(rng.integers(0, days)) * 86400 + int(rng.choice(24, p=HOUR_P)) * 3600 + int(rng.integers(0, 3600))
    s = world.sample_customer()
    offsets, step = [], 0
    for _ in range(k):
        offsets.append(step)
        step += int(rng.integers(5, 40))          # rythme proche de celui d'une rafale frauduleuse
    c = world.contacts[s]
    receivers = []
    for _ in range(k):
        r = int(c[rng.integers(len(c))]) if rng.random() < 0.7 else int(rng.integers(0, world.n))
        receivers.append((s + 1) % world.n if r == s else r)
    return {"id": bid, "t": t, "k": k, "sender": s, "offsets": offsets, "receivers": receivers,
            "base": float(world.typical[s]) * float(rng.uniform(0.3, 1.2))}   # montant « de cotisation »


def _generate(n: int, fraud_rate: float, seed: int, n_accounts, days: int, start,
              burst_share: float = LEGIT_BURST_SHARE, test_days: int = 0, test_fraud_rate: float = None,
              unreported_share: float = 0.0):
    """n = nombre total de lignes (entraînement + test). Avec test_days > 0, les test_days derniers jours
    reçoivent ~n * test_days / (days + test_days) lignes au taux test_fraud_rate (défaut : fraud_rate).
    unreported_share : part des événements SCAM / STRUCTURING / AGENT_SPLIT jamais signalés (is_fraud = 0
    dans le CSV, mais le vrai scénario reste dans le fichier de scénarios)."""
    rng = np.random.default_rng(seed)
    start = start or DEFAULT_START
    world = _World(rng, n_accounts or max(300, n // 15))
    rows, meta = [], []          # meta : (instant, n° d'ordre, scénario, event_id, signalement), une par ligne
    counter = [0]
    device_ids = {}

    def device_id(device: int) -> str:
        """Identifiant public d'un appareil : hash salé par la seed. Les numéros internes sont croissants
        (un grand numéro = appareil créé en cours de route) : les écrire tels quels trahirait les fraudes."""
        if device not in device_ids:
            h = hashlib.blake2b(f"{seed}:{device}".encode(), digest_size=6).hexdigest()
            device_ids[device] = f"dev-{h}"
        return device_ids[device]

    spent_today = {}             # (client, jour local) -> total déjà dépensé, pour le plafond journalier

    def emit(t: float, s: int, r: int, tx_type: str, amount: float, channel: str, city: int,
             device: int, fraud: int, scenario: str = "", event_id: int = -1, reported_t=None) -> float:
        """Applique la transaction aux soldes et enregistre la ligne. Retourne le montant réel (0 si annulée)."""
        if tx_type not in DEBIT_TYPES and tx_type != "CASH_IN":
            raise ValueError(f"Type de transaction inconnu : {tx_type!r}")
        if s == r:
            raise ValueError("L'émetteur et le receveur doivent être deux comptes différents")
        amount = float(int(amount))
        sb, rb = float(world.balance[s]), float(world.balance[r])     # soldes AVANT
        day_key = (s, int(t) // 86400)
        if tx_type in DEBIT_TYPES:
            amount = min(amount, sb)      # on ne dépense pas plus que son solde
            if s < world.n:               # plafonds KYC : fraudeurs compris, l'opérateur les impose à tous
                amount = min(amount, TX_CAP, DAILY_CAP - spent_today.get(day_key, 0.0))
        else:
            amount = min(amount, rb)      # dépôt : l'agent ne peut pas donner plus d'e-money qu'il n'en a
        if amount < 100:
            return 0.0                    # transaction annulée
        if tx_type == "CASH_IN":          # le client dépose : il gagne, l'agent « donne » de l'e-money
            sa, ra = sb + amount, rb - amount
        else:                             # l'émetteur perd, le receveur gagne
            sa, ra = sb - amount, rb + amount
        world.balance[s], world.balance[r] = sa, ra
        if tx_type in DEBIT_TYPES and s < world.n:
            spent_today[day_key] = spent_today.get(day_key, 0.0) + amount
        if rng.random() < 0.002:          # rares incohérences de journalisation (n'affectent que le CSV)
            sa = sa + float(rng.choice([-1, 1]) * _round_amount(amount * rng.uniform(0.05, 0.5), 1.0))
        counter[0] += 1
        rows.append({
            "transaction_id": str(uuid.UUID(int=(int(rng.integers(0, 2**62)) << 64) | counter[0])),
            "timestamp": (start + timedelta(seconds=int(t))).astimezone(timezone.utc).isoformat(),
            "sender_id": world.acct_id(s), "receiver_id": world.acct_id(r), "tx_type": tx_type,
            "amount": amount, "sender_balance_before": sb, "sender_balance_after": float(sa),
            "receiver_balance_before": rb, "receiver_balance_after": float(ra),
            "operator": OPERATORS[world.operator[s]] if s < world.n else OPERATORS[0],
            "channel": channel, "city": CITIES[city], "device_id": device_id(device),
            "is_fraud": fraud,
        })
        meta.append((int(t), counter[0], scenario, event_id, reported_t))
        return amount

    # --- Planification : événements de fraude d'abord, puis le nombre de lignes normales ---
    # Période d'entraînement [0, days[ puis, si test_days > 0, période de test [days, days + test_days[
    # avec son propre taux de fraude (même monde, mêmes comptes, soldes continus : vrai split temporel).
    total_days = days + test_days
    n_test = int(round(n * test_days / total_days))
    periods = [(0, days, n - n_test, fraud_rate)]
    if test_days > 0:
        periods.append((days, total_days, n_test, fraud_rate if test_fraud_rate is None else test_fraud_rate))
    events, n_fraud_target = [], 0
    for day_lo, day_hi, n_period, rate in periods:
        target = int(round(n_period * rate))
        n_fraud_target += target
        total = 0
        while total < target:
            remaining = target - total
            kind = str(rng.choice(KINDS, p=KIND_P))
            if kind in MULTI_ROW_KINDS and remaining < 5:
                kind = "SCAM"                 # une rafale de moins de 5 lignes n'aurait pas de sens
            if kind == "ATO":
                k = int(rng.integers(1, 4))
            elif kind in ("VELOCITY", "AGENT_SPLIT"):
                k = int(rng.integers(5, 11))
            elif kind == "STRUCTURING":
                k = int(rng.integers(5, 10))  # 9 x < 100 000 reste sous le plafond journalier
            else:
                k = int(rng.integers(1, 3))
            k = min(k, remaining)
            events.append(_plan_event(rng, world, len(events), kind, k, day_lo, day_hi, unreported_share))
            total += k

    # Rafales légitimes (leurs identifiants continuent ceux des événements de fraude)
    bursts, burst_rows = [], 0
    burst_target = int(round(n * burst_share))
    while burst_rows < burst_target:
        k = int(rng.integers(4, 11))
        bursts.append(_plan_burst(rng, world, len(events) + len(bursts), k, total_days))
        burst_rows += k
    burst_by_id = {b["id"]: b for b in bursts}

    n_funded = sum(1 for e in events if e["kind"] in FUNDED_KINDS)   # 1 dépôt de mule par événement financé
    n_legit = max(0, n - n_fraud_target - n_funded - burst_rows - len(bursts))   # len(bursts) : dépôts de départ
    day = rng.integers(0, total_days, n_legit)
    t_legit = day * 86400 + rng.choice(24, n_legit, p=HOUR_P) * 3600 + rng.integers(0, 3600, n_legit)
    senders = rng.choice(world.n, n_legit, p=world.p_sender)
    types = rng.choice(list(TYPE_P), n_legit, p=list(TYPE_P.values()))
    u_round, u_city, u_dev, u_chan, u_rec, u_empty, u_phone = rng.random((7, n_legit))

    # Chronologie : (instant, priorité, a, b). Priorité 0 = normale, 1 = dépôt de mule, 2 = ligne de fraude,
    # 3 = ligne de rafale légitime. À instant égal, on respecte cet ordre.
    timeline = [(int(t_legit[i]), 0, i, 0) for i in range(n_legit)]
    for ev in events:
        for j in range(ev["k"]):
            timeline.append((ev["t"] + ev["offsets"][j], 2, ev["id"], j))
        if ev["kind"] in FUNDED_KINDS:
            timeline.append((ev["t_fund"], 1, ev["id"], 0))
    for b in bursts:
        for j in range(b["k"]):
            timeline.append((b["t"] + b["offsets"][j], 3, b["id"], j))
    timeline.sort()

    def normal(idx: int, t: int) -> None:
        """Une transaction normale (idx = position dans les tirages préparés)."""
        s, tx_type = int(senders[idx]), str(types[idx])
        if u_phone[idx] < P_PHONE_CHANGE:               # changement de téléphone légitime
            world.device[s] = world.new_device()
        city = int(world.home_city[s]) if u_city[idx] > 0.07 else int(rng.integers(0, len(CITIES)))
        ud = u_dev[idx]
        if ud < P_SHARED_DEVICE:                        # téléphone prêté / cybercafé
            device = int(rng.choice(world.ring_devices))
        elif ud < P_SHARED_DEVICE + P_SECOND_DEVICE:    # 2e appareil connu
            device = world.n + s
        else:
            device = int(world.device[s])
        if tx_type == "AIRTIME":
            amount = float(rng.choice(AIRTIME_AMOUNTS))
        else:
            mult = {"CASH_IN": 1.6, "CASH_OUT": 1.2, "TRANSFER": 1.0, "PAYMENT": 0.7}[tx_type]
            amount = _round_amount(world.typical[s] * mult * rng.lognormal(0, 0.6), u_round[idx])
        if tx_type in DEBIT_TYPES and u_empty[idx] < 0.008:    # vidage légitime (loyer, scolarité)
            amount = _round_amount(world.balance[s] * rng.uniform(0.85, 1.0), 1.0)
        elif tx_type in DEBIT_TYPES and u_empty[idx] < 0.04:   # grosse dépense légitime (commerce, épargne)
            amount = _round_amount(world.balance[s] * rng.uniform(0.25, 0.9), u_round[idx])
        if tx_type in DEBIT_TYPES and world.balance[s] < amount:   # solde insuffisant -> recharge d'abord
            tx_type = "CASH_IN"
            amount = _round_amount(max(amount * 1.5, world.typical[s] * 3), u_round[idx])
        if tx_type == "TRANSFER":
            c = world.contacts[s]
            u = u_rec[idx]
            if u < 0.85:                                # contact régulier
                r = int(c[rng.integers(len(c))])
            elif u < 1.0 - MULE_LEGIT_SHARE:            # inconnu
                r = int(rng.integers(0, world.n))
            else:                                       # un compte qui servira (aussi) de mule
                r = world.pick_mule()
            if r == s:
                r = (s + 1) % world.n
        elif tx_type == "CASH_IN":
            r = world.agent(amount)         # l'agent doit avoir assez d'e-money pour le dépôt
        elif tx_type == "CASH_OUT":
            r = world.agent()
        else:
            r = world.merchant()
        if tx_type in ("CASH_IN", "CASH_OUT"):
            channel = "AGENT" if u_chan[idx] < 0.92 else "USSD"
        else:
            channel = "APP" if (world.app_user[s] and u_chan[idx] < 0.85) or u_chan[idx] < 0.05 else "USSD"
        emit(t, s, r, tx_type, amount, channel, city, device, 0)

    def burst_row(b: dict, j: int, t: int) -> None:
        """Une ligne d'une rafale légitime : transfert habituel, étiqueté NORMAL (is_fraud = 0)."""
        s = b["sender"]
        if j == 0:   # le client a de quoi payer : sinon il fait d'abord un dépôt (vraie transaction normale)
            need = b["base"] * 1.2 * b["k"] * 1.1 - float(world.balance[s])
            if need >= 100:
                amount = _round_amount(need, 0.3)
                emit(t, s, world.agent(amount), "CASH_IN", amount, "AGENT",
                     int(world.home_city[s]), int(world.device[s]), 0)
        amt = _round_amount(b["base"] * rng.uniform(0.8, 1.2), rng.random())
        emit(t, s, b["receivers"][j], "TRANSFER", amt, "APP" if world.app_user[s] else "USSD",
             int(world.home_city[s]), int(world.device[s]), 0, "LEGIT_BURST", b["id"])

    def fund_mule(ev: dict, t: int) -> None:
        """VELOCITY / STRUCTURING : la mule dépose en agent de quoi financer l'événement (vraie transaction,
        étiquetée normale)."""
        m = ev["mule"]
        need = sum(ev["amounts"]) * 1.2 - float(world.balance[m])
        if need >= 100:
            amount = _round_amount(need, 0.3)
            emit(t, m, world.agent(amount), "CASH_IN", amount, "AGENT",
                 int(world.home_city[m]), int(world.device[m]), 0)

    def event_row(ev: dict, j: int, t: int) -> None:
        """Une ligne d'un événement de fraude (les montants dépendent des soldes À CET INSTANT)."""
        kind, eid = ev["kind"], ev["id"]
        # Étiquette : 1 si la fraude est un jour signalée, sinon 0 (le vrai scénario reste dans le fichier
        # de scénarios). Mêmes arguments de fin pour toutes les lignes de l'événement.
        tag = (int(ev["reported"]), kind, eid, ev["reported_t"])
        if kind == "ATO":
            v, m = ev["victim"], ev["mule"]
            if j % 2 == 0:       # la victime est vidée vers la mule
                amt = _round_amount(world.balance[v] * rng.uniform(0.4, 1.0), rng.random())
                ev["got"] = emit(t, v, m, "TRANSFER", amt, ev["channel"], ev["city"], ev["device"], *tag)
            elif ev["got"] >= 100:   # la mule retire aussitôt une part de ce qu'elle vient de recevoir
                emit(t, m, world.agent(), "CASH_OUT", ev["got"] * rng.uniform(0.85, 1.0), "AGENT",
                     int(rng.integers(0, len(CITIES))), ev["device"], *tag)
        elif kind == "VELOCITY":
            emit(t, ev["mule"], ev["receivers"][j], "TRANSFER", ev["amounts"][j], "USSD", ev["city"],
                 ev["device"], *tag)
        elif kind == "SCAM":     # la victime agit depuis son appareil habituel
            v = ev["victim"]
            amt = min(world.typical[v] * rng.uniform(3, 15), world.balance[v] * rng.uniform(0.2, 0.9))
            emit(t, v, ev["dest"], "TRANSFER", _round_amount(amt, rng.random()),
                 "APP" if world.app_user[v] else "USSD", int(world.home_city[v]), int(world.device[v]), *tag)
        elif kind == "STRUCTURING":   # la mule agit depuis SON appareil et SA ville : rien d'anormal isolément
            m = ev["mule"]
            emit(t, m, ev["receivers"][j], "TRANSFER", ev["amounts"][j],
                 "APP" if world.app_user[m] else "USSD", int(world.home_city[m]), int(world.device[m]), *tag)
        else:  # AGENT_SPLIT : dépôts fractionnés, même client, même agent, à quelques secondes d'écart
            c = ev["customer"]
            emit(t, c, ev["agent"], "CASH_IN", ev["amounts"][j], "AGENT", int(world.home_city[c]),
                 int(world.device[c]), *tag)

    # --- Rejeu du temps : chaque élément est traité à son instant exact ---
    for t, prio, a, b in timeline:
        if prio == 0:
            normal(a, t)
        elif prio == 1:
            fund_mule(events[a], t)
        elif prio == 2:
            event_row(events[a], b, t)
        else:
            burst_row(burst_by_id[a], b, t)

    df = pd.DataFrame(rows, columns=list(FIELDS))
    info = pd.DataFrame(meta, columns=["_t", "_seq", "fraud_scenario", "event_id", "_reported_t"])
    info["reported_at"] = [
        "" if pd.isna(x) else (start + timedelta(seconds=int(x))).astimezone(timezone.utc).isoformat()
        for x in info.pop("_reported_t")]
    df = pd.concat([df, info], axis=1).sort_values(["_t", "_seq"]).reset_index(drop=True)
    scenarios = df[SCENARIO_COLS].copy()
    df = df.drop(columns=["_t", "_seq", *SCENARIO_COLS])
    return df, scenarios


def generate_dataset(n: int = 100_000, fraud_rate: float = 0.02, seed: int = 42,
                     n_accounts: int = None, days: int = 30, start: datetime = None,
                     with_scenarios: bool = False, burst_share: float = LEGIT_BURST_SHARE,
                     test_days: int = 0, test_fraud_rate: float = None, unreported_share: float = 0.0):
    """Retourne un DataFrame respectant exactement src.common.schema.FIELDS (mêmes noms de colonnes).
    Avec with_scenarios=True, retourne (df, scenarios) ; scenarios (SCENARIO_COLS) sert
    uniquement à l'analyse, jamais à l'entraînement. Avec test_days > 0, df couvre days + test_days jours
    (les lignes à partir de start + days forment la période de test, au taux test_fraud_rate)."""
    df, scen = _generate(n, fraud_rate, seed, n_accounts, days, start, burst_share, test_days, test_fraud_rate,
                         unreported_share)
    return (df, scen) if with_scenarios else df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200_000)
    p.add_argument("--fraud-rate", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--accounts", type=int, default=None,
                   help="nombre de clients (défaut : n // 15, minimum 300)")
    p.add_argument("--burst-share", type=float, default=LEGIT_BURST_SHARE,
                   help="part des lignes qui sont des rafales légitimes (0 pour les désactiver)")
    p.add_argument("--out", default=str(DATASET_PATH))
    p.add_argument("--test-days", type=int, default=0,
                   help="jours ajoutés APRÈS --days et écrits à part dans <out>_test.csv (0 : pas de jeu de test). "
                        "--n est alors le total, réparti au prorata des jours")
    p.add_argument("--test-fraud-rate", type=float, default=0.003,
                   help="taux de fraude de la période de test (réaliste : 0,1 à 0,5 %%)")
    p.add_argument("--unreported-share", type=float, default=0.0,
                   help="part des événements SCAM / STRUCTURING / AGENT_SPLIT jamais signalés (is_fraud = 0)")
    a = p.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df, scen = _generate(a.n, a.fraud_rate, a.seed, a.accounts, a.days, DEFAULT_START, a.burst_share,
                         a.test_days, a.test_fraud_rate, a.unreported_share)
    is_test = pd.to_datetime(df["timestamp"]) >= DEFAULT_START + timedelta(days=a.days)
    outputs = [(a.out, ~is_test, a.fraud_rate)]
    if a.test_days > 0:
        outputs.append((str(a.out).replace(".csv", "_test.csv"), is_test, a.test_fraud_rate))
    for path, mask, rate in outputs:
        part, part_scen = df[mask], scen[mask]
        part.to_csv(path, index=False)
        pd.concat([part[["transaction_id"]], part_scen], axis=1).to_csv(
            str(path).replace(".csv", "_scenarios.csv"), index=False)
        print(f"{len(part)} transactions écrites dans {path} (fraudes : {part.is_fraud.sum()}, "
              f"taux {part.is_fraud.mean():.2%}, visé {rate:.2%})")
        print(part_scen.loc[part.is_fraud == 1, "fraud_scenario"].value_counts().to_string())
        hidden = (part.is_fraud == 0) & ~part_scen.fraud_scenario.isin(["", "LEGIT_BURST"])
        if hidden.any():
            print(f"fraudes jamais signalées (is_fraud = 0) : {hidden.sum()} lignes")
        print(f"rafales légitimes (is_fraud = 0) : {(part_scen.fraud_scenario == 'LEGIT_BURST').sum()} lignes")


if __name__ == "__main__":
    main()
