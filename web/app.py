import os
import sys
import json
import re
import time
import socket
import ssl
import subprocess
import threading
import base64
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect

from core.config import (
    config_manager,
    COMPONENTS_PRESETS,
    VERSION,
    RESOURCE_DIR,
    update_presets,
    get_system_php_path
)
from core.apache_manager import ApacheManager
from core.mysql_manager import MySQLManager
from core.logger import logger
from core.downloader import (
    download_file,
    extract_zip,
    configure_php,
    configure_pma,
    surgical_cleanup,
    robust_rmtree
)

# Global service instances
apache_manager = ApacheManager()
mysql_manager = MySQLManager()

# Background installation state
install_state = {
    "in_progress": False,
    "title": "",
    "message": "",
    "percent": 0,
    "error": None
}
install_lock = threading.Lock()

def ensure_sample_index_php():
    """Creates a sample index.php with phpinfo() in htdocs if it does not exist."""
    raw_htdocs = config_manager.get("htdocs_dir")
    install_dir = Path(config_manager.get("install_dir"))
    htdocs_path = Path(raw_htdocs) if raw_htdocs else install_dir.parent / "htdocs"
    try:
        htdocs_path.mkdir(parents=True, exist_ok=True)
        index_file = htdocs_path / "index.php"
        if not index_file.exists():
            with open(index_file, "w", encoding="utf-8") as f:
                f.write("<?php phpinfo(); ?>\n")
            logger.log(f"Created sample index.php with phpinfo() in {htdocs_path}", "INFO")
    except Exception as e:
        logger.log(f"Note: Could not create sample index.php: {e}", "WARNING")

