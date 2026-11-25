"""Run everything: churn model -> survival -> retention engine -> messages -> results/*.json.

Usage: python -m churnlab.pipeline   (about 30 seconds)
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import messages, model, retention, survival
from .config import HORIZON_MONTHS, OFFER_KEYS, OFFERS, RESULTS_DIR, ROOT
from .data import load


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return None if not np.isfinite(o) else round(o, 5)
    return o


def save(name, obj):
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(_clean(obj), separators=(",", ":")))


def churn_by(df, col, order=None):
    g = df.groupby(col)["churn"].agg(["mean", "size"]).reset_index()
    if order:
        g[col] = pd.Categorical(g[col], order, ordered=True)
        g = g.sort_values(col)
    return [{"group": str(r[col]), "churn_rate": float(r["mean"]), "customers": int(r["size"])} for _, r in g.iterrows()]


def message_eval(active: pd.DataFrame, n: int = 300) -> dict:
    sample = active.sample(n, random_state=1)
    clean = total = caught = injected = 0
    by_type = {}
    for _, row in sample.iterrows():
        c = row.to_dict()
        for off in OFFER_KEYS:
            for lang in ("en", "fr"):
                f = messages.facts(c, off)
                t = messages.template(f, lang)
                total += 1
                clean += not messages.validate(t, f, lang)
                for k, v in messages.corruptions(t, f, lang).items():
                    hit = bool(messages.validate(v, f, lang))
                    injected += 1
                    caught += hit
                    by_type.setdefault(k, [0, 0])
                    by_type[k][0] += hit
                    by_type[k][1] += 1
    return {"customers": n, "messages": total, "clean_pass_rate": clean / total, "injected_errors": injected,
            "caught_rate": caught / injected, "by_type": {k: v[0] / v[1] for k, v in by_type.items()}}


def main():
    t0 = time.time()
    df = load()
    m = model.run(df)
    print(f"churn model: best={m['best_model']} test AUC={m['comparison'][m['best_model']]['test']['roc_auc']:.3f}")
    s = survival.run(df)
    print(f"survival: concordance {s['concordance']}")
    act = (df["churn"] == 0).to_numpy()
    active = df[act].reset_index(drop=True)
    r = retention.run(active, s["p_churn_window"][act], s["conditional_survival"][act])
    print("retention:", {k: round(v["net_value"]) for k, v in r["strategies"].items()})

    pc = r.pop("per_customer")
    cond = s["conditional_survival"][act]
    risk = m["scores"][act]
    drivers = [d for d, a in zip(m["drivers"], act) if a]
    exp_m = s["expected_months"][act]
    records = []
    for i, c in active.iterrows():
        rec_offer = pc["recommended"][i]
        msg = {}
        if rec_offer != "none":
            f = messages.facts(c.to_dict(), rec_offer)
            msg = {"en": messages.template(f, "en"), "fr": messages.template(f, "fr")}
        records.append({
            "id": c["customerID"], "tenure": int(c["tenure"]), "contract": c["Contract"], "internet": c["InternetService"],
            "payment": c["PaymentMethod"], "monthly": float(c["MonthlyCharges"]), "senior": int(c["SeniorCitizen"]),
            "tech_support": c["TechSupport"], "services": int(c["n_services"]),
            "risk": float(risk[i]), "p6": float(s["p_churn_window"][act][i]), "expected_months": float(exp_m[i]),
            "revenue_at_risk": float(c["MonthlyCharges"] * (HORIZON_MONTHS - exp_m[i])),
            "value_if_retained": float(pc["value_if_retained"][i]), "drivers": drivers[i],
            "uplift": {k: float(pc["uplift_est"][i, j]) for j, k in enumerate(OFFER_KEYS)},
            "uplift_true": {k: float(pc["uplift_true"][i, j]) for j, k in enumerate(OFFER_KEYS)},
            "net": {k: float(pc["net_value_est"][i, j]) for j, k in enumerate(OFFER_KEYS)},
            "spend": {k: float(pc["costs"][i, j] + 5.0) for j, k in enumerate(OFFER_KEYS)},
            "recommended": rec_offer, "survival": [round(float(v), 4) for v in cond[i]], "message": msg,
        })
    save("customers", records)

    rev_risk = sum(x["revenue_at_risk"] for x in records)
    overview = {
        "customers": int(len(df)), "active": int(act.sum()), "churned": int((~act).sum()),
        "churn_rate": float(df["churn"].mean()), "revenue_at_risk_24m": rev_risk,
        "monthly_revenue_active": float(active["MonthlyCharges"].sum()),
        "model": {k: v for k, v in m.items() if k not in ("scores", "drivers", "test_index")},
        "survival": {k: v for k, v in s.items() if k in ("concordance", "km_by_contract", "time_ratios")},
        "churn_by": {
            "contract": churn_by(df, "Contract", ["Month-to-month", "One year", "Two year"]),
            "internet": churn_by(df, "InternetService"), "payment": churn_by(df, "PaymentMethod"),
            "tenure": churn_by(df.assign(tb=pd.cut(df.tenure, [-1, 6, 12, 24, 48, 72],
                                                    labels=["0-6", "7-12", "13-24", "25-48", "49-72"])), "tb",
                               ["0-6", "7-12", "13-24", "25-48", "49-72"]),
        },
        "offers": {k: {"label": v["label"], "label_fr": v["label_fr"]} for k, v in OFFERS.items()},
    }
    save("overview", overview)
    save("retention", r)
    save("messages_eval", message_eval(active))
    static = ROOT / "web" / "data"
    static.mkdir(parents=True, exist_ok=True)
    for f in RESULTS_DIR.glob("*.json"):
        (static / f.name).write_text(f.read_text())
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
