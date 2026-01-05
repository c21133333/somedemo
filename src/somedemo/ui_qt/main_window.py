import ctypes
import ctypes.wintypes
import os
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

from somedemo.recorder_core import RecorderCore


def _resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
    return os.path.join(base_dir, filename)


class UiSignals(QtCore.QObject):
    log_signal = QtCore.Signal(str)
    event_signal = QtCore.Signal(dict)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("鼠标录制工具 (Qt)")
        self.resize(920, 620)
        self.setFont(QtGui.QFont("Microsoft YaHei UI", 10))
        icon_path = _resource_path(os.path.join("assets", "icons", "cat.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self._signals = UiSignals()
        self._signals.log_signal.connect(self._append_log)
        self._signals.event_signal.connect(self._add_event_row)

        self.core = RecorderCore(
            log_callback=self._signals.log_signal.emit,
            event_callback=self._signals.event_signal.emit,
        )

        self._last_dt = None

        central = QtWidgets.QWidget(self)
        central.setObjectName("root")
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Status bar
        status_layout = QtWidgets.QHBoxLayout()
        status_title = QtWidgets.QLabel("当前状态:")
        self.status_label = QtWidgets.QLabel("就绪")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)
        main_layout.addLayout(status_layout)

        # Top controls
        controls = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("开始录制 (Ctrl+S)")
        self.stop_btn = QtWidgets.QPushButton("停止 (Ctrl+E)")
        self.play_btn = QtWidgets.QPushButton("回放 (Ctrl+P)")
        self.open_btn = QtWidgets.QPushButton("打开脚本 (Ctrl+O)")
        self.save_btn = QtWidgets.QPushButton("保存脚本 (Ctrl+Shift+S)")

        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.open_btn)
        controls.addWidget(self.save_btn)
        controls.addStretch(1)
        main_layout.addLayout(controls)

        loop_layout = QtWidgets.QHBoxLayout()
        loop_label = QtWidgets.QLabel("回放次数:")
        self.loop_spin = QtWidgets.QSpinBox()
        self.loop_spin.setRange(1, 9999)
        self.loop_spin.setValue(1)
        self.loop_infinite_chk = QtWidgets.QCheckBox("无限循环")
        loop_layout.addWidget(loop_label)
        loop_layout.addWidget(self.loop_spin)
        loop_layout.addWidget(self.loop_infinite_chk)
        loop_layout.addStretch(1)
        main_layout.addLayout(loop_layout)

        # Event table
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["时间(秒)", "类型", "X", "Y", "按钮", "按下", "延迟(秒)"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table, 1)

        # Log output
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("日志...")
        self.log_box.setMaximumBlockCount(5000)
        main_layout.addWidget(self.log_box, 0)

        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn.clicked.connect(self._stop_action)
        self.play_btn.clicked.connect(self._play)
        self.open_btn.clicked.connect(self._open_script)
        self.save_btn.clicked.connect(self._save_script)

        self._bind_shortcuts()
        self._apply_theme()
        self._update_ui_state()
        self._register_hotkeys()

        self._ui_timer = QtCore.QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._update_ui_state)
        self._ui_timer.start()

    def _register_hotkeys(self):
        self._unregister_hotkeys()
        self._hotkey_map = {}
        self._hotkey_registered = []

        user32 = ctypes.windll.user32
        self._user32 = user32
        hwnd = int(self.winId())

        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_NOREPEAT = 0x4000
        VK_S = 0x53
        VK_E = 0x45
        VK_P = 0x50
        VK_T = 0x54
        VK_O = 0x4F

        def bind_hotkey(hotkey_id, modifiers, vk, callback):
            ok = user32.RegisterHotKey(hwnd, hotkey_id, modifiers | MOD_NOREPEAT, vk)
            if ok:
                self._hotkey_map[hotkey_id] = callback
                self._hotkey_registered.append(hotkey_id)
            else:
                self._append_log(f"快捷键注册失败: id={hotkey_id} (可能被占用)")

        bind_hotkey(1, MOD_CONTROL, VK_S, self._start_recording)
        bind_hotkey(2, MOD_CONTROL, VK_E, self._stop_action)
        bind_hotkey(3, MOD_CONTROL, VK_P, self._play)
        bind_hotkey(4, MOD_CONTROL, VK_T, self._stop_action)
        bind_hotkey(5, MOD_CONTROL, VK_O, self._open_script)
        bind_hotkey(6, MOD_CONTROL | MOD_SHIFT, VK_S, self._save_script)

    def _unregister_hotkeys(self):
        if not getattr(self, "_user32", None):
            return
        for hotkey_id in getattr(self, "_hotkey_registered", []):
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._hotkey_registered = []

    def nativeEvent(self, eventType, message):
        if eventType in ("windows_generic_MSG", "windows_dispatcher_MSG"):
            addr = int(message)
            msg = ctypes.wintypes.MSG.from_address(addr)
            WM_HOTKEY = 0x0312
            if msg.message == WM_HOTKEY:
                hotkey_id = int(msg.wParam)
                callback = self._hotkey_map.get(hotkey_id)
                if callback:
                    QtCore.QTimer.singleShot(0, callback)
                    return True, 0
        return super().nativeEvent(eventType, message)

    def _apply_theme(self):
        self.setStyleSheet(
            """
            QWidget#root {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #141b2f, stop:0.45 #1a2340, stop:1 #13203a);
                color: #f0f6ff;
            }
            QLabel {
                color: #dde6f3;
            }
            QLabel#statusLabel {
                padding: 4px 10px;
                border-radius: 10px;
                background: rgba(56, 139, 253, 0.2);
                border: 1px solid rgba(120, 180, 255, 0.45);
                color: #58a6ff;
                font-weight: 600;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb, stop:1 #06b6d4);
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #22d3ee);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1d4ed8, stop:1 #0891b2);
            }
            QPushButton:disabled {
                background: #30363d;
                color: #8b949e;
            }
            QSpinBox, QCheckBox {
                color: #c9d1d9;
            }
            QSpinBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(120, 180, 255, 0.35);
                border-radius: 6px;
                padding: 2px 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid rgba(88, 166, 255, 0.35);
                background: transparent;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background: #22d3ee;
                border: 1px solid #22d3ee;
                border-radius: 4px;
            }
            QTableWidget {
                background: rgba(22, 30, 54, 0.85);
                border: 1px solid rgba(120, 180, 255, 0.25);
                border-radius: 10px;
                gridline-color: rgba(120, 180, 255, 0.16);
                selection-background-color: rgba(96, 165, 250, 0.35);
                selection-color: #f0f6ff;
            }
            QHeaderView::section {
                background: rgba(59, 130, 246, 0.25);
                color: #f0f6ff;
                padding: 6px;
                border: none;
            }
            QTableCornerButton::section {
                background: rgba(59, 130, 246, 0.25);
                border: none;
            }
            QPlainTextEdit {
                background: rgba(18, 26, 48, 0.85);
                border: 1px solid rgba(120, 180, 255, 0.25);
                border-radius: 10px;
                color: #c9d6ea;
                padding: 8px;
            }
            """
        )

    def _bind_shortcuts(self):
        self.start_btn.setShortcut(QtGui.QKeySequence("Ctrl+S"))
        self.stop_btn.setShortcut(QtGui.QKeySequence("Ctrl+E"))
        self.play_btn.setShortcut(QtGui.QKeySequence("Ctrl+P"))
        self.open_btn.setShortcut(QtGui.QKeySequence("Ctrl+O"))
        self.save_btn.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))

        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+T"), self, activated=self._stop_action)

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            "padding: 4px 10px;"
            "border-radius: 10px;"
            "background: rgba(31, 111, 235, 0.15);"
            "border: 1px solid rgba(88, 166, 255, 0.35);"
            f"color: {color};"
            "font-weight: 600;"
        )

    def _update_ui_state(self):
        if self.core.recording:
            self._set_status("录制中", "#d1242f")
        elif self.core.playing:
            self._set_status("回放中", "#0969da")
        else:
            self._set_status("就绪", "#1a7f37")

        can_stop = self.core.recording or self.core.playing
        self.stop_btn.setEnabled(can_stop)
        self.start_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.play_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.open_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.save_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.loop_spin.setEnabled(not self.core.recording and not self.core.playing)
        self.loop_infinite_chk.setEnabled(not self.core.recording and not self.core.playing)

    def _append_log(self, message):
        ts = time.strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{ts}] {message}")

    def _set_row_item(self, row, col, value):
        item = QtWidgets.QTableWidgetItem(value)
        self.table.setItem(row, col, item)

    def _add_event_row(self, event):
        row = self.table.rowCount()
        self.table.insertRow(row)

        dt = event.get("dt", 0)
        delay = 0
        if self._last_dt is not None:
            delay = max(0, dt - self._last_dt)
        self._last_dt = dt

        self._set_row_item(row, 0, f"{dt:.4f}")
        self._set_row_item(row, 1, str(event.get("type", "")))
        self._set_row_item(row, 2, str(event.get("x", "")))
        self._set_row_item(row, 3, str(event.get("y", "")))
        self._set_row_item(row, 4, str(event.get("button", "")))
        self._set_row_item(row, 5, str(event.get("pressed", "")))
        self._set_row_item(row, 6, f"{delay:.4f}")

        self.table.scrollToBottom()

    def _populate_table(self, events):
        self.table.setRowCount(0)
        self._last_dt = None
        for event in events:
            self._add_event_row(event)

    def _start_recording(self):
        self._populate_table([])
        self.core.start_recording()
        self._update_ui_state()

    def _stop_action(self):
        if self.core.recording:
            self.core.stop_recording()
            self._populate_table(self.core.get_events_copy())
        elif self.core.playing:
            self.core.stop_playback()
        self._update_ui_state()

    def _play(self):
        self.core.play_trajectory(
            loop_count=self.loop_spin.value(),
            loop_infinite=self.loop_infinite_chk.isChecked(),
        )
        self._update_ui_state()

    def _open_script(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "打开脚本",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        if self.core.open_script(path):
            self._populate_table(self.core.get_events_copy())
        self._update_ui_state()

    def _save_script(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "保存脚本",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        self.core.save_script(path)
        self._update_ui_state()

    def closeEvent(self, event):
        self._unregister_hotkeys()
        super().closeEvent(event)


def run():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
