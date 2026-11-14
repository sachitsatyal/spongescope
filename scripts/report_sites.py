"""Coverage of the candidate-site scanner by label (run after features.sites)."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
pairs = pd.read_parquet(ROOT / "data" / "processed" / "fct_pairs.parquet")
tab = pd.read_parquet(ROOT / "data" / "features" / "sites" / "pairs.parquet")
d = pairs[["pair_id", "label", "pair_type"]].merge(tab, on="pair_id")

count_cols = [c for c in tab.columns if c.startswith("n_") and c not in ("n_sites", "n_kept")]
print("share of pairs with >= 1 site of each type")
print(d.groupby("label")[count_cols].apply(lambda g: (g > 0).mean()).round(3).T.to_string())
print(
    "\nany site:", d.groupby("label")["n_sites"].apply(lambda s: (s > 0).mean()).round(3).to_dict()
)
print("median sites per pair:", d.groupby("label")["n_sites"].median().to_dict())
print(f"pairs hitting the site cap: {(d.n_sites > d.n_kept).mean():.3f}")
print("\nany site by negative type:")
print(d.groupby("pair_type")["n_sites"].apply(lambda s: (s > 0).mean()).round(3).to_string())
