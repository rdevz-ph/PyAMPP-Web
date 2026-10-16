import sys
import threading
from collections import deque
from datetime import datetime

class SystemLogger:
    def __init__(self, max_entries=500):
        self.max_entries = max_entries
        self.logs = deque(maxlen=max_entries)
        self.lock = threading.Lock()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

    def log(self, message, level="INFO"):
        if not message:
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "message": str(message).rstrip()
        }
        
        with self.lock:
            self.logs.append(entry)

        # Print to real terminal if available
        try:
            if self._orig_stdout:
                self._orig_stdout.write(f"[{timestamp}] [{level.upper()}] {entry['message']}\n")
                self._orig_stdout.flush()
        except Exception:
            pass

    def write(self, message):
        msg = str(message).strip()
        if msg:
            self.log(msg, "SYS")

    def flush(self):
        pass

    def get_logs(self, limit=100, level=None):
        with self.lock:
            items = list(self.logs)
            
        if level and level.upper() != "ALL":
            items = [item for item in items if item["level"] == level.upper()]
            
        if limit and limit > 0:
            items = items[-limit:]
            
        return items

    def clear(self):
        with self.lock:
            self.logs.clear()

logger = SystemLogger()
