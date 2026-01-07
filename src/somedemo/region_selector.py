import sys
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets


class RegionSelector(QtWidgets.QWidget):
    region_selected = QtCore.Signal(object)
    finished = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CrossCursor))
        self.setMouseTracking(True)

        self._rubber_band = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Rectangle, self
        )
        self._origin: Optional[QtCore.QPoint] = None

    def showEvent(self, event):
        super().showEvent(event)
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.virtualGeometry())
        self.show()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 80))

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        self._origin = event.position().toPoint()
        self._rubber_band.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
        self._rubber_band.show()

    def mouseMoveEvent(self, event):
        if not self._origin:
            return
        current = event.position().toPoint()
        rect = QtCore.QRect(self._origin, current).normalized()
        self._rubber_band.setGeometry(rect)

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or not self._origin:
            return
        current = event.position().toPoint()
        rect = QtCore.QRect(self._origin, current).normalized()
        self._rubber_band.hide()
        self._origin = None
        if rect.width() > 0 and rect.height() > 0:
            global_rect = QtCore.QRect(
                rect.topLeft() + self.geometry().topLeft(), rect.size()
            )
            region = self._to_physical_region(global_rect)
            self.region_selected.emit(region)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)

    def _to_physical_region(self, rect: QtCore.QRect) -> Tuple[int, int, int, int]:
        win_region = _logical_to_physical_region(rect, int(self.winId()))
        if win_region:
            return win_region
        screen = _resolve_screen_for_rect(rect)
        if not screen:
            return rect.x(), rect.y(), rect.width(), rect.height()
        screen_geom = screen.geometry()
        screen_size = screen_geom.size()
        if screen_size.width() <= 0 or screen_size.height() <= 0:
            return rect.x(), rect.y(), rect.width(), rect.height()
        physical = _match_physical_rect_for_screen(screen)
        if physical:
            left, top, width, height = physical
            scale_x = width / max(1, screen_size.width())
            scale_y = height / max(1, screen_size.height())
            rel_x = rect.x() - screen_geom.x()
            rel_y = rect.y() - screen_geom.y()
            phys_x = left + int(round(rel_x * scale_x))
            phys_y = top + int(round(rel_y * scale_y))
            phys_w = int(round(rect.width() * scale_x))
            phys_h = int(round(rect.height() * scale_y))
            return phys_x, phys_y, phys_w, phys_h
        dpr = float(getattr(screen, "devicePixelRatio", lambda: 1.0)() or 1.0)
        rel_x = rect.x() - screen_geom.x()
        rel_y = rect.y() - screen_geom.y()
        phys_x = int(round(screen_geom.x() * dpr + rel_x * dpr))
        phys_y = int(round(screen_geom.y() * dpr + rel_y * dpr))
        phys_w = int(round(rect.width() * dpr))
        phys_h = int(round(rect.height() * dpr))
        return phys_x, phys_y, phys_w, phys_h


def _list_physical_monitors() -> List[Tuple[str, int, int, int, int]]:
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        import ctypes.wintypes
    except Exception:
        return []

    user32 = ctypes.windll.user32

    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szDevice", ctypes.wintypes.WCHAR * 32),
        ]

    monitors: List[Tuple[str, int, int, int, int]] = []

    def _callback(hmonitor, hdc, lprc, lparam):
        info = MONITORINFOEX()
        info.cbSize = ctypes.sizeof(MONITORINFOEX)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            monitors.append(
                (info.szDevice, rect.left, rect.top, rect.right, rect.bottom)
            )
        return 1

    cb = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.wintypes.LPARAM,
    )(_callback)

    if not user32.EnumDisplayMonitors(0, 0, cb, 0):
        return []
    return monitors


def _get_monitor_physical_rect(name: str) -> Optional[Tuple[int, int, int, int]]:
    monitors = _list_physical_monitors()
    if not monitors:
        return None
    for dev, left, top, right, bottom in monitors:
        if dev == name:
            return left, top, right - left, bottom - top
    if len(monitors) == 1:
        _, left, top, right, bottom = monitors[0]
        return left, top, right - left, bottom - top
    return None


def _match_physical_rect_for_screen(
    screen: QtGui.QScreen,
) -> Optional[Tuple[int, int, int, int]]:
    physical = _get_monitor_physical_rect(screen.name())
    if physical:
        return physical
    monitors = _list_physical_monitors()
    if not monitors:
        return None
    geom = screen.geometry()
    dpr = float(getattr(screen, "devicePixelRatio", lambda: 1.0)() or 1.0)
    expect_left = int(round(geom.x() * dpr))
    expect_top = int(round(geom.y() * dpr))
    expect_w = int(round(geom.width() * dpr))
    expect_h = int(round(geom.height() * dpr))
    best = None
    best_score = None
    for _, left, top, right, bottom in monitors:
        width = right - left
        height = bottom - top
        score = (
            abs(left - expect_left)
            + abs(top - expect_top)
            + abs(width - expect_w)
            + abs(height - expect_h)
        )
        if best_score is None or score < best_score:
            best_score = score
            best = (left, top, width, height)
    return best


