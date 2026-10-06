"""Générateur de transactions Mobile Money simulées, version réaliste (v1).

Ce qui rend les données crédibles (et ce qu'on doit expliquer dans le rapport) :
  * Comptes PERSISTANTS : chaque compte a un profil (ville d'origine, montant habituel, appareil,
    contacts réguliers, opérateur). Une même personne fait donc plusieurs transactions cohérentes.
  * Montants en XAF ENTIERS et souvent RONDS (500, 1 000, 5 000...), le franc CFA n'a pas de centimes.
  * Rythme JOUR / NUIT réaliste : pic en journée et en soirée, creux la nuit.
  * Activité très INÉGALE : quelques comptes très actifs, beaucoup de comptes peu actifs.
  * Soldes cohérents : chaque transaction respecte la comptabilité (avant/après), à de rares erreurs près.
  * Agents (dépôt/retrait) et marchands (paiement/crédit téléphonique) distincts des clients.

Trois scénarios de fraude, volontairement de difficulté différente :
  1. PRISE DE CONTRÔLE (ATO)  : appareil jamais vu, souvent autre ville, de nuit, vers un compte « mule »
                                qui retire aussitôt l'argent en agent.
  2. RAFALE (VELOCITY)        : 5 à 10 petits transferts en moins de 2 minutes vers des inconnus.
  3. ARNAQUE (SCAM)           : la victime envoie elle-même un gros montant à un inconnu, depuis son
                                appareil habituel : très difficile à distinguer d'un cas normal.

Cas normaux « trompeurs » (pour que la détection ne soit pas triviale) : vidage de solde légitime
(loyer, scolarité), changement de téléphone, déplacement dans une autre ville, activité de nuit.

Usage :
    python -m src.generator.generate_dataset --n 200000 --fraud-rate 0.02 --seed 42
Écrit data/transactions.csv (contrat src/common/schema.py) et data/transactions_scenarios.csv
(transaction_id, fraud_scenario) pour l'analyse : ce second fichier ne sert JAMAIS à l'entraînement.
"""
import argparse
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config.settings import DATA_DIR, DATASET_PATH
from src.common.schema import CHANNELS, CITIES, FIELDS, OPERATORS, TX_TYPES

# Probabilité d'activité par heure (0h..23h) : creux la nuit, pic matinée et soirée.
HOUR_WEIGHTS = np.array([0.3, 0.15, 0.1, 0.1, 0.2, 0.6, 1.6, 3.0, 4.0, 4.6, 4.8, 5.2,
                         5.6, 5.2, 4.6, 4.6, 5.0, 5.6, 6.0, 5.0, 3.6, 2.2, 1.1, 0.6])
HOUR_P = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()
# Les fraudes automatisées visent plutôt la nuit.
NIGHT_WEIGHTS = np.array([4, 4, 4, 3.5, 3, 1.5, 0.8] + [0.4] * 17, dtype=float)
FRAUD_HOUR_P = 0.5 * HOUR_P + 0.5 * (NIGHT_WEIGHTS / NIGHT_WEIGHTS.sum())

CITY_P = np.array([0.30, 0.25, 0.10, 0.08, 0.07, 0.05, 0.08, 0.07])
TYPE_P = {"CASH_IN": 0.22, "CASH_OUT": 0.27, "TRANSFER": 0.28, "PAYMENT": 0.15, "AIRTIME": 0.08}
DEBIT_TYPES = ("CASH_OUT", "TRANSFER", "PAYMENT", "AIRTIME")
AIRTIME_AMOUNTS = np.array([100, 200, 500, 1000, 2000, 5000])


