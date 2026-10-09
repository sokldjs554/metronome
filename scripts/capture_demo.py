"""Drive the five-step dashboard with Playwright and capture the README assets.

Walks the real flow against a running `metronome demo` (API + in-process worker): data profile
and a CSV check, candidate training with the promotion gate, deployment table and a forecast call,
stream replay until a detector alarm retrains and hot-swaps the model, the policy page, and a
phone-width shot. Writes numbered PNGs, a slideshow GIF and capture-report.json.

Usage: python scripts/capture_demo.py --url http://127.0.0.1:8000 --out docs/assets/demo
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def sample_csv(path: Path) -> Path:
    """72 hourly rows with one duplicate, one gap and one missing value, so the check has something to say."""
    rows = ["timestamp,load,temp"]
    t0 = dt.datetime(2024, 1, 1)
    for h in range(72):
        if h == 30:
            continue
        ts = (t0 + dt.timedelta(hours=h)).strftime("%Y-%m-%d %H:%M:%S")
        temp = "" if h == 40 else f"{20 + h / 24:.2f}"
        rows.append(f"{ts},{50 + h % 7},{temp}")
        if h == 10:
            rows.append(f"{ts},{50 + h % 7},20.1")
    path.write_text("\n".join(rows) + "\n")
    return path


def shot(page: Page, out: Path, name: str) -> None:
    page.wait_for_timeout(600)
    page.screenshot(path=str(out / name), full_page=True)


def slideshow_gif(
    out: Path, names: list[str], width: int = 960, crop_h: int = 820, seconds: float = 2.4
) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    frames = []
    for name in names:
        im = Image.open(out / name).convert("RGB")
        im = im.resize((width, int(im.height * width / im.width)))
        im = im.crop((0, 0, width, min(crop_h, im.height)))
        canvas = Image.new("RGB", (width, crop_h), (246, 247, 244))
        canvas.paste(im, (0, 0))
        frames.append(canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    gif = out / "demo.gif"
    frames[0].save(
        gif, save_all=True, append_images=frames[1:], duration=int(seconds * 1000), loop=0, optimize=True
    )
    return gif


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="docs/assets/demo")
    ap.add_argument("--candidate", default="linear", help="model family to train as the candidate")
    ap.add_argument("--max-steps", type=int, default=400, help="max 1-day replay steps before giving up")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "url": args.url,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with sync_playwright() as p:
        exe = os.environ.get("METRONOME_CHROMIUM")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 1000}, locale="ko-KR")
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector("#chip-ready.ok", timeout=60_000)
        report["first_version"] = page.evaluate(
            "() => fetch('/ready').then(r => r.json()).then(d => d.model)"
        )

        # 1 · data: profile, then the CSV check with a deliberately flawed sample
        page.wait_for_function(
            "() => document.querySelectorAll('#channel-table tbody tr').length > 0", timeout=30_000
        )
        page.set_input_files("#upload-file", str(sample_csv(out / "sample.csv")))
        page.click("#btn-upload")
        page.wait_for_selector("#upload-result .badge", timeout=30_000)
        shot(page, out, "01-data.png")
        report["csv_check"] = page.evaluate(
            "() => document.querySelector('#upload-result .badge').textContent"
        )

        # 2 · models: train a candidate of another family, then let the gate decide
        page.click(".step[data-panel=models]")
        page.wait_for_function(
            "() => document.querySelectorAll('#leaderboard-table tbody tr').length > 1", timeout=30_000
        )
        page.select_option("#cand-model", args.candidate)
        page.fill("#cand-epochs", "3")
        page.click("#btn-candidate")
        page.wait_for_function(
            "() => /등록됨|실패/.test(document.querySelector('#candidates-table').textContent)",
            timeout=600_000,
        )
        page.wait_for_timeout(3500)
        gate = page.query_selector("#candidates-table [data-promote]")
        if gate:
            gate.click()
            page.wait_for_timeout(3500)
        shot(page, out, "02-models.png")
        report["candidate"] = page.evaluate(
            "() => fetch('/v1/candidates').then(r => r.json()).then(d => d.jobs.at(-1))"
        )
        report["gate"] = page.inner_text("#cand-status")
        # the gate's own record: decision time, evaluation window, sample size, both MAEs, reason
        report["gate_decision"] = page.evaluate(
            "() => fetch('/v1/candidates').then(r => r.json()).then(d => (d.jobs.at(-1) || {}).gate)"
        )

        # 3 · deploy: versions, activate/rollback buttons, forecast call
        page.click(".step[data-panel=deploy]")
        page.wait_for_function(
            "() => document.querySelectorAll('#versions-table tbody tr').length >= 1", timeout=30_000
        )
        page.click("#btn-forecast")
        page.wait_for_function(
            "() => document.querySelector('#chart-forecast').childElementCount > 5", timeout=30_000
        )
        shot(page, out, "03-deploy.png")
        report["forecast"] = page.inner_text("#fc-status")

        # 4 · monitor: replay until a detector alarm retrains and the API swaps to the new version
        page.click(".step[data-panel=monitor]")
        page.click("#btn-start")
        page.wait_for_selector("#btn-step7:not([disabled])", timeout=60_000)
        before = page.evaluate("() => fetch('/ready').then(r => r.json()).then(d => d.model)")
        swapped = False
        for step in range(args.max_steps):
            page.click("#btn-step1")
            page.wait_for_timeout(250)
            events = page.evaluate("() => fetch('/v1/events').then(r => r.json())")
            if any(s["to"] != before and s["reason"] == "gate" for s in events["swaps"]):
                report["swap"] = events["swaps"][-1]
                report["steps_to_swap"] = step + 1
                swapped = True
                break
        for _ in range(10):  # a little more stream so both versions show in the daily chart
            page.click("#btn-step1")
            page.wait_for_timeout(200)
        page.wait_for_timeout(3500)
        shot(page, out, "04-monitor.png")
        report["swapped"] = swapped
        report["decisions"] = page.evaluate(
            "() => fetch('/v1/events').then(r => r.json()).then(d => d.decisions)"
        )
        report["monitor"] = page.evaluate(
            "() => fetch('/v1/monitor').then(r => r.json()).then(m => ({active: m.active_version, rolling: m.rolling_7d_mae, alarms: m.alarms.length, resolved: m.resolved_forecasts}))"
        )

        # 5 · policy
        page.click(".step[data-panel=policy]")
        page.wait_for_function(
            "() => document.querySelectorAll('#pareto-grid figure').length > 0", timeout=30_000
        )
        shot(page, out, "05-policy.png")

        # phone width, on the models step where the live table is
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, locale="ko-KR"
        )
        mp = mobile.new_page()
        mp.goto(args.url + "#models", wait_until="networkidle")
        mp.wait_for_selector("#chip-ready.ok", timeout=60_000)
        mp.wait_for_function(
            "() => document.querySelectorAll('#candidates-table tbody tr').length > 0", timeout=30_000
        )
        shot(mp, out, "06-mobile.png")
        browser.close()

    gif = slideshow_gif(
        out, ["01-data.png", "02-models.png", "03-deploy.png", "04-monitor.png", "05-policy.png"]
    )
    report["gif"] = str(gif) if gif else None
    (out / "capture-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