def _resolve_screen_for_rect(rect: QtCore.QRect) -> Optional[QtGui.QScreen]:
    screens = QtGui.QGuiApplication.screens()
    if not screens:
        return None
    cx = rect.center().x()
    cy = rect.center().y()
    logical_pick = None
    for screen in screens:
        if screen.geometry().contains(QtCore.QPoint(cx, cy)):
            logical_pick = screen
            break
    physical_pick = None
    for screen in screens:
        physical = _match_physical_rect_for_screen(screen)
        if not physical:
            continue
        left, top, width, height = physical
        if left <= cx < left + width and top <= cy < top + height:
            physical_pick = screen
            break
    return physical_pick or logical_pick


def _logical_to_physical_region(
    rect: QtCore.QRect, hwnd: int
) -> Optional[Tuple[int, int, int, int]]:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes
    except Exception:
        return None

    user32 = ctypes.windll.user32
    func = getattr(user32, "LogicalToPhysicalPointForPerMonitorDPI", None)
    if not func:
        return None

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.wintypes.LONG), ("y", ctypes.wintypes.LONG)]

    tl = rect.topLeft()
    br = rect.bottomRight()
    p1 = POINT(tl.x(), tl.y())
    p2 = POINT(br.x(), br.y())
    if not func(hwnd, ctypes.byref(p1)):
        return None
    if not func(hwnd, ctypes.byref(p2)):
        return None
    left = int(p1.x)
    top = int(p1.y)
    right = int(p2.x)
    bottom = int(p2.y)
    width = max(1, right - left + 1)
    height = max(1, bottom - top + 1)
    return left, top, width, height


def select_region() -> Optional[Tuple[int, int, int, int]]:
    app = QtWidgets.QApplication.instance()
    owns_app = False
    if not app:
        app = QtWidgets.QApplication([])
        owns_app = True

    selector = RegionSelector()
    result = {"region": None}

    def on_selected(region):
        result["region"] = region

    selector.region_selected.connect(on_selected)
    loop = QtCore.QEventLoop()
    selector.finished.connect(loop.quit)
    selector.show()
    loop.exec()

    if owns_app:
        app.processEvents()
    return result["region"]


def physical_to_logical_region(
    region: Optional[Tuple[int, int, int, int]],
) -> Optional[Tuple[int, int, int, int]]:
    if not region:
        return None
    x, y, w, h = region
    cx = x + w // 2
    cy = y + h // 2
    for screen in QtGui.QGuiApplication.screens():
        physical = _match_physical_rect_for_screen(screen)
        geom = screen.geometry()
        if physical:
            left, top, pw, ph = physical
            if left <= cx < left + pw and top <= cy < top + ph:
                scale_x = pw / max(1, geom.width())
                scale_y = ph / max(1, geom.height())
                rel_x = x - left
                rel_y = y - top
                log_x = geom.x() + int(round(rel_x / scale_x))
                log_y = geom.y() + int(round(rel_y / scale_y))
                log_w = int(round(w / scale_x))
                log_h = int(round(h / scale_y))
                return log_x, log_y, log_w, log_h
        dpr = float(getattr(screen, "devicePixelRatio", lambda: 1.0)() or 1.0)
        left = int(round(geom.x() * dpr))
        top = int(round(geom.y() * dpr))
        pw = int(round(geom.width() * dpr))
        ph = int(round(geom.height() * dpr))
        if left <= cx < left + pw and top <= cy < top + ph:
            rel_x = x - left
            rel_y = y - top
            log_x = geom.x() + int(round(rel_x / dpr))
            log_y = geom.y() + int(round(rel_y / dpr))
            log_w = int(round(w / dpr))
            log_h = int(round(h / dpr))
            return log_x, log_y, log_w, log_h
    return x, y, w, h


def get_monitor_scale_for_region(
    region: Optional[Tuple[int, int, int, int]],
) -> Tuple[float, float]:
    if not region:
        return 1.0, 1.0
    x, y, w, h = region
    cx = x + w // 2
    cy = y + h // 2
    for screen in QtGui.QGuiApplication.screens():
        physical = _match_physical_rect_for_screen(screen)
        geom = screen.geometry()
        if physical:
            left, top, pw, ph = physical
            if left <= cx < left + pw and top <= cy < top + ph:
                scale_x = pw / max(1, geom.width())
                scale_y = ph / max(1, geom.height())
                return scale_x, scale_y
        dpr = float(getattr(screen, "devicePixelRatio", lambda: 1.0)() or 1.0)
        left = int(round(geom.x() * dpr))
        top = int(round(geom.y() * dpr))
        pw = int(round(geom.width() * dpr))
        ph = int(round(geom.height() * dpr))
        if left <= cx < left + pw and top <= cy < top + ph:
            return dpr, dpr
    return 1.0, 1.0


def get_screen_debug_info() -> List[Dict[str, object]]:
    info = []
    for screen in QtGui.QGuiApplication.screens():
        geom = screen.geometry()
        dpr = float(getattr(screen, "devicePixelRatio", lambda: 1.0)() or 1.0)
        physical = _get_monitor_physical_rect(screen.name())
        matched = _match_physical_rect_for_screen(screen)
        info.append(
            {
                "name": screen.name(),
                "geometry": (geom.x(), geom.y(), geom.width(), geom.height()),
                "device_pixel_ratio": dpr,
                "physical_rect": physical,
                "matched_physical_rect": matched,
            }
        )
    return info


if __name__ == "__main__":
    region = select_region()
    print(region)
