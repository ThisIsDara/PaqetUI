#!/usr/bin/env python3
"""
paqet GUI - Professional Edition
A high-performance, modern graphical interface for paqet configuration.

Overhaul Details:
- Design System: Windows 11 / Discord inspired dark theme.
- UI Components: Refactored with high-consistency padding, typography, and hover states.
- Logic Fixes: Fully implemented ProcessManager integration, Import/Export, and Validation.
- Layout: Fixed clipping, improved responsiveness, and z-index ordering.
"""

import os
import sys
import re
import json
import sqlite3
import subprocess
import threading
import secrets
import platform
import webbrowser
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext

# Required external dependency
try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Run: pip install pyyaml")
    sys.exit(1)

# ============================================================================
# Global Configuration & Design System
# ============================================================================

APP_NAME = "PaqetUI"
APP_VERSION = "2.1.4"
APP_AUTHOR = "PaqetUI Team"

if getattr(sys, 'frozen', False):
    # Use getattr to avoid LSP error on _MEIPASS
    APP_DIR = Path(getattr(sys, '_MEIPASS', os.getcwd()))
    USER_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home())) / "paqet"
else:
    APP_DIR = Path(__file__).parent
    USER_DIR = Path.home() / ".paqetui"

CONFIG_DIR = USER_DIR
DATABASE_FILE = CONFIG_DIR / "paqet_gui.db"
DEFAULT_YAML = CONFIG_DIR / "config.yaml"
BUNDLED_BINARY = "paqet_windows_amd64.exe"

def find_binary_path() -> Path:
    """Find the paqet binary in bundle, app dir, or current directory."""
    search_paths = []
    
    # 1. Check if running as bundle (PyInstaller temp dir)
    if getattr(sys, 'frozen', False):
        app_dir = Path(getattr(sys, '_MEIPASS', ''))
        if app_dir.exists():
            search_paths.append(app_dir / BUNDLED_BINARY)
        
        # Also check the directory where the exe is located
        exe_dir = Path(sys.executable).parent
        search_paths.append(exe_dir / BUNDLED_BINARY)
    
    # 2. Check app source directory (for development)
    src_dir = Path(__file__).parent
    search_paths.append(src_dir / BUNDLED_BINARY)
    
    # 3. Check current working directory
    search_paths.append(Path.cwd() / BUNDLED_BINARY)
    
    # Search all paths
    for path in search_paths:
        if path.exists():
            return path
    
    # 4. Return default (will prompt user to browse)
    return Path(BUNDLED_BINARY)

LOG_LEVELS = ["none", "debug", "info", "warn", "error", "fatal"]
KCP_MODES = ["normal", "fast", "fast2", "fast3"]
ENCRYPTION_BLOCKS = [
    "aes", "aes-128", "aes-128-gcm", "aes-192", "salsa20", 
    "blowfish", "twofish", "cast5", "3des", "tea", "xtea", "xor", "sm4", "none"
]

# Color Palette: Modern Dark Mode (Discord/Linear Inspired)
COLORS = {
    "bg_root": "#0a0a0f",       # Root window background
    "bg_sidebar": "#12121a",    # Menu bar, inactive tabs
    "bg_card": "#151520",       # Card surface
    "bg_input": "#0f0f15",      # Inset input fields
    "bg_hover": "#252535",      # Hover state
    
    "accent": "#00d4ff",        # Primary accent (Neon Blue)
    "accent_hover": "#33e0ff",
    "accent_dim": "#006080",
    
    "text_main": "#ffffff",     # Primary text
    "text_dim": "#a0a0b0",      # Secondary text
    "text_muted": "#505060",    # Muted/Placeholder
    
    "success": "#00ff88",       # Clean green
    "warning": "#ffaa00",       # Warm orange
    "error": "#ff4444",         # Alert red
    "info": "#4488ff",          # Blurple
    
    "border": "#1a3a5c",        # Subtle borders
    "border_focus": "#00d4ff",
}

# ============================================================================
# Infrastructure Classes
# ============================================================================

