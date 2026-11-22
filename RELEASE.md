# PyAMPP 1.0.2-web Release Notes

## What's New

### Added
* Added an Auto-open webpage on launch preference checkbox in the controller window to open the web management dashboard automatically when the server starts.
* Added native High-DPI display scaling support and an explicit Application User Model ID on Windows so taskbar icons and text render crisply on high-resolution monitors.
* Added a 9-frame multi-resolution icon generator in the build script to package icons at all standard Windows DPI scaling sizes.
* Added support for PHP 8.6.0 download presets.

### Changed
* Updated PHP version presets to the latest security releases: PHP 8.5.13, 8.4.28, 8.3.37, and 8.2.36.
* Moved PHP 8.1.34 to archived releases in download presets.
* Updated window title bar and taskbar icon rendering using native Win32 messages to eliminate blurry icon scaling in desktop windows.

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

* PHP: 8.6.0, 8.5.13, 8.4.28, 8.3.37, 8.2.36, 8.1.34 (Archive), 8.0.30 (Archive), and 7.4.33 (Archive)
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
