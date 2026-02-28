// =============================================
// MAP
// =============================================
const map = L.map('map', { zoomControl: true }).setView([34.0224, -118.2851], 13);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19,
}).addTo(map);

// =============================================
// STATE
// =============================================
const location_interval = 5;  // interval of updating location, seconds
const deviceMarkers = {};
const deviceTrails = {};
const deviceTrailCoords = {};
const geofenceCircles = {};
let clickedLatLng = null;
let lastNotifCount = 0;
let expandBarOpen = false;
let seenNotifIds = new Set();
const COLORS = ['#f59e0b', '#22c55e', '#3b82f6', '#ef4444', '#a855f7', '#ec4899'];
const MAX_PREVIEW = 3; // How many notifications to show in sidebar

// =============================================
// EXPAND BAR TOGGLE
// =============================================
function toggleExpandBar() {
    expandBarOpen = !expandBarOpen;
    document.getElementById('notif-expand-bar').classList.toggle('open', expandBarOpen);
}

function openExpandBar() {
    if (!expandBarOpen) {
        expandBarOpen = true;
        document.getElementById('notif-expand-bar').classList.add('open');
    }
}

// =============================================
// TOAST
// =============================================
function showToast(notif) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast ' + notif.type;
    toast.innerHTML = '<div>' + notif.message + '</div><div class="toast-time">' + notif.timestamp + '</div>';
    toast.onclick = () => { openExpandBar(); toast.remove(); };
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// =============================================
// MAP CLICK
// =============================================
let clickMarker = null;
map.on('click', function (e) {
    clickedLatLng = e.latlng;
    if (clickMarker) { clickMarker.setLatLng(e.latlng); }
    else {
        clickMarker = L.circleMarker(e.latlng, {
            radius: 8, color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.6,
        }).addTo(map);
    }
});

// =============================================
// DEVICE ICON
// =============================================
function createDeviceIcon(color) {
    return L.divIcon({
        className: '',
        html: '<div style="width:18px;height:18px;background:' + color +
                ';border:3px solid white;border-radius:50%;box-shadow:0 0 10px ' + color + '88;"></div>',
        iconSize: [18, 18], iconAnchor: [9, 9],
    });
}

// =============================================
// DRAW GEOFENCES
// =============================================
function drawGeofences(geofences) {
    geofences.forEach(gf => {
        if (geofenceCircles[gf.id]) return;
        const circle = L.circle([gf.lat, gf.lon], {
            radius: gf.radius, color: '#f59e0b', fillColor: '#f59e0b',
            fillOpacity: 0.08, weight: 1.5, dashArray: '6 4',
        }).addTo(map);
        L.marker([gf.lat, gf.lon], {
            icon: L.divIcon({
                className: '',
                html: '<div style="color:#f59e0b;font-size:11px;font-weight:600;white-space:nowrap;text-shadow:0 0 4px #0f172a,0 0 8px #0f172a;">' + gf.name + '</div>',
                iconAnchor: [-10, 10],
            }),
        }).addTo(map);
        geofenceCircles[gf.id] = circle;
    });
}

// =============================================
// UPDATE DEVICES
// =============================================
function updateDevices(devices) {
    const listEl = document.getElementById('device-list');
    let cardsHtml = '';

    devices.forEach((dev, i) => {
        const color = COLORS[i % COLORS.length];
        const lat = dev.lat, lon = dev.lon;

        if (deviceMarkers[dev.name]) { deviceMarkers[dev.name].setLatLng([lat, lon]); }
        else { deviceMarkers[dev.name] = L.marker([lat, lon], { icon: createDeviceIcon(color) }).addTo(map); }

        deviceMarkers[dev.name].unbindTooltip();
        deviceMarkers[dev.name].bindTooltip(
            '<div class="device-tooltip"><div class="tt-name">' + dev.name + '</div>' +
            '<div class="tt-meta">' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '<br>' +
            'Batt: ' + dev.batt + '% | ' + dev.last_update + '</div></div>',
            { permanent: false, direction: 'top', offset: [0, -12], className: '' }
        );

        if (!deviceTrailCoords[dev.name]) deviceTrailCoords[dev.name] = [];
        const coords = deviceTrailCoords[dev.name];
        const last = coords[coords.length - 1];
        if (!last || last[0] !== lat || last[1] !== lon) {
            coords.push([lat, lon]);
            if (coords.length > 200) coords.shift();
        }
        if (deviceTrails[dev.name]) { deviceTrails[dev.name].setLatLngs(coords); }
        else { deviceTrails[dev.name] = L.polyline(coords, { color: color, weight: 3, opacity: 0.6 }).addTo(map); }

        cardsHtml += '<div class="device-card" onclick="map.setView([' + lat + ',' + lon + '],16)" style="cursor:pointer;margin-top:8px;">' +
            '<div class="device-header"><div class="device-avatar" style="background:' + color + '">' + dev.name[0] + '</div>' +
            '<div class="device-name">' + dev.name + '</div></div>' +
            '<div class="device-meta">' +
            '<span>📍 ' + lat.toFixed(4) + ', ' + lon.toFixed(4) + '</span>' +
            '<span>🔋 ' + dev.batt + '%</span>' +
            '<span>📶 ' + (dev.conn === 'w' ? 'WiFi' : dev.conn === 'm' ? 'Mobile' : dev.conn) + '</span>' +
            '<span>⏱ ' + (dev.last_update ? dev.last_update.split(' ')[1] : '--') + '</span>' +
            '</div></div>';
    });

    if (cardsHtml) listEl.innerHTML = cardsHtml;
}

