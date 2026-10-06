"""Drive the live dashboard with Playwright: replay the stream until a retrain fires and the worker
hot-swaps the model, taking screenshots along the way and recording a video.

Usage: python scripts/capture_demo.py --url http://127.0.0.1:8000 --out artifacts/demo
Requires a running `metronome serve` and `metronome worker` against the same registry.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="artifacts/demo")
    ap.add_argument("--schedule-days", type=int, default=0)
    ap.add_argument("--max-steps", type=int, default=400, help="max 1-day steps before giving up")
    ap.add_argument("--video", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {"url": args.url, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx_kwargs: dict[str, object] = {"viewport": {"width": 1280, "height": 1000}, "locale": "ko-KR"}
        if args.video:
            ctx_kwargs["record_video_dir"] = str(out / "video")
            ctx_kwargs["record_video_size"] = {"width": 1280, "height": 1000}
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector("#chip-ready.ok", timeout=30_000)
        page.screenshot(path=str(out / "01-ready.png"), full_page=True)

        if args.schedule_days:
            page.fill("#schedule-days", str(args.schedule_days))
        page.click("#btn-start")
        page.wait_for_selector("#btn-step7:not([disabled])", timeout=30_000)
        page.screenshot(path=str(out / "02-replay-started.png"), full_page=True)

        swapped = False
        first_version = page.evaluate("() => fetch('/v1/models').then(r => r.json()).then(m => m.active.version)")
        report["first_version"] = first_version
        for step in range(args.max_steps):
            page.click("#btn-step1")
            page.wait_for_timeout(250)
            events = page.evaluate("() => fetch('/v1/events').then(r => r.json())")
            if events["retrain_requests"] and "03-retrain-requested.png" not in report:
                page.wait_for_timeout(1500)
                page.screenshot(path=str(out / "03-retrain-requested.png"), full_page=True)
                report["03-retrain-requested.png"] = events["retrain_requests"][-1]
            if any(s["to"] != first_version for s in events["swaps"]):
                page.wait_for_timeout(3500)  # let the dashboard poll once more
                page.screenshot(path=str(out / "04-hot-swapped.png"), full_page=True)
                report["swap"] = events["swaps"][-1]
                report["steps_to_swap"] = step + 1
                swapped = True
                break
        for _ in range(10):  # a little more stream after the swap so both versions show in the chart
            page.click("#btn-step1")
            page.wait_for_timeout(200)
        page.wait_for_timeout(3500)
        page.screenshot(path=str(out / "05-after-swap.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "06-mobile.png"), full_page=True)
        report["swapped"] = swapped
        report["monitor"] = page.evaluate("() => fetch('/v1/monitor').then(r => r.json())")
        report["models"] = page.evaluate("() => fetch('/v1/models').then(r => r.json())")
        ctx.close()
        browser.close()
        if args.video:
            videos = sorted((out / "video").glob("*.webm"))
            if videos:
                shutil.move(str(videos[-1]), str(out / "demo.webm"))
                if shutil.which("ffmpeg"):
                    subprocess.run(
                        [
                            "ffmpeg", "-y", "-i", str(out / "demo.webm"), "-vf",
                            "fps=6,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer",
                            str(out / "demo.gif"),
                        ],
                        check=False,
                        capture_output=True,
                    )
    (out / "capture-report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: v for k, v in report.items() if k not in {"monitor", "models"}}, indent=2, default=str))


if __name__ == "__main__":
    main()
