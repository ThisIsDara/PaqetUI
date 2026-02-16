"""
Build script for paqet GUI
Creates a standalone Windows executable with the paqet binary bundled inside.

Usage:
    python build.py

Requirements:
    pip install pyinstaller pyyaml

Output:
    dist/paqet_gui.exe - Standalone executable with bundled paqet binary
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Configuration
APP_NAME = "PaqetUI"
SCRIPT_NAME = "paqet_gui.py"
FONT_FILES = []  # Add font files if needed
PAQET_BINARY = "paqet_windows_amd64.exe"
ICON_FILE = "icon.ico"  # Optional icon file

def check_requirements():
    """Check if required packages are installed."""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("[X] PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("[OK] PyInstaller installed")
    
    try:
        import yaml
        print("[OK] PyYAML found")
    except ImportError:
        print("[X] PyYAML not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
        print("[OK] PyYAML installed")

def find_paqet_binary():
    """Find the paqet binary to bundle."""
    # Check in current directory
    gui_dir = Path(__file__).parent
    project_root = gui_dir.parent
    
    search_paths = [
        gui_dir / PAQET_BINARY,
        project_root / PAQET_BINARY,
        gui_dir / "paqet.exe",
        project_root / "paqet.exe",
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None

def build():
    """Build the executable."""
    gui_dir = Path(__file__).parent
    project_root = gui_dir.parent
    
    print("=" * 60)
    print("paqet GUI Builder")
    print("=" * 60)
    print()
    
    # Check requirements
    print("Checking requirements...")
    check_requirements()
    print()
    
    # Find paqet binary
    print("Looking for paqet binary...")
    paqet_binary = find_paqet_binary()
    
    if paqet_binary:
        print(f"[OK] Found paqet binary: {paqet_binary}")
    else:
        print(f"[!] Warning: paqet binary not found. The exe will work but won't have bundled binary.")
        print(f"  Expected locations:")
        print(f"    - {gui_dir / PAQET_BINARY}")
        print(f"    - {project_root / PAQET_BINARY}")
    print()
    
    # Prepare PyInstaller command
    script_path = gui_dir / SCRIPT_NAME
    
    if not script_path.exists():
        print(f"[X] Error: {SCRIPT_NAME} not found in {gui_dir}")
        sys.exit(1)
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--onefile",
        "--windowed",  # No console window
        "--clean",
        "--noconfirm",
    ]
    
    # Add icon if available
    icon_path = gui_dir / ICON_FILE
    if icon_path.exists():
        cmd.extend(["--icon", str(icon_path)])
        print(f"[OK] Using icon: {icon_path}")
    else:
        print(f"[i] No icon file found at {icon_path}")
    
    # Add paqet binary as binary (not data) - this ensures it's bundled correctly
    if paqet_binary:
        # Format: --add-binary "source;destination" (Windows uses ; as separator)
        cmd.extend(["--add-binary", f"{paqet_binary};."])
        print(f"[OK] Bundling paqet binary (as binary)")
    
    # Hidden imports that might be needed
    cmd.extend([
        "--hidden-import", "yaml",
        "--hidden-import", "sqlite3",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.scrolledtext",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
    ])
    
    # Add the script
    cmd.append(str(script_path))
    
    # Set working directory
    os.chdir(gui_dir)
    
    print()
    print("Building executable...")
    print(f"Command: {' '.join(cmd)}")
    print()
    
    # Run PyInstaller
    try:
        subprocess.check_call(cmd)
        print()
        print("=" * 60)
        print("[OK] Build successful!")
        print("=" * 60)
        
        dist_path = gui_dir / "dist" / f"{APP_NAME}.exe"
        if dist_path.exists():
            size_mb = dist_path.stat().st_size / (1024 * 1024)
            print(f"Output: {dist_path}")
            print(f"Size: {size_mb:.1f} MB")
            
            # Copy to project root as well
            root_output = project_root / f"{APP_NAME}.exe"
            shutil.copy2(dist_path, root_output)
            print(f"Also copied to: {root_output}")
            
            # Also copy the paqet binary to dist and project root (as backup)
            if paqet_binary and paqet_binary.exists():
                shutil.copy2(paqet_binary, gui_dir / "dist" / PAQET_BINARY)
                shutil.copy2(paqet_binary, project_root / PAQET_BINARY)
                print(f"Also copied binary to: {gui_dir / 'dist' / PAQET_BINARY}")
        
        print()
        print("The executable includes:")
        print("  • Python runtime")
        print("  • PyYAML library")
        print("  • SQLite database support")
        if paqet_binary:
            print(f"  • Bundled paqet binary ({PAQET_BINARY})")
        print()
        print("You can distribute the single .exe file to users.")
        
    except subprocess.CalledProcessError as e:
        print(f"[X] Build failed with error code {e.returncode}")
        sys.exit(1)

def clean():
    """Clean build artifacts."""
    gui_dir = Path(__file__).parent
    
    dirs_to_remove = ["build", "dist", "__pycache__"]
    files_to_remove = [f"{APP_NAME}.spec"]
    
    print("Cleaning build artifacts...")
    
    for dir_name in dirs_to_remove:
        dir_path = gui_dir / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"  Removed: {dir_path}")
    
    for file_name in files_to_remove:
        file_path = gui_dir / file_name
        if file_path.exists():
            file_path.unlink()
            print(f"  Removed: {file_path}")
    
    print("[OK] Clean complete")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        build()
