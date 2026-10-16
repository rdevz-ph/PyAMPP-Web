# Changelog

All notable changes to PyAMPP will be documented in this file.

## [1.0.0-web] - 2026-10-17

### Added
* Initial release of the PyAMPP portable web development stack manager for Windows.
* Added a local Web Management Dashboard with real-time process monitoring, memory metrics, and port status for Apache and MySQL.
* Added global service controls to start, stop, or restart all servers with unified status indicators.
* Added a Component Setup Wizard to install, verify, and update Apache, MySQL, PHP, and phpMyAdmin using version presets.
* Added an automatic server restart trigger when saving settings so running Apache and MySQL servers apply new ports and paths immediately.
* Added a PHP Extensions Manager to search and toggle extensions in `php.ini` with an automatic Apache restart option.
* Added a PHP CLI Tester to execute PHP commands, inspect module configurations, and test code snippets from the browser.
* Added a Global PHP Setup utility to register the portable PHP binary with the Windows system PATH using administrator elevation.
* Added a Diagnostics and SSL Verification tool to test port listening status, TCP socket latency, HTTP reachability, and local certificates.
* Added a real-time System Logs viewer with log level filtering, auto-scroll controls, and console log clearing.
* Added a Paths & Directories settings manager to configure the base installation folder, document root (`htdocs`), and MySQL data storage.
* Added a lightweight Windows system tray companion app to control the web dashboard and access quick actions from the notification area.
* Added an application update checker in the controller window with background checks, a manual Check for Updates button on the footer, and direct notifications when newer releases are available.
* Added version presets supporting PHP 7.4 through 8.5, Apache 2.4, MySQL 5.7 through 8.4, and phpMyAdmin 5.2.