def create_app():
    # Resolve static and template directories
    base_dir = Path(__file__).parent
    if not (base_dir / "templates").exists():
        base_dir = RESOURCE_DIR / "web"
    template_dir = str(base_dir / "templates")
    static_dir = str(base_dir / "static")

    app = Flask(
        "pyampp_web",
        template_folder=template_dir,
        static_folder=static_dir
    )
    app.config["SECRET_KEY"] = "pyampp-secret-local-key"

    # Ensure sample index.php exists in htdocs
    ensure_sample_index_php()
    # Context processor to pass common variables to all templates
    @app.context_processor
    def inject_common():
        install_dir = config_manager.get("install_dir", "C:\\PyAMPP\\bin")
        norm_install = os.path.normpath(str(install_dir))
        if norm_install.lower().endswith(os.sep + "bin") or norm_install.lower().endswith("/bin"):
            install_root = os.path.dirname(norm_install)
        else:
            install_root = norm_install

        return {
            "version": VERSION,
            "config": config_manager.config,
            "install_root": install_root,
            "presets": COMPONENTS_PRESETS
        }

    # ==========================================
    # HTML View Routes
    # ==========================================
    @app.route("/")
    def index():
        config_manager.validate_binaries()
        if not config_manager.get("wizard_completed", False):
            return redirect("/wizard")
        return redirect("/dashboard")

    @app.route("/dashboard")
    def dashboard():
        config_manager.validate_binaries()
        wizard_needed = not config_manager.get("wizard_completed", False)
        if wizard_needed and request.args.get("skip") != "1":
            return redirect("/wizard")
        return render_template(
            "dashboard.html",
            active_page="dashboard",
            wizard_skipped=(wizard_needed and request.args.get("skip") == "1")
        )

    @app.route("/php-extensions")
    def php_extensions():
        return render_template("php_extensions.html", active_page="php_extensions")

    @app.route("/php-cli")
    def php_cli():
        return render_template("php_cli.html", active_page="php_cli")

    @app.route("/php-global")
    def php_global():
        return render_template("php_global.html", active_page="php_global")

    @app.route("/diagnostics")
    def diagnostics():
        return render_template("diagnostics.html", active_page="diagnostics")

    @app.route("/logs")
    def logs():
        return render_template("logs.html", active_page="logs")

    @app.route("/settings")
    def settings():
        return render_template("settings.html", active_page="settings")

    @app.route("/wizard")
    def wizard():
        return render_template("wizard.html", active_page="wizard")

    @app.route("/about")
    def about():
        return render_template("about.html", active_page="about")

    # ==========================================
    # JSON API Routes
    # ==========================================

    @app.route("/api/status", methods=["GET"])
    def get_status():
        # Update paths from latest config
        apache_manager.update_paths()
        mysql_manager.update_paths()

        # Apache status
        apache_running = apache_manager.is_running()
        apache_proc = apache_manager.get_process_by_port() if apache_running else None
        apache_pid = apache_proc.pid if apache_proc else None
        apache_mem = f"{apache_proc.memory_info().rss / 1024 / 1024:.1f} MB" if apache_proc else "-"

        # MySQL status
        mysql_running = mysql_manager.is_running()
        mysql_proc = mysql_manager.get_process_by_port() if mysql_running else None
        mysql_pid = mysql_proc.pid if mysql_proc else None
        mysql_mem = f"{mysql_proc.memory_info().rss / 1024 / 1024:.1f} MB" if mysql_proc else "-"

        # Installed components check
        install_dir = Path(config_manager.get("install_dir"))
        php_dir = install_dir / "php"
        apache_dir = install_dir / "apache" / "Apache24"
        mysql_dir = mysql_manager.find_mysql_dir()
        pma_dir = apache_dir / "htdocs" / "phpmyadmin"

        installed = {
            "php": (php_dir / "php.exe").exists(),
            "apache": (apache_dir / "bin" / "httpd.exe").exists(),
            "mysql": bool(mysql_dir and (mysql_dir / "bin" / "mysqld.exe").exists()),
            "phpmyadmin": pma_dir.exists()
        }

        # Detect installed versions if possible
        versions = {
            "php": "Not Installed",
            "apache": "Not Installed",
            "mysql": "Not Installed",
            "phpmyadmin": "Not Installed"
        }

        if installed["php"]:
            try:
                res = subprocess.run(
                    [str(php_dir / "php.exe"), "-v"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if res.returncode == 0:
                    first_line = res.stdout.splitlines()[0]
                    versions["php"] = first_line.split(" ")[1] if len(first_line.split(" ")) > 1 else "Installed"
            except Exception:
                versions["php"] = "Installed"

        if installed["apache"]:
            try:
                res = subprocess.run(
                    [str(apache_dir / "bin" / "httpd.exe"), "-v"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if "Server version:" in line:
                            versions["apache"] = line.split("/")[1].split(" ")[0]
                            break
            except Exception:
                versions["apache"] = "Installed"

        if installed["mysql"]:
            try:
                res = subprocess.run(
                    [str(mysql_dir / "bin" / "mysqld.exe"), "--version"],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if res.returncode == 0:
                    parts = res.stdout.split("Ver ")
                    if len(parts) > 1:
                        versions["mysql"] = parts[1].split(" ")[0]
                    else:
                        versions["mysql"] = "Installed"
            except Exception:
                versions["mysql"] = "Installed"

        if installed["phpmyadmin"]:
            # Check version from RELEASE-DATE or README
            version_file = pma_dir / "RELEASE-DATE"
            if version_file.exists():
                try:
                    versions["phpmyadmin"] = version_file.read_text().splitlines()[0].strip()
                except Exception:
                    versions["phpmyadmin"] = "Installed"
            else:
                versions["phpmyadmin"] = "Installed"

        return jsonify({
            "apache": {
                "running": apache_running,
                "port": config_manager.get("apache_port"),
                "pid": apache_pid,
                "memory": apache_mem
            },
            "mysql": {
                "running": mysql_running,
                "port": config_manager.get("mysql_port"),
                "pid": mysql_pid,
                "memory": mysql_mem
            },
            "installed": installed,
            "versions": versions
        })

    @app.route("/api/service/<service>/<action>", methods=["POST"])
    def manage_service(service, action):
        service = service.lower()
        action = action.lower()

        apache_manager.update_paths()
        mysql_manager.update_paths()

        if service == "apache":
            if action == "start":
                logger.log("Starting Apache HTTP Server...", "INFO")
                ok, msg = apache_manager.start_server()
                logger.log(f"Apache: {msg}", "INFO" if ok else "ERROR")
            elif action == "stop":
                logger.log("Stopping Apache HTTP Server...", "INFO")
                ok, msg = apache_manager.stop()
                logger.log(f"Apache: {msg}", "INFO" if ok else "ERROR")
            elif action == "restart":
                logger.log("Restarting Apache HTTP Server...", "INFO")
                apache_manager.stop()
                time.sleep(1.0)
                ok, msg = apache_manager.start_server()
                logger.log(f"Apache: {msg}", "INFO" if ok else "ERROR")
            else:
                return jsonify({"success": False, "message": f"Invalid action {action}"}), 400
            return jsonify({"success": ok, "message": msg})

        elif service == "mysql":
            if action == "start":
                logger.log("Starting MySQL Database Server...", "INFO")
                ok, msg = mysql_manager.start_server()
                logger.log(f"MySQL: {msg}", "INFO" if ok else "ERROR")
            elif action == "stop":
                logger.log("Stopping MySQL Database Server...", "INFO")
                ok, msg = mysql_manager.stop()
                logger.log(f"MySQL: {msg}", "INFO" if ok else "ERROR")
            elif action == "restart":
                logger.log("Restarting MySQL Database Server...", "INFO")
                mysql_manager.stop()
                time.sleep(1.0)
                ok, msg = mysql_manager.start_server()
                logger.log(f"MySQL: {msg}", "INFO" if ok else "ERROR")
            else:
                return jsonify({"success": False, "message": f"Invalid action {action}"}), 400
            return jsonify({"success": ok, "message": msg})

        elif service == "all":
            if action == "start":
                logger.log("Starting all services (Apache and MySQL)...", "INFO")
                ok_m, msg_m = mysql_manager.start_server()
                logger.log(f"MySQL: {msg_m}", "INFO" if ok_m else "ERROR")
                ok_a, msg_a = apache_manager.start_server()
                logger.log(f"Apache: {msg_a}", "INFO" if ok_a else "ERROR")
                all_ok = ok_m and ok_a
                return jsonify({"success": all_ok, "message": f"Apache: {msg_a} | MySQL: {msg_m}"})
            elif action == "stop":
                logger.log("Stopping all services (Apache and MySQL)...", "INFO")
                ok_a, msg_a = apache_manager.stop()
                logger.log(f"Apache: {msg_a}", "INFO" if ok_a else "ERROR")
                ok_m, msg_m = mysql_manager.stop()
                logger.log(f"MySQL: {msg_m}", "INFO" if ok_m else "ERROR")
                return jsonify({"success": True, "message": f"Apache: {msg_a} | MySQL: {msg_m}"})
            elif action == "restart":
                logger.log("Restarting all services (Apache and MySQL)...", "INFO")
                apache_manager.stop()
                mysql_manager.stop()
                time.sleep(1.0)
                ok_m, msg_m = mysql_manager.start_server()
                logger.log(f"MySQL: {msg_m}", "INFO" if ok_m else "ERROR")
                ok_a, msg_a = apache_manager.start_server()
                logger.log(f"Apache: {msg_a}", "INFO" if ok_a else "ERROR")
                return jsonify({"success": ok_m and ok_a, "message": f"Services restarted. Apache: {msg_a} | MySQL: {msg_m}"})
            else:
                return jsonify({"success": False, "message": f"Invalid action {action}"}), 400

        return jsonify({"success": False, "message": f"Unknown service: {service}"}), 400

    @app.route("/api/config", methods=["GET", "POST"])
    def handle_config():
        if request.method == "GET":
            return jsonify(config_manager.config)

        data = request.get_json() or {}
        try:
            # Check running status of services before modifying config or paths
            was_apache_running = apache_manager.is_running()
            was_mysql_running = mysql_manager.is_running()

            # Stop running services first to release port listeners and file locks cleanly
            if was_apache_running:
                logger.log("Stopping Apache before applying updated settings...", "INFO")
                apache_manager.stop()

            if was_mysql_running:
                logger.log("Stopping MySQL before applying updated settings...", "INFO")
                mysql_manager.stop()

            if was_apache_running or was_mysql_running:
                time.sleep(1.0)

            for key, val in data.items():
                if isinstance(val, str) and key in ("htdocs_dir", "install_dir", "mysql_data_dir"):
                    val = os.path.normpath(val.strip())
                    if key == "install_dir":
                        if not (val.lower().endswith(os.sep + "bin") or val.lower().endswith("/bin")):
                            val = os.path.normpath(os.path.join(val, "bin"))
                    try:
                        Path(val).mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logger.log(f"Note: Could not create directory {val}: {e}", "WARNING")
                config_manager.set(key, val)
            config_manager.save()

            # Ensure managers pick up new paths and ports immediately
            apache_manager.update_paths()
            mysql_manager.update_paths()
            ensure_sample_index_php()

            # Sync Apache conf if apache is installed
            try:
                if apache_manager.install_dir and (apache_manager.install_dir / "conf" / "httpd.conf").exists():
                    apache_manager.configure()
            except Exception as e:
                logger.log(f"Note: Could not update Apache conf after path change: {e}", "WARNING")

            # Sync MySQL conf if mysql is installed
            try:
                if mysql_manager.mysql_dir and (mysql_manager.mysql_dir / "bin" / "mysqld.exe").exists():
                    mysql_manager.configure()
            except Exception as e:
                logger.log(f"Note: Could not update MySQL conf after path change: {e}", "WARNING")

            # Auto-restart services that were previously running so new settings take effect
            restarted = []
            if was_apache_running:
                logger.log("Auto-restarting Apache to apply updated settings...", "INFO")
                ok_a, msg_a = apache_manager.start_server()
                logger.log(f"Apache: {msg_a}", "INFO" if ok_a else "ERROR")
                if ok_a:
                    restarted.append("Apache")
                else:
                    restarted.append(f"Apache (start failed: {msg_a})")

            if was_mysql_running:
                logger.log("Auto-restarting MySQL to apply updated settings...", "INFO")
                ok_m, msg_m = mysql_manager.start_server()
                logger.log(f"MySQL: {msg_m}", "INFO" if ok_m else "ERROR")
                if ok_m:
                    restarted.append("MySQL")
                else:
                    restarted.append(f"MySQL (start failed: {msg_m})")

            if restarted:
                msg = f"Settings saved. Auto-restarted running server(s): {', '.join(restarted)}."
            else:
                msg = "Settings saved successfully."

            logger.log(f"Configuration updated via Web UI. {msg}", "INFO")
            return jsonify({"success": True, "message": msg, "restarted": restarted})
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed to save settings: {e}"}), 500

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        level = request.args.get("level", "ALL")
        limit = int(request.args.get("limit", 150))
        entries = logger.get_logs(limit=limit, level=level)
        return jsonify({"logs": entries})

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        logger.clear()
        return jsonify({"success": True, "message": "Logs cleared."})

    @app.route("/api/php/extensions", methods=["GET", "POST"])
    def handle_php_extensions():
        install_dir = config_manager.get("install_dir") or ""
        php_dir = Path(install_dir) / "php"
        php_ini_path = php_dir / "php.ini"

        if not php_ini_path.exists():
            return jsonify({"success": False, "message": "php.ini file not found. Please install PHP first."})

        # Regex patterns matching exact valid PHP extension lines while stripping inline comments
        ext_pattern = re.compile(r'^\s*(;)?\s*(zend_)?extension\s*=\s*([^;]+?)(?:\s*;.*)?$', re.IGNORECASE)
        valid_ext_name = re.compile(r'^(php_)?[a-zA-Z0-9_\-]+(\.dll)?$', re.IGNORECASE)

        if request.method == "GET":
            try:
                parsed_extensions = {}
                with open(php_ini_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        match = ext_pattern.match(line)
                        if match:
                            is_commented = match.group(1) is not None
                            is_zend = match.group(2) is not None
                            raw_name = match.group(3).strip().strip("'\"").strip()

                            # Skip empty names, examples, paths, or non-Windows binaries
                            if (not raw_name or
                                raw_name.lower() == "modulename" or
                                "<ext>" in raw_name or
                                "/" in raw_name or
                                "\\" in raw_name or
                                raw_name.lower().endswith(".so") or
                                not valid_ext_name.match(raw_name)):
                                continue

                            clean_name = raw_name
                            if clean_name.lower().endswith(".dll"):
                                clean_name = clean_name[:-4]
                            if clean_name.lower().startswith("php_"):
                                clean_name = clean_name[4:]

                            lower_name = clean_name.lower()
                            # If duplicate, prioritize the enabled (uncommented) entry
                            if lower_name in parsed_extensions:
                                existing_item = parsed_extensions[lower_name]
                                if not existing_item["enabled"] and not is_commented:
                                    parsed_extensions[lower_name] = {
                                        "name": clean_name,
                                        "enabled": True,
                                        "is_zend": is_zend
                                    }
                            else:
                                parsed_extensions[lower_name] = {
                                    "name": clean_name,
                                    "enabled": not is_commented,
                                    "is_zend": is_zend
                                }

                extensions = list(parsed_extensions.values())
                extensions.sort(key=lambda x: x["name"].lower())
                return jsonify({"success": True, "extensions": extensions})
            except Exception as e:
                return jsonify({"success": False, "message": f"Error reading php.ini: {e}"}), 500

        # POST: Update extensions in php.ini
        data = request.get_json() or {}
        enabled_list = [name.lower() for name in data.get("enabled_extensions", [])]
        restart_apache = data.get("restart_apache", False)

        try:
            with open(php_ini_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                match = ext_pattern.match(line)
                if match:
                    raw_name = match.group(3).strip().strip("'\"").strip()
                    if (not raw_name or
                        raw_name.lower() == "modulename" or
                        "<ext>" in raw_name or
                        "/" in raw_name or
                        "\\" in raw_name or
                        raw_name.lower().endswith(".so") or
                        not valid_ext_name.match(raw_name)):
                        continue

                    clean_name = raw_name
                    if clean_name.lower().endswith(".dll"):
                        clean_name = clean_name[:-4]
                    if clean_name.lower().startswith("php_"):
                        clean_name = clean_name[4:]

                    should_enable = clean_name.lower() in enabled_list
                    is_currently_commented = line.lstrip().startswith(";")

                    if should_enable and is_currently_commented:
                        # Remove first semicolon to enable
                        semi_idx = line.find(";")
                        if semi_idx >= 0:
                            lines[i] = line[:semi_idx] + line[semi_idx+1:]
                    elif not should_enable and not is_currently_commented:
                        # Prepend semicolon to disable
                        lines[i] = ";" + line

            with open(php_ini_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            logger.log("PHP extensions updated in php.ini.", "INFO")

            msg = "PHP extensions saved to php.ini."
            if restart_apache and apache_manager.is_running():
                apache_manager.stop()
                time.sleep(1.0)
                ok, restart_msg = apache_manager.start_server()
                msg += f" Apache restarted: {restart_msg}"

            return jsonify({"success": True, "message": msg})
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed to update php.ini: {e}"}), 500

    @app.route("/api/php/cli", methods=["POST"])
    def run_php_cli():
        data = request.get_json() or {}
        raw_cmd = data.get("command", "").strip()
        if not raw_cmd:
            return jsonify({"output": "", "error": "No command provided."})

        php_dir = Path(config_manager.get("install_dir")) / "php"
        php_exe = php_dir / "php.exe"

        if not php_exe.exists():
            return jsonify({"output": "", "error": f"PHP binaries not found at {php_exe}. Install PHP first."})

        if raw_cmd.startswith("php "):
            cmd = [str(php_exe)] + raw_cmd.split(" ", 1)[1].split()
        elif raw_cmd.startswith("-"):
            cmd = [str(php_exe)] + raw_cmd.split()
        else:
            cmd = [str(php_exe), "-r", raw_cmd]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return jsonify({
                "output": res.stdout,
                "error": res.stderr
            })
        except subprocess.TimeoutExpired:
            return jsonify({"output": "", "error": "Command timed out after 10 seconds."})
        except Exception as e:
            return jsonify({"output": "", "error": f"Execution error: {e}"})

    @app.route("/api/php/global", methods=["GET", "POST"])
    def handle_global_php():
        if request.method == "GET":
            try:
                php_path = get_system_php_path()
                if php_path:
                    return jsonify({"found": True, "path": php_path})
                return jsonify({"found": False, "path": ""})
            except Exception as e:
                return jsonify({"found": False, "error": str(e)})

        # POST: trigger PowerShell script as Admin
        php_dir = Path(config_manager.get("install_dir")) / "php"
        if not (php_dir / "php.exe").exists():
            return jsonify({"success": False, "message": "PHP is not installed in PyAMPP yet."}), 400

        ps_script = RESOURCE_DIR / "core" / "setup_global_php.ps1"
        if not ps_script.exists():
            return jsonify({"success": False, "message": f"PowerShell helper script not found at {ps_script}"}), 500

        try:
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"Start-Process powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script}\" -TargetPhpPath \"{php_dir}\"' -Verb RunAs -Wait"
            ]
            subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            
            # Immediately refresh process environment from registry
            resolved_php = get_system_php_path()
            logger.log(f"Global PHP setup completed. Resolved path: {resolved_php}", "INFO")
            return jsonify({
                "success": True,
                "message": "Global PHP configured. Reopen your terminal windows to recognize the updated PATH.",
                "path": resolved_php or str(php_dir / "php.exe")
            })
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed to execute administrator setup: {e}"}), 500

    @app.route("/api/diagnostics/run", methods=["GET"])
    def run_diagnostics():
        apache_port = config_manager.get("apache_port")
        mysql_port = config_manager.get("mysql_port")

        def test_port(port):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return {"ok": True, "status": "In Use / Listening", "detail": f"Port {port} is active and accepting connections."}
                return {"ok": False, "status": "Closed / Available", "detail": f"Port {port} is not listening."}

        # Apache Port
        res_ap = test_port(apache_port)

        # Apache HTTP Check
        import urllib.request
        res_http = {"ok": False, "status": "Unreachable", "detail": "HTTP request failed."}
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{apache_port}", headers={"User-Agent": "PyAMPP-Diagnostics"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                res_http = {"ok": True, "status": f"HTTP {resp.status} OK", "detail": "Apache responded successfully."}
        except Exception as e:
            res_http = {"ok": False, "status": "Offline / Unreachable", "detail": str(e)}

        # MySQL Port
        res_mp = test_port(mysql_port)

        # MySQL Ping
        res_mc = {"ok": False, "status": "No response", "detail": "Could not connect to MySQL socket."}
        try:
            t0 = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                s.connect(("127.0.0.1", mysql_port))
                t1 = time.time()
                res_mc = {"ok": True, "status": f"{(t1 - t0)*1000:.1f}ms", "detail": "TCP socket connected successfully."}
        except Exception as e:
            res_mc = {"ok": False, "status": "Connection Refused", "detail": str(e)}

        # PHP check
        php_dir = Path(config_manager.get("install_dir")) / "php"
        php_exe = php_dir / "php.exe"
        res_php = {"ok": False, "status": "Missing", "detail": "PHP binary not found."}
        if php_exe.exists():
            try:
                out = subprocess.run([str(php_exe), "-v"], capture_output=True, text=True, timeout=2, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if out.returncode == 0:
                    res_php = {"ok": True, "status": "Valid", "detail": out.stdout.splitlines()[0]}
            except Exception as e:
                res_php = {"ok": False, "status": "Error", "detail": str(e)}

        return jsonify({
            "apache_port": res_ap,
            "apache_http": res_http,
            "mysql_port": res_mp,
            "mysql_conn": res_mc,
            "php_cli": res_php
        })

    @app.route("/api/diagnostics/ssl", methods=["POST"])
    def check_ssl():
        data = request.get_json() or {}
        host = data.get("host", "localhost").strip()
        port = int(data.get("port", 443))

        try:
            from datetime import datetime, timezone
            import tempfile

            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            with socket.create_connection((host, port), timeout=4.0) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    der = ssock.getpeercert(binary_form=True)
                    if not der:
                        return jsonify({
                            "valid": False,
                            "error": "No certificate presented by remote host"
                        })

                    subject_str = host
                    issuer_str = "Self-signed or internal certificate"
                    not_after_str = None
                    days_left = None

                    try:
                        from cryptography import x509
                        from cryptography.hazmat.backends import default_backend
                        c = x509.load_der_x509_certificate(der, default_backend())
                        cn = c.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                        if cn:
                            subject_str = cn[0].value
                        org = c.issuer.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)
                        icn = c.issuer.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
                        if org:
                            issuer_str = org[0].value
                        elif icn:
                            issuer_str = icn[0].value
                        exp_dt = c.not_valid_after_utc if hasattr(c, 'not_valid_after_utc') else c.not_valid_after
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        not_after_str = exp_dt.strftime("%b %d %H:%M:%S %Y GMT")
                        days_left = (exp_dt - datetime.now(timezone.utc)).days
                    except Exception:
                        try:
                            pem = ssl.DER_cert_to_PEM_cert(der)
                            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as tf:
                                tf.write(pem)
                                tmp_name = tf.name
                            try:
                                dec = ssl._ssl._test_decode_cert(tmp_name)
                                sub_dict = dict(x[0] for x in dec.get('subject', []))
                                iss_dict = dict(x[0] for x in dec.get('issuer', []))
                                subject_str = sub_dict.get('commonName', host)
                                issuer_str = iss_dict.get('organizationName') or iss_dict.get('commonName', 'Self-signed or internal certificate')
                                not_after_str = dec.get('notAfter')
                                if not_after_str:
                                    exp_date = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                                    days_left = (exp_date - datetime.now(timezone.utc)).days
                            finally:
                                try:
                                    os.unlink(tmp_name)
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    is_valid = (days_left >= 0) if days_left is not None else True
                    return jsonify({
                        "valid": is_valid,
                        "subject": subject_str,
                        "issuer": issuer_str,
                        "expires": not_after_str or "Verified via TLS handshake",
                        "days_left": max(0, days_left) if days_left is not None else 0
                    })
        except Exception as e:
            return jsonify({
                "valid": False,
                "error": str(e)
            })

    @app.route("/api/updates/check", methods=["POST"])
    def check_updates():
        import requests
        url = config_manager.get("presets_url")
        if not url:
            return jsonify({"success": False, "message": "No presets URL configured."})

        # Normalize repository root URLs or blob URLs to raw presets.json
        clean_url = url.strip()
        if clean_url.rstrip("/").endswith("github.com/rdevz-ph/PyAMPP-Web") or clean_url.rstrip("/").endswith("github.com/rdevz-ph/PyAMPP-Windows"):
            clean_url = f"https://raw.githubusercontent.com/{clean_url.split('github.com/')[1].strip('/')}/main/presets.json"
        elif "github.com" in clean_url and "/blob/" in clean_url:
            clean_url = clean_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

        try:
            r = requests.get(clean_url, timeout=10)
            r.raise_for_status()
            new_presets = r.json()
            update_presets(new_presets)
            logger.log("Preset definitions refreshed from remote repository.", "INFO")
            return jsonify({"success": True, "message": "Component presets updated successfully."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Update check failed: {e}"})

    @app.route('/api/config/browse', methods=['POST', 'GET'])
    @app.route('/api/utils/browse-folder', methods=['POST', 'GET'])
    def browse_directory():
        try:
            data = request.get_json(silent=True) or {}
            initial_dir = data.get("initial_dir", "")
            if not initial_dir or not os.path.exists(initial_dir):
                initial_dir = config_manager.get("install_dir", "C:\\")

            if getattr(sys, 'frozen', False):
                cmd = [sys.executable, "--pick-folder", str(initial_dir)]
            else:
                main_py = str(Path(__file__).resolve().parent.parent / "main.py")
                cmd = [sys.executable, main_py, "--pick-folder", str(initial_dir)]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            selected = None
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("SELECTED_PATH:"):
                    selected = line[len("SELECTED_PATH:"):].strip()
                    break

            if not selected:
                # Fallback in case raw path was outputted
                for line in reversed(proc.stdout.splitlines()):
                    candidate = line.strip()
                    if candidate and os.path.exists(candidate):
                        selected = candidate
                        break

            if selected and os.path.exists(selected):
                selected = os.path.normpath(selected)
                return jsonify({"success": True, "path": selected})
            return jsonify({"success": False, "message": "No directory selected."})
        except Exception as e:
            logger.log(f"Browse directory error: {e}", "ERROR")
            return jsonify({"success": False, "message": str(e)})

    @app.route("/api/open-path", methods=["POST"])
    def open_target_path():
        data = request.get_json(silent=True) or {}
        target = data.get("target", "").strip()

        install_dir = Path(config_manager.get("install_dir"))
        resolved_path = None
        target_name = target

        if target in ("htdocs", "web_root"):
            raw_htdocs = config_manager.get("htdocs_dir")
            if raw_htdocs:
                resolved_path = Path(raw_htdocs)
            else:
                resolved_path = install_dir / "apache" / "Apache24" / "htdocs"
            target_name = "Document Root (htdocs)"
            resolved_path.mkdir(parents=True, exist_ok=True)
            ensure_sample_index_php()

        elif target in ("install_dir", "bin", "binaries"):
            resolved_path = install_dir
            target_name = "Binaries Directory"
            resolved_path.mkdir(parents=True, exist_ok=True)

        elif target in ("mysql_data", "data", "mysql_datadir"):
            raw_data = config_manager.get("mysql_data_dir")
            if raw_data:
                resolved_path = Path(raw_data)
            else:
                resolved_path = install_dir / "mysql_data"
            target_name = "MySQL Data Directory"
            resolved_path.mkdir(parents=True, exist_ok=True)

        elif target in ("php_ini", "php.ini"):
            resolved_path = install_dir / "php" / "php.ini"
            if not resolved_path.exists():
                dev_ini = install_dir / "php" / "php.ini-development"
                if dev_ini.exists():
                    try:
                        import shutil
                        shutil.copy2(dev_ini, resolved_path)
                    except Exception:
                        pass
            target_name = "php.ini"

        elif target in ("httpd_conf", "httpd.conf", "apache_conf"):
            resolved_path = install_dir / "apache" / "Apache24" / "conf" / "httpd.conf"
            target_name = "httpd.conf"

        elif target in ("my_ini", "my.ini", "mysql_conf"):
            mysql_dir = mysql_manager.find_mysql_dir()
            if mysql_dir and (mysql_dir / "my.ini").exists():
                resolved_path = mysql_dir / "my.ini"
            elif (install_dir / "mysql" / "my.ini").exists():
                resolved_path = install_dir / "mysql" / "my.ini"
            elif mysql_dir:
                resolved_path = mysql_dir / "my.ini"
            else:
                resolved_path = install_dir / "mysql" / "my.ini"
            target_name = "my.ini"

        elif target in ("apache_logs", "logs"):
            resolved_path = install_dir / "apache" / "Apache24" / "logs"
            target_name = "Apache Logs Directory"
            if resolved_path:
                resolved_path.mkdir(parents=True, exist_ok=True)

        if not resolved_path or not resolved_path.exists():
            return jsonify({
                "success": False,
                "message": f"{target_name} not found at {resolved_path if resolved_path else '-'}. Please ensure the component is installed."
            }), 404

        try:
            os.startfile(str(resolved_path))
            logger.log(f"Opened {target_name}: {resolved_path}", "INFO")
            return jsonify({
                "success": True,
                "message": f"Opened {target_name} in Windows"
            })
        except Exception as e:
            logger.log(f"Failed to open {target_name}: {e}", "ERROR")
            return jsonify({
                "success": False,
                "message": f"Failed to open {target_name}: {e}"
            }), 500

    # ==========================================
    # Background Component Download & Installation
    # ==========================================
    @app.route("/api/component/install", methods=["POST"])
    def install_components():
        global install_state
        with install_lock:
            if install_state["in_progress"]:
                return jsonify({"success": False, "message": "Another installation is already in progress."})

            data = request.get_json() or {}
            components = data.get("components", ["php", "apache", "mysql", "phpmyadmin"])

            install_state["in_progress"] = True
            install_state["title"] = "Starting Installation"
            install_state["message"] = "Preparing directories..."
            install_state["percent"] = 0
            install_state["error"] = None

            threading.Thread(target=_run_installation_worker, args=(components,), daemon=True).start()
            return jsonify({"success": True, "message": "Installation started."})

    @app.route("/api/component/progress", methods=["GET"])
    def get_progress():
        with install_lock:
            return jsonify(install_state)

    return app

def _run_installation_worker(components):
    global install_state
    try:
        install_dir = Path(config_manager.get("install_dir"))
        install_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = install_dir / "temp_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Stop active servers to avoid Windows file locks on binaries
        apache_manager.update_paths()
        mysql_manager.update_paths()
        was_apache = apache_manager.is_running()
        was_mysql = mysql_manager.is_running()

        if was_apache or was_mysql:
            with install_lock:
                install_state["title"] = "Stopping Active Services"
                install_state["message"] = "Stopping Apache and MySQL to prevent file locks..."
                install_state["percent"] = 0
            logger.log("Stopping active services before component installation...", "INFO")
            if was_apache:
                apache_manager.stop()
            if was_mysql:
                mysql_manager.stop()
            time.sleep(1.2)

        total = len(components)
        for idx, comp in enumerate(components):
            comp_key = comp.lower()
            url_key = f"{comp_key}_url" if comp_key != "phpmyadmin" else "phpmyadmin_url"
            url = config_manager.get(url_key)
            if not url:
                continue

            with install_lock:
                install_state["title"] = f"Installing {comp.upper()} ({idx+1}/{total})"
                install_state["message"] = f"Downloading {comp.upper()}..."
                install_state["percent"] = int((idx / total) * 100)

            logger.log(f"Downloading {comp} from {url}...", "INFO")
            archive_name = f"{comp_key}.zip"
            dest_archive = temp_dir / archive_name

            def progress_callback(pct):
                with install_lock:
                    if pct >= 0:
                        sub_pct = int(pct * 100)
                        install_state["percent"] = int(((idx + pct) / total) * 100)
                        install_state["message"] = f"Downloading {comp.upper()}: {sub_pct}%"

            success = download_file(url, dest_archive, progress_callback)
            if not success:
                raise RuntimeError(f"Failed to download {comp} from {url}")

            with install_lock:
                install_state["message"] = f"Extracting {comp.upper()} files..."

            logger.log(f"Extracting {comp}...", "INFO")

            if comp_key == "phpmyadmin":
                target = install_dir / "pma_tmp"
            else:
                target = install_dir / comp_key

            # Clean up old binaries before extraction (safely preserving data and htdocs)
            if target.exists() and comp_key != "phpmyadmin":
                logger.log(f"Cleaning old {comp_key} binaries before reinstall...", "INFO")
                try:
                    if len(str(target)) > 10:
                        to_keep = []
                        if comp_key == "mysql":
                            data_dir = Path(config_manager.get("mysql_data_dir")).resolve()
                            if data_dir.is_relative_to(target.resolve()):
                                to_keep.append(data_dir)
                        elif comp_key == "apache":
                            htdocs_dir = (target / "Apache24" / "htdocs").resolve()
                            if htdocs_dir.exists():
                                to_keep.append(htdocs_dir)
                            cfg_htdocs = Path(config_manager.get("htdocs_dir", "")).resolve()
                            if cfg_htdocs.exists() and cfg_htdocs.is_relative_to(target.resolve()):
                                to_keep.append(cfg_htdocs)

                        if to_keep:
                            surgical_cleanup(target, to_keep, logger)
                        else:
                            robust_rmtree(target)
                except Exception as e:
                    logger.log(f"Warning cleaning {comp_key} directory: {e}", "WARNING")

            target.mkdir(parents=True, exist_ok=True)

            if not extract_zip(dest_archive, target):
                raise RuntimeError(f"Failed to extract {comp_key} archive.")

            if comp_key == "php":
                configure_php(target, logger)
            elif comp_key == "apache":
                apache_manager.update_paths()
                apache_manager.configure()
                try:
                    apache_manager.enable_ssl(force=True)
                except Exception as e:
                    logger.log(f"Apache SSL configuration note: {e}", "WARNING")
            elif comp_key == "mysql":
                mysql_manager.update_paths()
            elif comp_key == "phpmyadmin":
                configure_pma(target, install_dir, logger)

            # Clean archive
            if dest_archive.exists():
                dest_archive.unlink(missing_ok=True)

        with install_lock:
            install_state["in_progress"] = False
            install_state["percent"] = 100
            install_state["title"] = "Installation Complete"
            install_state["message"] = "Components installed and configured."

        config_manager.set("wizard_completed", True)
        config_manager.save()
        ensure_sample_index_php()
        apache_manager.update_paths()
        mysql_manager.update_paths()
        logger.log("Component installation completed successfully.", "INFO")

    except Exception as e:
        with install_lock:
            install_state["in_progress"] = False
            install_state["error"] = str(e)
        logger.log(f"Component installation error: {e}", "ERROR")
