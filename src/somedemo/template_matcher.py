import json
import os
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


TemplateConfig = Dict[str, Any]
MatchResult = Dict[str, Any]


class TemplateMatcher:
    def __init__(self, templates: List[TemplateConfig]):
        self._templates = templates

    @classmethod
    def load_from_paths(
        cls, paths: List[str], threshold: float = 0.85
    ) -> "TemplateMatcher":
        templates = []
        for path in paths:
            image = cv2.imread(path, cv2.IMREAD_COLOR)
            if image is None:
                continue
            name = os.path.splitext(os.path.basename(path))[0]
            templates.append(
                {
                    "name": name,
                    "image": image,
                    "threshold": float(threshold),
                    "click": {},
                }
            )
        return cls(templates)

    @classmethod
    def load_from_json(cls, path: str) -> "TemplateMatcher":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        templates = []
        base_dir = os.path.dirname(path)
        for item in data.get("templates", []):
            name = item.get("name")
            path_value = item.get("path")
            if not name or not path_value:
                continue
            template_path = (
                path_value
                if os.path.isabs(path_value)
                else os.path.join(base_dir, path_value)
            )
            image = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if image is None:
                continue
            templates.append(
                {
                    "name": name,
                    "image": image,
                    "threshold": float(item.get("threshold", 0.85)),
                    "click": dict(item.get("click", {})),
                }
            )
        return cls(templates)

    def match(self, frame: np.ndarray) -> Optional[MatchResult]:
        best = None
        for tmpl in self._templates:
            template = tmpl["image"]
            if frame.shape[0] < template.shape[0] or frame.shape[1] < template.shape[1]:
                continue
            result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val < tmpl["threshold"]:
                continue
            if not best or max_val > best["confidence"]:
                best = {
                    "name": tmpl["name"],
                    "confidence": float(max_val),
                    "x": int(max_loc[0]),
                    "y": int(max_loc[1]),
                    "width": int(template.shape[1]),
                    "height": int(template.shape[0]),
                    "click": dict(tmpl.get("click", {})),
                }
        return best
