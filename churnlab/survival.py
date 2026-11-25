"""Survival analysis: not just *whether* a customer leaves, but *when*.

tenure = months as a customer; churn = 1 if they left (event), 0 if still active (censored).
A Weibull accelerated-failure-time model gives each active customer a survival curve, from which
we compute the chance of leaving in the next 6 months and the expected months retained over the
next 24 months, the basis of customer value."""
from __future__ import annotations

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter, WeibullAFTFitter
from lifelines.utils import concordance_index
from sklearn.model_selection import train_test_split

from .config import CHURN_WINDOW, HORIZON_MONTHS, SEED

# Duration-derived columns (tenure, TotalCharges) are left out: they would leak the answer.
SURV_CAT = ["Contract", "InternetService", "PaymentMethod", "TechSupport", "OnlineSecurity", "PaperlessBilling",
            "Partner", "Dependents", "StreamingTV", "StreamingMovies", "OnlineBackup", "DeviceProtection"]


def design(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.get_dummies(df[SURV_CAT], drop_first=True, dtype=float)
    X["MonthlyCharges"] = df["MonthlyCharges"] / 10.0
    X["SeniorCitizen"] = df["SeniorCitizen"].astype(float)
    X.columns = [c.replace(" ", "_").replace("(", "").replace(")", "") for c in X.columns]
    return X


def run(df: pd.DataFrame) -> dict:
    X = design(df)
    data = X.assign(duration=df["tenure"].clip(lower=0.5), event=df["churn"])
    tr, te = train_test_split(data, test_size=0.25, stratify=df["churn"], random_state=SEED)

    cox = CoxPHFitter(penalizer=0.01).fit(tr, "duration", "event")
    wb = WeibullAFTFitter(penalizer=0.01).fit(tr, "duration", "event")
    c_cox = concordance_index(te["duration"], -cox.predict_partial_hazard(te), te["event"])
    c_wb = concordance_index(te["duration"], wb.predict_median(te), te["event"])

    model = WeibullAFTFitter(penalizer=0.01).fit(data, "duration", "event")
    grid = np.arange(0, 73 + HORIZON_MONTHS)
    S = model.predict_survival_function(data, times=grid).to_numpy().T  # customers x months
    t = df["tenure"].to_numpy()
    rows = np.arange(len(df))
    s_now = np.clip(S[rows, t], 1e-6, None)
    cond = S[rows[:, None], t[:, None] + np.arange(1, HORIZON_MONTHS + 1)[None, :]] / s_now[:, None]
    p_window = 1 - cond[:, CHURN_WINDOW - 1]
    exp_months = cond.sum(axis=1)  # expected months retained in the next 24 (restricted mean)

    km = {}
    for contract, g in df.groupby("Contract"):
        k = KaplanMeierFitter().fit(g["tenure"], g["churn"])
        sf = k.survival_function_at_times(np.arange(0, 73, 3))
        km[contract] = [round(float(v), 4) for v in sf.values]

    top_effects = (model.summary.loc["lambda_"]["coef"].drop("Intercept").sort_values())
    return {
        "concordance": {"cox": float(c_cox), "weibull_aft": float(c_wb)},
        "p_churn_window": p_window, "expected_months": exp_months, "conditional_survival": cond,
        "km_by_contract": {"months": list(range(0, 73, 3)), "curves": km},
        "time_ratios": [{"feature": f, "time_ratio": float(np.exp(v))} for f, v in
                        list(top_effects.head(5).items()) + list(top_effects.tail(5).items())],
    }