def _round_amount(x: float, u: float) -> int:
    """Arrondit un montant comme le font les gens : souvent à 100, 500 ou 1 000 près."""
    x = max(float(x), 100.0)
    if u < 0.55:
        step = 1000 if x >= 10_000 else 500 if x >= 2_000 else 100
    elif u < 0.80:
        step = 500 if x >= 5_000 else 100
    else:
        step = 1
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
        w = rng.pareto(1.5, self.n) + 1.0                      # activité très inégale
        self.p_sender = w / w.sum()
        self.typical = rng.lognormal(np.log(6_000), 0.8, self.n)  # montant habituel du compte
        self.home_city = rng.choice(len(CITIES), self.n, p=CITY_P)
        self.operator = rng.choice(len(OPERATORS), self.n, p=[0.55, 0.45])
        self.app_user = rng.random(self.n) < 0.35
        self.device = np.arange(self.n)                          # appareil principal
        self.next_device = self.n * 2                            # compteur d'appareils neufs
        self.contacts = [rng.integers(0, self.n, rng.integers(3, 9)) for _ in range(self.n)]
        self.mules = rng.choice(self.n, max(8, self.n // 300), replace=False)
        self.ring_devices = [self.new_device() for _ in range(12)]  # appareils d'un réseau frauduleux

    def new_device(self) -> int:
        self.next_device += 1
        return self.next_device

    def acct_id(self, i: int) -> str:
        if i < self.n:
            return f"2376{i:08d}"
        if i < self.n + self.n_agents:
            return f"2377{i - self.n:08d}"
        return f"2378{i - self.n - self.n_agents:08d}"

    def agent(self) -> int:
        return self.n + int(self.rng.integers(0, self.n_agents))

    def merchant(self) -> int:
        return self.n + self.n_agents + int(self.rng.integers(0, self.n_merch))


def _generate(n: int, fraud_rate: float, seed: int, n_accounts, days: int, start):
    rng = np.random.default_rng(seed)
    start = start or datetime(2026, 9, 1, tzinfo=timezone.utc)
    world = _World(rng, n_accounts or max(300, n // 15))
    rows, scen = [], []
    counter = [0]

    def emit(t: float, s: int, r: int, tx_type: str, amount: float, channel: str, city: int,
             device: int, fraud: int, scenario: str = "") -> float:
        """Applique la transaction aux soldes et enregistre la ligne. Retourne le montant réel."""
        amount = float(int(amount))
        sb = world.balance[s]
        if tx_type in DEBIT_TYPES:
            amount = min(amount, float(sb))
        if amount < 100:
            return 0.0
        sa = sb - amount if tx_type in DEBIT_TYPES else sb + amount
        rb = world.balance[r]
        ra = rb - amount if tx_type == "CASH_IN" else rb + amount   # l'agent « donne » du e-money au dépôt
        world.balance[s], world.balance[r] = sa, ra
        if rng.random() < 0.002:                                    # rares incohérences de journalisation
            sa = sa + float(rng.choice([-1, 1]) * _round_amount(amount * rng.uniform(0.05, 0.5), 1.0))
        counter[0] += 1
        rows.append({
            "transaction_id": str(uuid.UUID(int=(int(rng.integers(0, 2**62)) << 64) | counter[0])),
            "timestamp": (start + timedelta(seconds=int(t))).isoformat(),
            "sender_id": world.acct_id(s), "receiver_id": world.acct_id(r), "tx_type": tx_type,
            "amount": amount, "sender_balance_before": float(sb), "sender_balance_after": float(sa),
            "receiver_balance_before": float(rb), "receiver_balance_after": float(ra),
            "operator": OPERATORS[world.operator[s]] if s < world.n else OPERATORS[0],
            "channel": channel, "city": CITIES[city], "device_id": f"dev-{device:07d}",
            "is_fraud": fraud,
        })
        scen.append(scenario)
        return amount

    # --- Planification : combien de lignes normales et de lignes frauduleuses ---
    n_fraud_target = int(round(n * fraud_rate))
    n_legit = n - n_fraud_target
    events, total = [], 0
    while total < n_fraud_target:
        kind = str(rng.choice(["ATO", "VELOCITY", "SCAM"], p=[0.45, 0.12, 0.43]))
        k = {"ATO": int(rng.integers(1, 4)), "VELOCITY": int(rng.integers(5, 11)),
             "SCAM": int(rng.integers(1, 3))}[kind]
        k = min(k, n_fraud_target - total)
        hour_p = HOUR_P if kind == "SCAM" else FRAUD_HOUR_P
        t = int(rng.integers(0, days)) * 86400 + int(rng.choice(24, p=hour_p)) * 3600 + int(rng.integers(0, 3600))
        events.append((t, kind, k))
        total += k
    day = rng.integers(0, days, n_legit)
    t_legit = day * 86400 + rng.choice(24, n_legit, p=HOUR_P) * 3600 + rng.integers(0, 3600, n_legit)
    senders = rng.choice(world.n, n_legit, p=world.p_sender)
    types = rng.choice(list(TYPE_P), n_legit, p=list(TYPE_P.values()))
    u_amt, u_round, u_city, u_dev, u_chan, u_rec, u_empty, u_phone = rng.random((8, n_legit))

    timeline = sorted([(int(t_legit[i]), 0, i) for i in range(n_legit)] + [(t, 1, j) for j, (t, _, _) in enumerate(events)])

    for t, is_event, idx in timeline:
        if not is_event:
            # ----- transaction normale -----
            s, tx_type = int(senders[idx]), str(types[idx])
            home = int(world.home_city[s])
            if u_phone[idx] < 0.0004:                       # changement de téléphone légitime
                world.device[s] = world.new_device()
            city = home if u_city[idx] > 0.07 else int(rng.integers(0, len(CITIES)))
            device = int(world.device[s]) if u_dev[idx] > 0.015 else world.n + s   # 2e appareil connu
            if tx_type == "AIRTIME":
                amount = float(rng.choice(AIRTIME_AMOUNTS))
            else:
                mult = {"CASH_IN": 1.6, "CASH_OUT": 1.2, "TRANSFER": 1.0, "PAYMENT": 0.7}[tx_type]
                amount = _round_amount(world.typical[s] * mult * rng.lognormal(0, 0.6), u_round[idx])
            if tx_type in DEBIT_TYPES and u_empty[idx] < 0.008:   # vidage légitime (loyer, scolarité)
                amount = _round_amount(world.balance[s] * rng.uniform(0.85, 1.0), 1.0)
            elif tx_type in DEBIT_TYPES and u_empty[idx] < 0.04:  # grosse dépense légitime (commerce, épargne)
                amount = _round_amount(world.balance[s] * rng.uniform(0.25, 0.9), u_round[idx])
            if tx_type in DEBIT_TYPES and world.balance[s] < amount:   # solde insuffisant -> recharge d'abord
                tx_type = "CASH_IN"
                amount = _round_amount(max(amount * 1.5, world.typical[s] * 3), u_round[idx])
            if tx_type == "TRANSFER":
                c = world.contacts[s]
                r = int(c[rng.integers(len(c))]) if u_rec[idx] < 0.85 else int(rng.integers(0, world.n))
                if r == s:
                    r = (s + 1) % world.n
            elif tx_type in ("CASH_IN", "CASH_OUT"):
                r = world.agent()
            else:
                r = world.merchant()
            if tx_type in ("CASH_IN", "CASH_OUT"):
                channel = "AGENT" if u_chan[idx] < 0.92 else "USSD"
            else:
                channel = "APP" if (world.app_user[s] and u_chan[idx] < 0.85) or u_chan[idx] < 0.05 else "USSD"
            emit(t, s, r, tx_type, amount, channel, city, device, 0)
            continue

        # ----- événement de fraude -----
        _, kind, k = events[idx]
        if kind == "ATO":
            victim = int(rng.integers(0, world.n))
            mule = int(rng.choice(world.mules))
            ring = int(rng.choice(world.ring_devices))
            city = int(rng.integers(0, len(CITIES))) if rng.random() < 0.6 else int(world.home_city[victim])
            ch = "USSD" if rng.random() < 0.6 else "APP"
            step = 0
            for row in range(k):
                tt = t + step
                if row % 2 == 0:       # la victime est vidée vers la mule
                    got = emit(tt, victim, mule, "TRANSFER",
                               _round_amount(world.balance[victim] * rng.uniform(0.4, 1.0), rng.random()),
                               ch, city, ring, 1, "ATO")
                else:                  # la mule retire aussitôt en agent
                    emit(tt, mule, world.agent(), "CASH_OUT", world.balance[mule] * rng.uniform(0.85, 1.0),
                         "AGENT", int(rng.integers(0, len(CITIES))), ring, 1, "ATO")
                step += int(rng.integers(20, 150))
        elif kind == "VELOCITY":
            s = int(rng.choice(world.mules))
            ring = int(rng.choice(world.ring_devices))
            city = int(rng.integers(0, len(CITIES)))
            amounts = [_round_amount(rng.uniform(5_000, 40_000), 0.3) for _ in range(k)]
            world.balance[s] = max(world.balance[s], sum(amounts) * 1.2)   # fonds reçus plus tôt
            step = 0
            for a in amounts:
                emit(t + step, s, int(rng.integers(0, world.n)), "TRANSFER", a, "USSD", city, ring, 1, "VELOCITY")
                step += int(rng.integers(5, 25))
        else:  # SCAM : la victime agit depuis son appareil habituel
            victim = int(rng.integers(0, world.n))
            dest = int(rng.choice(world.mules)) if rng.random() < 0.5 else int(rng.integers(0, world.n))
            if dest == victim:
                dest = (victim + 1) % world.n
            step = 0
            for _ in range(k):
                amt = min(world.typical[victim] * rng.uniform(3, 15), world.balance[victim] * rng.uniform(0.2, 0.9))
                emit(t + step, victim, dest, "TRANSFER", _round_amount(amt, rng.random()),
                     "APP" if world.app_user[victim] else "USSD", int(world.home_city[victim]),
                     int(world.device[victim]), 1, "SCAM")
                step += int(rng.integers(60, 600))

    df = pd.DataFrame(rows, columns=list(FIELDS))
    df["_scenario"] = scen
    df = df.sort_values(["timestamp", "transaction_id"]).reset_index(drop=True)
    scenarios = df.pop("_scenario")
    return df, scenarios


def generate_dataset(n: int = 100_000, fraud_rate: float = 0.02, seed: int = 42,
                     n_accounts: int = None, days: int = 30, start: datetime = None) -> pd.DataFrame:
    """Retourne un DataFrame respectant exactement src.common.schema.FIELDS (mêmes noms de colonnes)."""
    return _generate(n, fraud_rate, seed, n_accounts, days, start)[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200_000)
    p.add_argument("--fraud-rate", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--out", default=str(DATASET_PATH))
    a = p.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df, scen = _generate(a.n, a.fraud_rate, a.seed, None, a.days, None)
    df.to_csv(a.out, index=False)
    pd.DataFrame({"transaction_id": df["transaction_id"], "fraud_scenario": scen}).to_csv(
        str(a.out).replace(".csv", "_scenarios.csv"), index=False)
    print(f"{len(df)} transactions écrites dans {a.out} (fraudes: {df.is_fraud.sum()}, "
          f"taux {df.is_fraud.mean():.2%})")
    print(scen[df.is_fraud == 1].value_counts().to_string())


if __name__ == "__main__":
    main()
