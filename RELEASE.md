# PyAMPP 1.0.0-web Release Notes

PyAMPP 1.0.0-web is the initial release of the portable web development stack manager for Windows. It provides a browser-based management dashboard and a lightweight system tray controller to install, configure, and run Apache, MySQL, PHP, and phpMyAdmin without editing configuration files manually.

## Key Features

* Standalone Windows application that runs locally without requiring installation.
* Web Management Dashboard running at `http://127.0.0.1:5000` with real-time process monitoring, memory metrics, and port status for Apache and MySQL.
* Unified service controls to start, stop, and restart individual services or all servers at once.
* Component Setup Wizard to download, verify, and configure official binaries for Apache, MySQL, PHP, and phpMyAdmin using version presets.
* PHP Extensions Manager to search and toggle extensions in `php.ini` with an automatic Apache restart option.
* PHP CLI Tester to execute PHP commands and evaluate code snippets directly from the browser.
* Global PHP Setup tool to add or remove the portable PHP binary in the Windows system PATH using administrator elevation.
* Diagnostics and SSL Verification tool to test port listening status, TCP socket latency, and local HTTPS certificates.
* Real-time System Logs console with level filtering, auto-scroll, and log clearing controls.
* Paths configuration manager to set the base installation folder, custom document root (`htdocs`), and MySQL database directory.
* Windows system tray companion app to access quick controls, open the dashboard, or exit cleanly.
* Application update checker in the controller window with background checks, a manual Check for Updates button on the footer, and direct notifications for new releases.

## Included Version Presets

* PHP: 8.5.6, 8.4.21, 8.3.31, 8.2.31, 8.1.34, 8.0.30, and 7.4.33
* Apache: 2.4.66
* MySQL: 8.4.4, 8.0.40, and 5.7.44
* phpMyAdmin: 5.2.3, 5.2.2, and 5.2.1

## Quick Start

1. Download the `PyAMPP.exe` executable from the release assets.
2. Run the application. PyAMPP will minimize to your Windows system tray and open the dashboard in your default browser.
3. On first launch, follow the Component Setup Wizard to choose your preferred software versions and install the stack.
4. Click Start All on the dashboard to start your web server and database.

## Release History

For the complete release history, see [CHANGELOG.md](CHANGELOG.md).
