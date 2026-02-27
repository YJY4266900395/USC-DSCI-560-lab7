"""
DSCI 560 - Lab 7: Custom Mapping Solution
Real-time Location Tracker + Geofence Arrival/Departure Notifications
Group 8 - Trojan Trio
"""

import time
import threading
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, jsonify, render_template, request
import requests as http_requests

app = Flask(__name__)

# =============================================================================
# FILE PATHS FOR PERSISTENCE
# =============================================================================
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
GEOFENCES_FILE = os.path.join(DATA_DIR, "geofences.json")
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, "notifications.json")

# =============================================================================
# CONFIGURATION - Update these values
# =============================================================================

THINGSBOARD_URL = "http://3.151.116.127:8080"
TB_USERNAME = "tenant@thingsboard.org"
TB_PASSWORD = "tenant"

# Devices: Add more as teammates connect their phones
DEVICES = [
    {"name": "Eason", "token": "hr9qlCMjAL2XeF8shwsV"},
    {"name": "Qianshu", "token": "v1fJOM3x7IugnuBYD77A"},
    {"name": "Jinyao", "token": "3JotPkouUm2NfRV5XSqW"},
]

# =============================================================================
# EMAIL NOTIFICATION CONFIG
# =============================================================================
# To use Gmail: go to https://myaccount.google.com/apppasswords
# and generate an App Password (requires 2FA enabled on your Google account)
# Use that 16-char app password below, NOT your regular Gmail password

EMAIL_ENABLED = True  # Set to False to disable email notifications
EMAIL_SENDER = "pengqianshu2025@gmail.com"       # Your Gmail address
EMAIL_PASSWORD = "sehq saaa clul fgwl"       # Gmail App Password
EMAIL_RECIPIENTS = [                         # Who receives notifications
    "qianshup@usc.edu",
#     "teammate2@gmail.com",
#     "teammate3@gmail.com",
]

# Geofence locations: places you want to monitor
# radius is in meters
GEOFENCES = [
    {
        "id": "usc",
        "name": "USC Campus",
        "lat": 34.0224,
        "lon": -118.2851,
        "radius": 500,
    },
    {
        "id": "santa_monica",
        "name": "Santa Monica Beach",
        "lat": 34.0095,
        "lon": -118.4970,
        "radius": 300,
    },
    {
        "id": "koreatown",
        "name": "Koreatown",
        "lat": 34.0578,
        "lon": -118.3004,
        "radius": 500,
    },
]

# =============================================================================
# PERSISTENCE HELPERS
# =============================================================================

