"""Check a regenerated refit cache against the previous one: every forward entry (model m on days
>= m) must be bit-identical and every per-day weight hash equal, so the regeneration added the
backward window without changing anything the pre-registered results rest on.

    python scripts/compare_caches.py artifacts/cache artifacts/cache_v2 [name ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def compare(old_dir: Path, new_dir: Path, name: str) -> str:
    old, new = np.load(old_dir / f"{name}.npz"), np.load(new_dir / f"{name}.npz")
    meta_old = json.loads((old_dir / f"{name}.json").read_text())
    meta_new = json.loads((new_dir / f"{name}.json").read_text())
    a, b = old["abs_sum"], new["abs_sum"]
    n = a.shape[0]
    tri = np.triu(np.ones((n, n), dtype=bool))  # days >= model day
    fwd_equal = np.array_equal(a[tri], b[tri]) and np.array_equal(old["sq_sum"][tri], new["sq_sum"][tri])
    hashes = [m.get("state_sha256") for m in meta_old["days"]] == [m.get("state_sha256") for m in meta_new["days"]]
    val = np.array_equal(old["val_mae_fixed"], new["val_mae_fixed"])
    back = int(meta_new.get("backward_days", 0))
    low = np.tril(np.ones((n, n), dtype=bool), k=-1)
    within = np.zeros((n, n), dtype=bool)
    for m in range(n):
        within[m, max(0, m - back) : m] = True
    back_ok = back > 0 and np.isfinite(b[within]).all() and np.isnan(b[low & ~within]).all()
    status = "OK" if (fwd_equal and hashes and val and back_ok) else "DIFF"
    return (
        f"{name}: {status} forward_equal={fwd_equal} hashes_equal={hashes} val_equal={val} "
        f"backward_days={back} backward_filled={back_ok}"
    )


def main() -> int:
    old_dir, new_dir = Path(sys.argv[1]), Path(sys.argv[2])
    names = sys.argv[3:] or sorted(
        p.stem for p in new_dir.glob("*.npz") if not p.stem.endswith("_warm") and (old_dir / p.name).exists()
    )
    bad = 0
    for name in names:
        line = compare(old_dir, new_dir, name)
        bad += "DIFF" in line
        print(line)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
