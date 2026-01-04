import json
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from pynput import mouse, keyboard
import pyautogui

# Remove pyautogui's default pause to keep playback timing accurate
pyautogui.PAUSE = 0


class MouseRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("鼠标录制工具")
        self.root.geometry("320x360")

        self.trajectory = []
        self.recording = False
        self.playing = False
        self.start_time = None
        self.record_start_perf = None
        self.last_sample_dt = None
        self.mouse_listener = None
        self.play_thread = None
        self.hotkey_listener = None
        self.file_path = "trajectory.json"
        self.fixed_freq = 60  # Hz
        self.loop_count_var = tk.IntVar(value=1)
        self.loop_infinite_var = tk.BooleanVar(value=False)

        # GUI Elements
        self.status_label = tk.Label(root, text="就绪", anchor="w")
        self.status_label.pack(fill=tk.X, padx=8, pady=(8, 4))

        control_frame = tk.LabelFrame(root, text="控制", bd=1, padx=6, pady=4, relief=tk.GROOVE)
        control_frame.pack(fill=tk.X, padx=8, pady=4)

        self.start_btn = tk.Button(control_frame, text="开始录制 (Ctrl+S)", command=self.start_recording)
        self.start_btn.pack(pady=2, fill=tk.X)

        self.stop_recording_btn = tk.Button(control_frame, text="结束录制 (Ctrl+E)", command=self.stop_recording, state=tk.DISABLED)
        self.stop_recording_btn.pack(pady=2, fill=tk.X)

        self.play_btn = tk.Button(control_frame, text="播放 (Ctrl+P)", command=self.play_trajectory)
        self.play_btn.pack(pady=2, fill=tk.X)

        self.stop_play_btn = tk.Button(control_frame, text="停止 (Ctrl+T)", command=self.stop_playback, state=tk.DISABLED)
        self.stop_play_btn.pack(pady=2, fill=tk.X)

        self.save_btn = tk.Button(control_frame, text="保存录制文件", command=self.save_to_file, state=tk.DISABLED)
        self.save_btn.pack(pady=2, fill=tk.X)

        self.load_btn = tk.Button(control_frame, text="选择文件", command=self.choose_file)
        self.load_btn.pack(pady=2, fill=tk.X)

        loop_frame = tk.LabelFrame(root, text="播放次数", bd=1, padx=6, pady=4, relief=tk.GROOVE)
        loop_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(loop_frame, text="次数(1+):").pack(side=tk.LEFT, padx=(0, 6))
        self.loop_entry = tk.Entry(loop_frame, textvariable=self.loop_count_var, width=6, justify="center")
        self.loop_entry.pack(side=tk.LEFT)
        self.loop_infinite_chk = tk.Checkbutton(loop_frame, text="无限循环", variable=self.loop_infinite_var)
        self.loop_infinite_chk.pack(side=tk.LEFT, padx=8)

        # Bind shortcuts (Tk focused)
        root.bind("<Control-s>", lambda e: self.start_recording())
        root.bind("<Control-e>", lambda e: self.stop_recording())
        root.bind("<Control-p>", lambda e: self.play_trajectory())
        root.bind("<Control-t>", lambda e: self.stop_playback())
        # Global hotkeys (work when window unfocused)
        self._start_global_hotkeys()

    # ---------------------- Recording ----------------------
    def on_move(self, x, y):
        if self.recording:
            now = time.perf_counter()
            if self.record_start_perf is None:
                self.record_start_perf = now
                self.last_sample_dt = 0
            dt = now - self.record_start_perf
            # Sample based on fixed frequency; keep handler lightweight to reduce stutter
            if self.last_sample_dt is None or dt - self.last_sample_dt >= 1 / self.fixed_freq:
                self.trajectory.append({"type": "move", "x": x, "y": y, "dt": dt})
                self.last_sample_dt = dt

    def on_click(self, x, y, button, pressed):
        if self.recording:
            now = time.perf_counter()
            if self.record_start_perf is None:
                self.record_start_perf = now
                self.last_sample_dt = 0
            dt = now - self.record_start_perf
            self.trajectory.append({"type": "click", "x": x, "y": y, "button": str(button), "pressed": pressed, "dt": dt})

    def start_recording(self):
        self.recording = True
        self.trajectory.clear()
        self.start_time = None
        self.record_start_perf = None
        self.last_sample_dt = None
        self.status_label.config(text="正在录制...")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_recording_btn.config(state=tk.NORMAL)
        self.play_btn.config(state=tk.DISABLED)
        self.stop_play_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)

        # Start mouse listener
        self.mouse_listener = mouse.Listener(on_move=self.on_move, on_click=self.on_click)
        self.mouse_listener.start()

    def stop_recording(self):
        self.recording = False
        self.status_label.config(text=f"录制结束，已保存到 {self.file_path}")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_recording_btn.config(state=tk.DISABLED)
        self.play_btn.config(state=tk.NORMAL)
        self.stop_play_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.NORMAL if self.trajectory else tk.DISABLED)

        if self.trajectory:
            try:
                with open(self.file_path, "w") as f:
                    json.dump(self.trajectory, f)
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")
        else:
            messagebox.showinfo("提示", "没有录制到轨迹。")

        if self.mouse_listener:
            self.mouse_listener.stop()

    # ---------------------- Playback ----------------------
    def play_trajectory(self):
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            messagebox.showerror("错误", f"{self.file_path} 不存在。")
            return
        except json.JSONDecodeError:
            messagebox.showerror("错误", f"{self.file_path} 文件损坏。")
            return
        if not data:
            messagebox.showinfo("提示", f"{self.file_path} 中没有数据。")
            return

        self.playing = True
        self.status_label.config(text="正在播放...")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_recording_btn.config(state=tk.DISABLED)
        self.play_btn.config(state=tk.DISABLED)
        self.stop_play_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.DISABLED)

        infinite_loop = self.loop_infinite_var.get()
        try:
            loops = int(self.loop_count_var.get())
            if loops < 1:
                loops = 1
                self.loop_count_var.set(1)
        except Exception:
            loops = 1
            self.loop_count_var.set(1)

        # Play in thread
        self.play_thread = threading.Thread(target=self._play, args=(data, loops, infinite_loop), daemon=True)
        self.play_thread.start()

    def _play(self, data, loops, infinite_loop):
        prev_dt = 0
        prev_pos = None
        loop_index = 0
        while self.playing and (infinite_loop or loop_index < loops):
            prev_dt = 0
            for point in data:
                if not self.playing:
                    break
                dt = point["dt"]
                sleep_time = max(0, dt - prev_dt)
                # Split long sleeps for better stop responsiveness
                while sleep_time > 0 and self.playing:
                    chunk = min(0.05, sleep_time)  # Smaller chunks
                    time.sleep(chunk)
                    sleep_time -= chunk
                if not self.playing:
                    break
                if point["type"] == "click":
                    button = point["button"].split(".")[1]  # 'left' or 'right'
                    if point["pressed"]:
                        pyautogui.mouseDown(button=button)
                    else:
                        pyautogui.mouseUp(button=button)
                else:  # move
                    x, y = point["x"], point["y"]
                    # Move instantly; timing is handled by the sleep above to match recorded intervals
                    pyautogui.moveTo(x, y, duration=0)
                    prev_pos = (x, y)
                prev_dt = dt
            loop_index += 1

        self.playing = False
        # Update UI in main thread
        self.root.after(0, self._update_ui_after_play)

    def _update_ui_after_play(self):
        self.status_label.config(text="播放完成" if self.playing else "播放停止")
        self.start_btn.config(state=tk.NORMAL)
        self.play_btn.config(state=tk.NORMAL)
        self.stop_play_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.NORMAL if self.trajectory else tk.DISABLED)

    def stop_playback(self):
        self.playing = False
        # Do not join, let it end naturally but responsively due to split sleeps
        self.status_label.config(text="正在停止播放...")
        # Ensure UI updates even if playback loop exits immediately
        self.root.after(0, self._update_ui_after_play)

    # ---------------------- Hotkeys ----------------------
    def _start_global_hotkeys(self):
        # Use GlobalHotKeys to ensure triggers even when window is unfocused
        if self.hotkey_listener:
            return

        def wrap(fn):
            return lambda: self.root.after(0, fn)

        hotkeys = {
            "<ctrl>+s": wrap(self.start_recording),
            "<ctrl>+e": wrap(self.stop_recording),
            "<ctrl>+p": wrap(self.play_trajectory),
            "<ctrl>+t": wrap(self.stop_playback),
        }
        self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
        self.hotkey_listener.start()

    # ---------------------- File actions ----------------------
    def choose_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if path:
            self.file_path = path
            self.status_label.config(text=f"已选择: {self.file_path}")

    def save_to_file(self):
        if not self.trajectory:
            messagebox.showinfo("提示", "没有可保存的轨迹。")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if path:
            try:
                with open(path, "w") as f:
                    json.dump(self.trajectory, f)
                self.file_path = path
                self.status_label.config(text=f"已保存到: {self.file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MouseRecorderApp(root)
    root.mainloop()
