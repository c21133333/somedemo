import threading
import time
from typing import Callable, Optional, Tuple

import numpy as np
import mss


FrameCallback = Callable[[np.ndarray], None]


class ScreenCapture:
    def __init__(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        fps: float = 10.0,
        frame_callback: Optional[FrameCallback] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.region = region
        self.fps = max(0.1, float(fps))
        self.frame_callback = frame_callback
        self.log_callback = log_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def _get_monitor(self, sct: mss.mss) -> dict:
        if self.region:
            x, y, width, height = self.region
            return {"left": x, "top": y, "width": width, "height": height}
        return sct.monitors[1]

    def start(self) -> bool:
        if self._running:
            self._log("屏幕采集已在运行中。")
            return False
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._log("屏幕采集已启动。")
        return True

    def stop(self) -> bool:
        if not self._running:
            self._log("屏幕采集未在运行。")
            return False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._running = False
        self._log("屏幕采集已停止。")
        return True

    def get_latest_frame(self) -> Optional[np.ndarray]:
        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def _run(self) -> None:
        interval = 1.0 / self.fps
        next_ts = time.perf_counter()
        with mss.mss() as sct:
            monitor = self._get_monitor(sct)
            while not self._stop_event.is_set():
                start = time.perf_counter()
                shot = sct.grab(monitor)
                frame = np.array(shot, dtype=np.uint8)[:, :, :3]
                frame = np.ascontiguousarray(frame)
                with self._lock:
                    self._latest_frame = frame
                if self.frame_callback:
                    self.frame_callback(frame)

                next_ts += interval
                sleep_time = max(0.0, next_ts - time.perf_counter())
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif time.perf_counter() - start > interval * 2:
                    next_ts = time.perf_counter()
        self._running = False


if __name__ == "__main__":
    capture = ScreenCapture(region=None, fps=5)
    capture.start()
    time.sleep(1.0)
    frame = capture.get_latest_frame()
    capture.stop()
    if frame is not None:
        print(frame.shape)
