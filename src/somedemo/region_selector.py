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
            self.region_selected.emit(
                (rect.x(), rect.y(), rect.width(), rect.height())
            )
        self.close()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)


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