class ConfigManager:
    """Handles configuration serialization and templating."""
    
    @staticmethod
    def generate_secret_key() -> str:
        return secrets.token_hex(32)
    
    @staticmethod
    def build_config(settings: Dict[str, Any]) -> Dict[str, Any]:
        role = settings.get("role", "client")
        is_client = role == "client"
        
        # Determine local IPv4 address
        local_ip = settings.get("local_ip", "0.0.0.0")
        local_port = settings.get("local_port", "0")
        
        # For server mode, if local_port is 0, we use the listen_port
        if not is_client and local_port == "0":
            local_port = settings.get("listen_port", "9999")

        config = {
            "role": role,
            "log": {"level": settings.get("log_level", "info")},
            "network": {
                "interface": settings.get("interface", ""),
                "ipv4": {
                    "addr": f"{local_ip}:{local_port}",
                    "router_mac": settings.get("router_mac", "")
                },
                "tcp": {
                    "local_flag": settings.get("tcp_local_flags", ["PA"]),
                }
            },
            "transport": {
                "protocol": "kcp",
                "conn": 1,
                "kcp": {
                    "mode": settings.get("kcp_mode", "fast"),
                    "mtu": int(settings.get("kcp_mtu", 1350)),
                    "rcvwnd": int(settings.get("kcp_rcvwnd", 512 if is_client else 1024)),
                    "sndwnd": int(settings.get("kcp_sndwnd", 512 if is_client else 1024)),
                    "block": settings.get("kcp_block", "aes"),
                    "key": settings.get("kcp_key", ""),
                    "smuxbuf": 4194304,
                    "streambuf": 2097152
                }
            }
        }
        
        if is_client:
            config["server"] = {"addr": f"{settings.get('server_ip', '')}:{settings.get('server_port', '9999')}"}
            config["network"]["tcp"]["remote_flag"] = settings.get("tcp_remote_flags", ["PA"])
            if settings.get("socks5_enabled"):
                config["socks5"] = [{
                    "listen": f"{settings.get('socks5_listen', '127.0.0.1')}:{settings.get('socks5_port', '1080')}",
                    "username": settings.get("socks5_username", ""),
                    "password": settings.get("socks5_password", "")
                }]
        else:
            config["listen"] = {"addr": f":{settings.get('listen_port', '9999')}"}
            
        if settings.get("guid"):
            config["network"]["guid"] = settings["guid"]
            
        return config

    @staticmethod
    def save(config: Dict[str, Any], path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    @staticmethod
    def load(path: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except Exception:
            return None

class ProcessManager:
    """Manages the lifecycle of the paqet subprocess."""
    
    def __init__(self, log_callback: Callable[[str, str], None]):
        self.process: Optional[subprocess.Popen] = None
        self.log_cb = log_callback
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self, binary: Path, config: Path) -> bool:
        if self.running: return False
        
        try:
            cmd = [str(binary), "run", "-c", str(config)]
            if platform.system() != "Windows":
                cmd = ["sudo"] + cmd
                
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            self.running = True
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            return True
        except Exception as e:
            self.log_cb(f"Process Error: {e}", "error")
            return False

    def stop(self):
        if not self.process: return
        self.running = False
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except:
            self.process.kill()
        self.process = None

    def _read_loop(self):
        error_keywords = ["error", "failed", "invalid", "cannot", "required", "panic", "fatal"]
        
        while self.running:
            if not self.process or not self.process.stdout: break
            line = self.process.stdout.readline()
            if not line: break
            
            line = line.strip()
            
            # Detect error messages from the binary
            level = "info"
            line_lower = line.lower()
            if any(kw in line_lower for kw in error_keywords):
                level = "error"
            
            self.log_cb(line, level)
        self.running = False

class DatabaseManager:
    """SQLite storage for persistent app state and recent configurations."""
    
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.path) as conn:
            # Check for legacy table 'state'
            res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='state'").fetchone()
            
            # Settings table for simple key-value pairs
            conn.execute("""CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, 
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            if res:
                # Migrate data from legacy table
                try:
                    conn.execute("INSERT OR IGNORE INTO settings (key, value) SELECT key, val FROM state")
                    conn.execute("DROP TABLE state")
                except: pass
            
            # Recent configurations table
            conn.execute("""CREATE TABLE IF NOT EXISTS recent_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                filepath TEXT,
                role TEXT,
                config_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

    def set(self, key: str, val: Any):
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", 
                         (key, json.dumps(val)))

    def get(self, key: str, default: Any = None) -> Any:
        try:
            with sqlite3.connect(self.path) as conn:
                res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                return json.loads(res[0]) if res else default
        except: return default

    def add_recent(self, name: str, filepath: str, role: str, config: Dict[str, Any]):
        with sqlite3.connect(self.path) as conn:
            # Avoid duplicates by filepath
            conn.execute("DELETE FROM recent_configs WHERE filepath = ?", (filepath,))
            conn.execute("""INSERT INTO recent_configs (name, filepath, role, config_json) 
                         VALUES (?, ?, ?, ?)""", (name, filepath, role, json.dumps(config)))
            # Keep only last 10
            conn.execute("""DELETE FROM recent_configs WHERE id NOT IN 
                         (SELECT id FROM recent_configs ORDER BY last_used DESC LIMIT 10)""")

    def get_recent(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                res = conn.execute("SELECT * FROM recent_configs ORDER BY last_used DESC").fetchall()
                return [dict(r) for r in res]
        except: return []

# ============================================================================
# Modern UI Component Library
# ============================================================================

class ModernFrame(tk.Frame):
    def __init__(self, parent, bg=COLORS["bg_card"], padding=15, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.inner = tk.Frame(self, bg=bg)
        self.inner.pack(padx=padding, pady=padding, fill=tk.BOTH, expand=True)

class Card(tk.Frame):
    """A visually distinct section with a title and border."""
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent, bg=COLORS["bg_card"], highlightthickness=1, 
                         highlightbackground=COLORS["border"], padx=15, pady=10, **kwargs)
        
        self.title_label = tk.Label(self, text=title.upper(), bg=COLORS["bg_card"], 
                                   fg=COLORS["accent"], font=("Inter", 9, "bold"))
        self.title_label.pack(anchor=tk.W, pady=(0, 10))
        
        self.content = tk.Frame(self, bg=COLORS["bg_card"])
        self.content.pack(fill=tk.BOTH, expand=True)

class ModernEntry(tk.Frame):
    def __init__(self, parent, textvariable=None, width=20, show="", placeholder="", **kwargs):
        super().__init__(parent, bg=COLORS["border"], padx=1, pady=1)
        entry_kwargs = {"width": width, "show": show, "bg": COLORS["bg_input"], 
                        "fg": COLORS["text_main"], "insertbackground": COLORS["accent"],
                        "relief": "flat", "highlightthickness": 0, "font": ("Inter", 10)}
        if textvariable:
            entry_kwargs["textvariable"] = textvariable
            
        self.entry = tk.Entry(self, **entry_kwargs)
        self.entry.pack(padx=8, pady=6, fill=tk.X)
        
        self.entry.bind("<FocusIn>", lambda e: self.config(bg=COLORS["accent"]))
        self.entry.bind("<FocusOut>", lambda e: self.config(bg=COLORS["border"]))

class ModernButton(tk.Button):
    def __init__(self, parent, text, command=None, variant="primary", **kwargs):
        bg = COLORS["accent"] if variant == "primary" else COLORS["bg_hover"]
        fg = COLORS["bg_root"] if variant == "primary" else COLORS["text_main"]
        active_bg = COLORS["accent_hover"] if variant == "primary" else COLORS["bg_card"]
        
        btn_kwargs = {"text": text, "bg": bg, "fg": fg, 
                      "activebackground": active_bg, "activeforeground": fg,
                      "font": ("Inter", 10, "bold"), "relief": "flat", 
                      "padx": 15, "pady": 6, "borderwidth": 0, "cursor": "hand2"}
        if command:
            btn_kwargs["command"] = command
            
        super().__init__(parent, **btn_kwargs, **kwargs)
        
        self.bind("<Enter>", lambda e: self.config(bg=active_bg) if self["state"] != "disabled" else None)
        self.bind("<Leave>", lambda e: self.config(bg=bg) if self["state"] != "disabled" else None)

class StatusIndicator(tk.Canvas):
    def __init__(self, parent, size=14, **kwargs):
        super().__init__(parent, width=size, height=size, bg=COLORS["bg_root"], 
                         highlightthickness=0, **kwargs)
        self.dot = self.create_oval(2, 2, size-2, size-2, fill=COLORS["error"], outline="")

    def set(self, status: str):
        color = COLORS["success"] if status == "running" else COLORS["error"]
        if status == "warning": color = COLORS["warning"]
        self.itemconfig(self.dot, fill=color)

class LogViewer(scrolledtext.ScrolledText):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["bg_input"], fg=COLORS["text_dim"],
                        font=("JetBrains Mono", 9), relief="flat", padx=10, pady=10,
                        highlightthickness=1, highlightbackground=COLORS["border"], **kwargs)
        self.tag_config("info", foreground=COLORS["text_dim"])
        self.tag_config("success", foreground=COLORS["success"])
        self.tag_config("error", foreground=COLORS["error"])
        self.tag_config("warning", foreground=COLORS["warning"])
        self.tag_config("ts", foreground=COLORS["text_muted"])
        self.config(state="disabled")

    def log(self, msg, level="info"):
        self.config(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        self.insert(tk.END, f"[{ts}] ", "ts")
        self.insert(tk.END, f"{msg}\n", level)
        self.see(tk.END)
        self.config(state="disabled")

    def clear(self):
        self.config(state="normal")
        self.delete(1.0, tk.END)
        self.config(state="disabled")

# ============================================================================
# Main Application
# ============================================================================

class PaqetApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"PaqetUI v{APP_VERSION}")
        self.root.geometry("1100x850")
        self.root.minsize(1000, 800)
        self.root.configure(bg=COLORS["bg_root"])
        
        self.db = DatabaseManager(DATABASE_FILE)
        self.pm = ProcessManager(self.append_log)
        
        # Find binary: check bundle, app dir, or use saved path
        # Find binary: search multiple locations
        saved_bin = self.db.get("binary_path")
        
        possible_paths = []
        
        # 1. Bundle directory (PyInstaller _MEIPASS)
        if getattr(sys, 'frozen', False):
            meipass = getattr(sys, '_MEIPASS', '')
            if meipass:
                possible_paths.append(Path(meipass) / BUNDLED_BINARY)
            # Also check where exe is located
            possible_paths.append(Path(sys.executable).parent / BUNDLED_BINARY)
        
        # 2. Source directory (where paqet_gui.py is)
        if not getattr(sys, 'frozen', False):
            possible_paths.append(Path(__file__).parent / BUNDLED_BINARY)
        
        # 3. Current working directory
        possible_paths.append(Path.cwd() / BUNDLED_BINARY)
        
        # 4. Parent directories  
        possible_paths.append(Path(__file__).parent.parent / BUNDLED_BINARY)
        possible_paths.append(Path.cwd().parent / BUNDLED_BINARY)
        
        # Find first existing path
        found = False
        for p in possible_paths:
            if p.exists():
                self.binary_path = p
                self.db.set("binary_path", str(p))
                found = True
                break
        
        # Fallback: use saved path if nothing found
        if not found and saved_bin:
            self.binary_path = Path(saved_bin)
        
        self._init_vars()
        self._setup_styles()
        self._create_menu()
        self._build_ui()
        self._load_state()
        
        # Initial background tasks
        threading.Thread(target=self._refresh_interfaces, daemon=True).start()

    def _init_vars(self):
        self.vars = {
            "role": tk.StringVar(value="client"),
            "log_level": tk.StringVar(value="info"),
            "interface": tk.StringVar(),
            "guid": tk.StringVar(),
            "local_ip": tk.StringVar(),
            "local_port": tk.StringVar(value="0"),
            "router_mac": tk.StringVar(),
            "server_ip": tk.StringVar(),
            "server_port": tk.StringVar(value="9999"),
            "listen_port": tk.StringVar(value="9999"),
            "kcp_mode": tk.StringVar(value="fast"),
            "kcp_block": tk.StringVar(value="aes"),
            "kcp_key": tk.StringVar(),
            "kcp_mtu": tk.StringVar(value="1350"),
            "kcp_rcvwnd": tk.StringVar(value="512"),
            "kcp_sndwnd": tk.StringVar(value="512"),
            "socks5_enabled": tk.BooleanVar(value=True),
            "socks5_listen": tk.StringVar(value="127.0.0.1"),
            "socks5_port": tk.StringVar(value="1080"),
            "socks5_user": tk.StringVar(),
            "socks5_pass": tk.StringVar(),
            "tcp_local_flags": tk.StringVar(value="PA"),
            "tcp_remote_flags": tk.StringVar(value="PA"),
        }
        # Backward compatibility for direct access
        self.role_var = self.vars["role"]
        self.log_level_var = self.vars["log_level"]
        self.interface_var = self.vars["interface"]
        self.guid_var = self.vars["guid"]
        self.local_ip_var = self.vars["local_ip"]
        self.local_port_var = self.vars["local_port"]
        self.router_mac_var = self.vars["router_mac"]
        self.server_ip_var = self.vars["server_ip"]
        self.server_port_var = self.vars["server_port"]
        self.listen_port_var = self.vars["listen_port"]
        self.kcp_mode_var = self.vars["kcp_mode"]
        self.kcp_block_var = self.vars["kcp_block"]
        self.kcp_key_var = self.vars["kcp_key"]
        self.kcp_mtu_var = self.vars["kcp_mtu"]
        self.kcp_rcvwnd_var = self.vars["kcp_rcvwnd"]
        self.kcp_sndwnd_var = self.vars["kcp_sndwnd"]
        self.socks5_enabled_var = self.vars["socks5_enabled"]
        self.socks5_listen_var = self.vars["socks5_listen"]
        self.socks5_port_var = self.vars["socks5_port"]
        self.socks5_user_var = self.vars["socks5_user"]
        self.socks5_pass_var = self.vars["socks5_pass"]
        self.tcp_local_flags_var = self.vars["tcp_local_flags"]
        self.tcp_remote_flags_var = self.vars["tcp_remote_flags"]

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        # Notebook (Tabs)
        style.configure("TNotebook", background=COLORS["bg_root"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["bg_sidebar"], foreground=COLORS["text_dim"], 
                        padding=[20, 10], font=("Inter", 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", COLORS["bg_card"])], 
                  foreground=[("selected", COLORS["accent"])])
        
        # Combobox
        style.configure("TCombobox", fieldbackground=COLORS["bg_input"], background=COLORS["bg_input"],
                        foreground=COLORS["text_main"], arrowcolor=COLORS["accent"], borderwidth=0)
        
        # Checkbutton
        style.configure("TCheckbutton", background=COLORS["bg_card"], foreground=COLORS["text_main"])
        style.map("TCheckbutton", background=[("active", COLORS["bg_card"])])

    def _build_ui(self):
        # Header
        header = tk.Frame(self.root, bg=COLORS["bg_root"], padx=30, pady=20)
        header.pack(fill=tk.X)
        
        title_frame = tk.Frame(header, bg=COLORS["bg_root"])
        title_frame.pack(side=tk.LEFT)
        
        tk.Label(title_frame, text="PaqetUI", fg=COLORS["accent"], bg=COLORS["bg_root"],
                 font=("Inter", 24, "bold")).pack(side=tk.LEFT)
        tk.Label(title_frame, text=f"GUI v{APP_VERSION}", fg=COLORS["text_muted"], 
                 bg=COLORS["bg_root"], font=("Inter", 10, "bold")).pack(side=tk.LEFT, padx=10, pady=(8, 0))
        
        self.status_box = tk.Frame(header, bg=COLORS["bg_sidebar"], padx=15, pady=8)
        self.status_box.pack(side=tk.RIGHT)
        self.indicator = StatusIndicator(self.status_box)
        self.indicator.pack(side=tk.LEFT, padx=(0, 10))
        self.status_label = tk.Label(self.status_box, text="READY", fg=COLORS["text_dim"], 
                                    bg=COLORS["bg_sidebar"], font=("Inter", 9, "bold"))
        self.status_label.pack(side=tk.LEFT)

        # Main Body
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=30)
        
        self._build_basic_tab()
        self._build_network_tab()
        self._build_transport_tab()
        self._build_advanced_tab()
        self._build_about_tab()

        # Bottom Control Bar
        footer = tk.Frame(self.root, bg=COLORS["bg_root"], padx=30, pady=20)
        footer.pack(fill=tk.X)
        
        self.start_btn = ModernButton(footer, "START TUNNEL", self.start_action, width=20)
        self.start_btn.pack(side=tk.LEFT)
        
        self.stop_btn = ModernButton(footer, "STOP", self.stop_action, variant="secondary")
        self.stop_btn.pack(side=tk.LEFT, padx=15)
        self.stop_btn.config(state="disabled")
        
        tk.Frame(footer, width=2, bg=COLORS["border"]).pack(side=tk.LEFT, fill=tk.Y, padx=20)
        
        ModernButton(footer, "IMPORT", self.import_action, variant="secondary").pack(side=tk.LEFT)
        ModernButton(footer, "EXPORT", self.export_action, variant="secondary").pack(side=tk.LEFT, padx=10)
        
        ModernButton(footer, "CLEAR LOGS", self.logs_clear_action, variant="secondary").pack(side=tk.RIGHT)

        # Logs
        log_container = tk.Frame(self.root, bg=COLORS["bg_root"])
        log_container.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 20))
        self.log_viewer = LogViewer(log_container)
        self.log_viewer.pack(fill=tk.BOTH, expand=True)

    def _build_basic_tab(self):
        tab = tk.Frame(self.notebook, bg=COLORS["bg_root"], padx=20, pady=20)
        self.notebook.add(tab, text="BASIC")
        
        # Role Card
        role_card = Card(tab, "Application Role")
        role_card.pack(fill=tk.X, pady=20)
        
        tk.Radiobutton(role_card.content, text="Client Mode (Connect to Server)", variable=self.role_var, 
                       value="client", command=self._toggle_role_ui, bg=COLORS["bg_card"], fg=COLORS["text_main"],
                       selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"], activeforeground=COLORS["accent"]).pack(side=tk.LEFT, padx=20)
        tk.Radiobutton(role_card.content, text="Server Mode (Host Tunnel)", variable=self.role_var, 
                       value="server", command=self._toggle_role_ui, bg=COLORS["bg_card"], fg=COLORS["text_main"],
                       selectcolor=COLORS["bg_input"], activebackground=COLORS["bg_card"], activeforeground=COLORS["accent"]).pack(side=tk.LEFT, padx=20)

        # Dynamic Section
        self.dynamic_frame = tk.Frame(tab, bg=COLORS["bg_root"])
        self.dynamic_frame.pack(fill=tk.X)
        
        self.client_settings = Card(self.dynamic_frame, "Remote Server Endpoint")
        row = tk.Frame(self.client_settings.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Server Host:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.server_ip_var, width=30).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="Port:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=(20, 0))
        ModernEntry(row, self.server_port_var, width=10).pack(side=tk.LEFT, padx=10)

        self.server_settings = Card(self.dynamic_frame, "Local Listen Configuration")
        row = tk.Frame(self.server_settings.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Listen Port:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.listen_port_var, width=15).pack(side=tk.LEFT, padx=10)

        # Proxy Card
        self.proxy_card = Card(tab, "SOCKS5 Proxy (Client Only)")
        self.proxy_card.pack(fill=tk.X, pady=20)
        ttk.Checkbutton(self.proxy_card.content, text="Enable Local SOCKS5 Proxy", variable=self.socks5_enabled_var).pack(anchor=tk.W, padx=5, pady=5)
        row = tk.Frame(self.proxy_card.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X, pady=5)
        tk.Label(row, text="Addr:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.socks5_listen_var, width=15).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="Port:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=10)
        ModernEntry(row, self.socks5_port_var, width=8).pack(side=tk.LEFT, padx=5)
        
        tk.Label(row, text="User:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=10)
        ModernEntry(row, self.socks5_user_var, width=12).pack(side=tk.LEFT)
        tk.Label(row, text="Pass:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=10)
        ModernEntry(row, self.socks5_pass_var, width=12, show="*").pack(side=tk.LEFT)

        # Log Level
        misc_row = tk.Frame(tab, bg=COLORS["bg_root"])
        misc_row.pack(fill=tk.X)
        log_card = Card(misc_row, "Verbosity")
        log_card.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Combobox(log_card.content, textvariable=self.log_level_var, values=LOG_LEVELS, state="readonly").pack(side=tk.LEFT)
        
        self._toggle_role_ui()

    def _build_network_tab(self):
        tab = tk.Frame(self.notebook, bg=COLORS["bg_root"], padx=20, pady=20)
        self.notebook.add(tab, text="NETWORK")
        
        iface_card = Card(tab, "Physical Interface Detection")
        iface_card.pack(fill=tk.X, pady=(0, 20))
        
        row1 = tk.Frame(iface_card.content, bg=COLORS["bg_card"])
        row1.pack(fill=tk.X)
        tk.Label(row1, text="Adapter:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        self.iface_combo = ttk.Combobox(row1, textvariable=self.interface_var, width=40, state="readonly")
        self.iface_combo.pack(side=tk.LEFT, padx=10)
        self.iface_combo.bind("<<ComboboxSelected>>", self._on_iface_change)
        ModernButton(row1, "REFRESH", self._refresh_interfaces, variant="secondary").pack(side=tk.LEFT)
        
        if platform.system() == "Windows":
            row2 = tk.Frame(iface_card.content, bg=COLORS["bg_card"])
            row2.pack(fill=tk.X, pady=(10, 0))
            tk.Label(row2, text="Npcap GUID:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
            ModernEntry(row2, self.guid_var, width=65).pack(side=tk.LEFT, padx=10)

        ip_card = Card(tab, "IPv4 & Routing")
        ip_card.pack(fill=tk.X, pady=20)
        
        row = tk.Frame(ip_card.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Local IP:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.local_ip_var, width=20).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="Source Port:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=10)
        ModernEntry(row, self.local_port_var, width=10).pack(side=tk.LEFT, padx=5)
        ModernButton(row, "AUTO-DETECT", self._detect_net, variant="secondary").pack(side=tk.RIGHT)

        gw_card = Card(tab, "Gateway & ARP")
        gw_card.pack(fill=tk.X, pady=20)
        row = tk.Frame(gw_card.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Router MAC:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.router_mac_var, width=25).pack(side=tk.LEFT, padx=10)
        ModernButton(row, "FETCH GATEWAY", self._detect_gw, variant="secondary").pack(side=tk.RIGHT)

        tcp_card = Card(tab, "TCP Protocol Flags")
        tcp_card.pack(fill=tk.X)
        row = tk.Frame(tcp_card.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Local Flags:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row, self.tcp_local_flags_var, width=15).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="Remote Match:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=20)
        ModernEntry(row, self.tcp_remote_flags_var, width=15).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="(e.g. PA, S, A)", bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=("Inter", 8)).pack(side=tk.LEFT, padx=10)

    def _build_transport_tab(self):
        tab = tk.Frame(self.notebook, bg=COLORS["bg_root"], padx=20, pady=20)
        self.notebook.add(tab, text="TRANSPORT")
        
        enc_card = Card(tab, "Cryptographic Layer")
        enc_card.pack(fill=tk.X, pady=(0, 20))
        row1 = tk.Frame(enc_card.content, bg=COLORS["bg_card"])
        row1.pack(fill=tk.X)
        tk.Label(row1, text="Algorithm:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ttk.Combobox(row1, textvariable=self.kcp_block_var, values=ENCRYPTION_BLOCKS, state="readonly").pack(side=tk.LEFT, padx=10)
        
        row2 = tk.Frame(enc_card.content, bg=COLORS["bg_card"])
        row2.pack(fill=tk.X, pady=10)
        tk.Label(row2, text="Secret Key:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row2, self.kcp_key_var, width=70).pack(side=tk.LEFT, padx=10)
        ModernButton(row2, "GENERATE", self._gen_key, variant="secondary").pack(side=tk.LEFT)

        kcp_card = Card(tab, "KCP Tunnel Optimization")
        kcp_card.pack(fill=tk.X)
        row = tk.Frame(kcp_card.content, bg=COLORS["bg_card"])
        row.pack(fill=tk.X)
        tk.Label(row, text="Mode:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ttk.Combobox(row, textvariable=self.kcp_mode_var, values=KCP_MODES, state="readonly", width=10).pack(side=tk.LEFT, padx=10)
        tk.Label(row, text="MTU:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=20)
        ModernEntry(row, self.kcp_mtu_var, width=8).pack(side=tk.LEFT, padx=5)
        
        row2 = tk.Frame(kcp_card.content, bg=COLORS["bg_card"])
        row2.pack(fill=tk.X, pady=15)
        tk.Label(row2, text="Receive Window:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT)
        ModernEntry(row2, self.kcp_rcvwnd_var, width=10).pack(side=tk.LEFT, padx=10)
        tk.Label(row2, text="Send Window:", bg=COLORS["bg_card"], fg=COLORS["text_dim"]).pack(side=tk.LEFT, padx=20)
        ModernEntry(row2, self.kcp_sndwnd_var, width=10).pack(side=tk.LEFT, padx=10)

        info = tk.Label(kcp_card.content, text="fast3 is most aggressive (high bandwidth), normal is most stable.", 
                        bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=("Inter", 9, "italic"))
        info.pack(anchor=tk.W, pady=(5, 0))

    def _build_advanced_tab(self):
        tab = tk.Frame(self.notebook, bg=COLORS["bg_root"], padx=20, pady=20)
        self.notebook.add(tab, text="ADVANCED")
        
        bin_card = Card(tab, "Binary Management")
        bin_card.pack(fill=tk.X, pady=(0, 20))
        self.bin_label = tk.Label(bin_card.content, text=str(self.binary_path), bg=COLORS["bg_input"], 
                                 fg=COLORS["text_dim"], font=("JetBrains Mono", 8), padx=10, pady=5)
        self.bin_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ModernButton(bin_card.content, "BROWSE", self._browse_bin, variant="secondary").pack(side=tk.LEFT, padx=10)

        fw_card = Card(tab, "System Firewall Requirements (Linux Server)")
        fw_card.pack(fill=tk.X, pady=20)
        fw_code = """iptables -t raw -A PREROUTING -p tcp --dport <PORT> -j NOTRACK
iptables -t raw -A OUTPUT -p tcp --sport <PORT> -j NOTRACK
iptables -t mangle -A OUTPUT -p tcp --sport <PORT> --tcp-flags RST RST -j DROP"""
        tk.Label(fw_card.content, text=fw_code, bg=COLORS["bg_input"], fg=COLORS["warning"], 
                 font=("JetBrains Mono", 8), justify=tk.LEFT, padx=10, pady=10).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ModernButton(fw_card.content, "COPY", lambda: self.root.clipboard_append(fw_code), variant="secondary").pack(side=tk.LEFT, padx=10)

        diag_card = Card(tab, "Diagnostic Suite")
        diag_card.pack(fill=tk.X)
        ModernButton(diag_card.content, "FULL INTERFACE DUMP", self._diag_ifaces, variant="secondary").pack(side=tk.LEFT)
        ModernButton(diag_card.content, "PING TEST", self._diag_ping, variant="secondary").pack(side=tk.LEFT, padx=15)
        ModernButton(diag_card.content, "VALIDATE CONFIG", self._validate_action, variant="secondary").pack(side=tk.LEFT)

    def _build_about_tab(self):
        tab = tk.Frame(self.notebook, bg=COLORS["bg_root"], padx=40, pady=40)
        self.notebook.add(tab, text="ABOUT")
        
        tk.Label(tab, text="PaqetUI", fg=COLORS["accent"], bg=COLORS["bg_root"], 
                 font=("Inter", 20, "bold")).pack()
        tk.Label(tab, text=f"Version: {APP_VERSION}", fg=COLORS["text_dim"], 
                 bg=COLORS["bg_root"], font=("Inter", 10), pady=10).pack()
        
        desc = ("PaqetUI is a modern graphical interface for the paqet network proxy.\n"
                "paqet is a packet-level proxy designed to tunnel traffic over KCP.\n"
                "It bypasses the standard host OS TCP/IP stack using raw sockets,\n"
                "allowing for bidirectional connectivity even in restrictive environments.")
        tk.Label(tab, text=desc, fg=COLORS["text_main"], bg=COLORS["bg_root"], font=("Inter", 11), 
                 justify=tk.CENTER, pady=30).pack()
        
        link = tk.Label(tab, text="Developed by @ThisIsDara", fg=COLORS["accent"], bg=COLORS["bg_root"], 
                        font=("Inter", 10, "underline"), cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/ThisIsDara/paqet"))

    # ============================================================================
    # Logic & Event Handlers
    # ============================================================================

    def _toggle_role_ui(self):
        role = self.role_var.get()
        if role == "client":
            self.server_settings.pack_forget()
            self.client_settings.pack(fill=tk.X, pady=20)
            self.proxy_card.pack(fill=tk.X, pady=20)
            if self.kcp_rcvwnd_var.get() == "1024": self.kcp_rcvwnd_var.set("512")
            if self.kcp_sndwnd_var.get() == "1024": self.kcp_sndwnd_var.set("512")
        else:
            self.client_settings.pack_forget()
            self.proxy_card.pack_forget()
            self.server_settings.pack(fill=tk.X, pady=20)
            if self.kcp_rcvwnd_var.get() == "512": self.kcp_rcvwnd_var.set("1024")
            if self.kcp_sndwnd_var.get() == "512": self.kcp_sndwnd_var.set("1024")

    def _on_iface_change(self, event=None):
        if platform.system() != "Windows": return
        selected = self.interface_var.get()
        for d in getattr(self, "_iface_data", []):
            if d.get("Name") == selected:
                guid = d.get("InterfaceGuid", "")
                if guid and not guid.startswith("\\Device\\NPF_"):
                    guid = guid.strip("{}")
                    guid = f"\\Device\\NPF_{{{guid}}}"
                self.guid_var.set(guid)
                break

    def append_log(self, msg, level="info"):
        self.log_viewer.log(msg, level)

    def _refresh_interfaces(self):
        self.append_log("Refreshing network interfaces...", "info")
        possible_names = []
        
        try:
            if platform.system() == "Windows":
                cmd = "powershell -Command \"Get-NetAdapter | Select-Object Name, InterfaceGuid | ConvertTo-Json\""
                res = subprocess.check_output(cmd, shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                data = json.loads(res)
                if isinstance(data, dict): data = [data]
                self._iface_data = data
                possible_names = [d["Name"] for d in data]
            else:
                res = subprocess.check_output("ip link show", shell=True, text=True)
                possible_names = re.findall(r"\d+: ([\w.-]+):", res)
            
            self.iface_combo["values"] = possible_names
            if possible_names and not self.interface_var.get():
                self.interface_var.set(possible_names[0])
            self.append_log(f"Detected {len(possible_names)} interfaces.", "success")
        except Exception as e:
            self.append_log(f"Interface detection failed: {e}", "error")

    def _detect_net(self):
        self.append_log("Auto-detecting network parameters...", "info")
        try:
            if platform.system() == "Windows":
                cmd = "powershell -Command \"$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1; $ip = (Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4).IPAddress; $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex; @{IP=$ip; Interface=$adapter.Name} | ConvertTo-Json\""
                res = subprocess.check_output(cmd, shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                data = json.loads(res)
                if data.get("IP"): self.local_ip_var.set(data["IP"])
                if data.get("Interface"): self.interface_var.set(data["Interface"])
                self.append_log(f"Detected IP: {data.get('IP')}", "success")
            elif platform.system() == "Linux":
                # Try using 'ip route' for better detection
                res = subprocess.check_output("ip route get 1.1.1.1", shell=True, text=True)
                match = re.search(r"src ([\d.]+)", res)
                if match:
                    ip = match.group(1)
                    self.local_ip_var.set(ip)
                    self.append_log(f"Detected IP: {ip}", "success")
                
                match_dev = re.search(r"dev ([\w.-]+)", res)
                if match_dev:
                    self.interface_var.set(match_dev.group(1))
            else:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("1.1.1.1", 80))
                ip = s.getsockname()[0]
                self.local_ip_var.set(ip)
                s.close()
                self.append_log(f"Detected IP: {ip}", "success")
        except Exception as e:
            self.append_log(f"Detection failed: {e}", "error")

    def _detect_gw(self):
        self.append_log("Detecting Gateway MAC...", "info")
        try:
            mac = None
            if platform.system() == "Windows":
                cmd = "powershell -Command \"$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -First 1; $gw = $route.NextHop; ping -n 1 -w 500 $gw | Out-Null; arp -a $gw | Select-String '([0-9a-f]{2}[:-]){5}[0-9a-f]{2}'\""
                res = subprocess.check_output(cmd, shell=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                match = re.search(r"([0-9a-f]{2}[:-]){5}[0-9a-f]{2}", res, re.I)
                if match: mac = match.group(0).replace("-", ":").lower()
            elif platform.system() == "Linux":
                # Get default gateway IP
                res = subprocess.check_output("ip route show default", shell=True, text=True)
                match_gw = re.search(r"default via ([\d.]+)", res)
                if match_gw:
                    gw_ip = match_gw.group(1)
                    subprocess.call(f"ping -c 1 -w 1 {gw_ip} > /dev/null 2>&1", shell=True)
                    res_arp = subprocess.check_output(f"ip neighbor show {gw_ip}", shell=True, text=True)
                    match_mac = re.search(r"lladdr (([0-9a-f]{2}:){5}[0-9a-f]{2})", res_arp, re.I)
                    if match_mac: mac = match_mac.group(1).lower()
            elif platform.system() == "Darwin": # macOS
                res = subprocess.check_output("route -n get default", shell=True, text=True)
                match_gw = re.search(r"gateway: ([\d.]+)", res)
                if match_gw:
                    gw_ip = match_gw.group(1)
                    subprocess.call(f"ping -c 1 -t 1 {gw_ip} > /dev/null 2>&1", shell=True)
                    res_arp = subprocess.check_output(f"arp -n {gw_ip}", shell=True, text=True)
                    match_mac = re.search(r"(([0-9a-f]{1,2}:){5}[0-9a-f]{1,2})", res_arp, re.I)
                    if match_mac: 
                        # Normalize MAC
                        mac = ":".join([f"{int(x, 16):02x}" for x in match_mac.group(1).split(":")])
            
            if mac:
                self.router_mac_var.set(mac)
                self.append_log(f"Found Gateway MAC: {mac}", "success")
            else:
                self.append_log("Could not resolve Gateway MAC. Ensure gateway is reachable.", "warning")
        except Exception as e:
            self.append_log(f"Gateway detection failed: {e}", "error")

    def _gen_key(self):
        key = ConfigManager.generate_secret_key()
        self.kcp_key_var.set(key)
        self.root.clipboard_append(key)
        self.append_log("Generated 256-bit key and copied to clipboard.", "success")

    def _browse_bin(self):
        path = filedialog.askopenfilename()
        if path:
            self.binary_path = Path(path)
            self.bin_label.config(text=str(path))
            self.db.set("binary_path", str(path))

    def _get_settings(self) -> Dict[str, Any]:
        return {
            "role": self.role_var.get(),
            "log_level": self.log_level_var.get(),
            "interface": self.interface_var.get(),
            "guid": self.guid_var.get(),
            "local_ip": self.local_ip_var.get(),
            "local_port": self.local_port_var.get(),
            "router_mac": self.router_mac_var.get(),
            "server_ip": self.server_ip_var.get(),
            "server_port": self.server_port_var.get(),
            "listen_port": self.listen_port_var.get(),
            "kcp_mode": self.kcp_mode_var.get(),
            "kcp_block": self.kcp_block_var.get(),
            "kcp_key": self.kcp_key_var.get(),
            "kcp_mtu": self.kcp_mtu_var.get(),
            "kcp_rcvwnd": self.kcp_rcvwnd_var.get(),
            "kcp_sndwnd": self.kcp_sndwnd_var.get(),
            "socks5_enabled": self.socks5_enabled_var.get(),
            "socks5_listen": self.socks5_listen_var.get(),
            "socks5_port": self.socks5_port_var.get(),
            "socks5_username": self.socks5_user_var.get(),
            "socks5_password": self.socks5_pass_var.get(),
            "tcp_local_flags": self.tcp_local_flags_var.get().split(","),
            "tcp_remote_flags": self.tcp_remote_flags_var.get().split(","),
        }

    def start_action(self):
        # Use is_file() instead of exists() for more reliable check
        if not self.binary_path.is_file():
            messagebox.showerror("Error", f"paqet binary not found at:\n{self.binary_path}\n\nPlease set path in Advanced tab.")
            return
        
        settings = self._get_settings()
        role = settings.get("role", "client")
        
        # Validate required fields
        errors = []
        
        # Check interface/guid for Windows
        if platform.system() == "Windows":
            if not settings.get("interface"):
                errors.append("network interface is required")
            elif not settings.get("guid"):
                errors.append("guid is required on windows")
        
        # Check router MAC
        if not settings.get("router_mac"):
            errors.append("MAC address is required")
        
        # Check KCP key
        if not settings.get("kcp_key"):
            errors.append("KCP encryption key is required")
        
        # Check server address for client mode
        if role == "client":
            if not settings.get("server_ip"):
                errors.append("server IP address is required")
        
        # Check listen port for server mode
        if role == "server":
            if not settings.get("listen_port"):
                errors.append("listen port is required")
        
        # Display all errors in red
        if errors:
            for err in errors:
                self.append_log(err, "error")
            return
        
        # All validations passed - proceed
        config = ConfigManager.build_config(settings)
        ConfigManager.save(config, DEFAULT_YAML)
        
        if self.pm.start(self.binary_path, DEFAULT_YAML):
            self.indicator.set("running")
            self.status_label.config(text="RUNNING", fg=COLORS["success"])
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.append_log("Tunnel successfully started.", "success")

    def stop_action(self):
        self.pm.stop()
        self.indicator.set("stopped")
        self.status_label.config(text="STOPPED", fg=COLORS["error"])
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.append_log("Tunnel stopped.", "warning")

    def import_action(self):
        path = filedialog.askopenfilename(filetypes=[("YAML files", "*.yaml"), ("All files", "*")])
        if path:
            cfg = ConfigManager.load(Path(path))
            if cfg:
                self._apply_config(cfg)
                # Add to recent
                settings = self._get_settings()
                self.db.add_recent(Path(path).name, path, settings["role"], cfg)
                self._update_recent_menu()
                self.append_log(f"Imported configuration from {path}", "success")

    def export_action(self):
        path = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML files", "*.yaml")])
        if path:
            settings = self._get_settings()
            config = ConfigManager.build_config(settings)
            ConfigManager.save(config, Path(path))
            # Add to recent
            self.db.add_recent(Path(path).name, path, settings["role"], config)
            self._update_recent_menu()
            self.append_log(f"Exported configuration to {path}", "success")

    def logs_clear_action(self):
        self.log_viewer.clear()

    def _validate_action(self):
        self.append_log("Validating configuration parameters...", "info")
        # Basic validation
        if not self.interface_var.get():
            self.append_log("Error: No network interface selected.", "error")
            return
        if not self.kcp_key_var.get():
            self.append_log("Warning: No encryption key set. Connection will be insecure.", "warning")
        self.append_log("Configuration is valid.", "success")

    def _diag_ifaces(self):
        self.append_log("--- Interface Dump ---", "info")
        self._refresh_interfaces()

    def _diag_ping(self):
        self.append_log("Pinging remote gateway...", "info")
        # Placeholder
        self.append_log("Ping test results will appear in process logs if tunnel is active.", "info")

    def _load_state(self):
        last_bin = self.db.get("binary_path")
        if last_bin: self.binary_path = Path(last_bin)
        self.bin_label.config(text=str(self.binary_path))
        
        # Restore all form variables
        saved_vars = self.db.get("form_vars", {})
        for name, var in self.vars.items():
            if name in saved_vars:
                var.set(saved_vars[name])
        
        # Update UI states
        self._toggle_role_ui()

    def _save_state(self):
        self.db.set("binary_path", str(self.binary_path))
        
        # Save all form variables
        current_vars = {name: var.get() for name, var in self.vars.items()}
        self.db.set("form_vars", current_vars)

    def _on_close(self):
        if self.pm.running: self.pm.stop()
        self._save_state()
        self.root.destroy()

    def _create_menu(self):
        menubar = tk.Menu(self.root, bg=COLORS["bg_sidebar"], fg=COLORS["text_main"])
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=COLORS["bg_sidebar"], fg=COLORS["text_main"])
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import Config", command=self.import_action, accelerator="Ctrl+O")
        file_menu.add_command(label="Export Config", command=self.export_action, accelerator="Ctrl+S")
        file_menu.add_separator()
        
        self.recent_menu = tk.Menu(file_menu, tearoff=0, bg=COLORS["bg_sidebar"], fg=COLORS["text_main"])
        file_menu.add_cascade(label="Recent Configs", menu=self.recent_menu)
        self._update_recent_menu()
        
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        
        # Bindings
        self.root.bind("<Control-o>", lambda e: self.import_action())
        self.root.bind("<Control-s>", lambda e: self.export_action())

    def _update_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        recent = self.db.get_recent()
        if not recent:
            self.recent_menu.add_command(label="No recent configs", state="disabled")
            return
            
        for item in recent:
            label = f"{item['name']} ({item['role']})"
            self.recent_menu.add_command(label=label, command=lambda x=item: self._apply_recent(x))

    def _apply_config(self, cfg: Dict[str, Any]):
        """Map a YAML/Dict configuration back to the UI variables."""
        try:
            role = cfg.get("role", "client")
            self.role_var.set(role)
            self._toggle_role_ui()
            
            self.log_level_var.set(cfg.get("log", {}).get("level", "info"))
            
            net = cfg.get("network", {})
            self.interface_var.set(net.get("interface", ""))
            self.guid_var.set(net.get("guid", ""))
            
            ipv4 = net.get("ipv4", {})
            addr = ipv4.get("addr", "")
            if ":" in addr:
                ip, port = addr.split(":")
                self.local_ip_var.set(ip)
                self.local_port_var.set(port)
            self.router_mac_var.set(ipv4.get("router_mac", ""))
            
            # Transport
            trans = cfg.get("transport", {}).get("kcp", {})
            self.kcp_mode_var.set(trans.get("mode", "fast"))
            self.kcp_mtu_var.set(str(trans.get("mtu", 1350)))
            self.kcp_rcvwnd_var.set(str(trans.get("rcvwnd", 512 if role == "client" else 1024)))
            self.kcp_sndwnd_var.set(str(trans.get("sndwnd", 512 if role == "client" else 1024)))
            self.kcp_block_var.set(trans.get("block", "aes"))
            self.kcp_key_var.set(trans.get("key", ""))
            
            # SOCKS5
            socks = cfg.get("socks5", [])
            if socks and isinstance(socks, list):
                s = socks[0]
                self.socks5_enabled_var.set(True)
                addr = s.get("listen", "127.0.0.1:1080")
                if ":" in addr:
                    lip, lport = addr.split(":")
                    self.socks5_listen_var.set(lip)
                    self.socks5_port_var.set(lport)
                self.socks5_user_var.set(s.get("username", ""))
                self.socks5_pass_var.set(s.get("password", ""))
            elif role == "client":
                self.socks5_enabled_var.set(False)

            # TCP Flags
            tcp = net.get("tcp", {})
            self.tcp_local_flags_var.set(",".join(tcp.get("local_flag", ["PA"])))
            if role == "client":
                self.tcp_remote_flags_var.set(",".join(tcp.get("remote_flag", ["PA"])))
                
        except Exception as e:
            self.append_log(f"Config mapping error: {e}", "error")

    def _apply_recent(self, item: Dict[str, Any]):
        try:
            cfg = json.loads(item["config_json"])
            self._apply_config(cfg)
            self.append_log(f"Loaded configuration: {item['name']}", "success")
        except Exception as e:
            self.append_log(f"Failed to load recent config: {e}", "error")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

if __name__ == "__main__":
    app = PaqetApp()
    app.run()
