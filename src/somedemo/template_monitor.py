import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np
import pyautogui

from somedemo.region_selector import (
    get_monitor_scale_for_region,
    get_screen_debug_info,
    physical_to_logical_region,
    select_region,
)


def ensure_dpi_aware() -> None:
    if sys.platform != "win32":
        return
    try:
        # DPI aware keeps screenshots and mouse clicks aligned to physical pixels.
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


@dataclass
class TemplateItem:
    name: str
    image: np.ndarray
    gray: np.ndarray
    source: str
    meta: Dict[str, object]
    path: str


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _log(message: str, logger: Optional[Callable[[str], None]]) -> None:
    if logger:
        logger(message)
    else:
        print(message)


def _get_monitor_resolution(region: Tuple[int, int, int, int]) -> Tuple[int, int]:
    cx = region[0] + region[2] // 2
    cy = region[1] + region[3] // 2
    with mss.mss() as sct:
        for mon in sct.monitors[1:]:
            left, top = mon["left"], mon["top"]
            width, height = mon["width"], mon["height"]
            if left <= cx < left + width and top <= cy < top + height:
                return width, height
    return region[2], region[3]


def _warn_if_env_mismatch(
    templates: List[TemplateItem],
    region: Optional[Tuple[int, int, int, int]],
    logger: Optional[Callable[[str], None]],
) -> None:
    if not region:
        region = _get_full_screen()
    current_res = _get_monitor_resolution(region)
    scale_x, scale_y = get_monitor_scale_for_region(region)
    for tmpl in templates:
        meta_res = tmpl.meta.get("screen_resolution")
        meta_scale = tmpl.meta.get("dpi_scale")
        if meta_res and isinstance(meta_res, (list, tuple)) and len(meta_res) == 2:
            if int(meta_res[0]) != current_res[0] or int(meta_res[1]) != current_res[1]:
                _log(
                    f"Template '{tmpl.name}' captured at {meta_res}, current {current_res}.",
                    logger,
                )
        if meta_scale and isinstance(meta_scale, (list, tuple)) and len(meta_scale) == 2:
            try:
                sx = float(meta_scale[0])
                sy = float(meta_scale[1])
                if abs(sx - scale_x) > 0.01 or abs(sy - scale_y) > 0.01:
                    _log(
                        f"Template '{tmpl.name}' DPI scale {meta_scale}, current {[scale_x, scale_y]}.",
                        logger,
                    )
            except Exception:
                continue


def _capture_region(region: Tuple[int, int, int, int]) -> np.ndarray:
    left, top, width, height = region
    with mss.mss() as sct:
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        frame = np.array(shot, dtype=np.uint8)[:, :, :3]
        return np.ascontiguousarray(frame)


