import json

import numpy as np

from churnlab.config import RESULTS_DIR
from churnlab.data import feature_frame, load


def res(name):
    return json.loads((RESULTS_DIR / f"{name}.json").read_text())


def test_dataset_is_clean():
    df = load()
    assert len(df) == 7043 and df["customerID"].is_unique
    assert df["TotalCharges"].notna().all()
    assert abs(df["churn"].mean() - 0.2654) < 0.001
    X = feature_frame(df)
    assert not X.isna().any().any()


def test_churn_model_quality():
    m = res("overview")["model"]
    best = m["comparison"][m["best_model"]]["test"]
    assert best["roc_auc"] > 0.83
    assert best["lift_top10"] > 2.5
    rates = m["decile_churn_rate"]
    assert rates[0] > rates[4] > rates[9]  # risk ranking is monotone in broad strokes


def test_survival_model():
    s = res("overview")["survival"]
    assert s["concordance"]["weibull_aft"] > 0.8
    curves = s["km_by_contract"]["curves"]
    assert curves["Two year"][-1] > curves["One year"][-1] > curves["Month-to-month"][-1]


def test_customer_records_are_consistent():
    cs = res("customers")
    assert len(cs) == 5174
    c = cs[0]
    assert 0 <= c["risk"] <= 1 and 0 <= c["p6"] <= 1 and 0 <= c["expected_months"] <= 24
    assert all(np.diff(c["survival"]) <= 1e-9)  # survival never increases
    targeted = [x for x in cs if x["recommended"] != "none"]
    assert targeted and all(x["net"][x["recommended"]] > 0 and x["message"]["en"] and x["message"]["fr"] for x in targeted)
