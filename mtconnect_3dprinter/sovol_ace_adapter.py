# MTConnect adapter for Sovol Ace Printer
# Updated 4/16/2026 for High-Speed Digital Twin Sync
# Trevor Kates
#!/usr/bin/env python3

import socket
import time
import sys
import argparse
import json
import urllib.request # Uses built-in library, no 'pip install' needed

# --- DYNAMIC CONFIGURATION ---
parser = argparse.ArgumentParser(description='Sovol Ace MTConnect Adapter')
parser.add_argument('--ip', type=str, default="192.168.1.8", help='Printer IP Address')
parser.add_argument('--port', type=int, default=7125, help='Printer Port')
args = parser.parse_args()

TCP_IP = args.ip
TCP_PORT = args.port
# ------------------------------

def get_printer_data():
    """
    Fetches data from Moonraker API via HTTP.
    """
    # This URL tells Klipper to give us exactly the data we need
    url = f"http://{TCP_IP}:{TCP_PORT}/printer/objects/query?print_stats&toolhead&extruder&heater_bed"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        # If you see this in the terminal, the Pi can't reach the printer API
        # print(f"API Error: {e}") 
        return None

def main():
    from mtconnect_adapter import Adapter
    from data_item import Event, Sample

    # Adapter talks to Agent on 7878. Unity talks to Agent on 5001.
    adapter = Adapter(('0.0.0.0', 7878))

    # Define Data Items
    avail = Event('avail')
    execution = Event('exec')
    x_pos = Sample('x_pos')
    y_pos = Sample('y_pos')
    z_pos = Sample('z_pos')
    extruder_temp = Sample('ext_temp')
    bed_temp = Sample('bed_temp')

    adapter.add_data_item(avail); adapter.add_data_item(execution)
    adapter.add_data_item(x_pos); adapter.add_data_item(y_pos); adapter.add_data_item(z_pos)
    adapter.add_data_item(extruder_temp); adapter.add_data_item(bed_temp)

    adapter.start()
    avail.set_value('AVAILABLE')

    print(f"--- MTConnect Adapter Started ---")
    print(f"Targeting Moonraker API: http://{TCP_IP}:{TCP_PORT}")

    try:
        while True:
            data = get_printer_data()
            
            adapter.begin_gather()

            if data and 'result' in data:
                status = data['result']['status']
                
                # 1. Update Execution State
                state = status.get('print_stats', {}).get('state', 'IDLE').upper()
                execution.set_value(state)

                # 2. Update Positions (Moonraker Path)
                pos = status.get('toolhead', {}).get('position', [0, 0, 0, 0])
                x_pos.set_value(round(pos[0], 3))
                y_pos.set_value(round(pos[1], 3))
                z_pos.set_value(round(pos[2], 3))

                # 3. Update Temperatures
                ext = status.get('extruder', {}).get('temperature', 0)
                bed = status.get('heater_bed', {}).get('temperature', 0)
                extruder_temp.set_value(round(ext, 2))
                bed_temp.set_value(round(bed, 2))
                
                # Debug print so you can see it working in the terminal
                # print(f"X:{pos[0]} Y:{pos[1]} Z:{pos[2]}")
            else:
                execution.set_value('UNAVAILABLE')

            adapter.complete_gather()
            time.sleep(0.5) # Fast update for Unity smoothing

    except KeyboardInterrupt:
        avail.set_value('UNAVAILABLE')
        adapter.stop()

if __name__ == "__main__":
    main()