# MTConnect adapter for Sovol Ace Printer
# 2/11/2026 revised by Trevor Kates
# Research Project: ME498/ME597 Purdue University
# 1Hz update frequency, print statements for debugging

import time, datetime, requests
from data_item import Event, Sample
from mtconnect_adapter import Adapter

class SovolAceAdapter:
    def __init__(self, host, port, printer_ip):
        """Initializes the communication bridge between the Printer and Agent."""
        print(f"Initializing Adapter for Printer: {printer_ip}...") # debug statement
        self.adapter = Adapter((host, port)) # Connects to local MTConnect Agent
        self.printer_ip = printer_ip

        # Static URL for Moonraker API queries
        self.query_url = (f"http://{printer_ip}:7125/printer/objects/query?"
                          "extruder&heater_bed&toolhead&print_stats&"
                          "display_status&virtual_sdcard&"
                          "filament_switch_sensor%20filament_sensor")
        self.create_mtconnect_entities()

    def create_mtconnect_entities(self): #device.xml data items
        # Connectivity and Temperatures
        self.avail = Event('avail'); self.adapter.add_data_item(self.avail)
        self.bed_temp = Sample('bed_temp'); self.adapter.add_data_item(self.bed_temp)
        self.ext_temp = Sample('ext_temp'); self.adapter.add_data_item(self.ext_temp)

        # Motion/Positioning
        self.x_pos = Sample('x_pos'); self.adapter.add_data_item(self.x_pos)
        self.y_pos = Sample('y_pos'); self.adapter.add_data_item(self.y_pos)
        self.z_pos = Sample('z_pos'); self.adapter.add_data_item(self.z_pos)

        # Controller state and file info
        self.execution = Event('exec'); self.adapter.add_data_item(self.execution)
        self.program = Event('prog'); self.adapter.add_data_item(self.program)

        # Status messages for print and filament
        self.fil_status = Event('fil_status'); self.adapter.add_data_item(self.fil_status)
        self.print_status = Event('print_status'); self.adapter.add_data_item(self.print_status)
        self.print_progress = Sample('print_progress'); self.adapter.add_data_item(self.print_progress)

    def poll_printer(self):
       #returns JSON status from the API
        try:
            response = requests.get(self.query_url, timeout=5)
            r = response.json()
            # Validation debugging checks for expected JSON
            if 'result' not in r or 'status' not in r['result']:
                print(f"!! API Issue: {r}")
                return None
            return r['result']['status']
        except Exception as e:
            print(f"!! Network Error: {e}")
            return None

    def gather_data(self):
        #main run loop
        print("Starting Data Loop...") # debug statement
        while True:
            data = self.poll_printer()
            if data:
                # Group all api updates into single MTConnect transaction
                self.adapter.begin_gather()
                self.avail.set_value("AVAILABLE")

                # thermal data parsing
                ext = data.get('extruder', {}).get('temperature', 0)
                bed = data.get('heater_bed', {}).get('temperature', 0)

                # toolhead coordinates parsing
                pos = data.get('toolhead', {}).get('position', [0,0,0,0])
                stats = data.get('print_stats', {})

                # MTConnect value updates
                self.ext_temp.set_value(ext)
                self.bed_temp.set_value(bed)
                self.x_pos.set_value(pos[0]); self.y_pos.set_value(pos[1]); self.z_pos.set_value(pos[2])
                self.execution.set_value(stats.get('state', 'standby').upper())
                self.program.set_value(stats.get('filename', 'NONE'))

                # progress and display string updates
                prog = data.get('virtual_sdcard', {}).get('progress', 0)
                self.print_progress.set_value(round(prog * 100, 1))
                self.print_status.set_value(data.get('display_status', {}).get('message', 'Idle'))

                # filament sensor boolean logic prolly unnecessary 
                fil = data.get('filament_switch_sensor filament_sensor', {}).get('filament_detected', False)
                self.fil_status.set_value("LOADED" if fil else "OUT")

                self.adapter.complete_gather()
                print(f"{datetime.datetime.now()}: Status Synced | Ext: {ext}C | Bed: {bed}C")
            else:
                print(f"{datetime.datetime.now()}: No valid data from printer...")

            # 1Hz polling frequency can be changed
            time.sleep(1)

if __name__ == "__main__":
    # function parameters: Agent IP, Agent Port, Printer IP
    sovol_adapter = SovolAceAdapter('127.0.0.1', 7878, '192.168.1.8')
    sovol_adapter.adapter.start() # Starts the internal SHDR server
    sovol_adapter.gather_data() # Enters the infinite polling loop