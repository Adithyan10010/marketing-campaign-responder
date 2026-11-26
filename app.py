"""Marketing Campaign Responder - Flask backend (with Supabase history)."""
import os
import warnings
from datetime import date, datetime

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

warnings.filterwarnings("ignore")

# Load SUPABASE_URL / SUPABASE_KEY from the .env file (always next to app.py)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_ENV_PATH = os.path.join(_APP_DIR, ".env")
_loaded = load_dotenv(_ENV_PATH)

# ---- DEBUG (remove once everything works) ----
print("[DEBUG] App folder        :", _APP_DIR)
print("[DEBUG] Looking for .env  :", _ENV_PATH)
print("[DEBUG] .env file exists  :", os.path.exists(_ENV_PATH))
print("[DEBUG] load_dotenv result:", _loaded)
print("[DEBUG] Files in folder   :", os.listdir(_APP_DIR))
_dbg_url = os.environ.get("SUPABASE_URL")
_dbg_key = os.environ.get("SUPABASE_KEY")
print("[DEBUG] SUPABASE_URL      :", _dbg_url)
print("[DEBUG] SUPABASE_KEY      :", (_dbg_key[:12] + "..." + str(len(_dbg_key)) + " chars") if _dbg_key else None)
# ----------------------------------------------

# Compatibility shim: lets a model saved with sklearn 1.6.x load on newer versions.
import sklearn.compose._column_transformer as _ct
if not hasattr(_ct, "_RemainderColsList"):
    class _RemainderColsList(list):
        def __setstate__(self, state):
            pass
    _RemainderColsList.__module__ = "sklearn.compose._column_transformer"
    _ct._RemainderColsList = _RemainderColsList

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLE = joblib.load(os.path.join(BASE_DIR, "marketing_model_v2.pkl"))
MODEL = BUNDLE["model"]


def _repair_for_newer_sklearn(model):
    """Models pickled with sklearn 1.6.x lack an attribute newer SimpleImputer
    versions expect. Restore it so the model runs on newer scikit-learn."""
    from sklearn.impute import SimpleImputer
    for cc in model.calibrated_classifiers_:
        prep = cc.estimator.named_steps["prep"]
        for _name, trans, _cols in prep.transformers_:
            if not hasattr(trans, "named_steps"):
                continue
            imp = trans.named_steps.get("imputer")
            if isinstance(imp, SimpleImputer) and not hasattr(imp, "_fill_dtype"):
                imp._fill_dtype = imp.statistics_.dtype


import sklearn
if sklearn.__version__ != BUNDLE.get("sklearn_version"):
    _repair_for_newer_sklearn(MODEL)
FEATURES = BUNDLE["features"]
THRESHOLD_OVERRIDE = 0.15   # your chosen cut-off; set to None to use the model's stored value
THRESHOLD = float(THRESHOLD_OVERRIDE if THRESHOLD_OVERRIDE is not None else BUNDLE["threshold"])
REF_DATE = datetime.strptime(BUNDLE["ref_date"], "%Y-%m-%d").date()
METRICS = BUNDLE.get("metrics", {})

# ---------------------------------------------------------------------------
# Supabase (optional: the app still works if credentials are missing)
# ---------------------------------------------------------------------------
supabase = None
_SB_URL = os.environ.get("SUPABASE_URL")
_SB_KEY = os.environ.get("SUPABASE_KEY")
if _SB_URL and _SB_KEY:
    try:
        from supabase import create_client
        supabase = create_client(_SB_URL.strip(), _SB_KEY.strip())
        print("[DEBUG] Supabase client created OK")
        # Quick connectivity test: tries to read the table
        try:
            supabase.table("predictions").select("id").limit(1).execute()
            print("[DEBUG] 'predictions' table reachable - DB is working")
        except Exception as exc:
            print("[DEBUG] Client created, but table query failed:", exc)
    except Exception as exc:
        print("[DEBUG] Supabase connection failed:", type(exc).__name__, exc)
else:
    print("[DEBUG] SUPABASE_URL / SUPABASE_KEY not set - prediction history is disabled.")
    print("[DEBUG] URL present:", bool(_SB_URL), "| KEY present:", bool(_SB_KEY))

app = Flask(__name__, static_folder="public", static_url_path="")