// =============================================
// RENDER A SINGLE NOTIFICATION ITEM (shared by both panels)
// =============================================
function renderNotifItem(n) {
    return '<div class="notif-item ' + n.type + '">' +
            '<div>' + n.message + '</div>' +
            '<div class="notif-time">' + n.timestamp + '</div></div>';
}

// =============================================
// UPDATE NOTIFICATIONS
// =============================================
function updateNotifications(notifs) {
    const previewEl = document.getElementById('notif-preview');
    const expandListEl = document.getElementById('notif-expand-list');
    const viewAllEl = document.getElementById('notif-view-all');

    if (!notifs || notifs.length === 0) {
        previewEl.innerHTML = '<div class="notif-empty">No notifications yet</div>';
        expandListEl.innerHTML = '<div class="notif-empty">No notifications yet</div>';
        viewAllEl.style.display = 'none';
        return;
    }

    // Toast for new ones
    notifs.forEach(n => {
        const id = n.timestamp + n.device + n.type + n.location;
        if (!seenNotifIds.has(id)) {
            seenNotifIds.add(id);
            if (lastNotifCount > 0) showToast(n);
        }
    });

    if (notifs.length === lastNotifCount) return;
    lastNotifCount = notifs.length;

    const reversed = [...notifs].reverse();

    // Sidebar preview: only show last few
    const previewItems = reversed.slice(0, MAX_PREVIEW);
    previewEl.innerHTML = previewItems.map(renderNotifItem).join('');

    // Expanded bar: show ALL notifications
    expandListEl.innerHTML = reversed.map(renderNotifItem).join('');
}

// =============================================
// ADD GEOFENCE
// =============================================
async function addGeofence() {
    const name = document.getElementById('gf-name').value.trim();
    const radius = parseInt(document.getElementById('gf-radius').value);
    if (!clickedLatLng) { alert('Click on the map first to set the geofence location.'); return; }
    if (!name) { alert('Please enter a name for the geofence.'); return; }
    try {
        const resp = await fetch('/api/geofence', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ name, lat: clickedLatLng.lat, lon: clickedLatLng.lng, radius }),
        });
        const data = await resp.json();
        if (data.status === 'ok') {
            drawGeofences([data.geofence]);
            document.getElementById('gf-name').value = '';
            if (clickMarker) { map.removeLayer(clickMarker); clickMarker = null; }
            clickedLatLng = null;
        }
    } catch (e) { console.error('Failed to add geofence:', e); }
}

// =============================================
// CLEAR NOTIFICATIONS
// =============================================
async function clearNotifications() {
    try {
        await fetch('/api/notifications/clear', { method: 'POST' });
        document.getElementById('notif-preview').innerHTML = '<div class="notif-empty">No notifications yet</div>';
        document.getElementById('notif-expand-list').innerHTML = '<div class="notif-empty">No notifications yet</div>';
        document.getElementById('notif-view-all').style.display = 'none';
        lastNotifCount = 0;
        seenNotifIds.clear();
    } catch (e) { console.error(e); }
}

// =============================================
// POLLING
// =============================================
async function poll() {
    try {
        const resp = await fetch('/api/locations');
        const data = await resp.json();
        updateDevices(data.devices || []);
        updateNotifications(data.notifications || []);
        drawGeofences(data.geofences || []);
        document.getElementById('poll-status').textContent =
            'Live | ' + data.devices.length + ' device(s) | updated ' + new Date().toLocaleTimeString();
    } catch (e) {
        document.getElementById('poll-status').textContent = 'Connection error';
        console.error('Poll error:', e);
    }
}
poll();
setInterval(poll, location_interval * 1000);
