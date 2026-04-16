This code is outdated, please visit new repository for the correct code - 4/16/26 Trevor



# Sovol Ace MTConnect Adapter for Robotic Integration

## Project Overview
This repository contains the MTConnect Agent and Adapter configuration for the **Sovol SV06 Ace** 3D printer. This project is part of a research initiative for **ME498/ME597** at Purdue University, focusing on the autonomous synchronization between a 3D printer and a robotic manipulator arm. 

Using **MTConnect** standards, we provide a data stream that allows the robotic manipulator arm to monitor printer status, nozzle coordinates, and safety sensors to facilitate automated part removal.

---

## System Architecture
The system follows a three-tier set-up:
1. **Source (Sovol Ace)**: A Klipper-based 3D printer running a Moonraker API.
2. **Adapter (Python)**: A custom script running on a **Raspberry Pi 4** that polls the Klipper API and translates the JSON data into MTConnect SHDR format.
3. **Agent (C++)**: The MTConnect Agent that ingests the SHDR data and serves it as structured XML over HTTP on port 5001.

---

## Repository Structure
* `agent_run`: The compiled MTConnect Agent binary.
* `agent.cfg`: Configuration file defining the adapter port and device mapping.
* `Device.xml`: The XML schema defining the printer's components, including Axes, Controller, and AI-ready sensors.
* `sovol_ace_adapter.py`: The main Python script that connects the printer to the Agent.
* `mtconnect_adapter.py` & `data_item.py`: Core libraries for formatting MTConnect data.