EDUCATION = ["Basic", "2n Cycle", "Graduation", "Master", "PhD"]
MARITAL = ["Single", "Married", "Together", "Divorced", "Widow", "Alone"]
SPEND_COLS = ["MntWines", "MntFruits", "MntMeatProducts",
              "MntFishProducts", "MntSweetProducts", "MntGoldProds"]
CMP_COLS = ["AcceptedCmp1", "AcceptedCmp2", "AcceptedCmp3", "AcceptedCmp4", "AcceptedCmp5"]

FRIENDLY = {
    "Income": "Annual income", "Kidhome": "Kids at home", "Teenhome": "Teens at home",
    "Recency": "Days since last purchase", "MntWines": "Wine spend",
    "MntFruits": "Fruit spend", "MntMeatProducts": "Meat spend",
    "MntFishProducts": "Fish spend", "MntSweetProducts": "Sweets spend",
    "MntGoldProds": "Gold products spend", "NumDealsPurchases": "Discount purchases",
    "NumWebPurchases": "Web purchases", "NumCatalogPurchases": "Catalog purchases",
    "NumStorePurchases": "Store purchases", "NumWebVisitsMonth": "Web visits / month",
    "AcceptedCmp1": "Accepted campaign 1", "AcceptedCmp2": "Accepted campaign 2",
    "AcceptedCmp3": "Accepted campaign 3", "AcceptedCmp4": "Accepted campaign 4",
    "AcceptedCmp5": "Accepted campaign 5", "Complain": "Filed a complaint",
    "Age": "Age", "Customer_Days": "Customer tenure", "Total_Children": "Total children",
    "Total_Spend": "Total spend", "Total_Purchases": "Total purchases",
    "Total_Accepted": "Past campaigns accepted", "Spend_per_Income": "Spend vs. income",
}


def num(data, key, lo, hi, integer=True):
    try:
        val = float(data.get(key, 0) or 0)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number.")
    if not lo <= val <= hi:
        raise ValueError(f"'{key}' must be between {lo} and {hi}.")
    return int(round(val)) if integer else val


