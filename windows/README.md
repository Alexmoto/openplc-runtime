# OpenPLC Runtime - Windows Installer

This directory contains the infrastructure for building a Windows installer for OpenPLC Runtime using MSYS2 and Inno Setup.

## Overview

The Windows installer bundles a complete MSYS2 environment with all required dependencies (GCC, Python, etc.) so users can run OpenPLC Runtime on Windows without needing to install any additional software.

## Files

- `setup.iss` - Inno Setup script that creates the Windows installer
- `StartOpenPLC.bat` - Windows launcher script that starts the runtime inside MSYS2
- `provision-msys2.sh` - Script to install packages and configure MSYS2 (used during CI build)

## Building the Installer

### Automated Build (GitHub Actions)

The installer is automatically built by GitHub Actions when:
- A tag starting with `v` is pushed (e.g., `v4.0.0`)
- The workflow is manually triggered via `workflow_dispatch`

The workflow:
1. Sets up MSYS2 on a Windows runner
2. Installs all required packages (GCC, Python, CMake, etc.)
3. Builds the OpenPLC Runtime
4. Creates a Python virtual environment with all dependencies
5. Packages everything into an Inno Setup installer
6. Uploads the installer to GitHub Releases (for tag pushes)

### Manual Build

To build the installer manually on a Windows machine:

1. Install MSYS2 from https://www.msys2.org/
2. Open MSYS2 MSYS terminal and run:
   ```bash
   pacman -Syu --noconfirm
   pacman -S --noconfirm base-devel gcc make cmake pkg-config python python-pip git sqlite3
   ```
3. Clone and build OpenPLC Runtime:
   ```bash
   git clone https://github.com/Autonomy-Logic/openplc-runtime.git
   cd openplc-runtime
   python3 -m venv venvs/runtime
   ./venvs/runtime/bin/python3 -m pip install -r requirements.txt
   ./venvs/runtime/bin/python3 -m pip install -e .
   mkdir build && cd build && cmake .. && make
   ```
4. Install Inno Setup from https://jrsoftware.org/isinfo.php
5. Create the payload directory structure:
   ```
   windows/
     payload/
       msys64/     <- Copy your MSYS2 installation here
       openplc-runtime/  <- Copy the runtime files here
   ```
6. Run Inno Setup compiler:
   ```
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" windows\setup.iss
   ```

## Installation

The installer creates a per-user installation (no admin rights required) at:
```
%LOCALAPPDATA%\OpenPLC Runtime\
```

This includes:
- `msys64/` - Complete MSYS2 environment
- `openplc-runtime/` - OpenPLC Runtime files
- `StartOpenPLC.bat` - Launcher script

## Usage

After installation, users can:
1. Use the Start Menu shortcut "Start OpenPLC Runtime"
2. Or run `StartOpenPLC.bat` directly

The runtime will start and be accessible at https://localhost:8443

## Size Considerations

The installer is large (~500MB-1GB compressed) because it includes:
- Complete MSYS2 environment
- GCC toolchain (needed for compiling PLC programs)
- Python with all dependencies
- OpenPLC Runtime

To reduce size, the build process:
- Cleans pacman package cache
- Removes unnecessary log files
- Excludes test files and development tools

## Troubleshooting

### Runtime fails to start
- Ensure the installation path does not contain spaces
- Try running as administrator if permission issues occur
- Check that antivirus is not blocking MSYS2 executables

### Compilation errors
- The GCC toolchain is bundled with the installer
- If compilation fails, check that the build directory exists

### Socket errors
- The runtime uses Unix domain sockets via MSYS2
- Ensure no other instance is running
- Check that the `/run/runtime` directory exists in MSYS2
