# -*- coding: utf-8 -*-
import argparse
import json
import time
from typing import Dict, Iterable, List, Optional, Tuple

import pyautogui
import pytesseract
from pynput import keyboard, mouse


def parse_keywords(raw: str) -> List[str]:
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]


def iter_text_boxes(
    lang: str,
    region: Optional[Tuple[int, int, int, int]],
) -> Iterable[Tuple[str, int, int, int, int, int]]:
    screenshot = pyautogui.screenshot(region=region)
    data = pytesseract.image_to_data(
        screenshot, lang=lang, output_type=pytesseract.Output.DICT
    )
    for i, text in enumerate(data.get("text", [])):
        text = (text or "").strip()
        if not text:
            continue
        try:
            conf = int(float(data.get("conf", [0])[i]))
        except (ValueError, TypeError):
            conf = 0
        x = int(data.get("left", [0])[i])
        y = int(data.get("top", [0])[i])
        w = int(data.get("width", [0])[i])
        h = int(data.get("height", [0])[i])
        if region:
            x += region[0]
            y += region[1]
        yield text, conf, x, y, w, h


def should_click(
    text: str,
    keywords: List[str],
    conf: int,
    min_conf: int,
    cooldown: float,
    last_click: Dict[str, float],
) -> Tuple[bool, str]:
    if conf < min_conf:
        return False, ""
    for kw in keywords:
        if kw in text:
            now = time.time()
            if now - last_click.get(kw, 0.0) < cooldown:
                return False, ""
            last_click[kw] = now
            return True, kw
    return False, ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor screen text and auto-click when keywords appear."
    )
    parser.add_argument(
        "--keywords",
        default="准备,挑战",
        help="Comma-separated keywords to match.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between scans.",
    )
    parser.add_argument(
        "--min-conf",
        type=int,
        default=60,
        help="Minimum OCR confidence to accept.",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=2.0,
        help="Minimum seconds between clicks for the same keyword.",
    )
    parser.add_argument(
        "--lang",
        default="chi_sim",
        help="Tesseract language, e.g. chi_sim, eng.",
    )
    parser.add_argument(
        "--tesseract",
        default="",
        help="Optional path to tesseract executable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect only; do not click.",
    )
    parser.add_argument(
        "--region",
        default="",
        help="Scan region as left,top,width,height (screen coords).",
    )
    parser.add_argument(
        "--select-region",
        action="store_true",
        help="Interactively drag to select scan region.",
    )
    parser.add_argument(
        "--save-region",
        default="",
        help="Save selected/parsed region to a json file.",
    )
    parser.add_argument(
        "--load-region",
        default="",
        help="Load region from a json file.",
    )
    args = parser.parse_args()

    if args.tesseract:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    keywords = parse_keywords(args.keywords)
    if not keywords:
        raise SystemExit("No keywords provided.")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    last_click: Dict[str, float] = {}
    region: Optional[Tuple[int, int, int, int]] = None
    if args.load_region:
        region = load_region_file(args.load_region)
    if args.select_region:
        region = select_region()
    if args.region:
        try:
            parts = [int(p.strip()) for p in args.region.split(",")]
        except ValueError:
            raise SystemExit("Invalid --region, use left,top,width,height.")
        if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
            raise SystemExit("Invalid --region, use left,top,width,height.")
        region = (parts[0], parts[1], parts[2], parts[3])
    if args.save_region and region:
        save_region_file(args.save_region, region)

    print(
        "Monitoring. Move mouse to top-left corner to abort (pyautogui failsafe)."
    )
    try:
        while True:
            clicked = False
            for text, conf, x, y, w, h in iter_text_boxes(args.lang, region):
                ok, kw = should_click(
                    text, keywords, conf, args.min_conf, args.cooldown, last_click
                )
                if not ok:
                    continue
                cx = x + max(w // 2, 1)
                cy = y + max(h // 2, 1)
                if args.dry_run:
                    print(f"Match '{kw}' at ({cx}, {cy}) conf={conf} text='{text}'")
                else:
                    print(f"Click '{kw}' at ({cx}, {cy}) conf={conf} text='{text}'")
                    pyautogui.click(cx, cy)
                clicked = True
                break

            if not clicked and args.dry_run:
                print("No match.")
            time.sleep(max(args.interval, 0.1))
    except KeyboardInterrupt:
        print("Stopped.")


def select_region() -> Tuple[int, int, int, int]:
    print("Drag to select region: press left mouse, drag, release.")
    start: List[int] = []
    end: List[int] = []
    cancelled = {"value": False}
    mouse_listener: Optional[mouse.Listener] = None

    def on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> bool:
        if button != mouse.Button.left:
            return False
        if pressed:
            start[:] = [x, y]
        else:
            end[:] = [x, y]
            return False
        return True

    def on_press_key(key) -> bool:
        if key == keyboard.Key.esc:
            cancelled["value"] = True
            if mouse_listener:
                mouse_listener.stop()
            return False
        return True

    with keyboard.Listener(on_press=on_press_key) as key_listener:
        with mouse.Listener(on_click=on_click) as listener:
            mouse_listener = listener
            listener.join()
        key_listener.stop()

    if cancelled["value"]:
        raise SystemExit("Selection cancelled.")
    if len(start) != 2 or len(end) != 2:
        raise SystemExit("Selection cancelled.")
    left = min(start[0], end[0])
    top = min(start[1], end[1])
    width = abs(end[0] - start[0])
    height = abs(end[1] - start[1])
    if width == 0 or height == 0:
        raise SystemExit("Selection too small.")
    print(f"Selected region: {left},{top},{width},{height}")
    return left, top, width, height


def save_region_file(path: str, region: Tuple[int, int, int, int]) -> None:
    data = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2)
    print(f"Region saved to {path}")


def load_region_file(path: str) -> Tuple[int, int, int, int]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    try:
        left = int(data["left"])
        top = int(data["top"])
        width = int(data["width"])
        height = int(data["height"])
    except (KeyError, TypeError, ValueError):
        raise SystemExit("Invalid region file format.")
    if width <= 0 or height <= 0:
        raise SystemExit("Invalid region file format.")
    return left, top, width, height


if __name__ == "__main__":
    main()
