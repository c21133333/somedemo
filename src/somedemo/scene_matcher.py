import json
import os
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


SceneRule = Dict[str, Any]


def load_scene_rules(path: str) -> List[SceneRule]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("scene rules must be a list")
    return data


def _resolve_path(base_dir: Optional[str], value: str) -> str:
    if os.path.isabs(value) or not base_dir:
        return value
    return os.path.join(base_dir, value)


def _get_region(image: np.ndarray, region: Optional[List[int]]) -> Tuple[np.ndarray, int, int]:
    if not region:
        return image, 0, 0
    x, y, w, h = region
    x = max(0, x)
    y = max(0, y)
    w = max(0, w)
    h = max(0, h)
    return image[y : y + h, x : x + w], x, y


def _match_template(
    image: np.ndarray,
    rule: SceneRule,
    base_dir: Optional[str],
) -> bool:
    template_path = rule.get("template")
    if not template_path:
        return False
    template_path = _resolve_path(base_dir, template_path)
    template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
    if template is None:
        return False
    if template.ndim == 3 and template.shape[2] == 4:
        template = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)

    region = rule.get("region")
    roi, _, _ = _get_region(image, region)
    if roi.size == 0:
        return False
    if roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
        return False

    method_name = rule.get("method", "TM_CCOEFF_NORMED")
    method = getattr(cv2, method_name, cv2.TM_CCOEFF_NORMED)
    result = cv2.matchTemplate(roi, template, method)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    threshold = float(rule.get("threshold", 0.9))
    return max_val >= threshold


def _match_color(image: np.ndarray, rule: SceneRule) -> bool:
    region = rule.get("region")
    roi, _, _ = _get_region(image, region)
    if roi.size == 0:
        return False
    lower = np.array(rule.get("lower", [0, 0, 0]), dtype=np.uint8)
    upper = np.array(rule.get("upper", [255, 255, 255]), dtype=np.uint8)
    mask = np.all((roi >= lower) & (roi <= upper), axis=2)
    ratio = float(rule.get("ratio", 1.0))
    return float(mask.mean()) >= ratio


def match_scene(
    image: np.ndarray,
    rules: List[SceneRule],
    base_dir: Optional[str] = None,
) -> Optional[str]:
    for rule in rules:
        name = rule.get("name")
        rule_type = rule.get("type")
        if not name or not rule_type:
            continue
        if rule_type == "template":
            if _match_template(image, rule, base_dir):
                return name
        elif rule_type == "color":
            if _match_color(image, rule):
                return name
    return None
