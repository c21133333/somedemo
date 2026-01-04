# Python Project

This is a basic Python project scaffold.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run the project: `python src/main.py`

## Usage

Describe how to use the project here.

## Mouse Recorder Tool

Run the GUI mouse recorder: `python src/mouse_recorder.py`

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

To build a standalone executable: `pyinstaller --onefile src/mouse_recorder.py`

The executable will be in the dist/ folder.

## Testing

Run tests: `pytest`