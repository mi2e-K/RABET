"""Probe which statsmodels / scipy / seaborn / pandas_flavor sub-modules
are actually loaded when ``import pingouin`` runs, and then exercise the
ICC computation. Cross-check the result against our PyInstaller excludes
list to spot collisions.
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path

# Make the project root importable so we can read the excludes list.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from build_packaging_common import COMMON_EXCLUDED_MODULES  # noqa: E402

# Wipe pingouin / friends so the import below loads fresh.
for mod in list(sys.modules):
    if mod.startswith(("pingouin", "statsmodels", "scipy", "seaborn", "pandas_flavor")):
        del sys.modules[mod]

import pingouin as pg  # noqa: E402

# Now run a tiny ICC like the Reliability tab does.
import numpy as np
import pandas as pd
n = 8
a = np.arange(n, dtype=float)
b = a + np.random.default_rng(0).normal(0, 0.5, n)
df = pd.DataFrame({
    "target": list(range(n)) * 2,
    "rater":  ["A"] * n + ["B"] * n,
    "rating": np.concatenate([a, b]),
})
icc_df = pg.intraclass_corr(data=df, targets="target", raters="rater", ratings="rating")
print("ICC test sample (ICC2 row):")
print(icc_df.loc[icc_df["Type"] == "ICC2"].to_string())
print()

loaded = sorted(
    k for k in sys.modules
    if k.startswith(("statsmodels", "scipy", "seaborn", "pandas_flavor"))
)
print(f"Total {len(loaded)} relevant submodules loaded after pingouin + ICC.")
print()

excludes = set(COMMON_EXCLUDED_MODULES)
collisions = []
for mod in loaded:
    # Direct match
    if mod in excludes:
        collisions.append((mod, mod))
        continue
    # Prefix match - e.g. excludes 'statsmodels.tsa' must catch 'statsmodels.tsa.something'
    for ex in excludes:
        if mod.startswith(ex + "."):
            collisions.append((mod, ex))
            break

if collisions:
    print("=== COLLISIONS (loaded modules covered by an exclude pattern) ===")
    for mod, ex in collisions:
        print(f"  {mod}  <- excluded by '{ex}'")
else:
    print("No collisions between loaded modules and the excludes list.")
