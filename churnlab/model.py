"""Churn prediction: logistic regression baseline vs LightGBM, judged the way a retention team would use them."""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import SEED
from .data import feature_frame


def models():
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)),
        "lightgbm": LGBMClassifier(n_estimators=400, learning_rate=0.02, num_leaves=15, min_child_samples=40,
                                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=2.0,
                                   verbose=-1, random_state=SEED),
    }


def lift_metrics(y, p, top=0.10):
    order = np.argsort(-p)
    k = int(len(p) * top)
    top_rate = y[order[:k]].mean()
    k20 = int(len(p) * 0.20)
    return {"lift_top10": float(top_rate / y.mean()), "churn_rate_top10": float(top_rate),
            "capture_top20": float(y[order[:k20]].sum() / y.sum())}


def evaluate(y, p):
    return {"roc_auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)), **lift_metrics(np.asarray(y), np.asarray(p))}


READABLE = {
    "Contract_Month-to-month": "Month-to-month contract", "Contract_Two_year": "Two-year contract",
    "Contract_One_year": "One-year contract", "InternetService_Fiber_optic": "Fiber optic internet",
    "PaymentMethod_Electronic_check": "Pays by electronic check", "TechSupport_No": "No tech support",
    "OnlineSecurity_No": "No online security", "PaperlessBilling_Yes": "Paperless billing",
    "tenure": "Tenure", "MonthlyCharges": "Monthly bill", "TotalCharges": "Total charges",
    "SeniorCitizen": "Senior citizen", "n_services": "Number of services", "auto_pay": "Automatic payment",
    "Dependents_No": "No dependents", "Partner_No": "No partner", "StreamingTV_Yes": "Streams TV",
    "StreamingMovies_Yes": "Streams movies", "OnlineBackup_No": "No online backup",
    "DeviceProtection_No": "No device protection", "InternetService_DSL": "DSL internet",
    "InternetService_No": "No internet service", "avg_monthly_spend_gap": "Recent bill increase",
    "MultipleLines_Yes": "Multiple lines", "PhoneService_Yes": "Phone service",
}


def readable(feature: str) -> str:
    return READABLE.get(feature, feature.replace("_", " "))


def describe(feature: str, c) -> str:
    """Turn a SHAP feature into a reason a retention agent can read, using the customer's own values."""
    if feature == "tenure":
        return f"Short tenure ({int(c['tenure'])} months)" if c["tenure"] < 24 else f"Tenure of {int(c['tenure'])} months"
    if feature == "MonthlyCharges":
        return f"High monthly bill (${c['MonthlyCharges']:.2f})"
    if feature == "TotalCharges":
        return f"Low total spend so far (${c['TotalCharges']:,.0f})"
    if feature == "avg_monthly_spend_gap":
        return f"Bill above its historical average (+${c['avg_monthly_spend_gap']:.2f})"
    if feature == "n_services":
        return f"Few services ({int(c['n_services'])})"
    if feature == "auto_pay":
        return "No automatic payment"
    if feature == "SeniorCitizen":
        return "Senior citizen"
    return readable(feature)


def run(df: pd.DataFrame) -> dict:
    X, y = feature_frame(df), df["churn"].to_numpy()
    idx_tr, idx_te = train_test_split(np.arange(len(df)), test_size=0.25, stratify=y, random_state=SEED)
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    comparison, test_preds = {}, {}
    for name, m in models().items():
        oof = cross_val_predict(m, X.iloc[idx_tr], y[idx_tr], cv=cv, method="predict_proba")[:, 1]
        m.fit(X.iloc[idx_tr], y[idx_tr])
        p_te = m.predict_proba(X.iloc[idx_te])[:, 1]
        test_preds[name] = p_te
        comparison[name] = {"cv_roc_auc": float(roc_auc_score(y[idx_tr], oof)), "test": evaluate(y[idx_te], p_te)}
    best = max(comparison, key=lambda k: comparison[k]["cv_roc_auc"])

    # Honest scores for every customer: out-of-fold predictions from the chosen model
    scores = cross_val_predict(models()[best], X, y, cv=cv, method="predict_proba")[:, 1]

    # Explanations from the LightGBM model (tree SHAP), used for drivers in both cases
    gbm = models()["lightgbm"].fit(X, y)
    sv = shap.TreeExplainer(gbm).shap_values(X)
    sv = sv[1] if isinstance(sv, list) else sv
    global_imp = (pd.Series(np.abs(sv).mean(axis=0), index=X.columns).sort_values(ascending=False).head(12))
    drivers = []
    for i in range(len(X)):
        row = pd.Series(sv[i], index=X.columns)
        top = row[row > 0].sort_values(ascending=False).head(3)
        drivers.append([{"feature": describe(f, df.iloc[i]), "impact": round(float(v), 3)} for f, v in top.items()])

    frac_pos, mean_pred = calibration_curve(y[idx_te], test_preds[best], n_bins=10, strategy="quantile")
    order = np.argsort(-test_preds[best])
    deciles = [float(y[idx_te][order][i * len(order) // 10:(i + 1) * len(order) // 10].mean()) for i in range(10)]
    return {
        "best_model": best, "comparison": comparison, "scores": scores, "drivers": drivers,
        "global_importance": [{"feature": readable(f), "mean_abs_shap": float(v)} for f, v in global_imp.items()],
        "calibration": {"predicted": mean_pred.tolist(), "observed": frac_pos.tolist()},
        "decile_churn_rate": deciles, "base_rate": float(y.mean()), "n_test": int(len(idx_te)),
        "test_index": idx_te.tolist(),
    }