def save_json(filepath, data):
    """Save data to a JSON file."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save {filepath}: {e}")


def load_json(filepath, default=None):
    """Load data from a JSON file, return default if not found."""
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load {filepath}: {e}")
    return default if default is not None else []


def load_geofences():
    """Load geofences from file, or use defaults if no file exists."""
    saved = load_json(GEOFENCES_FILE)
    if saved:
        return saved
    # First run: use defaults and save them
    save_json(GEOFENCES_FILE, GEOFENCES)
    return GEOFENCES


# =============================================================================
# STATE TRACKING (persisted)
# =============================================================================

# Store latest location for each device
device_locations = {}

# Store geofence state: {device_name: {geofence_id: True/False}}
geofence_state = {}

# Load saved data
GEOFENCES = load_geofences()
notifications = load_json(NOTIFICATIONS_FILE, [])

# JWT token for ThingsBoard API
tb_jwt_token = None


# =============================================================================
# THINGSBOARD API HELPERS
# =============================================================================

def get_tb_token():
    """Authenticate with ThingsBoard and get JWT token."""
    global tb_jwt_token
    try:
        resp = http_requests.post(
            f"{THINGSBOARD_URL}/api/auth/login",
            json={"username": TB_USERNAME, "password": TB_PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        tb_jwt_token = resp.json().get("token")
        return tb_jwt_token
    except Exception as e:
        print(f"[ERROR] Failed to get ThingsBoard token: {e}")
        return None


def get_device_id_by_token(access_token):
    """Get device ID from ThingsBoard using the device access token."""
    if not tb_jwt_token:
        get_tb_token()
    try:
        resp = http_requests.get(
            f"{THINGSBOARD_URL}/api/v1/{access_token}/attributes",
            timeout=10,
        )
        # Alternative: use the tenant API to find device
        headers = {"X-Authorization": f"Bearer {tb_jwt_token}"}
        resp = http_requests.get(
            f"{THINGSBOARD_URL}/api/tenant/devices?pageSize=100&page=0",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to get device ID: {e}")
        return None


def get_latest_telemetry(access_token):
    """Get latest telemetry data for a device using its access token."""
    try:
        resp = http_requests.get(
            f"{THINGSBOARD_URL}/api/v1/{access_token}/attributes",
            timeout=10,
        )
        # Use the simpler HTTP API to get telemetry
        # ThingsBoard stores latest telemetry accessible via token
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        print(f"[ERROR] Failed to get telemetry: {e}")
        return None


def get_telemetry_via_jwt(device_name, access_token):
    """
    Get latest telemetry using ThingsBoard REST API with JWT auth.
    This is more reliable for reading telemetry.
    """
    if not tb_jwt_token:
        get_tb_token()

    try:
        # First, find the device ID by listing tenant devices
        headers = {"X-Authorization": f"Bearer {tb_jwt_token}"}
        resp = http_requests.get(
            f"{THINGSBOARD_URL}/api/tenant/devices?pageSize=100&page=0",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        devices = resp.json().get("data", [])

        device_id = None
        for d in devices:
            # Match by name or check credentials
            if d.get("name", "").lower().replace(" ", "") in device_name.lower().replace(" ", ""):
                device_id = d["id"]["id"]
                break
            # Also try matching by checking the device name contains our name
            if device_name.lower() in d.get("name", "").lower():
                device_id = d["id"]["id"]
                break

        if not device_id:
            # If we can't find by name, try to get all and match
            for d in devices:
                # Get device credentials to match token
                cred_resp = http_requests.get(
                    f"{THINGSBOARD_URL}/api/device/{d['id']['id']}/credentials",
                    headers=headers,
                    timeout=10,
                )
                if cred_resp.status_code == 200:
                    cred = cred_resp.json()
                    if cred.get("credentialsId") == access_token:
                        device_id = d["id"]["id"]
                        break

        if not device_id:
            print(f"[WARN] Could not find device for {device_name}")
            return None

        # Now get latest telemetry
        telemetry_resp = http_requests.get(
            f"{THINGSBOARD_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys=lat,lon,batt,vel,conn",
            headers=headers,
            timeout=10,
        )
        telemetry_resp.raise_for_status()
        data = telemetry_resp.json()

        result = {}
        for key, values in data.items():
            if values:
                result[key] = values[0].get("value")

        return result

    except Exception as e:
        print(f"[ERROR] JWT telemetry fetch failed for {device_name}: {e}")
        return None


# =============================================================================
# EMAIL NOTIFICATION
# =============================================================================

def send_email_notification(subject, body):
    """Send email notification to all recipients in a background thread."""
    if not EMAIL_ENABLED:
        return

    def _send():
        try:
            msg = MIMEMultipart()
            msg["From"] = EMAIL_SENDER
            msg["To"] = ", ".join(EMAIL_RECIPIENTS)
            msg["Subject"] = subject

            html_body = f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background: #1e293b; color: #e2e8f0; border-radius: 10px;">
                <h2 style="color: #f59e0b; margin-top: 0;">📡 Trojan Trio Tracker</h2>
                <p style="font-size: 16px;">{body}</p>
                <p style="font-size: 12px; color: #64748b; margin-top: 20px;">
                    Sent at {time.strftime("%Y-%m-%d %H:%M:%S")}
                </p>
            </div>
            """
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENTS, msg.as_string())

            print(f"[EMAIL] Sent: {subject}")
        except Exception as e:
            print(f"[EMAIL ERROR] Failed to send email: {e}")

    # Send in background thread so it doesn't block polling
    threading.Thread(target=_send, daemon=True).start()


