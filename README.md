# PaqetUI 🌐

A modern graphical interface for the paqet network proxy.

[English](./README.md) | [فارسی](./README-FA.md)

---

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/github/v/release/ThisIsDara/PaqetUI?include_prereleases&style=flat)](https://github.com/ThisIsDara/PaqetUI/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)](https://github.com/ThisIsDara/PaqetUI)

## Features ✨

- Modern dark theme (Discord/Linear inspired) 🌙
- Client & Server mode support 🔄
- Auto network interface detection 📡
- KCP encryption configuration 🔐
- Real-time process logging 📋
- Import/Export YAML configs 📁
- Persistent settings 💾

## Screenshots 📸

> Add your screenshots here

## Download ⬇️

Get the latest release from [GitHub Releases](https://github.com/ThisIsDara/PaqetUI/releases).

## Usage 🚀

1. Run `PaqetUI.exe`
2. Select Client or Server mode
3. Configure your network settings
4. Click **START TUNNEL**

## Requirements ⚙️

- Windows 10/11
- Npcap (for Windows)

## Build from Source 🛠️

```bash
# Clone the repository
git clone https://github.com/ThisIsDara/PaqetUI.git
cd PaqetUI

# Install dependencies
pip install -r requirements.txt

# Run the GUI
python paqet_gui.py
```

## Build Executable 📦

```bash
pip install pyinstaller pyyaml
python build.py
```

## License 📄

MIT License
