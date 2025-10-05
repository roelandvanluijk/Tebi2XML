import pandas as pd
import numpy as np

def to_float(x):
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except Exception:
        try:
            return float(str(x))
        except Exception:
            return np.nan
