#!/usr/bin/env python3
"""Probe camera indexes 0-9, pick camera that sees your face, update config.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CONFIG = ROOT / "config.json"

from src.camera_utils import probe_cameras, pick_camera_index  # noqa: E402


def pick_best(results: list[dict]) -> int | None:
    working = [r for r in results if r["ok"]]
    if not working:
        return None
    if any(r["face_hits"] > 0 for r in working):
        working.sort(key=lambda r: r["face_hits"], reverse=True)
    else:
        working.sort(key=lambda r: r["frames"], reverse=True)
    return int(working[0]["index"])


def update_config(index: int) -> None:
    cfg = {}
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["camera_index"] = str(index)
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    print("=== Camera probe (indexes 0-9) — sit in front of camera ===")
    results = probe_cameras(10, face_check=True)
    for r in results:
        if r["ok"]:
            print(f"  index {r['index']}: {r['width']}x{r['height']}  frames={r['frames']}/20  face_hits={r['face_hits']}/20")
        else:
            print(f"  index {r['index']}: NOT AVAILABLE")

    best = pick_best(results)
    if best is None:
        print("\nFAIL: No working camera found.")
        return 1

    update_config(best)
    print(f"\nSELECTED camera index: {best}")
    print(f"Saved to {CONFIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
