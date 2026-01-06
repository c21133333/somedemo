import json
import os
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


TemplateConfig = Dict[str, Any]
MatchResult = Dict[str, Any]
EDGE_LOW = 50
EDGE_HIGH = 150
USE_EDGE_MATCH = True
MATCH_MODE = "gray+edge(max)"
BLUR_KERNEL = (3, 3)
BLUR_SIGMA = 0


def _edge(image: np.ndarray) -> np.ndarray:
    gray = _to_gray(image)
    return cv2.Canny(gray, EDGE_LOW, EDGE_HIGH)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(image, BLUR_KERNEL, BLUR_SIGMA)


def _normalize_threshold(value: float) -> float:
    return max(0.65, min(0.75, float(value)))


class TemplateMatcher:
    def __init__(self, templates: List[TemplateConfig]):
        self._templates = templates
        self._scales = [1.0, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3]

    def match_mode(self) -> str:
        if USE_EDGE_MATCH:
            return MATCH_MODE
        return "gray"

    def _iter_scaled_templates(self, template: np.ndarray):
        for scale in self._scales:
            if scale == 1.0:
                yield template, 1.0
                continue
            new_w = max(1, int(round(template.shape[1] * scale)))
            new_h = max(1, int(round(template.shape[0] * scale)))
            if new_w == template.shape[1] and new_h == template.shape[0]:
                yield template, 1.0
                continue
            interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
            resized = cv2.resize(template, (new_w, new_h), interpolation=interpolation)
            yield resized, scale

    def _resize_template(self, template: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1.0:
            return template
        new_w = max(1, int(round(template.shape[1] * scale)))
        new_h = max(1, int(round(template.shape[0] * scale)))
        if new_w == template.shape[1] and new_h == template.shape[0]:
            return template
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        return cv2.resize(template, (new_w, new_h), interpolation=interpolation)

    def best_confidence(self, frame: np.ndarray) -> Optional[MatchResult]:
        frame_gray = _to_gray(frame)
        frame_edge = _edge(frame_gray) if USE_EDGE_MATCH else None
        best = None
        for tmpl in self._templates:
            template_gray = tmpl.get("gray")
            if template_gray is None:
                continue
            for scale in self._scales:
                tmpl_gray = self._resize_template(template_gray, scale)
                if (
                    frame_gray.shape[0] < tmpl_gray.shape[0]
                    or frame_gray.shape[1] < tmpl_gray.shape[1]
                ):
                    continue
                result = cv2.matchTemplate(
                    frame_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED
                )
                _, gray_val, _, max_loc = cv2.minMaxLoc(result)
                edge_val = -1.0
                edge_loc = max_loc
                if USE_EDGE_MATCH and frame_edge is not None:
                    edge_scaled = _edge(tmpl_gray)
                    if (
                        frame_edge.shape[0] >= edge_scaled.shape[0]
                        and frame_edge.shape[1] >= edge_scaled.shape[1]
                    ):
                        edge_res = cv2.matchTemplate(
                            frame_edge, edge_scaled, cv2.TM_CCOEFF_NORMED
                        )
                        _, edge_val, _, edge_loc = cv2.minMaxLoc(edge_res)
                use_edge = edge_val > gray_val
                conf = float(edge_val if use_edge else gray_val)
                pick_loc = edge_loc if use_edge else max_loc
                if not best or conf > best["confidence"]:
                    best = {
                        "name": tmpl.get("name", ""),
                        "confidence": conf,
                        "gray_conf": float(gray_val),
                        "edge_conf": float(edge_val),
                        "x": int(pick_loc[0]),
                        "y": int(pick_loc[1]),
                        "width": int(tmpl_gray.shape[1]),
                        "height": int(tmpl_gray.shape[0]),
                        "scale": float(scale),
                    }
        return best

    def describe(self) -> List[Dict[str, int]]:
        summary: List[Dict[str, int]] = []
        for tmpl in self._templates:
            image = tmpl.get("image")
            if image is None:
                continue
            summary.append(
                {
                    "name": str(tmpl.get("name", "")),
                    "width": int(image.shape[1]),
                    "height": int(image.shape[0]),
                }
            )
        return summary

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
                    "gray": _to_gray(image),
                    "edge": _edge(image),
                    "threshold": _normalize_threshold(threshold),
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
                    "gray": _to_gray(image),
                    "edge": _edge(image),
                    "threshold": _normalize_threshold(item.get("threshold", 0.85)),
                    "click": dict(item.get("click", {})),
                }
            )
        return cls(templates)

    def match(self, frame: np.ndarray) -> Optional[MatchResult]:
        frame_gray = _to_gray(frame)
        frame_edge = _edge(frame_gray) if USE_EDGE_MATCH else None
        best = None
        for tmpl in self._templates:
            template_gray = tmpl.get("gray")
            if template_gray is None:
                continue
            for scale in self._scales:
                tmpl_gray = self._resize_template(template_gray, scale)
                if (
                    frame_gray.shape[0] < tmpl_gray.shape[0]
                    or frame_gray.shape[1] < tmpl_gray.shape[1]
                ):
                    continue
                result = cv2.matchTemplate(
                    frame_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED
                )
                _, gray_val, _, max_loc = cv2.minMaxLoc(result)
                edge_val = -1.0
                edge_loc = max_loc
                if USE_EDGE_MATCH and frame_edge is not None:
                    edge_scaled = _edge(tmpl_gray)
                    if (
                        frame_edge.shape[0] >= edge_scaled.shape[0]
                        and frame_edge.shape[1] >= edge_scaled.shape[1]
                    ):
                        edge_res = cv2.matchTemplate(
                            frame_edge, edge_scaled, cv2.TM_CCOEFF_NORMED
                        )
                        _, edge_val, _, edge_loc = cv2.minMaxLoc(edge_res)
                use_edge = edge_val > gray_val
                conf = float(edge_val if use_edge else gray_val)
                pick_loc = edge_loc if use_edge else max_loc
                if conf < tmpl["threshold"]:
                    continue
                if not best or conf > best["confidence"]:
                    best = {
                        "name": tmpl["name"],
                        "confidence": conf,
                        "gray_conf": float(gray_val),
                        "edge_conf": float(edge_val),
                        "x": int(pick_loc[0]),
                        "y": int(pick_loc[1]),
                        "width": int(tmpl_gray.shape[1]),
                        "height": int(tmpl_gray.shape[0]),
                        "scale": float(scale),
                        "click": dict(tmpl.get("click", {})),
                    }
        return best
