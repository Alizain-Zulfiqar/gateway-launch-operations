#!/bin/bash
# Double-click launcher for macOS (Terminal opens briefly, then the app UI).
cd "$(dirname "$0")"
chmod +x run_mac.sh 2>/dev/null || true
exec ./run_mac.sh
