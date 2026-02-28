# DSCI 560 - Lab 7

Group 8 Trojan Trio

### 1. Overview

This lab demonstrates how to collect real-time GPS data from a mobile device and send telemetry data to a ThingsBoard server deployed on AWS EC2 using HTTP protocol.

### 2. AWS Setup
- Step 1: Launch EC2 Instance
- Launch Ubuntu EC2 instance
- Open port 8080 in Security Group
- Public IP: http://3.151.116.127:8080
- Login:
Username: tenant@thingsboard.org
Password: tenant
### 3.Create Device in ThingsBoard
- Go to:
Entities → Devices → Add Device
- Create:
Device Name: Phone-Eason
- After creation:
Click Device → Copy Access Token
- Example:
hr9qlCMjAL2XeF8shwsV

### 4.Configure OwnTracks (Mobile App)

Install:
OwnTracks (iOS or Android)
- Step 1: Set Connection Mode
- Preferences → Connection
- Set:
Mode: HTTP
- URL: http://3.151.116.127:8080/api/v1/<ACCESS_TOKEN>/telemetry
- Example:http://3.151.116.127:8080/api/v1/hr9qlCMjAL2XeF8shwsV/telemetry

- Step 2: Enable Location
Phone Settings:
Allow location access: Always
Enable precise location
- Step 3: Enable Extended Data
Preferences → Reporting
Enable:Extended Data
### 5.Sending GPS Data
When the app starts: A status packet is sent
Location data (lat, lon) is sent when movement is detected
Move 20–50 meters to trigger GPS update.
### 6. Verify in ThingsBoard
- Go to:
Entities → Devices → Phone-Eason
- Open:
Latest Telemetry
You should see:lat， lon， batt，conn
- Example:
lat: 34.032913
batt: 50
conn: w

### 7. Start Mapping Program - Live Tracker

Dependencies: flask, requests

```bash
python app.py
```

Then view the map on http://127.0.0.1:5001. 

To test the functions with control panel, visit http://127.0.0.1:5001/test.

You can add geofences on the map. When devices enter/leave the geofence, the website will pop a notification, and email notification will be sent to preset addresses. 