def capture_program_template(
    output_dir: str, name: Optional[str] = None, logger: Optional[Callable[[str], None]] = None
) -> Optional[str]:
    ensure_dpi_aware()
    region = select_region()
    if not region:
        _log("Template capture cancelled.", logger)
        return None
    _log(f"Template capture region (physical): {region}", logger)
    logical = physical_to_logical_region(region)
    _log(f"Template capture region (logical): {logical}", logger)
    _log(f"Template capture screen info: {get_screen_debug_info()}", logger)

    image = _capture_region(region)
    if image.size <= 0:
        _log("Captured image is empty.", logger)
        return None

    os.makedirs(output_dir, exist_ok=True)
    base_name = name or f"program_capture_{int(time.time())}"
    image_path = os.path.join(output_dir, f"{base_name}.png")
    meta_path = os.path.join(output_dir, f"{base_name}.json")

    cv2.imwrite(image_path, image)

    scale_x, scale_y = get_monitor_scale_for_region(region)
    screen_w, screen_h = _get_monitor_resolution(region)
    meta = {
        "source": "program_capture",
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "screen_resolution": [int(screen_w), int(screen_h)],
        "dpi_scale": [float(scale_x), float(scale_y)],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    _log(f"Template saved: {image_path}", logger)
    return image_path


def _load_template_image(path: str, logger: Optional[Callable[[str], None]]) -> Optional[np.ndarray]:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        _log(f"Failed to load image: {path}", logger)
        return None
    if image.size <= 0:
        _log(f"Invalid image size: {path}", logger)
        return None
    if image.ndim != 3:
        _log(f"Image must be RGB/BGR: {path}", logger)
        return None
    if image.shape[2] != 3:
        _log(f"Image must be RGB/BGR (3 channels): {path}", logger)
        return None
    return image


def _load_meta(path: str) -> Dict[str, object]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def load_template_item(
    path: str, source: str, logger: Optional[Callable[[str], None]]
) -> Optional[TemplateItem]:
    image = _load_template_image(path, logger)
    if image is None:
        return None

    meta_path = os.path.splitext(path)[0] + ".json"
    meta = _load_meta(meta_path)
    if not meta:
        meta = {}

    if source == "local_image":
        _log(
            "Local image template has no capture metadata; ensure DPI/resolution match.",
            logger,
        )

    name = os.path.splitext(os.path.basename(path))[0]
    return TemplateItem(
        name=name,
        image=image,
        gray=_to_gray(image),
        source=source,
        meta=meta,
        path=path,
    )


class TemplateManager:
    def __init__(self, threshold: float = 0.9, logger: Optional[Callable[[str], None]] = None):
        self._templates: List[TemplateItem] = []
        self.threshold = max(0.9, min(1.0, float(threshold)))
        self.logger = logger

    def add(self, item: TemplateItem) -> None:
        self._templates.append(item)

    def load_local_images(self, paths: List[str]) -> None:
        for path in paths:
            item = load_template_item(path, "local_image", self.logger)
            if item:
                self.add(item)

    def load_program_captures(self, paths: List[str]) -> None:
        for path in paths:
            item = load_template_item(path, "program_capture", self.logger)
            if item:
                self.add(item)

    def iter_by_priority(self) -> List[TemplateItem]:
        # Program capture templates are preferred for DPI-accurate matching.
        priority = {"program_capture": 0, "local_image": 1}
        return sorted(
            self._templates,
            key=lambda tmpl: (priority.get(tmpl.source, 99), tmpl.name),
        )


def match_frame(
    frame: np.ndarray, templates: List[TemplateItem], threshold: float
) -> Optional[Dict[str, object]]:
    frame_gray = _to_gray(frame)
    for tmpl in templates:
        if (
            frame_gray.shape[0] < tmpl.gray.shape[0]
            or frame_gray.shape[1] < tmpl.gray.shape[1]
        ):
            continue
        result = cv2.matchTemplate(frame_gray, tmpl.gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if float(max_val) >= threshold:
            return {
                "name": tmpl.name,
                "confidence": float(max_val),
                "x": int(max_loc[0]),
                "y": int(max_loc[1]),
                "width": int(tmpl.gray.shape[1]),
                "height": int(tmpl.gray.shape[0]),
                "source": tmpl.source,
                "path": tmpl.path,
            }
    return None


def click_match_center(
    match: Dict[str, object], region: Optional[Tuple[int, int, int, int]]
) -> None:
    x = int(match["x"]) + int(match["width"]) // 2
    y = int(match["y"]) + int(match["height"]) // 2
    if region:
        x += int(region[0])
        y += int(region[1])
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    pyautogui.click(x, y)


def monitor_and_click(
    region: Optional[Tuple[int, int, int, int]],
    manager: TemplateManager,
    fps: float = 2.0,
) -> None:
    ensure_dpi_aware()
    _warn_if_env_mismatch(manager.iter_by_priority(), region, manager.logger)
    fps = max(0.1, float(fps))
    interval = 1.0 / fps
    while True:
        start = time.perf_counter()
        frame = _capture_region(region) if region else _capture_region(_get_full_screen())
        match = match_frame(frame, manager.iter_by_priority(), manager.threshold)
        if match:
            click_match_center(match, region)
        elapsed = time.perf_counter() - start
        sleep_time = max(0.0, interval - elapsed)
        time.sleep(sleep_time)


def _get_full_screen() -> Tuple[int, int, int, int]:
    with mss.mss() as sct:
        mon = sct.monitors[1]
        return mon["left"], mon["top"], mon["width"], mon["height"]


def main() -> None:
    ensure_dpi_aware()
    parser = argparse.ArgumentParser(description="Template match monitor (DPI aware).")
    parser.add_argument(
        "--capture-template",
        action="store_true",
        help="Capture a program template via on-screen selection.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.getcwd(), "templates"),
        help="Directory for captured templates.",
    )
    parser.add_argument(
        "--templates",
        nargs="*",
        default=[],
        help="Local template image paths (png/jpg).",
    )
    parser.add_argument(
        "--program-templates",
        nargs="*",
        default=[],
        help="Program-captured template image paths (png).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="Match threshold (>= 0.9).",
    )
    parser.add_argument(
        "--select-region",
        action="store_true",
        help="Select monitoring region on screen.",
    )
    parser.add_argument("--fps", type=float, default=2.0, help="Monitor FPS.")
    args = parser.parse_args()

    if args.capture_template:
        capture_program_template(args.output_dir)
        return

    region = select_region() if args.select_region else None
    manager = TemplateManager(threshold=args.threshold)
    if args.program_templates:
        manager.load_program_captures(args.program_templates)
    if args.templates:
        manager.load_local_images(args.templates)
    if not manager.iter_by_priority():
        print("No templates loaded.")
        return

    monitor_and_click(region, manager, fps=args.fps)


if __name__ == "__main__":
    main()
