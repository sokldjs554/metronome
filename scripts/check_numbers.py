"""Verify every number quoted in Markdown against the artifact it cites.

Markdown marks a number like this:

    <!-- num:artifacts/cadence_summary.json#datasets/etth1/expanding/policies/never/mae_mean:.4f -->0.4123<!-- /num -->

`path#a/b/c:format` names the JSON file (relative to the repo root), a slash-separated path into
it (list indices are integers; keys may contain dots), and an optional Python format spec. The text between the markers
must equal the formatted value exactly. A file with zero markers fails under --require-markers,
so a document cannot pass by having nothing to check.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MARK = re.compile(r"<!--\s*num:([^#\s]+)#([^\s:]+)(?::([^\s]+))?\s*-->(.*?)<!--\s*/num\s*-->", re.S)


def resolve(obj: Any, dotted: str) -> Any:
    for key in dotted.split("/"):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def check_file(md: Path, root: Path, cache: dict[Path, Any]) -> list[str]:
    errors: list[str] = []
    text = md.read_text(encoding="utf-8")
    found = 0
    for m in MARK.finditer(text):
        found += 1
        rel, pointer, fmt, shown = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        path = root / rel
        if path not in cache:
            if not path.exists():
                errors.append(f"{md}: {rel} does not exist")
                continue
            cache[path] = json.loads(path.read_text())
        try:
            value = resolve(cache[path], pointer)
        except (KeyError, IndexError, TypeError) as exc:
            errors.append(f"{md}: {rel}#{pointer}: {exc!r}")
            continue
        expected = format(value, fmt) if fmt else str(value)
        if expected != shown:
            errors.append(f"{md}: {rel}#{pointer} shows {shown!r} but artifact says {expected!r}")
    return errors + ([] if found else [f"{md}: no numeric markers"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--root", default=".")
    ap.add_argument("--require-markers", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    cache: dict[Path, Any] = {}
    errors: list[str] = []
    checked = 0
    for f in args.files:
        md = Path(f)
        if not md.exists():
            errors.append(f"{md}: missing")
            continue
        errs = check_file(md, root, cache)
        if not args.require_markers:
            errs = [e for e in errs if not e.endswith("no numeric markers")]
        errors.extend(errs)
        checked += 1
    for e in errors:
        print("ERROR", e)
    print(f"checked {checked} files, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
