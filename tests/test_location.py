import io
from fractions import Fraction

import pytest
from PIL import Image

from location import (
    DEVICE_LOCATION,
    GPS_IFD,
    PHOTO_GPS,
    distance_m,
    format_location_block,
    gps_from_photo,
    maps_link,
    parse_geolocation,
)
from photo import resize_photo


def _jpeg(gps: dict | None = None, size=(40, 20)) -> bytes:
    img = Image.new("RGB", size, "gray")
    exif = Image.Exif()
    if gps:
        exif[GPS_IFD] = gps
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _dms(d, m, s):
    return (Fraction(d), Fraction(m), Fraction(s).limit_denominator(1000))


def test_gps_from_photo_north_east():
    # Dashashwamedh Ghat, Varanasi: 25°18'25.6"N 83°00'37.0"E
    photo = _jpeg({1: "N", 2: _dms(25, 18, 25.6), 3: "E", 4: _dms(83, 0, 37.0)})
    assert gps_from_photo(photo) == (25.307111, 83.010278)


def test_gps_from_photo_south_west_is_negative():
    photo = _jpeg({1: "S", 2: _dms(33, 52, 4), 3: "W", 4: _dms(70, 40, 0)})
    lat, lon = gps_from_photo(photo)
    assert lat < 0 and lon < 0


def test_gps_from_photo_missing_or_garbage():
    assert gps_from_photo(_jpeg()) is None
    assert gps_from_photo(b"not an image") is None
    assert gps_from_photo(_jpeg({1: "N", 2: _dms(0, 0, 0), 3: "E", 4: _dms(0, 0, 0)})) is None


def test_resize_drops_exif_and_limits_size():
    big = _jpeg({1: "N", 2: _dms(25, 18, 25.6), 3: "E", 4: _dms(83, 0, 37.0)}, size=(3000, 1500))
    small = resize_photo(big)
    assert Image.open(io.BytesIO(small)).size == (1024, 512)
    assert gps_from_photo(small) is None


def test_distance_m():
    assert distance_m((25.0, 83.0), (25.0, 83.0)) == 0
    assert distance_m((25.0, 83.0), (26.0, 83.0)) == pytest.approx(111_195, rel=1e-3)
    assert distance_m((25.307111, 83.010278), (25.307111, 83.011278)) == pytest.approx(100.6, abs=1)


def test_maps_link():
    assert maps_link(25.3071111, 83.01) == "https://www.google.com/maps?q=25.307111,83.010000"


def test_parse_geolocation():
    assert parse_geolocation(None) == (None, None)
    device, error = parse_geolocation(
        {"coords": {"latitude": 25.30711149, "longitude": 83.0102781, "accuracy": 15.2}, "timestamp": 1_761_369_120_000}
    )
    assert error is None
    assert device == {"lat": 25.307111, "lon": 83.010278, "accuracy_m": 15.2, "timestamp_ms": 1_761_369_120_000}
    device, error = parse_geolocation({"error": {"code": 1, "message": "User denied Geolocation"}})
    assert device is None and "denied" in error


def test_location_block_with_everything():
    block = format_location_block(
        {
            "address": "Lanka Road",
            "landmark": "Near Lanka Gate, BHU",
            "city": "Varanasi",
            "pin": "221005",
            "pothole": (25.307111, 83.010278),
            "pothole_source": PHOTO_GPS,
            "device": {"lat": 25.30712, "lon": 83.01026, "accuracy_m": 15.2, "timestamp_ms": 1_761_369_120_000},
        }
    )
    assert block.splitlines() == [
        "──────── Location details ────────",
        "Address (reported): Lanka Road, Varanasi - 221005",
        "Landmark: Near Lanka Gate, BHU",
        "Pothole coordinates: 25.307111, 83.010278  (source: photo GPS)",
        "Reporter's current location: 25.307120, 83.010260  (±15 m, 25 Oct 2025 10:42 IST)",
        "Google Maps: https://www.google.com/maps?q=25.307111,83.010278",
    ]


def test_location_block_without_coordinates():
    block = format_location_block(
        {"landmark": "Near Lanka Gate", "city": "Varanasi", "pothole": None, "pothole_source": None, "device": None}
    )
    assert "Pothole coordinates: not available" in block
    assert "Google Maps" not in block
    assert "Reporter's current location" not in block


def test_location_block_device_source():
    block = format_location_block(
        {
            "landmark": "X",
            "city": "Varanasi",
            "pothole": (25.1, 83.2),
            "pothole_source": DEVICE_LOCATION,
            "device": {"lat": 25.1, "lon": 83.2, "accuracy_m": None, "timestamp_ms": None},
        }
    )
    assert "(source: device location)" in block
    assert "Reporter's current location: 25.100000, 83.200000\n" in block
