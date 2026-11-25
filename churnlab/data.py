"""Load and clean the IBM Telco Customer Churn dataset (7,043 customers)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DATA_PATH

CATEGORICAL = ["gender", "Partner", "Dependents", "PhoneService", "MultipleLines", "InternetService",
               "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV",
               "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod"]
NUMERIC = ["SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges", "n_services", "auto_pay", "avg_monthly_spend_gap"]
SERVICES = ["PhoneService", "MultipleLines", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
            "TechSupport", "StreamingTV", "StreamingMovies"]


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    # 11 brand-new customers (tenure 0) have a blank TotalCharges: they have not been billed yet
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"].str.strip(), errors="coerce").fillna(0.0)
    df["churn"] = (df["Churn"] == "Yes").astype(int)
    df["n_services"] = (df[SERVICES] == "Yes").sum(axis=1) + (df["InternetService"] != "No").astype(int)
    df["auto_pay"] = df["PaymentMethod"].str.contains("automatic").astype(int)
    # Difference between the current bill and the average historical bill: recent price rises show up here
    avg = np.where(df["tenure"] > 0, df["TotalCharges"] / df["tenure"].clip(lower=1), df["MonthlyCharges"])
    df["avg_monthly_spend_gap"] = (df["MonthlyCharges"] - avg).round(2)
    return df


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot encoded features for scikit-learn / LightGBM."""
    X = pd.get_dummies(df[CATEGORICAL], drop_first=False, dtype=float)
    for c in NUMERIC:
        X[c] = df[c].astype(float)
    X.columns = [c.replace(" ", "_").replace("(", "").replace(")", "") for c in X.columns]
    return X
