import json

from churnlab.config import RESULTS_DIR


def res():
    return json.loads((RESULTS_DIR / "retention.json").read_text())


def test_uplift_targeting_beats_common_practice():
    s = res()["strategies"]
    assert s["random"]["net_value"] < 0
    assert s["uplift_value"]["net_value"] > 2 * s["highest_risk_discount"]["net_value"]
    assert s["oracle"]["net_value"] >= s["uplift_value"]["net_value"]
    for v in s.values():
        assert v["cost"] <= res()["budget"] + 1


def test_uplift_estimates_track_truth():
    assert all(c > 0.6 for c in res()["uplift_corr_with_truth"].values())


def test_model_selection_did_not_use_truth():
    sel = res()["model_selection"]
    best = min(sel["validation_log_loss"], key=lambda r: r["log_loss"])
    assert {k: best[k] for k in ("min_child_samples", "num_leaves", "n_estimators")} == sel["chosen"]


def test_holdout_check_is_reported_and_winners_curse_measured():
    r = res()
    h = r["strategies"]["uplift_value"]["holdout_check"]
    assert h["churn_with_offer"] < h["churn_control"]
    assert 0 < r["estimate_realisation_ratio"] < 1
