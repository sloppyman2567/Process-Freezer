#!/bin/sh
# Install Process Freezer for the current user: create the virtualenv, install
# the process-freezer command, and add a desktop menu entry.
set -eu

project=$(cd "$(dirname "$0")" && pwd)
bin_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
python=${PYTHON:-python3}

if ! command -v "$python" >/dev/null 2>&1; then
    echo "error: $python not found; install Python 3.10 or newer" >&2
    exit 1
fi

if [ ! -x "$project/.venv/bin/python" ]; then
    echo "Creating .venv"
    "$python" -m venv --system-site-packages "$project/.venv"
fi

echo "Installing the process-freezer command"
"$project/.venv/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$project/.venv/bin/python" -m pip install --quiet --upgrade --editable "$project"

mkdir -p "$bin_dir" "$apps_dir"
ln -sf "$project/.venv/bin/process-freezer" "$bin_dir/process-freezer"

cat > "$apps_dir/process-freezer.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Process Freezer
Comment=Briefly pause one of your processes
Exec=$bin_dir/process-freezer
Icon=utilities-system-monitor
Terminal=false
Categories=System;
Keywords=freeze;pause;process;cgroup;
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" >/dev/null 2>&1 || true
fi

echo
echo "Installed. Run 'process-freezer' or launch Process Freezer from your menu."
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) echo "Note: $bin_dir is not on your PATH." ;;
esac
