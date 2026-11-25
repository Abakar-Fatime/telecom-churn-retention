"""Next-best-action: which offer, for which customer, within which budget.

The public dataset has no history of retention offers, so the company's past campaigns are
SIMULATED on the real customers: four quarterly randomised tests (control + 3 offers, 25% each),
with offer effects that depend on each customer's real profile. Because the true effects are
known, every targeting strategy can be scored exactly, and also estimated the way a real company
would, on a held-out randomised wave.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from .config import CONTACT_COST, OFFER_KEYS, OFFERS, SEED
from .data import feature_frame

ARMS = ["control", *OFFER_KEYS]
N_WAVES = 4


def true_effects(df: pd.DataFrame) -> pd.DataFrame:
    """Relative reduction in churn probability for each offer (simulation ground truth)."""
    m2m = df["Contract"].eq("Month-to-month")
    price_sensitive = m2m & (df["MonthlyCharges"] >= 70)
    no_support = df["TechSupport"].eq("No")
    eff = pd.DataFrame(index=df.index)
    eff["discount"] = np.select([price_sensitive, m2m], [0.45, 0.15], 0.05)
    eff["contract"] = np.select([m2m & (df["tenure"] >= 6), m2m], [0.50, 0.10], 0.0)
    eff["support"] = np.select([no_support & df["InternetService"].eq("Fiber optic"),
                                no_support & df["InternetService"].eq("DSL")], [0.40, 0.20], 0.0)
    # "Sleeping dogs": loyal long-contract customers contacted with any offer churn MORE (the call
    # reminds them to compare prices). A risk-only strategy never sees this.
    sleeping = df["Contract"].eq("Two year") & (df["tenure"] >= 48)
    eff.loc[sleeping, OFFER_KEYS] = -0.15
    return eff


def value_if_retained(df, cond_survival):
    """Revenue over the next 24 months from a customer who does not churn in the 6-month window."""
    after = cond_survival[:, 6:] / np.clip(cond_survival[:, [5]], 1e-6, None)
    return df["MonthlyCharges"].to_numpy() * (6 + after.sum(axis=1))


def offer_costs(df) -> pd.DataFrame:
    return pd.DataFrame({k: df.apply(OFFERS[k]["cost"], axis=1) for k in OFFER_KEYS}, index=df.index)


def simulate_campaigns(df, p0, eff, rng):
    rows = []
    for w in range(N_WAVES):
        arm = rng.integers(0, len(ARMS), len(df))
        rel = np.column_stack([np.zeros(len(df)), eff[OFFER_KEYS].to_numpy()])[np.arange(len(df)), arm]
        p = np.clip(p0 * (1 - rel), 0, 1)
        rows.append(pd.DataFrame({"row": np.arange(len(df)), "wave": w + 1, "arm": np.array(ARMS)[arm],
                                  "churned": (rng.random(len(df)) < p).astype(int)}))
    return pd.concat(rows, ignore_index=True)


CANDIDATES = [  # (min_child_samples, num_leaves, n_estimators): from flexible to heavily regularised
    (150, 8, 300), (300, 8, 200), (500, 4, 200), (800, 4, 150), (1200, 4, 120),
]


def _clf(mcs, leaves, n):
    return LGBMClassifier(n_estimators=n, learning_rate=0.03, num_leaves=leaves, min_child_samples=mcs,
                          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=SEED)


def fit_uplift(X: pd.DataFrame, camp: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """T-learner per offer: P(churn | control) - P(churn | offer).

    Regularisation is chosen WITHOUT the simulation truth: each candidate is trained on waves 1-3 and
    scored by the log-loss of its per-arm churn predictions on the held-out wave 4, exactly what a
    real team could do. The chosen setting is then refit on waves 1-3 for the final estimates."""
    from sklearn.metrics import log_loss
    train, valid = camp[camp.wave < N_WAVES], camp[camp.wave == N_WAVES]

    def fit_arm(a, params):
        t = train[train.arm == a]
        return _clf(*params).fit(X.iloc[t.row.to_numpy()], t.churned)

    scores = {}
    for params in CANDIDATES:
        losses = []
        for a in ARMS:
            v = valid[valid.arm == a]
            losses.append(log_loss(v.churned, fit_arm(a, params).predict_proba(X.iloc[v.row.to_numpy()])[:, 1]))
        scores[params] = float(np.mean(losses))
    best = min(scores, key=scores.get)
    p_ctrl = fit_arm("control", best).predict_proba(X)[:, 1]
    out = pd.DataFrame(index=X.index)
    for k in OFFER_KEYS:
        out[k] = p_ctrl - fit_arm(k, best).predict_proba(X)[:, 1]
    out["p_control"] = p_ctrl
    selection = {"chosen": {"min_child_samples": best[0], "num_leaves": best[1], "n_estimators": best[2]},
                 "validation_log_loss": [{"min_child_samples": p[0], "num_leaves": p[1], "n_estimators": p[2],
                                          "log_loss": v} for p, v in scores.items()]}
    return out, selection


def select(score: pd.DataFrame, costs: pd.DataFrame, budget: float, offer_of=None):
    """Greedy: take customers by expected net value until the budget (offer + contact cost) is spent."""
    if offer_of is None:
        offer_of = score.idxmax(axis=1)
    best = score.to_numpy()[np.arange(len(score)), [OFFER_KEYS.index(o) for o in offer_of]]
    spend = costs.to_numpy()[np.arange(len(costs)), [OFFER_KEYS.index(o) for o in offer_of]] + CONTACT_COST
    order = np.argsort(-best)
    chosen, total = [], 0.0
    for i in order:
        if best[i] <= 0 or total + spend[i] > budget:
            continue
        chosen.append(i)
        total += spend[i]
    return np.array(chosen, int), np.asarray(offer_of)


def evaluate(chosen, offer_of, true_uplift_abs, value, costs):
    if len(chosen) == 0:
        return {"contacted": 0, "churners_prevented": 0.0, "revenue_saved": 0.0, "cost": 0.0, "net_value": 0.0, "roi": 0.0}
    k = [OFFER_KEYS.index(o) for o in offer_of[chosen]]
    up = true_uplift_abs[chosen, k]
    saved = float((up * value[chosen]).sum())
    cost = float(costs.to_numpy()[chosen, k].sum() + CONTACT_COST * len(chosen))
    return {"contacted": int(len(chosen)), "churners_prevented": float(up.sum()), "revenue_saved": saved,
            "cost": cost, "net_value": saved - cost, "roi": (saved - cost) / cost,
            "offer_mix": {o: int((offer_of[chosen] == o).sum()) for o in OFFER_KEYS}}


def holdout_check(chosen, offer_of, camp_test, n_boot=500, seed=1):
    """What a real company could measure on the held-out randomised wave: among the customers a
    policy selects, compare churn of those who happened to get the recommended offer vs control."""
    rng = np.random.default_rng(seed)
    sel = pd.Series(offer_of[chosen], index=chosen)
    t = camp_test[camp_test.row.isin(sel.index)]
    got = t[t.arm.to_numpy() == sel.loc[t.row].to_numpy()].churned.to_numpy()
    ctrl = t[t.arm == "control"].churned.to_numpy()
    diff = ctrl.mean() - got.mean()
    boots = [rng.choice(ctrl, len(ctrl)).mean() - rng.choice(got, len(got)).mean() for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"churn_control": float(ctrl.mean()), "churn_with_offer": float(got.mean()), "n_control": int(len(ctrl)),
            "n_offer": int(len(got)), "reduction": float(diff), "ci_low": float(lo), "ci_high": float(hi)}


def run(df_active: pd.DataFrame, p0: np.ndarray, cond_survival: np.ndarray, budget: float = 40_000) -> dict:
    rng = np.random.default_rng(SEED)
    df_active = df_active.reset_index(drop=True)
    X = feature_frame(df_active).assign(p_survival=p0)
    eff = true_effects(df_active)
    value = value_if_retained(df_active, cond_survival)
    costs = offer_costs(df_active)
    true_abs = (p0[:, None] * eff[OFFER_KEYS].to_numpy())   # absolute churn reduction per offer

    camp = simulate_campaigns(df_active, p0, eff, rng)
    up, model_selection = fit_uplift(X, camp)
    est_abs = up[OFFER_KEYS].to_numpy()

    net_pred = pd.DataFrame(est_abs * value[:, None] - costs.to_numpy() - CONTACT_COST, columns=OFFER_KEYS)
    net_true = pd.DataFrame(true_abs * value[:, None] - costs.to_numpy() - CONTACT_COST, columns=OFFER_KEYS)
    risk = pd.DataFrame(np.repeat(p0[:, None], 3, axis=1), columns=OFFER_KEYS)
    rand = pd.DataFrame(rng.random((len(df_active), 3)), columns=OFFER_KEYS)
    rand_offer = np.array(OFFER_KEYS)[rng.integers(0, 3, len(df_active))]

    def strategies(b):
        return {
            "random": select(rand, costs, b, rand_offer),
            "highest_risk_discount": select(risk, costs, b, np.array(["discount"] * len(df_active))),
            "uplift_value": select(net_pred, costs, b),
            "oracle": select(net_true, costs, b),
        }

    camp_test = camp[camp.wave == N_WAVES]
    results = {}
    for name, (ch, off) in strategies(budget).items():
        results[name] = evaluate(ch, off, true_abs, value, costs)
        if name in ("highest_risk_discount", "uplift_value"):
            results[name]["holdout_check"] = holdout_check(ch, off, camp_test)
    curve = []
    for b in [5_000, 10_000, 20_000, 40_000, 60_000, 80_000, 120_000]:
        row = {"budget": b}
        for name, (ch, off) in strategies(b).items():
            row[name] = evaluate(ch, off, true_abs, value, costs)["net_value"]
        curve.append(row)

    ch, off = strategies(budget)["uplift_value"]
    k_sel = [OFFER_KEYS.index(o) for o in off[ch]]
    estimated_net = float(net_pred.to_numpy()[ch, k_sel].sum())
    results["uplift_value"]["estimated_net_value"] = estimated_net
    # Winner's curse: customers picked because their estimates look best are, on average, over-estimated
    realisation = results["uplift_value"]["net_value"] / estimated_net if estimated_net > 0 else None
    recommended = np.array(["none"] * len(df_active), dtype=object)
    recommended[ch] = off[ch]
    corr = {k: float(np.corrcoef(est_abs[:, i], true_abs[:, i])[0, 1]) for i, k in enumerate(OFFER_KEYS)}
    arm_rates = camp.groupby("arm").churned.mean().to_dict()
    return {
        "budget": budget, "strategies": results, "model_selection": model_selection,
        "estimate_realisation_ratio": realisation, "budget_curve": curve, "uplift_corr_with_truth": corr,
        "campaign_summary": {"waves": N_WAVES, "observations": int(len(camp)), "arm_churn_rate": arm_rates},
        "per_customer": {"value_if_retained": value, "uplift_est": est_abs, "uplift_true": true_abs,
                         "net_value_est": net_pred.to_numpy(), "costs": costs.to_numpy(),
                         "recommended": recommended, "sleeping_dog": (eff["discount"] < 0).to_numpy()},
    }
