# Bachelor Thesis Repository

This repository accompanies the bachelor thesis:

**Investigation of reversible electrolyzers and implementation of energy management control strategies through IoT embedded microcontroller**

Technical University of Denmark (DTU), 2026  
Authors: Jacob Norman Sørensen and Matilde Marie Grønkjær Matell

## Purpose

The repository contains the code, experimental data, analysis files, and supporting material used to develop and evaluate a lab-scale Energy Management System (EMS). The EMS controls power flow between grid, photovoltaic source, battery, reversible PEM fuel cell/electrolyzer, and load by selecting between predefined operating scenarios.

## Repository Overview

- `EMS Control App/` contains the final Arduino UNO Q application. This is the main implementation used for EMS monitoring, scenario control, WebUI interaction, and logging.
- `EMS Control App/sketch/` contains the Arduino sketch for relay control, INA226 measurements, scenario application, and embedded safety checks.
- `EMS Control App/python/` contains the Python supervisory EMS logic, including the control loop, scheduler, state handling, Arduino bridge, and system limits.
- `EMS Control App/assets/` contains the WebUI used for live monitoring and manual/demo control.
- `data/` contains experimental measurements from battery, PEM/RFC, PV, EMS system, demand profile, and sensor tests.
- `control_parameters_new/` contains notebooks and scripts used to derive control parameters for the final EMS implementation.
- `Arduino_IDE_files/` contains Arduino sketches used on the "Arduino R4 Wifi" and "Arduino Nano". The file "R4_controllableLoad.ino" is used on the "Arduino R4 Wifi". The file "NANO_LED.ino" is code for the "Arduino Nano", which was written in the previous bachelor project.
- `requirements.txt` lists Python dependencies used for analysis and supporting scripts.

## Submitted Archives

Two archives are intended for submission with the thesis:

- `EMS_Control_App.zip`: contains only `EMS Control App/` and is intended for upload to the Arduino App Lab interface.
- `Bachelor_repository.zip`: contains the full repository, including the EMS application, analysis files, experimental data, and supporting Arduino code.

Generated or local development folders such as `.git/`, `.venv/`, and `__pycache__/` are not part of the intended archival content.

## Responsible Use of AI

Generative AI-assisted tools were used during parts of the project as support for programming, code structuring, data extraction, file conversion, debugging, documentation structure, grammar correction, language refinement, and checking text coherence.

Generative AI was not used as a primary source for scientific claims, nor was it used to make methodological decisions or decisions related to the design process of the project. All AI-generated suggestions were critically reviewed, adapted, and verified by the authors before any inclusion in the report. Factual claims are traceable to the cited literature, measured data, repository contents, or other documented project material.

The authors remain fully responsible for the submitted work, including the implementation, analysis choices, experimental interpretation, descriptions, figures, conclusions, and final thesis content. This declaration follows DTU’s emphasis on honesty, transparency, and accountability in academic work, as described in DTU’s Code of Honour and DTU Library guidance on referencing the use of generative AI 

- DTU Code of Honour: <https://student.dtu.dk/en/eksamen/eksamenssnyd/dtu-code-of-honour>
- DTU Library, referencing generative AI: <https://www.bibliotek.dtu.dk/en/publishing/reference-management/kunstig-intelligens>