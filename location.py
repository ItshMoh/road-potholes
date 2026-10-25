"""Location helpers: photo GPS, browser geolocation, distance, Maps link and the email location block."""
import io
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image

GPS_IFD = 0x8825
EARTH_RADIUS_M = 6_371_000
MISMATCH_M = 100  # photo GPS vs device location further apart than this -> ask the user
IST = ZoneInfo("Asia/Kolkata")

PHOTO_GPS = "photo GPS"
DEVICE_LOCATION = "device location"

GEO_ERRORS = {
    1: "Location permission was denied. You can still type the address and landmark.",
    2: "Your location is unavailable right now. You can still type the address and landmark.",
    3: "Getting your location timed out. Toggle it off and on to retry, or type the address.",
}


def _to_degrees(dms, ref) -> float:
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if str(ref).strip("\x00 ").upper() in ("S", "W") else value


def gps_from_photo(image_bytes: bytes) -> tuple[float, float] | None:
    """Decimal (lat, lon) from the photo's EXIF GPS tags, or None. Call before resizing."""
    try:
        gps = Image.open(io.BytesIO(image_bytes)).getexif().get_ifd(GPS_IFD)
        lat = _to_degrees(gps[2], gps.get(1, "N"))
        lon = _to_degrees(gps[4], gps.get(3, "E"))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OSError):
        return None
    # NaN (zero denominators) fails the range check; 0,0 means the camera had no fix.
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return round(lat, 6), round(lon, 6)


def parse_geolocation(result: dict | None) -> tuple[dict | None, str | None]:
    """Turn a streamlit-js-eval get_geolocation() result into (device, error_message).

    (None, None) means the browser hasn't answered yet.
    """
    if not result:
        return None, None
    if "error" in result:
        code = (result.get("error") or {}).get("code")
        return None, GEO_ERRORS.get(code, "Couldn't get your location. You can still type the address.")
    coords = result["coords"]
    return {
        "lat": round(coords["latitude"], 6),
        "lon": round(coords["longitude"], 6),
        "accuracy_m": coords.get("accuracy"),
        "timestamp_ms": result.get("timestamp"),
    }, None


def distance_m(a: tuple, b: tuple) -> float:
    """Haversine distance in metres between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def maps_link(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"


def format_ist(timestamp_ms: float) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, IST).strftime("%d %b %Y %H:%M IST")


def format_location_block(loc: dict) -> str:
    """Fixed English location block for the email, built by code so coordinates can't be altered.

    loc keys: address, landmark, city, pin, pothole (lat, lon) | None, pothole_source,
    device {lat, lon, accuracy_m, timestamp_ms} | None.
    """
    place = ", ".join(p for p in (loc.get("address"), loc.get("city")) if p)
    if loc.get("pin"):
        place = f"{place} - {loc['pin']}" if place else loc["pin"]
    lines = [
        "──────── Location details ────────",
        f"Address (reported): {place or 'not given'}",
        f"Landmark: {loc.get('landmark') or 'not given'}",
    ]

    pothole = loc.get("pothole")
    if pothole:
        lines.append(f"Pothole coordinates: {pothole[0]:.6f}, {pothole[1]:.6f}  (source: {loc.get('pothole_source')})")
    else:
        lines.append("Pothole coordinates: not available (please use the address and landmark)")

    device = loc.get("device")
    if device:
        details = []
        if device.get("accuracy_m") is not None:
            details.append(f"±{device['accuracy_m']:.0f} m")
        if device.get("timestamp_ms"):
            details.append(format_ist(device["timestamp_ms"]))
        suffix = f"  ({', '.join(details)})" if details else ""
        lines.append(f"Reporter's current location: {device['lat']:.6f}, {device['lon']:.6f}{suffix}")

    if pothole:
        lines.append(f"Google Maps: {maps_link(*pothole)}")
    return "\n".join(lines)
