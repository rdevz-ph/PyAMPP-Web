import os
import sys
import socket
import threading
import webbrowser
from pathlib import Path
from PIL import Image
import customtkinter as ctk
from tkinter import messagebox
import pystray
from pystray import MenuItem as item

from core.config import RESOURCE_DIR, config_manager, VERSION
from core.web_server import web_server_manager
from core.apache_manager import ApacheManager
from core.mysql_manager import MySQLManager
from core.logger import logger

class PyAMPP(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"PyAMPP {VERSION} - Local Server Controller")
        self.configure(fg_color=["#f1f5f9", "#0f172a"])

        # Window sizing with responsive minsize
        window_width = 480
        window_height = 530
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        pos_x = max(0, (screen_width // 2) - (window_width // 2))
        pos_y = max(0, (screen_height // 2) - (window_height // 2))
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")
        self.minsize(440, 500)
        self.resizable(True, True)

        # Window Icon
        self.icon_path = RESOURCE_DIR / "app.ico"
        if not self.icon_path.exists():
            self.icon_path = Path(__file__).parent.parent / "app.ico"
        if self.icon_path.exists():
            self.iconbitmap(str(self.icon_path))

        # Core service managers for exit cleanup
        self.apache = ApacheManager()
        self.mysql = MySQLManager()

        # System Tray
        self.tray_icon = None
        self.setup_tray()

        # Build UI layout
        self.setup_ui()

        # Single instance listener
        self.start_instance_listener()

        # Auto-start web server if enabled
        if config_manager.get("web_ui_autostart", True):
            self.after(200, self.start_server_action)

        # Check for application updates in the background
        self.check_for_updates_async()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)  # Expanding spacer pushes footer to bottom

        # Header Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=25, pady=(18, 8), sticky="ew")

        self.title_info_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.title_info_frame.pack(side="left", anchor="w")

        self.title_label = ctk.CTkLabel(
            self.title_info_frame,
            text=f"PyAMPP {VERSION}",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            self.title_info_frame,
            text="Local Web Management Controller",
            font=ctk.CTkFont(size=12),
            text_color=["#64748b", "#94a3b8"]
        )
        self.subtitle_label.pack(anchor="w")

        # Update button (placed on the right side of header, displayed when an update is available)
        self.latest_update_url = ""
        self.update_btn = ctk.CTkButton(
            self.header_frame,
            text="Update Available",
            command=self.open_update_url,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=["#2563eb", "#3b82f6"],
            hover_color=["#1d4ed8", "#2563eb"],
            text_color="#ffffff",
            height=28,
            cursor="hand2"
        )

        # Server Status Card
        self.card = ctk.CTkFrame(
            self,
            fg_color=["#ffffff", "#1e293b"],
            border_width=1,
            border_color=["#e2e8f0", "#334155"],
            corner_radius=10
        )
        self.card.grid(row=1, column=0, padx=25, pady=10, sticky="ew")
        self.card.grid_columnconfigure(1, weight=1)

        # Status row
        self.status_title = ctk.CTkLabel(
            self.card,
            text="Server Status:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.status_title.grid(row=0, column=0, padx=15, pady=(15, 8), sticky="w")

        self.status_badge = ctk.CTkLabel(
            self.card,
            text="OFFLINE",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=["#e2e8f0", "#334155"],
            text_color=["#475569", "#cbd5e1"],
            corner_radius=6,
            width=80,
            height=24
        )
        self.status_badge.grid(row=0, column=1, padx=15, pady=(15, 8), sticky="e")

        # URL row
        self.url_title = ctk.CTkLabel(
            self.card,
            text="Access URL:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.url_title.grid(row=1, column=0, padx=15, pady=8, sticky="w")

        current_port = config_manager.get("web_ui_port", 5000)
        self.url_link = ctk.CTkLabel(
            self.card,
            text=f"http://127.0.0.1:{current_port}",
            font=ctk.CTkFont(size=13, underline=True),
            text_color=["#1f6aa5", "#38bdf8"],
            cursor="hand2"
        )
        self.url_link.grid(row=1, column=1, padx=15, pady=8, sticky="e")
        self.url_link.bind("<Button-1>", lambda e: self.open_web_ui())

        # Port configuration row
        self.port_title = ctk.CTkLabel(
            self.card,
            text="Local Port:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.port_title.grid(row=2, column=0, padx=15, pady=(8, 15), sticky="w")

        self.port_entry = ctk.CTkEntry(self.card, width=90, height=26, font=ctk.CTkFont(size=12))
        self.port_entry.insert(0, str(current_port))
        self.port_entry.grid(row=2, column=1, padx=15, pady=(8, 15), sticky="e")

        # Primary Action: Open Web UI Button
        self.open_btn = ctk.CTkButton(
            self,
            text="Open Web UI Dashboard",
            command=self.open_web_ui,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            fg_color=["#1f6aa5", "#2563eb"],
            hover_color=["#174e79", "#1d4ed8"],
            text_color="#ffffff"
        )
        self.open_btn.grid(row=2, column=0, padx=25, pady=(8, 4), sticky="ew")

        # Server Control Buttons (Start / Stop / Restart)
        self.ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.ctrl_frame.grid(row=3, column=0, padx=25, pady=6, sticky="ew")
        self.ctrl_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_btn = ctk.CTkButton(
            self.ctrl_frame,
            text="Start Server",
            command=self.start_server_action,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=["#16a34a", "#15803d"],
            hover_color=["#15803d", "#166534"],
            text_color="#ffffff",
            height=32
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.stop_btn = ctk.CTkButton(
            self.ctrl_frame,
            text="Stop Server",
            command=self.stop_server_action,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=["#dc2626", "#b91c1c"],
            hover_color=["#b91c1c", "#991b1b"],
            text_color="#ffffff",
            height=32
        )
        self.stop_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.restart_btn = ctk.CTkButton(
            self.ctrl_frame,
            text="Restart Server",
            command=self.restart_server_action,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=["#475569", "#334155"],
            hover_color=["#334155", "#1e293b"],
            text_color="#ffffff",
            height=32
        )
        self.restart_btn.grid(row=0, column=2, padx=(4, 0), sticky="ew")

        # Status Message Label
        self.status_msg = ctk.CTkLabel(
            self,
            text="Ready. Click 'Start Server' to host the Web UI.",
            font=ctk.CTkFont(size=12),
            text_color=["#64748b", "#94a3b8"]
        )
        self.status_msg.grid(row=4, column=0, padx=25, pady=4, sticky="w")

        # Preferences Frame
        self.pref_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.pref_frame.grid(row=5, column=0, padx=25, pady=(2, 6), sticky="ew")

        self.autostart_chk = ctk.CTkCheckBox(
            self.pref_frame,
            text="Auto-start server on launch",
            font=ctk.CTkFont(size=12),
            command=self.save_preferences
        )
        self.autostart_chk.pack(anchor="w", pady=2)
        if config_manager.get("web_ui_autostart", True):
            self.autostart_chk.select()
        else:
            self.autostart_chk.deselect()

        # Responsive spacer to absorb extra height when window expands
        self.spacer = ctk.CTkFrame(self, fg_color="transparent")
        self.spacer.grid(row=6, column=0, sticky="nsew")

        # Footer Frame
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=7, column=0, padx=25, pady=(6, 16), sticky="sew")

        self.footer_dev = ctk.CTkLabel(
            self.footer,
            text="rdevz-ph | PyAMPP",
            font=ctk.CTkFont(size=11),
            text_color=["#64748b", "#94a3b8"]
        )
        self.footer_dev.pack(side="left")

        self.mode_switch = ctk.CTkSwitch(
            self.footer,
            text="Dark Mode",
            font=ctk.CTkFont(size=11),
            command=self.toggle_mode
        )
        self.mode_switch.pack(side="right")
        self.mode_switch.deselect()

        self.check_update_btn = ctk.CTkButton(
            self.footer,
            text="Check for Updates",
            command=lambda: self.check_for_updates_async(manual=True),
            font=ctk.CTkFont(size=11),
            height=24,
            width=115,
            fg_color=["#e2e8f0", "#334155"],
            hover_color=["#cbd5e1", "#475569"],
            text_color=["#1e293b", "#f8fafc"],
            cursor="hand2"
        )
        self.check_update_btn.pack(side="right", padx=(0, 12))

        # Update initial button state
        self.update_ui_state()

    def get_selected_port(self):
        try:
            val = int(self.port_entry.get().strip())
            return val if 1 <= val <= 65535 else 5000
        except Exception:
            return 5000

    def update_ui_state(self):
        is_running = web_server_manager.is_running()
        port = self.get_selected_port()
        self.url_link.configure(text=f"http://127.0.0.1:{port}")

        if is_running:
            self.status_badge.configure(
                text="ONLINE",
                fg_color=["#dcfce7", "#065f46"],
                text_color=["#166534", "#a7f3d0"]
            )
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.restart_btn.configure(state="normal")
            self.open_btn.configure(state="normal")
            self.port_entry.configure(state="disabled")
            self.status_msg.configure(
                text=f"Local server is active on http://127.0.0.1:{port}",
                text_color=["#16a34a", "#4ade80"]
            )
        else:
            self.status_badge.configure(
                text="OFFLINE",
                fg_color=["#f1f5f9", "#334155"],
                text_color=["#475569", "#cbd5e1"]
            )
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.restart_btn.configure(state="disabled")
            self.open_btn.configure(state="disabled")
            self.port_entry.configure(state="normal")
            self.status_msg.configure(
                text="Server is stopped.",
                text_color=["#64748b", "#94a3b8"]
            )

    def start_server_action(self):
        port = self.get_selected_port()
        config_manager.set("web_ui_port", port)
        config_manager.save()

        self.status_msg.configure(text="Starting local server...", text_color=["#1f6aa5", "#38bdf8"])
        self.update()

        def _start():
            ok, msg = web_server_manager.start(port=port)
            self.after(0, self.update_ui_state)
            if not ok:
                self.after(0, lambda: self.status_msg.configure(text=msg, text_color=["#dc2626", "#f87171"]))

        threading.Thread(target=_start, daemon=True).start()

    def stop_server_action(self):
        self.status_msg.configure(text="Stopping local server...", text_color=["#dc2626", "#f87171"])
        self.update()

        def _stop():
            web_server_manager.stop()
            self.after(0, self.update_ui_state)

        threading.Thread(target=_stop, daemon=True).start()

    def restart_server_action(self):
        port = self.get_selected_port()
        self.status_msg.configure(text="Restarting local server...", text_color=["#1f6aa5", "#38bdf8"])
        self.update()

        def _restart():
            web_server_manager.restart(port=port)
            self.after(0, self.update_ui_state)

        threading.Thread(target=_restart, daemon=True).start()

    def open_web_ui(self):
        port = self.get_selected_port()
        url = f"http://127.0.0.1:{port}"
        webbrowser.open(url)

    def save_preferences(self):
        autostart = bool(self.autostart_chk.get())
        config_manager.set("web_ui_autostart", autostart)
        config_manager.save()

    def toggle_mode(self):
        current_mode = ctk.get_appearance_mode()
        if current_mode in ["Dark", "System"]:
            ctk.set_appearance_mode("Light")
            self.mode_switch.configure(text="Light Mode")
            self.mode_switch.deselect()
        else:
            ctk.set_appearance_mode("Dark")
            self.mode_switch.configure(text="Dark Mode")
            self.mode_switch.select()

    def start_instance_listener(self):
        def listen():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', 49152))
                s.listen(1)
                while True:
                    conn, _ = s.accept()
                    try:
                        conn.settimeout(2.0)
                        data = conn.recv(1024).decode()
                        if data == "show":
                            self.after(0, self.show_window)
                    except Exception:
                        pass
                    finally:
                        conn.close()
            except Exception:
                pass

        threading.Thread(target=listen, daemon=True).start()

    def setup_tray(self):
        if self.icon_path.exists():
            image = Image.open(str(self.icon_path))
            menu = (
                item('Open Web UI', lambda *args: self.open_web_ui()),
                item('Show Controller', self.show_window, default=True),
                item('Restart Local Server', lambda *args: self.restart_server_action()),
                item('Exit PyAMPP', self.exit_app)
            )
            self.tray_icon = pystray.Icon("PyAMPP", image, "PyAMPP", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        self.after(0, self._deiconify_and_focus)

    def _deiconify_and_focus(self):
        self.deiconify()
        self.state('normal')
        self.lift()
        self.attributes("-topmost", True)
        self.after(10, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def center_dialog(self, dialog, width, height):
        """Centers a toplevel dialog directly inside the main controller window."""
        self.update_idletasks()
        dialog.update_idletasks()

        if os.name == 'nt':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                app_root = user32.GetAncestor(self.winfo_id(), 2) or self.winfo_id()
                dlg_root = user32.GetAncestor(dialog.winfo_id(), 2) or dialog.winfo_id()
                app_rect = (ctypes.c_long * 4)()
                dlg_rect = (ctypes.c_long * 4)()
                user32.GetWindowRect(app_root, ctypes.byref(app_rect))
                user32.GetWindowRect(dlg_root, ctypes.byref(dlg_rect))

                pw = app_rect[2] - app_rect[0]
                ph = app_rect[3] - app_rect[1]
                dw = dlg_rect[2] - dlg_rect[0]
                dh = dlg_rect[3] - dlg_rect[1]

                if dw > 50 and dh > 30:
                    x = app_rect[0] + max(0, (pw - dw) // 2)
                    y = app_rect[1] + max(0, (ph - dh) // 2)
                    user32.SetWindowPos(dlg_root, 0, x, y, 0, 0, 5) # SWP_NOSIZE | SWP_NOZORDER
                    return
            except Exception:
                pass

        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        main_w = self.winfo_width()
        main_h = self.winfo_height()

        pos_x = main_x + max(0, (main_w - width) // 2)
        pos_y = main_y + max(0, (main_h - height) // 2)

        dialog.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    def _center_native_dialog(self, title):
        """Asynchronously centers a native Windows dialog over the main window."""
        try:
            import ctypes
            import time
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ('left', ctypes.c_long),
                    ('top', ctypes.c_long),
                    ('right', ctypes.c_long),
                    ('bottom', ctypes.c_long)
                ]

            parent_hwnd = user32.GetAncestor(self.winfo_id(), 2)
            if not parent_hwnd:
                parent_hwnd = user32.GetParent(self.winfo_id())
            if not parent_hwnd:
                parent_hwnd = self.winfo_id()

            def _worker():
                for _ in range(80):
                    hwnd = user32.FindWindowW('#32770', title)
                    if hwnd:
                        pr = RECT()
                        mr = RECT()
                        user32.GetWindowRect(parent_hwnd, ctypes.byref(pr))
                        user32.GetWindowRect(hwnd, ctypes.byref(mr))
                        pw = pr.right - pr.left
                        ph = pr.bottom - pr.top
                        mw = mr.right - mr.left
                        mh = mr.bottom - mr.top
                        if mw > 50 and mh > 30:
                            x = pr.left + max(0, (pw - mw) // 2)
                            y = pr.top + max(0, (ph - mh) // 2)
                            user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 5) # SWP_NOSIZE | SWP_NOZORDER
                            time.sleep(0.02)
                            user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 5)
                            break
                    time.sleep(0.01)

            threading.Thread(target=_worker, daemon=True).start()
        except Exception:
            pass

    def on_closing(self):
        # Dialog on exit
        dialog = ctk.CTkToplevel(self)
        dialog.title("Exit PyAMPP")
        if self.icon_path.exists():
            dialog.iconbitmap(str(self.icon_path))

        dialog_width = 380
        dialog_height = 170
        dialog.geometry(f"{dialog_width}x{dialog_height}")

        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.attributes("-topmost", True)

        label = ctk.CTkLabel(dialog, text="Close PyAMPP or minimize to tray?", font=ctk.CTkFont(size=13, weight="bold"))
        label.pack(pady=(20, 15))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=5)

        def stop_exit():
            dialog.destroy()
            self.exit_app()

        def minimize():
            dialog.destroy()
            self.withdraw()

        exit_btn = ctk.CTkButton(btn_frame, text="Exit PyAMPP", command=stop_exit, fg_color="#dc2626", hover_color="#b91c1c", width=100)
        exit_btn.pack(side="left", padx=5, expand=True)

        tray_btn = ctk.CTkButton(btn_frame, text="Minimize to Tray", command=minimize, width=110)
        tray_btn.pack(side="left", padx=5, expand=True)

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", command=dialog.destroy, fg_color="gray", width=70)
        cancel_btn.pack(side="left", padx=5, expand=True)

        self.center_dialog(dialog, dialog_width, dialog_height)
        dialog.after(20, lambda: self.center_dialog(dialog, dialog_width, dialog_height))
        dialog.grab_set()

    def exit_app(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()

        # Stop local web server
        web_server_manager.stop()

        # Stop Apache & MySQL
        try:
            self.apache.stop()
            self.mysql.stop()
        except Exception:
            pass

        self.after(100, self.destroy)

    def check_for_updates_async(self, manual=False):
        """Checks for application updates in the background without blocking the UI."""
        if manual:
            self.check_update_btn.configure(state="disabled", text="Checking...")
        threading.Thread(target=lambda: self._check_for_updates_worker(manual=manual), daemon=True).start()

    def _check_for_updates_worker(self, manual=False):
        import requests
        import json

        url = config_manager.get("presets_url", "")
        if not url:
            url = "https://raw.githubusercontent.com/rdevz-ph/PyAMPP-Web/main/presets.json"

        clean_url = url.strip()
        if clean_url.rstrip("/").endswith("github.com/rdevz-ph/PyAMPP-Web") or clean_url.rstrip("/").endswith("github.com/rdevz-ph/PyAMPP-Windows"):
            clean_url = f"https://raw.githubusercontent.com/{clean_url.split('github.com/')[1].strip('/')}/main/presets.json"
        elif "github.com" in clean_url and "/blob/" in clean_url:
            clean_url = clean_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        latest_data = None
        fetch_failed = False
        try:
            resp = requests.get(clean_url, timeout=5)
            if resp.status_code == 200:
                latest_data = resp.json().get("latest_release")
            else:
                fetch_failed = True
        except Exception as e:
            fetch_failed = True
            logger.log(f"Remote update check failed ({e}). Checking local presets...", "DEBUG")

        if not latest_data:
            local_presets = RESOURCE_DIR / "presets.json"
            if not local_presets.exists():
                local_presets = Path(__file__).parent.parent / "presets.json"
            if local_presets.exists():
                try:
                    with open(local_presets, "r", encoding="utf-8") as f:
                        latest_data = json.load(f).get("latest_release")
                except Exception:
                    pass

        if manual:
            self.after(0, lambda: self.check_update_btn.configure(state="normal", text="Check for Updates"))

        if fetch_failed and manual and not latest_data:
            def _show_warn():
                self._center_native_dialog("Update Check")
                messagebox.showwarning(
                    "Update Check",
                    "Could not connect to the update server. Please check your internet connection.",
                    parent=self
                )
            self.after(0, _show_warn)
            return

        if not latest_data or not isinstance(latest_data, dict):
            if manual:
                def _show_warn():
                    self._center_native_dialog("Update Check")
                    messagebox.showwarning(
                        "Update Check",
                        "Release information is unavailable at this time.",
                        parent=self
                    )
                self.after(0, _show_warn)
            return

        remote_version = str(latest_data.get("version", "")).strip()
        remote_url = str(latest_data.get("url", "")).strip()

        if not remote_version:
            if manual:
                def _show_warn():
                    self._center_native_dialog("Update Check")
                    messagebox.showwarning(
                        "Update Check",
                        "Release information is unavailable at this time.",
                        parent=self
                    )
                self.after(0, _show_warn)
            return

        if self._is_newer_version(remote_version, VERSION):
            target_url = remote_url if remote_url else f"https://github.com/rdevz-ph/PyAMPP-Web/releases/tag/{remote_version}"
            self.after(0, lambda: self._show_update_notification(remote_version, target_url))
            if manual:
                def _prompt():
                    self._center_native_dialog("Update Available")
                    if messagebox.askyesno(
                        "Update Available",
                        f"A new version of PyAMPP is available ({remote_version}).\n\nWould you like to open the release page now?",
                        parent=self
                    ):
                        webbrowser.open(target_url)
                self.after(0, _prompt)
        else:
            if manual:
                def _show_info():
                    self._center_native_dialog("Check for Updates")
                    messagebox.showinfo(
                        "Check for Updates",
                        f"You are using the latest version of PyAMPP ({VERSION}).",
                        parent=self
                    )
                self.after(0, _show_info)

    def _is_newer_version(self, remote_str, current_str):
        import re
        if not remote_str:
            return False

        remote_nums = [int(x) for x in re.findall(r'\d+', remote_str)]
        current_nums = [int(x) for x in re.findall(r'\d+', current_str)]

        if not remote_nums:
            return False
        if not current_nums:
            return remote_str.strip().lower() != current_str.strip().lower()

        max_len = max(len(remote_nums), len(current_nums))
        r_padded = remote_nums + [0] * (max_len - len(remote_nums))
        c_padded = current_nums + [0] * (max_len - len(current_nums))

        if r_padded > c_padded:
            return True
        elif r_padded < c_padded:
            return False

        return False

    def _show_update_notification(self, remote_version, target_url):
        self.latest_update_url = target_url
        self.update_btn.configure(text=f"Update: {remote_version}")
        self.update_btn.pack(side="right", anchor="e", padx=(10, 0))
        logger.log(f"Update available: {remote_version} ({target_url})", "INFO")

    def open_update_url(self):
        if hasattr(self, "latest_update_url") and self.latest_update_url:
            webbrowser.open(self.latest_update_url)

if __name__ == "__main__":
    ctk.set_appearance_mode("Light")
    ctk.set_default_color_theme("blue")
    app = PyAMPP()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
