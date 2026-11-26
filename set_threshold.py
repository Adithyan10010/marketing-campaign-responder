import shutil
import joblib
from app import BUNDLE   # reuses app.py's loading + compatibility fixes

NEW_THRESHOLD = 0.15     # <- the value you want

# 1. keep a backup of the original
shutil.copy("marketing_model_v2.pkl", "marketing_model_v2_backup.pkl")

# 2. change the stored value and save under a new name
print("old threshold:", BUNDLE["threshold"])
BUNDLE["threshold"] = NEW_THRESHOLD
joblib.dump(BUNDLE, "marketing_model_v3.pkl")
print("saved marketing_model_v3.pkl with threshold", NEW_THRESHOLD)