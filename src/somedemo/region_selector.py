import sys
from typing import Optional, Tuple

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
        self.showFullScreen()

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
            region = self._to_physical_region(rect)
            self.region_selected.emit(region)
        self.close()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)

    def _to_physical_region(self, rect: QtCore.QRect) -> Tuple[int, int, int, int]:
        screen = self.screen()
        if not screen:
            return rect.x(), rect.y(), rect.width(), rect.height()
        screen_size = screen.size()
        if screen_size.width() <= 0 or screen_size.height() <= 0:
            return rect.x(), rect.y(), rect.width(), rect.height()
        physical = _get_monitor_physical_rect(screen.name())
        if not physical:
            return rect.x(), rect.y(), rect.width(), rect.height()
        left, top, width, height = physical
        scale_x = width / max(1, screen_size.width())
        scale_y = height / max(1, screen_size.height())
        phys_x = left + int(round(rect.x() * scale_x))
        phys_y = top + int(round(rect.y() * scale_y))
        phys_w = int(round(rect.width() * scale_x))
        phys_h = int(round(rect.height() * scale_y))
        return phys_x, phys_y, phys_w, phys_h


def _get_monitor_physical_rect(name: str) -> Optional[Tuple[int, int, int, int]]:
    if not name or sys.platform != "win32":
        return None
    try:
        import ctypes
        import ctypes.wintypes
    except Exception:
        return None

    user32 = ctypes.windll.user32

    class MONITORINFOEX(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("szDevice", ctypes.wintypes.WCHAR * 32),
        ]

    monitors = []

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
        return None

    for dev, left, top, right, bottom in monitors:
        if dev == name:
            return left, top, right - left, bottom - top
    return None


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


if __name__ == "__main__":
    region = select_region()
    print(region)
