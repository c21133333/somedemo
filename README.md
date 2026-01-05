# Python Project

This is a basic Python project scaffold.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run the project: `python -m somedemo.mouse_recorder`

## Usage

Describe how to use the project here.

## Mouse Recorder Tool

Run the GUI mouse recorder: `python -m somedemo.mouse_recorder`
Run the Qt GUI recorder: `python scripts/run_qt.py`
Run the region selector demo: `python -m somedemo.region_selector`
Run the screen capture demo: `python -m somedemo.screen_capture`
Use action executor: `python -m somedemo.action_executor`

- Click "开始录制 (Ctrl+S)" to begin recording mouse trajectory and clicks.
- Click "结束录制 (Ctrl+E)" to stop and save to trajectory.json.
- Click "播放 (Ctrl+P)" to play back the trajectory and clicks.
- Click "停止 (Ctrl+T)" to stop playback.

Shortcuts: Ctrl+S (Start), Ctrl+E (End), Ctrl+P (Play), Ctrl+T (Stop).

Adjust playback speed with the slider (0.5x to 5.0x).

Select recording frequency with the slider (30Hz to 500Hz, default 240Hz).

The tool now records mouse movements at user-selected frequency for precision, includes left/right click events, and uses distance-based duration for consistent movement speed during playback to reduce frame drops and speed inconsistencies.

If trajectory.json is missing or corrupted, an error dialog will appear.

## Building Executable

To build a standalone executable: `pyinstaller --onefile src/somedemo/mouse_recorder.py`

The executable will be in the dist/ folder.

## Testing

Run tests: `pytest`

## Region Selector Example

```python
from somedemo.region_selector import select_region

region = select_region()
if region:
    x, y, width, height = region
    print(x, y, width, height)
```

## Screen Capture Example

```python
import time

from somedemo.screen_capture import ScreenCapture

capture = ScreenCapture(region=(0, 0, 800, 600), fps=10)
capture.start()
time.sleep(1.5)
frame = capture.get_latest_frame()
capture.stop()
if frame is not None:
    print(frame.shape)
```

## Scene Matcher Example

Example rules file: `assets/scenes/sample_rules.json`

```python
import cv2

from somedemo.scene_matcher import load_scene_rules, match_scene

rules = load_scene_rules("assets/scenes/sample_rules.json")
image = cv2.imread("assets/templates/menu_button.png")
scene = match_scene(image, rules, base_dir=".")
print(scene)
```

## Action Executor Example

```python
from somedemo.action_executor import execute

region = (100, 100, 800, 600)
execute({"type": "click", "x": 10, "y": 20, "region": region, "delay": 2})
execute({"type": "double_click", "x": 40, "y": 60, "region": region, "delay": 2})
execute(
    {
        "type": "drag",
        "x1": 50,
        "y1": 50,
        "x2": 200,
        "y2": 160,
        "region": region,
        "duration": 0.3,
        "delay": 2,
    }
)
```

## Template Matcher Example

```python
import cv2

from somedemo.template_matcher import TemplateMatcher

matcher = TemplateMatcher.load_from_json("templates/sample_templates.json")
frame = cv2.imread("templates/confirm.png")
match = matcher.match(frame)
print(match)
```
