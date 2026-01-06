# -*- coding: utf-8 -*-
import ctypes
import ctypes.wintypes
import os
import sys
import time
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from somedemo.action_executor import execute, execute_match
from somedemo.recorder_core import RecorderCore
from somedemo.region_selector import select_region
from somedemo.scene_matcher import load_scene_rules, match_scene
from somedemo.screen_capture import ScreenCapture
from somedemo.template_matcher import TemplateMatcher


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
        self.setWindowTitle("\u4e3a\u4e86\u4e16\u754c\u548c\u5e73")
        self.resize(920, 620)
        self.setFont(QtGui.QFont("Microsoft YaHei UI", 10))
        icon_path = _resource_path(os.path.join("assets", "icons", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        self._signals = UiSignals()
        self._signals.log_signal.connect(self._append_log)
        self._signals.event_signal.connect(self._add_event_row)

        self.core = RecorderCore(
            log_callback=self._signals.log_signal.emit,
            event_callback=self._signals.event_signal.emit,
        )

        # CHANGE: automation state
        self._auto_region = None
        self._auto_capture = None
        self._auto_running = False
        self._auto_paused = False
        self._scene_rules = []
        self._scene_rules_path = _resource_path(
            os.path.join("assets", "scenes", "sample_rules.json")
        )
        self._scene_rules_base = _resource_path("")
        # CHANGE: template matching state
        self._template_matcher = None
        self._template_paths = []
        self._last_scene = None
        self._last_scene_ts = 0.0
        self._action_lock = threading.Lock()
        self._action_inflight = False
        self._capture_debug_logged = False

        self._last_dt = None

        central = QtWidgets.QWidget(self)
        central.setObjectName("root")
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # Status bar
        status_layout = QtWidgets.QHBoxLayout()
        status_title = QtWidgets.QLabel("\u5f53\u524d\u72b6\u6001")
        self.status_label = QtWidgets.QLabel("\u5c31\u7eea")
        self.status_label.setObjectName("statusLabel")
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)
        main_layout.addLayout(status_layout)

        # CHANGE: mode switch
        mode_layout = QtWidgets.QHBoxLayout()
        mode_label = QtWidgets.QLabel("\u529f\u80fd\u6a21\u5f0f:")
        self.mode_monitor_btn = QtWidgets.QPushButton("\u5c4f\u5e55\u76d1\u63a7")
        self.mode_recorder_btn = QtWidgets.QPushButton("\u9f20\u6807\u5f55\u5236")
        self.mode_monitor_btn.setCheckable(True)
        self.mode_recorder_btn.setCheckable(True)
        self.mode_monitor_btn.setChecked(True)
        self.mode_recorder_btn.setChecked(False)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_monitor_btn)
        mode_layout.addWidget(self.mode_recorder_btn)
        mode_layout.addStretch(1)
        main_layout.addLayout(mode_layout)

        self.mode_stack = QtWidgets.QStackedWidget()

        # Module: recorder controls
        recorder_group = QtWidgets.QGroupBox("\u9f20\u6807\u5f55\u5236")
        recorder_layout = QtWidgets.QVBoxLayout(recorder_group)
        controls = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("\u5f00\u59cb\u5f55\u5236 (Ctrl+S)")
        self.stop_btn = QtWidgets.QPushButton("\u505c\u6b62 (Ctrl+E)")
        self.play_btn = QtWidgets.QPushButton("\u56de\u653e (Ctrl+P)")
        self.open_btn = QtWidgets.QPushButton("\u6253\u5f00\u811a\u672c (Ctrl+O)")
        self.save_btn = QtWidgets.QPushButton("\u4fdd\u5b58\u811a\u672c (Ctrl+Shift+S)")

        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.open_btn)
        controls.addWidget(self.save_btn)
        controls.addStretch(1)
        recorder_layout.addLayout(controls)

        loop_layout = QtWidgets.QHBoxLayout()
        loop_label = QtWidgets.QLabel("\u56de\u653e\u6b21\u6570:")
        self.loop_spin = QtWidgets.QSpinBox()
        self.loop_spin.setRange(1, 9999)
        self.loop_spin.setValue(1)
        self.loop_infinite_chk = QtWidgets.QCheckBox("\u65e0\u9650\u5faa\u73af")
        loop_layout.addWidget(loop_label)
        loop_layout.addWidget(self.loop_spin)
        loop_layout.addWidget(self.loop_infinite_chk)
        loop_layout.addStretch(1)
        recorder_layout.addLayout(loop_layout)
        recorder_help_title = QtWidgets.QLabel("\u5f55\u5236\u8bf4\u660e:")
        recorder_help_text = QtWidgets.QLabel(
            "\u76d1\u542c\u5168\u5c40\u9f20\u6807\u5e76\u8bb0\u5f55\u8f68\u8ff9\u3002\u5efa\u8bae\u5f00\u59cb\u540e\u518d\u64cd\u4f5c\uff0c\u7ed3\u675f\u540e\u53ef\u56de\u653e\u6216\u4fdd\u5b58\u3002"
        )
        recorder_help_text.setWordWrap(True)
        recorder_shortcuts = QtWidgets.QLabel(
            "\u5feb\u6377\u952e: Ctrl+S \u5f00\u59cb\uff0cCtrl+E \u505c\u6b62\uff0cCtrl+P \u56de\u653e"
        )
        recorder_shortcuts.setWordWrap(True)
        recorder_layout.addWidget(recorder_help_title)
        recorder_layout.addWidget(recorder_help_text)
        recorder_layout.addWidget(recorder_shortcuts)
        recorder_layout.addStretch(1)
        recorder_page = QtWidgets.QWidget()
        recorder_page_layout = QtWidgets.QVBoxLayout(recorder_page)
        recorder_page_layout.setContentsMargins(0, 0, 0, 0)
        recorder_page_layout.addWidget(recorder_group)
        # CHANGE: recorder table (only in recorder mode)
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["\u65f6\u95f4(\u79d2)", "\u7c7b\u578b", "X", "Y", "\u6309\u94ae", "\u6309\u4e0b", "\u5ef6\u8fdf(\u79d2)"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setMinimumHeight(180)
        recorder_page_layout.addWidget(self.table)
        self.mode_stack.addWidget(recorder_page)

        # CHANGE: module: screen monitor controls
        monitor_group = QtWidgets.QGroupBox("\u5c4f\u5e55\u76d1\u63a7")
        monitor_layout = QtWidgets.QVBoxLayout(monitor_group)
        auto_layout = QtWidgets.QHBoxLayout()
        auto_label = QtWidgets.QLabel("\u81ea\u52a8\u6267\u884c:")
        self.auto_region_btn = QtWidgets.QPushButton("\u9009\u62e9\u76d1\u63a7\u533a\u57df")
        self.auto_start_btn = QtWidgets.QPushButton("\u5f00\u59cb (Ctrl+Alt+T)")
        self.auto_stop_btn = QtWidgets.QPushButton("\u505c\u6b62 (Ctrl+Alt+Y)")
        auto_layout.addWidget(auto_label)
        auto_layout.addWidget(self.auto_region_btn)
        auto_layout.addWidget(self.auto_start_btn)
        auto_layout.addWidget(self.auto_stop_btn)
        auto_layout.addStretch(1)
        monitor_layout.addLayout(auto_layout)

        fps_layout = QtWidgets.QHBoxLayout()
        fps_label = QtWidgets.QLabel("\u5904\u7406\u5e27\u7387(fps):")
        self.monitor_fps_spin = QtWidgets.QSpinBox()
        self.monitor_fps_spin.setRange(1, 30)
        self.monitor_fps_spin.setValue(2)
        fps_layout.addWidget(fps_label)
        fps_layout.addWidget(self.monitor_fps_spin)
        fps_layout.addStretch(1)
        monitor_layout.addLayout(fps_layout)

        # CHANGE: template config (screen monitor only)
        self.template_group = QtWidgets.QGroupBox("\u6a21\u677f\u56fe\u7247")
        self.template_group.setCheckable(False)
        template_group_layout = QtWidgets.QVBoxLayout(self.template_group)

        self.template_thumb_list = QtWidgets.QListWidget()
        self.template_thumb_list.setViewMode(QtWidgets.QListView.IconMode)
        self.template_thumb_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.template_thumb_list.setMovement(QtWidgets.QListView.Static)
        self.template_thumb_list.setIconSize(QtCore.QSize(72, 72))
        self.template_thumb_list.setSpacing(8)
        self.template_thumb_list.setMinimumHeight(120)
        self.template_thumb_list.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid rgba(120, 180, 255, 0.25); border-radius: 8px; }"
            "QListWidget::item { background: transparent; }"
        )
        self.template_thumb_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.template_thumb_list.installEventFilter(self)

        self.template_add_btn = QtWidgets.QToolButton(self.template_thumb_list)
        self.template_add_btn.setText("+")
        self.template_add_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.template_add_btn.setFixedSize(40, 40)
        self.template_add_btn.setStyleSheet(
            "QToolButton { background: #22c55e; color: white; border-radius: 20px; font-weight: 700; font-size: 14pt; }"
            "QToolButton:hover { background: #16a34a; }"
        )
        self.template_add_btn.raise_()
        self._reposition_add_button()

        template_group_layout.addWidget(self.template_thumb_list)

        monitor_layout.addWidget(self.template_group)

        template_threshold_layout = QtWidgets.QHBoxLayout()
        threshold_label = QtWidgets.QLabel("\u6a21\u677f\u5339\u914d\u9608\u503c:")
        self.template_threshold_spin = QtWidgets.QDoubleSpinBox()
        self.template_threshold_spin.setRange(0.7, 0.95)
        self.template_threshold_spin.setSingleStep(0.01)
        self.template_threshold_spin.setValue(0.85)
        template_threshold_layout.addWidget(threshold_label)
        template_threshold_layout.addWidget(self.template_threshold_spin)
        template_threshold_layout.addStretch(1)
        monitor_layout.addLayout(template_threshold_layout)

        template_click_layout = QtWidgets.QHBoxLayout()
        click_count_label = QtWidgets.QLabel("\u70b9\u51fb\u6b21\u6570:")
        self.template_click_count = QtWidgets.QSpinBox()
        self.template_click_count.setRange(1, 20)
        self.template_click_count.setValue(1)
        click_interval_label = QtWidgets.QLabel("\u95f4\u9694(ms):")
        self.template_click_interval = QtWidgets.QSpinBox()
        self.template_click_interval.setRange(0, 5000)
        self.template_click_interval.setValue(0)
        template_click_layout.addWidget(click_count_label)
        template_click_layout.addWidget(self.template_click_count)
        template_click_layout.addSpacing(12)
        template_click_layout.addWidget(click_interval_label)
        template_click_layout.addWidget(self.template_click_interval)
        template_click_layout.addStretch(1)
        monitor_layout.addLayout(template_click_layout)

        # CHANGE: random offset toggle
        random_layout = QtWidgets.QHBoxLayout()
        self.template_random_offset = QtWidgets.QCheckBox("\u968f\u673a\u504f\u79fb\u70b9\u51fb")
        self.template_random_offset.setChecked(True)
        random_layout.addWidget(self.template_random_offset)
        random_layout.addStretch(1)
        monitor_layout.addLayout(random_layout)
        monitor_page = QtWidgets.QWidget()
        monitor_page_layout = QtWidgets.QVBoxLayout(monitor_page)
        monitor_page_layout.setContentsMargins(0, 0, 0, 0)
        monitor_page_layout.addWidget(monitor_group)
        self.mode_stack.addWidget(monitor_page)

        self.mode_stack.setCurrentIndex(1)
        main_layout.addWidget(self.mode_stack)
        
        # Log output
        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("\u65e5\u5fd7...")
        self.log_box.setMaximumBlockCount(5000)
        main_layout.addWidget(self.log_box, 0)

        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn.clicked.connect(self._stop_action)
        self.play_btn.clicked.connect(self._play)
        self.open_btn.clicked.connect(self._open_script)
        self.save_btn.clicked.connect(self._save_script)
        # CHANGE: automation handlers
        self.auto_region_btn.clicked.connect(self._select_auto_region)
        self.auto_start_btn.clicked.connect(self._toggle_auto_start)
        self.auto_stop_btn.clicked.connect(self._stop_auto)
        # CHANGE: mode switch handlers
        self.mode_monitor_btn.clicked.connect(self._show_monitor_mode)
        self.mode_recorder_btn.clicked.connect(self._show_recorder_mode)
        # CHANGE: template config handler
        self.template_add_btn.clicked.connect(self._select_template_images)
        self.template_thumb_list.customContextMenuRequested.connect(
            self._show_template_menu
        )
        self.template_thumb_list.itemDoubleClicked.connect(
            self._remove_template_item
        )

        self._bind_shortcuts()
        self._apply_theme()
        self._update_ui_state()
        self._register_hotkeys()
        # CHANGE: initialize mode button states
        self._show_monitor_mode()

        self._ui_timer = QtCore.QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._update_ui_state)
        self._ui_timer.start()
        self._reposition_add_button()

    def _register_hotkeys(self):
        self._unregister_hotkeys()
        self._hotkey_map = {}
        self._hotkey_registered = []

        user32 = ctypes.windll.user32
        self._user32 = user32
        hwnd = int(self.winId())

        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_ALT = 0x0001
        MOD_NOREPEAT = 0x4000
        VK_S = 0x53
        VK_E = 0x45
        VK_P = 0x50
        VK_T = 0x54
        VK_O = 0x4F
        VK_Y = 0x59

        def bind_hotkey(hotkey_id, modifiers, vk, callback):
            ok = user32.RegisterHotKey(hwnd, hotkey_id, modifiers | MOD_NOREPEAT, vk)
            if ok:
                self._hotkey_map[hotkey_id] = callback
                self._hotkey_registered.append(hotkey_id)
            else:
                return False
            return True

        failures = 0
        if not bind_hotkey(1, MOD_CONTROL, VK_S, self._start_recording):
            failures += 1
        if not bind_hotkey(2, MOD_CONTROL, VK_E, self._stop_action):
            failures += 1
        if not bind_hotkey(3, MOD_CONTROL, VK_P, self._play):
            failures += 1
        if not bind_hotkey(4, MOD_CONTROL, VK_T, self._stop_action):
            failures += 1
        if not bind_hotkey(5, MOD_CONTROL, VK_O, self._open_script):
            failures += 1
        if not bind_hotkey(6, MOD_CONTROL | MOD_SHIFT, VK_S, self._save_script):
            failures += 1
        if failures == 6:
            self._hotkey_map = {}
            self._hotkey_registered = []
            self._append_log(
                "\u5168\u5c40\u5feb\u6377\u952e\u6ce8\u518c\u5931\u8d25\uff0c\u8bf7\u4f7f\u7528\u7a97\u53e3\u5185\u5feb\u6377\u952e\u3002"
            )
        if not bind_hotkey(7, MOD_CONTROL | MOD_ALT, VK_T, self._toggle_auto_start):
            self._append_log(
                "\u5168\u5c40\u5feb\u6377\u952e Ctrl+Alt+T \u6ce8\u518c\u5931\u8d25"
            )
        if not bind_hotkey(8, MOD_CONTROL | MOD_ALT, VK_Y, self._stop_auto):
            self._append_log(
                "\u5168\u5c40\u5feb\u6377\u952e Ctrl+Alt+Y \u6ce8\u518c\u5931\u8d25"
            )

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
            QPushButton[modeActive="true"] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #22c55e, stop:1 #16a34a);
                color: #f0fff4;
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
            QGroupBox::title {
                color: #f0f6ff;
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
        # CHANGE: automation shortcuts
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Alt+T"), self, activated=self._toggle_auto_start)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Alt+Y"), self, activated=self._stop_auto)

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
            self._set_status("\u5f55\u5236\u4e2d", "#d1242f")
        elif self.core.playing:
            self._set_status("\u56de\u653e\u4e2d", "#0969da")
        else:
            self._set_status("\u5c31\u7eea", "#1a7f37")

        can_stop = self.core.recording or self.core.playing
        self.stop_btn.setEnabled(can_stop)
        self.start_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.play_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.open_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.save_btn.setEnabled(not self.core.recording and not self.core.playing)
        self.loop_spin.setEnabled(not self.core.recording and not self.core.playing)
        self.loop_infinite_chk.setEnabled(not self.core.recording and not self.core.playing)
        # CHANGE: automation button states
        self.auto_start_btn.setEnabled(True)
        self.auto_stop_btn.setEnabled(self._auto_running)
        if not self._auto_running:
            self.auto_start_btn.setText("\u5f00\u59cb (Ctrl+Alt+T)")
        elif self._auto_paused:
            self.auto_start_btn.setText("\u7ee7\u7eed (Ctrl+Alt+T)")
        else:
            self.auto_start_btn.setText("\u6682\u505c (Ctrl+Alt+T)")
        if self._auto_running:
            if self._auto_paused:
                self._set_status("\u76d1\u63a7\u5df2\u6682\u505c", "#d29922")
            else:
                self._set_status("\u76d1\u63a7\u4e2d", "#2f81f7")
        else:
            if not self.core.recording and not self.core.playing:
                self._set_status("\u5c31\u7eea", "#1a7f37")
        # CHANGE: disable template controls while running
        can_edit_templates = not self._auto_running
        self.template_add_btn.setEnabled(can_edit_templates)
        self.template_threshold_spin.setEnabled(can_edit_templates)
        self.template_click_count.setEnabled(can_edit_templates)
        self.template_click_interval.setEnabled(can_edit_templates)
        self.template_random_offset.setEnabled(can_edit_templates)
        self.monitor_fps_spin.setEnabled(can_edit_templates)
        self.template_thumb_list.setEnabled(can_edit_templates)

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
            "\u6253\u5f00\u811a\u672c",
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
            "\u4fdd\u5b58\u811a\u672c",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        self.core.save_script(path)
        self._update_ui_state()

    # CHANGE: mode switching
    def _show_monitor_mode(self):
        self.mode_monitor_btn.setChecked(True)
        self.mode_recorder_btn.setChecked(False)
        self.mode_monitor_btn.setEnabled(True)
        self.mode_recorder_btn.setEnabled(True)
        self.mode_monitor_btn.setProperty("modeActive", True)
        self.mode_recorder_btn.setProperty("modeActive", False)
        self.mode_monitor_btn.style().unpolish(self.mode_monitor_btn)
        self.mode_monitor_btn.style().polish(self.mode_monitor_btn)
        self.mode_recorder_btn.style().unpolish(self.mode_recorder_btn)
        self.mode_recorder_btn.style().polish(self.mode_recorder_btn)
        self.mode_stack.setCurrentIndex(1)

    def _show_recorder_mode(self):
        self.mode_monitor_btn.setChecked(False)
        self.mode_recorder_btn.setChecked(True)
        self.mode_monitor_btn.setEnabled(True)
        self.mode_recorder_btn.setEnabled(True)
        self.mode_monitor_btn.setProperty("modeActive", False)
        self.mode_recorder_btn.setProperty("modeActive", True)
        self.mode_monitor_btn.style().unpolish(self.mode_monitor_btn)
        self.mode_monitor_btn.style().polish(self.mode_monitor_btn)
        self.mode_recorder_btn.style().unpolish(self.mode_recorder_btn)
        self.mode_recorder_btn.style().polish(self.mode_recorder_btn)
        self.mode_stack.setCurrentIndex(0)

    # CHANGE: automation flow
    def _select_auto_region(self):
        region = select_region()
        if region:
            self._auto_region = region
            self._signals.log_signal.emit(f"\u81ea\u52a8\u76d1\u63a7\u533a\u57df: {region}")

    def _load_scene_rules(self):
        if not os.path.exists(self._scene_rules_path):
            self._signals.log_signal.emit("\u6ca1\u6709\u627e\u5230\u573a\u666f\u89c4\u5219\u914d\u7f6e\u3002")
            return False
        try:
            self._scene_rules = load_scene_rules(self._scene_rules_path)
        except Exception as exc:
            self._signals.log_signal.emit(
                f"\u573a\u666f\u89c4\u5219\u8bfb\u53d6\u5931\u8d25: {exc}"
            )
            return False
        return True

    # CHANGE: template rules
    def _load_template_matcher(self):
        if not self._template_paths:
            self._signals.log_signal.emit("\u8bf7\u5148\u9009\u62e9\u6a21\u677f\u56fe\u7247\u3002")
            return False
        threshold = float(self.template_threshold_spin.value())
        self._template_matcher = TemplateMatcher.load_from_paths(
            self._template_paths, threshold=threshold
        )
        summary = self._template_matcher.describe()
        if summary:
            items = ", ".join(
                f"{item['name']}:{item['width']}x{item['height']}" for item in summary
            )
            self._signals.log_signal.emit(f"\u6a21\u677f\u5c3a\u5bf8: {items}")
        return True

    def _select_template_images(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "\u9009\u62e9\u6a21\u677f\u56fe\u7247",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*)",
        )
        if not paths:
            return
        existing = set(self._template_paths)
        for path in paths:
            if path in existing:
                continue
            pixmap = QtGui.QPixmap(path)
            if pixmap.isNull():
                continue
            icon = QtGui.QIcon(
                pixmap.scaled(
                    72,
                    72,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
            item = QtWidgets.QListWidgetItem(icon, os.path.basename(path))
            item.setToolTip(path)
            item.setData(QtCore.Qt.UserRole, path)
            self.template_thumb_list.addItem(item)
            self._template_paths.append(path)
        self._reposition_add_button()

    def _remove_template_item(self, item):
        path = item.data(QtCore.Qt.UserRole)
        if path in self._template_paths:
            self._template_paths.remove(path)
        row = self.template_thumb_list.row(item)
        self.template_thumb_list.takeItem(row)
        self._reposition_add_button()

    def _show_template_menu(self, point):
        item = self.template_thumb_list.itemAt(point)
        if not item:
            return
        menu = QtWidgets.QMenu(self)
        remove_action = menu.addAction("\u5220\u9664")
        action = menu.exec(self.template_thumb_list.mapToGlobal(point))
        if action == remove_action:
            self._remove_template_item(item)

    def _reposition_add_button(self):
        if not getattr(self, "template_add_btn", None):
            return
        margin = 8
        self.template_add_btn.move(margin, margin)

    def eventFilter(self, obj, event):
        if obj is getattr(self, "template_thumb_list", None) and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
        ):
            self._reposition_add_button()
        return super().eventFilter(obj, event)

    def _start_auto(self):
        if not self._auto_region:
            self._select_auto_region()
        if not self._auto_region:
            return
        scene_ok = self._load_scene_rules()
        template_ok = self._load_template_matcher()
        if not scene_ok and not template_ok:
            return
        self._auto_paused = False
        fps = int(self.monitor_fps_spin.value())
        self._auto_capture = ScreenCapture(
            region=self._auto_region,
            fps=fps,
            frame_callback=self._on_frame,
        )
        self._capture_debug_logged = False
        self._auto_capture.start()
        self._auto_running = True
        self._signals.log_signal.emit("\u81ea\u52a8\u76d1\u63a7\u5df2\u5f00\u59cb\u3002")
        self._update_ui_state()

    def _toggle_auto_start(self):
        if not self._auto_running:
            self._start_auto()
            return
        self._auto_paused = not self._auto_paused
        state = "\u6682\u505c" if self._auto_paused else "\u7ee7\u7eed"
        self._signals.log_signal.emit(f"\u81ea\u52a8\u76d1\u63a7{state}\u3002")
        self._update_ui_state()

    def _stop_auto(self):
        if not self._auto_running:
            return
        if self._auto_capture:
            self._auto_capture.stop()
            self._auto_capture = None
        self._auto_running = False
        self._auto_paused = False
        self._signals.log_signal.emit("\u81ea\u52a8\u76d1\u63a7\u5df2\u505c\u6b62\u3002")
        self._update_ui_state()

    def _on_frame(self, frame):
        if not self._auto_running or self._auto_paused:
            return
        if not self._capture_debug_logged:
            height, width = frame.shape[:2]
            self._signals.log_signal.emit(
                f"\u76d1\u63a7\u5e27\u5c3a\u5bf8: {width}x{height} region={self._auto_region}"
            )
            self._capture_debug_logged = True
        if self._template_matcher:
            match = self._template_matcher.match(frame)
            if match:
                if not match.get("click"):
                    match["click"] = {
                        "type": "left",
                        "click_count": int(self.template_click_count.value()),
                        "interval_ms": int(self.template_click_interval.value()),
                        "random_offset": bool(self.template_random_offset.isChecked()),
                        "delay_ms": 0,
                        "cooldown_ms": 0,
                    }
                self._signals.log_signal.emit(
                    f"\u6a21\u677f\u547d\u4e2d: {match['name']} conf={match['confidence']:.3f}"
                )

                def run_template_action():
                    with self._action_lock:
                        if self._action_inflight:
                            return
                        self._action_inflight = True
                    try:
                        execute_match(match, self._auto_region)
                    finally:
                        with self._action_lock:
                            self._action_inflight = False

                threading.Thread(target=run_template_action, daemon=True).start()
                return
        scene = match_scene(frame, self._scene_rules, base_dir=self._scene_rules_base)
        if not scene:
            return
        rule = next((r for r in self._scene_rules if r.get("name") == scene), None)
        action = rule.get("action") if rule else None
        if not action:
            return
        cooldown = float(rule.get("cooldown", 1.0))
        now = time.time()
        if self._last_scene == scene and now - self._last_scene_ts < cooldown:
            return
        self._last_scene = scene
        self._last_scene_ts = now

        action_config = dict(action)
        if not action_config.get("region"):
            action_config["region"] = self._auto_region

        def run_action():
            with self._action_lock:
                if self._action_inflight:
                    return
                self._action_inflight = True
            try:
                execute(action_config)
            finally:
                with self._action_lock:
                    self._action_inflight = False

        threading.Thread(target=run_action, daemon=True).start()

    def closeEvent(self, event):
        self._unregister_hotkeys()
        # CHANGE: stop automation cleanly
        self._stop_auto()
        super().closeEvent(event)


def run():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
