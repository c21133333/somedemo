import json
import threading
import time

import pyautogui
from pynput import mouse


class RecorderCore:
    def __init__(self, log_callback=None, event_callback=None):
        self.log_callback = log_callback
        self.event_callback = event_callback

        self.events = []
        self.recording = False
        self.playing = False
        self.file_path = "trajectory.json"
        self.fixed_freq = 60
        self.loop_count = 1
        self.loop_infinite = False

        self.record_start_perf = None
        self.last_sample_dt = None
        self.mouse_listener = None
        self.play_thread = None

        self._events_lock = threading.Lock()

        # Remove pyautogui's default pause to keep playback timing accurate
        pyautogui.PAUSE = 0

    def _log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def _emit_event(self, event):
        if self.event_callback:
            self.event_callback(event)

    def get_events_copy(self):
        with self._events_lock:
            return list(self.events)

    # ---------------------- Recording ----------------------
    def _add_event(self, event):
        with self._events_lock:
            self.events.append(event)
        self._emit_event(event)

    def _on_move(self, x, y):
        if not self.recording:
            return
        now = time.perf_counter()
        if self.record_start_perf is None:
            self.record_start_perf = now
            self.last_sample_dt = 0
        dt = now - self.record_start_perf
        if self.last_sample_dt is None or dt - self.last_sample_dt >= 1 / self.fixed_freq:
            self._add_event({"type": "move", "x": x, "y": y, "dt": dt})
            self.last_sample_dt = dt

    def _on_click(self, x, y, button, pressed):
        if not self.recording:
            return
        now = time.perf_counter()
        if self.record_start_perf is None:
            self.record_start_perf = now
            self.last_sample_dt = 0
        dt = now - self.record_start_perf
        self._add_event(
            {
                "type": "click",
                "x": x,
                "y": y,
                "button": str(button),
                "pressed": pressed,
                "dt": dt,
            }
        )

    def start_recording(self):
        if self.recording:
            self._log("录制已在进行中。")
            return False
        self.recording = True
        with self._events_lock:
            self.events.clear()
        self.record_start_perf = None
        self.last_sample_dt = None
        self._log("开始录制。")

        self.mouse_listener = mouse.Listener(on_move=self._on_move, on_click=self._on_click)
        self.mouse_listener.start()
        return True

    def stop_recording(self):
        if not self.recording:
            self._log("当前未在录制。")
            return False
        self.recording = False
        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener = None
        self._log("录制已停止。")
        if self.events:
            self.save_script(self.file_path)
        else:
            self._log("没有录制到事件。")
        return True

    # ---------------------- Playback ----------------------
    def play_trajectory(self, loop_count=None, loop_infinite=None):
        if self.playing:
            self._log("回放已在进行中。")
            return False
        data = self.get_events_copy()
        if not data and self.file_path:
            loaded = self.open_script(self.file_path)
            if loaded:
                data = self.get_events_copy()
        if not data:
            self._log("没有可回放的事件。")
            return False

        self.playing = True
        if loop_count is not None:
            self.loop_count = max(1, int(loop_count))
        if loop_infinite is not None:
            self.loop_infinite = bool(loop_infinite)
        self._log("开始回放。")
        self.play_thread = threading.Thread(
            target=self._play,
            args=(data, self.loop_count, self.loop_infinite),
            daemon=True,
        )
        self.play_thread.start()
        return True

    def _play(self, data, loop_count, loop_infinite):
        loop_index = 0
        while self.playing and (loop_infinite or loop_index < loop_count):
            if loop_infinite:
                self._log(f"回放循环次数: {loop_index + 1}")
            prev_dt = 0
            for point in data:
                if not self.playing:
                    break
                dt = point.get("dt", 0)
                sleep_time = max(0, dt - prev_dt)
                while sleep_time > 0 and self.playing:
                    chunk = min(0.05, sleep_time)
                    time.sleep(chunk)
                    sleep_time -= chunk
                if not self.playing:
                    break
                if point.get("type") == "click":
                    button = "left"
                    raw_button = point.get("button")
                    if isinstance(raw_button, str) and "." in raw_button:
                        button = raw_button.split(".")[1]
                    elif raw_button:
                        button = str(raw_button)
                    if point.get("pressed"):
                        pyautogui.mouseDown(button=button)
                    else:
                        pyautogui.mouseUp(button=button)
                else:
                    x = point.get("x")
                    y = point.get("y")
                    if x is not None and y is not None:
                        pyautogui.moveTo(x, y, duration=0)
                prev_dt = dt
            loop_index += 1

        self.playing = False
        self._log("回放已停止。")
        if loop_infinite:
            self._log(f"回放结束，总循环次数: {loop_index}")

    def stop_playback(self):
        if not self.playing:
            self._log("当前未在回放。")
            return False
        self.playing = False
        self._log("正在停止回放...")
        return True

    # ---------------------- File actions ----------------------
    def open_script(self, path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            self._log(f"脚本不存在: {path}")
            return False
        except json.JSONDecodeError:
            self._log(f"脚本文件格式错误: {path}")
            return False
        if not isinstance(data, list):
            self._log(f"脚本结构无效: {path}")
            return False

        with self._events_lock:
            self.events = data
        self.file_path = path
        self._log(f"已加载脚本: {path} (事件数: {len(data)})。")
        return True

    def save_script(self, path=None):
        if not self.events:
            self._log("没有可保存的事件。")
            return False
        target = path or self.file_path
        try:
            with open(target, "w") as f:
                json.dump(self.events, f)
        except Exception as exc:
            self._log(f"保存脚本失败: {exc}")
            return False
        self.file_path = target
        self._log(f"已保存脚本: {target}")
        return True
