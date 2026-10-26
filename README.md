# ErrorMonitor

Python GUI application for monitoring XML error logs from laboratory automation systems. Built as a production tool I used daily in my work as a lab technician.

## Background

This project originally started during my time working as a laboratory automation technician.
I had some previous programming experience, but it had been several years since I had worked with code. 
While working as a technician, I encountered a practical problem: machine errors were being written by the automation software into
XML files, and while there was software to read them, a clear overview of what was happening was difficult to maintain. 
There had been attempts at my company to build such a tool in the past, so I decided to build my own solution. 

The basic idea was simple:

1. Real-time: monitor a local directory containing the XML error files 
2. On-demand: choose a directory containing the XML error files.
3. Parse the XML files and extract relevant information 
4. Store the extracted data in an SQL Database
5. Present the information in a GUI so that errors could be followed along.

The files were originally transferred from the laboratory server to a local machine using Windows robocopy.
I used the software in my day-to-day work as a technician. It helped me get an overview of machine errors, see patterns, and notice problems earlier than I otherwise would have.

## Development

This project is my starting point for the transition into software development.
Although I had some programming experience with C#, I had to relearn many concepts and learn Python from the ground up. 
I used AI as a learning and development tool throughout the process — primarily as a teacher, assistant, and source of explanations.
The architecture, workflow, and overall concept of the application were designed by me based on the actual problem I was trying to solve. 
As a result, the project might contain some questionable design decisions.

## Current Status

This repository contains a rebuild of ErrorMonitor

## Tech Stack

- Python 3.9+ (type hints throughout)
- Tkinter for GUI
- SQLite with WAL mode for concurrent read/write
- xml.etree.ElementTree with streaming iterparse
- Threading for non-blocking background tasks


### Quick Start

Run main.py 

Database (error_log.db) is created automatically on first launch.

© 2026 Adam Abdulaev. All rights reserved.