def build_row(d):
    """Turn the form payload into the exact feature frame the model expects."""
    education = d.get("Education")
    marital = d.get("Marital_Status")
    if education not in EDUCATION:
        raise ValueError("Please choose an education level.")
    if marital not in MARITAL:
        raise ValueError("Please choose a marital status.")

    row = {"Education": education, "Marital_Status": marital}
    row["Income"] = num(d, "Income", 1, 1_000_000, integer=False)
    row["Kidhome"] = num(d, "Kidhome", 0, 5)
    row["Teenhome"] = num(d, "Teenhome", 0, 5)
    row["Recency"] = num(d, "Recency", 0, 365)
    for c in SPEND_COLS:
        row[c] = num(d, c, 0, 100_000)
    for c in ["NumDealsPurchases", "NumWebPurchases", "NumCatalogPurchases",
              "NumStorePurchases", "NumWebVisitsMonth"]:
        row[c] = num(d, c, 0, 500)
    for c in CMP_COLS:
        row[c] = 1 if str(d.get(c, 0)) in ("1", "true", "True") else 0
    row["Complain"] = 1 if str(d.get("Complain", 0)) in ("1", "true", "True") else 0
    row["Age"] = num(d, "Age", 18, 110)

    try:
        since = datetime.strptime(d.get("Customer_Since", ""), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Please enter a valid 'customer since' date.")
    if since > REF_DATE:
        since = REF_DATE
    row["Customer_Days"] = (REF_DATE - since).days

    # Engineered features (same definitions used at training time)
    row["Total_Children"] = row["Kidhome"] + row["Teenhome"]
    row["Total_Spend"] = sum(row[c] for c in SPEND_COLS)
    row["Total_Purchases"] = (row["NumDealsPurchases"] + row["NumWebPurchases"]
                              + row["NumCatalogPurchases"] + row["NumStorePurchases"])
    row["Total_Accepted"] = sum(row[c] for c in CMP_COLS)
    row["Spend_per_Income"] = row["Total_Spend"] / row["Income"]
    row["Living_With"] = "Partner" if marital in ("Married", "Together") else "Alone"
    return row


def explain(df, top=4):
    """Per-feature contribution to the log-odds (averaged over calibration folds)."""
    sums, n = {}, 0
    for cc in MODEL.calibrated_classifiers_:
        pipe = cc.estimator
        prep = pipe.named_steps["prep"]
        X = prep.transform(df)
        X = X.toarray() if hasattr(X, "toarray") else np.asarray(X)
        contrib = X[0] * pipe.named_steps["clf"].coef_[0]
        # Folds can differ in encoded categories, so aggregate by feature name.
        for name, val in zip(prep.get_feature_names_out(), contrib):
            sums[name] = sums.get(name, 0.0) + float(val)
        n += 1

    grouped = {}
    for name, val in sums.items():
        val /= n
        raw = name.split("__", 1)[1]
        if name.startswith("cat__"):
            col = next(c for c in ("Marital_Status", "Living_With", "Education") if raw.startswith(c))
            level = raw[len(col) + 1:]
            label = {"Marital_Status": "Marital status", "Living_With": "Living with",
                     "Education": "Education"}[col] + f": {level}"
        else:
            label = FRIENDLY.get(raw, raw)
        grouped[label] = grouped.get(label, 0) + val

    items = [{"label": k, "impact": round(v, 3)} for k, v in grouped.items() if abs(v) >= 0.05]
    up = sorted([i for i in items if i["impact"] > 0], key=lambda i: -i["impact"])[:top]
    down = sorted([i for i in items if i["impact"] < 0], key=lambda i: i["impact"])[:top]
    return up, down


def save_prediction(row, prob, responder, tier, up, down):
    """Store one prediction in Supabase. Never breaks the API if the DB fails."""
    if supabase is None:
        return False
    try:
        supabase.table("predictions").insert({
            "inputs": row,
            "probability": round(prob, 4),
            "threshold": round(THRESHOLD, 4),
            "responder": bool(responder),
            "tier": tier,
            "positive_factors": up,
            "negative_factors": down,
        }).execute()
        print("[DEBUG] Prediction saved to Supabase")
        return True
    except Exception as exc:
        print("[DEBUG] Supabase insert failed:", type(exc).__name__, exc)
        return False


@app.route("/")
def index():
    return render_template("index.html", education=EDUCATION, marital=MARITAL,
                           metrics=METRICS, ref_date=REF_DATE.isoformat())


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    try:
        row = build_row(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    df = pd.DataFrame([row])[FEATURES]
    prob = float(MODEL.predict_proba(df)[0, 1])
    responder = prob >= THRESHOLD

    if prob >= 0.50:
        tier = "Very high"
    elif prob >= 0.20:
        tier = "High"
    elif responder:
        tier = "Moderate"
    else:
        tier = "Low"

    try:
        up, down = explain(df)
    except Exception:
        up, down = [], []

    saved = save_prediction(row, prob, responder, tier, up, down)

    return jsonify({
        "probability": round(prob, 4),
        "threshold": round(THRESHOLD, 4),
        "responder": bool(responder),
        "tier": tier,
        "positive_factors": up,
        "negative_factors": down,
        "saved": saved,
        "derived": {
            "Total spend": f"${row['Total_Spend']:,}",
            "Total purchases": row["Total_Purchases"],
            "Campaigns accepted": row["Total_Accepted"],
            "Customer tenure": f"{row['Customer_Days'] / 365.25:.1f} yrs",
            "Spend / income": f"{row['Spend_per_Income'] * 100:.1f}%",
            "Household": row["Living_With"],
        },
    })


@app.route("/history")
def history():
    """Latest predictions from Supabase. Optional: /history?limit=50"""
    if supabase is None:
        return jsonify({"error": "Database not configured."}), 503
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
    except ValueError:
        limit = 20
    try:
        res = (supabase.table("predictions")
               .select("id, created_at, probability, tier, responder")
               .order("created_at", desc=True)
               .limit(limit)
               .execute())
        return jsonify(res.data)
    except Exception as exc:
        print("Supabase read failed:", exc)
        return jsonify({"error": "Could not load history."}), 500


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": BUNDLE.get("model_name"),
        "database": "connected" if supabase is not None else "not configured",
    })


if __name__ == "__main__":
    # Use debug=False in production
    app.run(debug=True, port=5000)