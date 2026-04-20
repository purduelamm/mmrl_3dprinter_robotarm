# Runs agent and adapter with less manual inputs
# Updated 4/16/2026
# Trevor Kates
#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

CONFIG_FILE="printer_ip.txt"
DEFAULT_IP="192.168.1.8"

# 1. IP Selection Logic in case printer IP is different
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

# 2. Kill any old agents running
pkill -f sovol_ace_adapter.py
pkill -f agent_run

# 3. Launch the sovol adapter in a new command prompt window
lxterminal --title="MTConnect ADAPTER" -e "bash -c 'python3 $DIR/sovol_ace_adapter.py --ip $TARGET_IP; echo; echo [Process Ended]; read'" &

# 4. Launch the AGENT in THIS Window
echo "--- STARTING MTCONNECT AGENT ---"
"$DIR/agent_run" "$DIR/agent.cfg"
