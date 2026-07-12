#!/bin/zsh
# setup_anesthos_ai.sh — Setup and start OmniRoute + Claude Code CLI profile
# Target: macOS Sequoia (POSIX compliant zsh/sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================================="
echo "Initializing OmniRoute and AI Configuration for AnesthOS"
echo "=========================================================="

# 1. Run Python configuration script
if [ -f "$SCRIPT_DIR/setup_anesthos_ai.py" ]; then
    echo "[*] Running configuration script..."
    python3 "$SCRIPT_DIR/setup_anesthos_ai.py"
else
    echo "[ERROR] setup_anesthos_ai.py not found at $SCRIPT_DIR/setup_anesthos_ai.py"
    exit 1
fi

# 2. Check if OmniRoute is already running on port 20128
echo "[*] Checking if OmniRoute is running on port 20128..."
if curl -s -o /dev/null -w "%{http_code}" http://localhost:20128/v1/models | grep -q "200" 2>/dev/null; then
    echo "[+] OmniRoute is already running and responding on port 20128."
else
    echo "[*] Starting OmniRoute globally on port 20128 in background..."
    export PORT=20128
    export DATA_DIR="$HOME/.omniroute"
    export OMNIROUTE_MAX_PENDING_MIGRATIONS=0
    # Launch in background, redirecting logs
    nohup omniroute > "$DATA_DIR/omniroute.log" 2>&1 &
    
    echo "[*] Waiting for OmniRoute to start..."
    for i in {1..15}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:20128/v1/models | grep -q "200" 2>/dev/null; then
            echo "[+] OmniRoute started successfully!"
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo "[WARNING] OmniRoute is taking longer than expected to start."
            echo "Please check logs at $DATA_DIR/omniroute.log"
        fi
    done
fi

# 3. Verify models list and presence of 'anesthos-brain'
echo "[*] Verifying models via curl http://localhost:20128/v1/models..."
if curl -s http://localhost:20128/v1/models | grep -q "anesthos-brain"; then
    echo "[PASS] 'anesthos-brain' combo model is registered and visible!"
else
    echo "[FAIL] 'anesthos-brain' combo model was not found in the model list."
    exit 1
fi

# 4. Verify OpenCode configuration
echo "[*] Verifying OpenCode configuration..."
OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"
if [ -f "$OPENCODE_CONFIG" ]; then
    echo "[PASS] OpenCode configuration exists at $OPENCODE_CONFIG"
else
    echo "[FAIL] OpenCode configuration not found!"
    exit 1
fi

# 5. Verify Claude Code profile
echo "[*] Verifying Claude Code profile..."
CLAUDE_PROFILE_DIR="$HOME/.claude/profiles/anesthos"
if [ -f "$CLAUDE_PROFILE_DIR/settings.json" ]; then
    echo "[PASS] Claude Code profile settings.json exists at $CLAUDE_PROFILE_DIR/settings.json"
else
    echo "[FAIL] Claude Code profile settings.json not found!"
    exit 1
fi

echo "=========================================================="
echo "Configuration & Verification Completed Successfully!"
echo "=========================================================="
