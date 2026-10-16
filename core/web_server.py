import threading
import time
import socket
import webbrowser
from werkzeug.serving import make_server
from core.config import config_manager
from core.logger import logger

class WebServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.server = make_server(host, port, app, threaded=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.log(f"Web server encountered error: {e}", "ERROR")

    def shutdown(self):
        try:
            self.server.shutdown()
        except Exception:
            pass

class WebServerManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(WebServerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.thread = None
        self.host = "127.0.0.1"
        self.port = int(config_manager.get("web_ui_port", 5000))
        self.is_started = False
        self._lock = threading.Lock()
        self._initialized = True

    def get_url(self):
        return f"http://{self.host}:{self.port}"

    def is_port_in_use(self, port=None):
        test_port = port or self.port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((self.host, test_port)) == 0

    def is_running(self):
        if not self.is_started or not self.thread or not self.thread.is_alive():
            return False
        return True

    def start(self, port=None):
        with self._lock:
            if self.is_running():
                return True, f"Local server is already running on {self.get_url()}"

            if port:
                self.port = int(port)
            else:
                self.port = int(config_manager.get("web_ui_port", 5000))

            # Avoid collisions if already in use by another app
            if self.is_port_in_use(self.port):
                logger.log(f"Port {self.port} is already in use.", "WARNING")
                return False, f"Port {self.port} is already in use by another program."

            try:
                import importlib
                import web.app
                importlib.reload(web.app)
                from web.app import create_app
                app = create_app()
                self.thread = WebServerThread(app, self.host, self.port)
                self.thread.start()
                self.is_started = True

                # Wait up to 1 second for socket bind
                start_time = time.time()
                while time.time() - start_time < 1.0:
                    if self.is_port_in_use(self.port):
                        break
                    time.sleep(0.1)

                logger.log(f"Local Web UI server started at {self.get_url()}", "INFO")
                return True, f"Local server started successfully at {self.get_url()}"
            except Exception as e:
                self.is_started = False
                logger.log(f"Failed to start local web server: {e}", "ERROR")
                return False, f"Failed to start local server: {e}"

    def stop(self):
        with self._lock:
            if not self.is_started or not self.thread:
                return True, "Local server is not running."

            try:
                self.thread.shutdown()
                self.thread.join(timeout=2.0)
                self.thread = None
                self.is_started = False
                logger.log("Local Web UI server stopped.", "INFO")
                return True, "Local server stopped successfully."
            except Exception as e:
                self.is_started = False
                self.thread = None
                logger.log(f"Error stopping local server: {e}", "ERROR")
                return False, f"Error stopping local server: {e}"

    def restart(self, port=None):
        self.stop()
        time.sleep(0.5)
        return self.start(port=port)

    def open_browser(self):
        webbrowser.open(self.get_url())

web_server_manager = WebServerManager()
