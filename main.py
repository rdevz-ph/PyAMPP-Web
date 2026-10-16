import os
import sys
# Fast-path for folder picker subprocess: avoid importing heavy GUI/app libraries or core modules
if len(sys.argv) > 1 and sys.argv[1] == "--pick-folder":
    try:
        import tkinter as tk
        from tkinter import filedialog
        initial_dir = sys.argv[2] if len(sys.argv) > 2 else ""
        while initial_dir and not os.path.exists(initial_dir):
            parent = os.path.dirname(initial_dir)
            if parent == initial_dir:
                break
            initial_dir = parent
        if not initial_dir or not os.path.exists(initial_dir):
            initial_dir = "C:\\"
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        selected = filedialog.askdirectory(initialdir=initial_dir, title="Select Directory")
        root.destroy()
        if selected:
            print(f"SELECTED_PATH:{os.path.normpath(selected)}")
    except Exception:
        pass
    sys.exit(0)

import socket

# Add the project root to sys.path to allow imports from core and gui
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from gui.app import PyAMPP
import customtkinter as ctk

def is_already_running():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('127.0.0.1', 49152))
        s.sendall(b"show")
        s.close()
        return True
    except:
        return False

def main():

    if is_already_running():
        sys.exit(0)

    log_path = os.path.join(os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else project_root, "startup_error.log")
    try:
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")
        app = PyAMPP()
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    except Exception as e:
        with open(log_path, "a") as f:
            import traceback
            f.write(f"\n--- {os.path.basename(sys.executable)} Error ---\n")
            f.write(str(e) + "\n")
            f.write(traceback.format_exc())
        print(f"Critical error: {e}")

if __name__ == "__main__":
    main()
