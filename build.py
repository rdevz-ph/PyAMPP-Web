import os
import sys
import subprocess
import shutil
import customtkinter
from PIL import Image
from pathlib import Path
from core.config import VERSION

def generate_multi_dpi_icon(master_image_path: str = "docs/images/pyampp.png", output_ico_path: str = "app.ico"):
    """
    Packages all 9 standard Windows icon frames into a single .ico file
    to prevent blurry scaling across High-DPI and standard displays.
    """
    if not os.path.exists(master_image_path):
        return
    try:
        master = Image.open(master_image_path).convert("RGBA")
        sizes = [256, 128, 64, 48, 40, 32, 24, 20, 16]
        frames = [(s, s) for s in sizes]
        master.save(output_ico_path, format="ICO", sizes=frames)
        print(f"Generated multi-frame icon ({len(sizes)} frames): {output_ico_path}")
    except Exception as e:
        print(f"Notice: Could not regenerate icon: {e}")

def build():
    # Application settings
    app_name = f"PyAMPP_{VERSION}"
    main_script = "main.py"
    icon_path = "app.ico" 

    # Generate multi-resolution icon frames before building
    generate_multi_dpi_icon("docs/images/pyampp.png", icon_path) 

    # Get CustomTkinter path
    ctk_path = os.path.dirname(customtkinter.__file__)

    # Ensure we are in the PyAMPP directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print(f"--- Starting Build for {app_name} ---")

    # Clean previous builds
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean", # Always clean cache
        f"--add-data={ctk_path};customtkinter/",
        "--collect-all", "customtkinter",
        f"--add-data=core;core/",
        f"--add-data=gui;gui/",
        f"--add-data=web;web/",
        f"--add-data=app.ico;.",
        f"--name={app_name}",
        "--hidden-import=psutil",
        "--hidden-import=requests",
        "--hidden-import=customtkinter",
        "--hidden-import=flask",
        "--hidden-import=jinja2",
        "--hidden-import=werkzeug",
        # Exclude common VC++ runtimes to force the app to use system ones
        # and prevent conflicts with PHP's required versions.
        "--exclude-module", "vcruntime140",
        "--exclude-module", "vcruntime140_1",
        "--exclude-module", "msvcp140",
        # Explicitly exclude internal testing tools and heavy optional libraries
        "--exclude-module", "tester_server",
        "--exclude-module", "numpy",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "cryptography",
        "--exclude-module", "bcrypt",
        "--version-file=version.txt",
        main_script
    ]

    if icon_path and os.path.exists(icon_path):
        cmd.append(f"--icon={icon_path}")

    print(f"Executing: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True, shell=True)
        print(f"\n--- Build Successful! ---")
        print(f"Executable is located in: {os.path.abspath('dist')}")
    except subprocess.CalledProcessError as e:
        print(f"\n--- Build Failed! ---")
        print(e)

if __name__ == "__main__":
    build()
