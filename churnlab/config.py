"""Paths, constants and the retention offer catalogue."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "telco_customer_churn.csv"
RESULTS_DIR = ROOT / "results"
SEED = 42
HORIZON_MONTHS = 24          # customer value is measured over the next 24 months
CHURN_WINDOW = 6             # retention campaigns target churn in the next 6 months
CONTACT_COST = 5.0           # cost of one outbound contact (call + SMS), USD

# Retention offers. cost(c) is the expected cost to the company if the customer accepts.
OFFERS = {
    "discount": {
        "label": "20% off the monthly bill for 6 months",
        "label_fr": "20 % de réduction sur la facture mensuelle pendant 6 mois",
        "cost": lambda c: 0.20 * c["MonthlyCharges"] * 6,
    },
    "contract": {
        "label": "Switch to a 1-year contract and get 1 month free",
        "label_fr": "Passez à un contrat d'un an et obtenez 1 mois gratuit",
        "cost": lambda c: 1.0 * c["MonthlyCharges"],
    },
    "support": {
        "label": "Free Tech Support and Online Security for 6 months",
        "label_fr": "Assistance technique et sécurité en ligne gratuites pendant 6 mois",
        "cost": lambda c: 6 * 4.0,   # internal cost of the two add-ons, about $4 a month
    },
}
OFFER_KEYS = list(OFFERS)
