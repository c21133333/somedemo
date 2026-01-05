import random
import time
from typing import Any, Dict, Optional, Tuple

import pyautogui
from pynput import keyboard


ActionConfig = Dict[str, Any]

_last_action_ts: Dict[str, float] = {}


def _apply_region(
    point: Tuple[int, int],
    region: Optional[Tuple[int, int, int, int]],
) -> Tuple[int, int]:
    if not region:
        return point
    x, y = point
    rx, ry, _, _ = region
    return x + rx, y + ry


def execute(action_config: ActionConfig) -> bool:
    action_type = action_config.get("type")
    if not action_type:
        raise ValueError("action_config.type is required")

    region = action_config.get("region")
    if region is not None and len(region) != 4:
        raise ValueError("region must be (x, y, width, height)")

    delay = float(action_config.get("delay", 2.0))
    abort_key = action_config.get("abort_key", keyboard.Key.esc)
    interrupted = {"value": False}

    def on_press(key):
        if key == abort_key:
            interrupted["value"] = True
            return False
        return True

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0

    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    try:
        start = time.time()
        while time.time() - start < delay:
            if interrupted["value"]:
                return False
            time.sleep(0.05)

        if interrupted["value"]:
            return False

        if action_type == "click":
            x, y = action_config["x"], action_config["y"]
            x, y = _apply_region((x, y), region)
            clicks = int(action_config.get("clicks", 1))
            interval = float(action_config.get("interval", 0.0))
            button = action_config.get("button", "left")
            pyautogui.click(x, y, clicks=clicks, interval=interval, button=button)
            return True

        if action_type == "double_click":
            x, y = action_config["x"], action_config["y"]
            x, y = _apply_region((x, y), region)
            button = action_config.get("button", "left")
            pyautogui.doubleClick(x, y, button=button)
            return True

        if action_type == "drag":
            x1, y1 = action_config["x1"], action_config["y1"]
            x2, y2 = action_config["x2"], action_config["y2"]
            x1, y1 = _apply_region((x1, y1), region)
            x2, y2 = _apply_region((x2, y2), region)
            duration = float(action_config.get("duration", 0.2))
            button = action_config.get("button", "left")
            pyautogui.moveTo(x1, y1)
            pyautogui.dragTo(x2, y2, duration=duration, button=button)
            return True

        raise ValueError(f"unknown action type: {action_type}")
    finally:
        listener.stop()


def execute_match(
    match_result: Dict[str, Any],
    region: Optional[Tuple[int, int, int, int]],
) -> bool:
    if not match_result:
        return False
    name = str(match_result.get("name", "template"))
    click_cfg = match_result.get("click", {}) or {}
    cooldown_ms = int(click_cfg.get("cooldown_ms", 0))
    now = time.time()
    if cooldown_ms > 0:
        last = _last_action_ts.get(name, 0.0)
        if now - last < cooldown_ms / 1000.0:
            return False

    offset_x = int(click_cfg.get("offset_x", 0))
    offset_y = int(click_cfg.get("offset_y", 0))
    delay_ms = int(click_cfg.get("delay_ms", 0))
    click_type = str(click_cfg.get("type", "left")).lower()
    click_count = int(click_cfg.get("click_count", 1))
    interval_ms = int(click_cfg.get("interval_ms", 0))

    x = int(match_result["x"]) + int(match_result["width"]) // 2 + offset_x
    y = int(match_result["y"]) + int(match_result["height"]) // 2 + offset_y
    if bool(click_cfg.get("random_offset", True)):
        rand_x = random.randint(
            -int(match_result["width"]) // 2, int(match_result["width"]) // 2
        )
        rand_y = random.randint(
            -int(match_result["height"]) // 2, int(match_result["height"]) // 2
        )
        x += rand_x
        y += rand_y
    if region:
        x, y = _apply_region((x, y), region)

    action_type = "click"
    button = "left"
    if click_type in ("double", "double_click", "dbl"):
        action_type = "double_click"
    elif click_type in ("right", "middle"):
        button = click_type
    action = {
        "type": action_type,
        "x": x,
        "y": y,
        "button": button,
        "delay": delay_ms / 1000.0,
        "clicks": max(1, click_count),
        "interval": max(0.0, interval_ms / 1000.0),
    }
    if action_type == "double_click" and click_count > 1:
        ok = True
        for _ in range(click_count):
            if not execute(action):
                ok = False
                break
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)
    else:
        ok = execute(action)
    if ok and cooldown_ms > 0:
        _last_action_ts[name] = now
    return ok


if __name__ == "__main__":
    print(
        "Use execute(action_config) from your code; see README for examples."
    )
