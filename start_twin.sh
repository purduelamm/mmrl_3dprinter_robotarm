# Runs agent and adapter with less manual inputs
# Updated 4/16/2026
# Trevor Kates
#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

CONFIG_FILE="printer_ip.txt"
DEFAULT_IP="192.168.1.8"

# 1. IP Selection Logic (Same as before)
if [ -f "$CONFIG_FILE" ]; then
    SUGGESTED_IP=$(cat "$CONFIG_FILE")
else
    SUGGESTED_IP=$DEFAULT_IP
fi

USER_INPUT=$(zenity --entry \
    --title="Printer Configuration" \
    --text="Enter the Printer IP Address:" \
    --entry-text="$SUGGESTED_IP")

if [ $? -ne 0 ]; then
    TARGET_IP=$SUGGESTED_IP
else
    TARGET_IP=$USER_INPUT
    echo "$TARGET_IP" > "$CONFIG_FILE"
fi

# 2. Kill old processes
pkill -f sovol_ace_adapter.py
pkill -f agent_run

# 3. Launch the ADAPTER in a NEW Window
# We add '; read' at the end so the window stays open if the script crashes
lxterminal --title="MTConnect ADAPTER" -e "bash -c 'python3 $DIR/sovol_ace_adapter.py --ip $TARGET_IP; echo; echo [Process Ended]; read'" &

# 4. Launch the AGENT in THIS Window
echo "--- STARTING MTCONNECT AGENT ---"
"$DIR/agent_run" "$DIR/agent.cfg"