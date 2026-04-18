# **Sovol SV06 Ace MTConnect Digital Twin Interface**

This repository contains the middleware and integration scripts required to synchronize a **Sovol SV06 Ace** 3D printer with a **Unity** virtual environment. The system utilizes the **MTConnect** standard (ANSI/MTC1.4-2018) to ensure a vendor-neutral, extensible data stream for real-time motion tracking and state monitoring.

---

## **System Architecture**

The integration architecture is divided into four distinct layers to ensure low-latency communication and data integrity:

1. **Hardware Interface (Moonraker API):** The printer serves hardware state and toolhead coordinates as JSON objects via the Moonraker API on **Port 7125**.  
2. **Middleware (Python Adapter):** The `sovol_ace_adapter.py` script polls the Moonraker API, parses the toolhead position, and transmits the data to the Agent on **Port 7878**.  
3. **Standardization Layer (MTConnect Agent):** The `agent_run` binary processes the incoming data stream according to the definitions in `Device.xml` and hosts a RESTful XML interface on **Port 5001**.  
4. **Visualization Layer (Unity):** A C\# implementation polls the Agent's XML feed and applies smoothed transforms to the virtual model.

---

## **Repository Structure**

* **`start_twin.sh`**: A shell script utilizing Zenity for the graphical configuration of the printer's IP address and automated process management.  
* **`sovol_ace_adapter.py`**: The primary Python bridge optimized for Moonraker/Klipper JSON-RPC communication.  
* **`agent_run` & `agent.cfg`**: The C++ MTConnect Agent executable and its associated configuration parameters.  
* **`Device.xml`**: The MTConnect Device Information Model defining the component hierarchy (X, Y, Z axes, Extruder, and Bed).  
* **`mtconnect_adapter.py` & `data_item.py`**: Supporting libraries for MTConnect-compliant data formatting.  
* **`Sovol Ace MTConnect Launcher.desktop`**: A Linux desktop entry file for deployment in a workstation environment.

---

## **Installation and Deployment**

### **1\. Environment Preparation**

The system is designed to run on a Raspberry Pi or similar Linux-based edge device within the same local area network (LAN) as the printer.

Bash  
\# Clone the repository and navigate to the directory  
cd \~/Desktop/mtconnect\_3dprinter

\# Ensure all binaries and scripts have execution permissions  
chmod \+x start\_twin.sh agent\_run

### **2\. Execution**

Launch the integration by executing the `start_twin.sh` script or using the desktop shortcut.

* Upon launch, a GUI prompt will request the **Printer IP Address**.  
* The script automatically manages process cleanup of previous sessions to prevent port conflicts.  
* Two terminal instances will initialize: the **Adapter** (data parsing) and the **Agent** (web server).

---

## **Unity Implementation**

The Unity client requires the `unity_mtconnect_reader.cs` script to be attached to a designated Controller GameObject.

### **Inspector Configuration**

* **Host IP:** The network IP address of the Raspberry Pi.  
* **Port:** **5001** (Requests must be directed to the Agent, not the Adapter).  
* **Component Mapping:** Assign the 3D transforms for the Toolhead, Gantry, and Bed.  
* **Data Item IDs:** Ensure mapping corresponds to the `Device.xml` IDs: `x_pos`, `y_pos`, and `z_pos`.