# =============================================================================
# GEOFENCE LOGIC
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two GPS points in meters."""
    import math
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_geofences(device_name, lat, lon):
    """Check if a device has entered or left any geofence."""
    if device_name not in geofence_state:
        geofence_state[device_name] = {}

    for fence in GEOFENCES:
        dist = haversine_distance(lat, lon, fence["lat"], fence["lon"])
        is_inside = dist <= fence["radius"]
        was_inside = geofence_state[device_name].get(fence["id"], None)

        if was_inside is not None:  # Skip first check (no previous state)
            if is_inside and not was_inside:
                # ENTERED the geofence
                notif = {
                    "type": "arrive",
                    "device": device_name,
                    "location": fence["name"],
                    "distance": round(dist),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": f"📍 {device_name} arrived at {fence['name']}",
                }
                notifications.append(notif)
                save_json(NOTIFICATIONS_FILE, notifications[-500:])  # Keep last 500
                print(f"[NOTIFY] {notif['message']}")
                send_email_notification(
                    f"📍 {device_name} arrived at {fence['name']}",
                    f"{device_name} just arrived at <b>{fence['name']}</b> "
                    f"(within {round(dist)}m of the geofence center)."
                )

            elif not is_inside and was_inside:
                # LEFT the geofence
                notif = {
                    "type": "depart",
                    "device": device_name,
                    "location": fence["name"],
                    "distance": round(dist),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": f"🚶 {device_name} left {fence['name']}",
                }
                notifications.append(notif)
                save_json(NOTIFICATIONS_FILE, notifications[-500:])  # Keep last 500
                print(f"[NOTIFY] {notif['message']}")
                send_email_notification(
                    f"🚶 {device_name} left {fence['name']}",
                    f"{device_name} just left <b>{fence['name']}</b> "
                    f"(now {round(dist)}m away from the geofence center)."
                )

        geofence_state[device_name][fence["id"]] = is_inside


# =============================================================================
# BACKGROUND POLLING
# =============================================================================

def poll_devices():
    """Background thread: poll ThingsBoard for latest device data."""
    print("[INFO] Starting device polling thread...")
    get_tb_token()

    while True:
        for device in DEVICES:
            name = device["name"]
            token = device["token"]

            data = get_telemetry_via_jwt(name, token)
            if data and "lat" in data and "lon" in data:
                try:
                    lat = float(data["lat"])
                    lon = float(data["lon"])
                except (ValueError, TypeError):
                    continue

                device_locations[name] = {
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "batt": data.get("batt", "N/A"),
                    "vel": data.get("vel", 0),
                    "conn": data.get("conn", "?"),
                    "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                check_geofences(name, lat, lon)

        # Refresh JWT token periodically
        if int(time.time()) % 300 < 10:
            get_tb_token()

        time.sleep(5)  # Poll every 5 seconds


# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html", geofences=GEOFENCES)


@app.route("/api/locations")
def api_locations():
    """Return latest locations + recent notifications."""
    return jsonify(
        {
            "devices": list(device_locations.values()),
            "notifications": notifications[-20:],  # last 20 notifications
            "geofences": GEOFENCES,
        }
    )


@app.route("/api/notifications/clear", methods=["POST"])
def clear_notifications():
    """Clear all notifications."""
    notifications.clear()
    save_json(NOTIFICATIONS_FILE, notifications)
    return jsonify({"status": "ok"})


@app.route("/api/geofence", methods=["POST"])
def add_geofence():
    """Add a custom geofence via the UI."""
    data = request.json
    new_fence = {
        "id": f"custom_{int(time.time())}",
        "name": data.get("name", "Custom Location"),
        "lat": float(data["lat"]),
        "lon": float(data["lon"]),
        "radius": int(data.get("radius", 200)),
    }
    GEOFENCES.append(new_fence)
    save_json(GEOFENCES_FILE, GEOFENCES)
    return jsonify({"status": "ok", "geofence": new_fence})


# =============================================================================
# TEST ENDPOINT - Simulate device location for testing
# =============================================================================

@app.route("/test")
def test_page():
    """Simple test page to simulate device movement."""
    return render_template("test.html", devices=DEVICES)


@app.route("/api/test/move", methods=["POST"])
def test_move_device():
    """Simulate moving a device to a specific location. For testing only."""
    data = request.json
    name = data.get("name", DEVICES[0]["name"] if DEVICES else "Test")
    lat = float(data["lat"])
    lon = float(data["lon"])

    # Update device location directly (bypass ThingsBoard)
    device_locations[name] = {
        "name": name,
        "lat": lat,
        "lon": lon,
        "batt": device_locations.get(name, {}).get("batt", "99"),
        "vel": 0,
        "conn": "test",
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Run geofence check (this will trigger notifications + emails)
    check_geofences(name, lat, lon)

    # Return what happened
    recent = [n for n in notifications[-5:] if n["device"] == name]
    return jsonify({"status": "ok", "location": {"lat": lat, "lon": lon}, "triggered": recent})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Start background polling thread
    poller = threading.Thread(target=poll_devices, daemon=True)
    poller.start()

    print("[INFO] Starting Flask server on http://localhost:5001")
    print("[INFO] Make sure ThingsBoard is accessible at", THINGSBOARD_URL)
    app.run(debug=False, host="0.0.0.0", port=5001)