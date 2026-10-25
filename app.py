"""Pothole Complaint Agent: one Streamlit page. Run with: streamlit run app.py"""
import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from streamlit_js_eval import get_geolocation

import complaint_log
from emailer import EmailError, build_email, compose_body, gmail_configured, send_email
from location import (
    DEVICE_LOCATION,
    IST,
    MISMATCH_M,
    PHOTO_GPS,
    distance_m,
    format_location_block,
    gps_from_photo,
    maps_link,
    parse_geolocation,
)
from photo import resize_photo
from sarvam_client import LANGUAGES, SarvamError, check_pothole, translate, write_complaint

load_dotenv()

DEPARTMENTS = json.loads((Path(__file__).resolve().parent / "departments.json").read_text(encoding="utf-8"))
SARVAM_READY = bool(os.getenv("SARVAM_API_KEY", "").strip())
GMAIL_READY = gmail_configured()
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "").strip()
TEST_MODE = os.getenv("TEST_MODE", "true").strip().lower() != "false"
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "hi-IN").strip()
SOURCE_LABELS = {PHOTO_GPS: "📷 Where the photo was taken", DEVICE_LOCATION: "📍 Where I am now"}

# State tied to one photo; cleared when a new photo is uploaded.
PHOTO_STATE = ("check", "letter", "ref_id", "created_at", "translated", "sent", "location_choice")

ss = st.session_state
ss.setdefault("city", os.getenv("DEFAULT_CITY", "Varanasi"))
ss.setdefault("reporter_name", os.getenv("REPORTER_NAME", ""))
ss.setdefault("reporter_phone", os.getenv("REPORTER_PHONE", ""))


def show_log_and_stop():
    """Past complaints always render at the bottom, even when the flow stops early."""
    st.divider()
    st.subheader("Past complaints")
    rows = complaint_log.read_all()
    if rows:
        st.dataframe(rows[::-1], hide_index=True)
    else:
        st.caption("No complaints sent yet.")
    st.stop()


def run_translation(body: str, language: str) -> None:
    with st.spinner(f"Translating to {language} with mayura:v1…"):
        ss.translated = {"source": (body, language), "text": translate(body, LANGUAGES[language])}


st.set_page_config(page_title="Pothole Complaint Agent", page_icon="🕳️")
st.title("🕳️ Pothole Complaint Agent")
st.caption("Photo → AI check → location → formal complaint → email to the road department. Powered by Sarvam AI.")

if not SARVAM_READY:
    st.error("SARVAM_API_KEY is missing in .env, so photo checking and letter writing are disabled.")
if not GMAIL_READY:
    st.error("GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set in .env, so sending is disabled.")
if TEST_MODE:
    st.warning(f"TEST MODE: emails go to YOU ({GMAIL_ADDRESS if GMAIL_READY else 'GMAIL_ADDRESS'}), not the department.", icon="🧪")

# 1. Photo ---------------------------------------------------------------------------------------
st.subheader("1. Photo")
uploaded = st.file_uploader("Upload one photo of the pothole", type=["jpg", "jpeg", "png"])
if uploaded is None:
    show_log_and_stop()
if ss.get("photo_id") != uploaded.file_id:
    raw = uploaded.getvalue()
    try:
        photo = resize_photo(raw)
    except OSError:
        st.error("Couldn't read this image. Please upload a JPG or PNG photo.")
        show_log_and_stop()
    for key in PHOTO_STATE:
        ss.pop(key, None)
    ss.update(photo_id=uploaded.file_id, photo=photo, photo_gps=gps_from_photo(raw))
st.image(ss.photo, width=420)

# 2. Pothole check (gemma4) ----------------------------------------------------------------------
st.subheader("2. Check photo")
if "check" not in ss and st.button("🔍 Check photo", type="primary", disabled=not SARVAM_READY):
    with st.spinner("Checking the photo with gemma4…"):
        try:
            ss.check = check_pothole(ss.photo)
        except SarvamError as e:
            st.error(str(e))
check = ss.get("check")
if not check:
    show_log_and_stop()
if not check["is_pothole"]:
    st.error(f"❌ This doesn't look like a pothole. {check['description']}\n\nPlease upload another photo.")
    show_log_and_stop()
st.success(f"✅ Pothole (Severity: {check['severity'].title()}): {check['description']}")

# 3. Location ------------------------------------------------------------------------------------
st.subheader("3. Location")
device = None
if st.toggle("📍 Get my current location", key="use_device_location"):
    # Returns None on the first render and the browser's answer after a rerun.
    device, geo_error = parse_geolocation(get_geolocation(component_key="geolocation"))
    if geo_error:
        st.info(geo_error)
    elif device is None:
        st.caption("Waiting for the browser… allow location access if asked.")
    else:
        accuracy = f" (±{device['accuracy_m']:.0f} m)" if device["accuracy_m"] is not None else ""
        st.write(f"📍 Your location: {device['lat']:.6f}, {device['lon']:.6f}{accuracy}")

photo_gps = ss.photo_gps
if photo_gps:
    st.write(f"📷 Photo GPS: {photo_gps[0]:.6f}, {photo_gps[1]:.6f}")
else:
    st.caption("📷 No GPS in the photo (camera location was off, or it came via WhatsApp).")

device_point = (device["lat"], device["lon"]) if device else None
pothole, source = None, None
if photo_gps and device_point and (gap := distance_m(photo_gps, device_point)) > MISMATCH_M:
    st.warning(f"Your current location is {gap:,.0f} m from where the photo was taken. Which one is the pothole?")
    source = st.radio(
        "Pothole location", [PHOTO_GPS, DEVICE_LOCATION], key="location_choice",
        format_func=SOURCE_LABELS.get, horizontal=True,
    )
    pothole = photo_gps if source == PHOTO_GPS else device_point
elif photo_gps:
    pothole, source = photo_gps, PHOTO_GPS
elif device_point:
    pothole, source = device_point, DEVICE_LOCATION

if pothole:
    st.map({"lat": [pothole[0]], "lon": [pothole[1]]}, zoom=16, size=8)
    st.markdown(
        f"**Pothole coordinates:** {pothole[0]:.6f}, {pothole[1]:.6f} ({source}) · "
        f"[Open in Google Maps]({maps_link(*pothole)})"
    )
else:
    st.warning(
        "No coordinates. The department may struggle to find the spot. "
        "Turn on your current location, or describe the landmark precisely."
    )

col1, col2 = st.columns(2)
col1.text_input("Address / area", key="address", placeholder="e.g. Lanka Road")
col2.text_input("Landmark *", key="landmark", placeholder="e.g. Near Lanka Gate, BHU")
col1.text_input("City *", key="city")
col2.text_input("PIN code", key="pin", max_chars=6)
address, landmark, city, pin = (ss[k].strip() for k in ("address", "landmark", "city", "pin"))
if pin and not (pin.isdigit() and len(pin) == 6):
    st.caption("⚠️ A PIN code has 6 digits.")

# 4–6. Reporter, department, language ------------------------------------------------------------
st.subheader("4. Reporter")
col1, col2 = st.columns(2)
col1.text_input("Your name *", key="reporter_name")
col2.text_input("Phone *", key="reporter_phone")
name, phone = ss.reporter_name.strip(), ss.reporter_phone.strip()

st.subheader("5. Department")
dept = DEPARTMENTS[
    st.selectbox(
        "Send to", range(len(DEPARTMENTS)), key="department",
        format_func=lambda i: f"{DEPARTMENTS[i]['name']} ({DEPARTMENTS[i]['covers']})",
    )
]

st.subheader("6. Language")
labels = list(LANGUAGES)
default_label = next((label for label, code in LANGUAGES.items() if code == DEFAULT_LANGUAGE), "English only")
language = st.selectbox("Add a translated version", labels, index=labels.index(default_label), key="language")
lang_code = LANGUAGES[language]

# 7. Complaint (sarvam-105b + mayura) ------------------------------------------------------------
st.subheader("7. Complaint")
missing = [label for label, value in (("Landmark", landmark), ("City", city), ("Your name", name), ("Phone", phone))
           if not value]
if missing:
    st.info("Fill in: " + ", ".join(missing))
if st.button("✍️ Write complaint", type="primary", disabled=bool(missing) or not SARVAM_READY):
    now = datetime.now(IST)
    facts = {
        "description": check["description"],
        "severity": check["severity"],
        "address": address,
        "landmark": landmark,
        "city": city,
        "pin": pin,
        "reported_at": now.strftime("%d %b %Y %H:%M IST"),
        "department": dept["name"],
        "reporter_name": name,
        "reporter_phone": phone,
    }
    try:
        with st.spinner("Writing the complaint with sarvam-105b…"):
            letter = write_complaint(facts)
        ss.update(
            letter={
                "subject": f"Pothole complaint – {landmark}, {city} (Severity: {check['severity'].title()})",
                "body": letter["body"],
            },
            ref_id=f"PH-{now:%Y%m%d-%H%M}",
            created_at=now,
        )
        ss.pop("translated", None)
        if lang_code:
            run_translation(letter["body"], language)
    except SarvamError as e:
        st.error(str(e))

if "letter" not in ss:
    show_log_and_stop()
# Keyless widgets: they keep the user's edits across reruns and reset when a new letter is written.
subject = st.text_input("Subject", value=ss.letter["subject"]).strip()
body = st.text_area("Letter (English)", value=ss.letter["body"], height=320).strip()

translation = ""
if lang_code:
    translated = ss.get("translated")
    if translated and translated["source"] == (body, language):
        translation = st.text_area(f"{language} version", value=translated["text"], height=320).strip()
    else:
        st.info(f"The {language} version is missing or out of date. It won't be in the email until you translate.")
        if st.button(f"🌐 Translate to {language}", disabled=not SARVAM_READY):
            try:
                run_translation(body, language)
                st.rerun()
            except SarvamError as e:
                st.error(str(e))

# 8. Email preview -------------------------------------------------------------------------------
st.subheader("8. Email preview")
ref_id, created_at = ss.ref_id, ss.created_at
photo_name = f"pothole_{created_at:%Y%m%d_%H%M}.jpg"
to = GMAIL_ADDRESS if TEST_MODE else dept["email"]
cc = None if TEST_MODE else GMAIL_ADDRESS
full_subject = f"[TEST] {subject}" if TEST_MODE else subject
location_block = format_location_block({
    "address": address, "landmark": landmark, "city": city, "pin": pin,
    "pothole": pothole, "pothole_source": source, "device": device,
})
email_body = compose_body(body, location_block, translation, language, photo_name, ref_id)

if TEST_MODE:
    st.warning("TEST MODE: this email will go to YOU, not the department.", icon="🧪")
st.markdown(f"**To:** {to or '—'}  \n**CC:** {cc or '—'}  \n**Subject:** {full_subject}")
st.code(email_body, language=None, wrap_lines=True)
st.caption(f"📎 Attachment: {photo_name}")

# 9. Confirm & Send ------------------------------------------------------------------------------
blockers = []
if not GMAIL_READY:
    blockers.append("Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to .env to enable sending.")
if not TEST_MODE and dept["email"].strip().lower().endswith("@example.com"):
    blockers.append(f"{dept['name']} still has a placeholder email in departments.json. Add the real address first.")
for blocker in blockers:
    st.error(blocker)

if ss.get("sent"):
    st.success(f"✅ Sent (Ref: {ss.sent}). Upload a new photo to report another pothole.")
elif st.button("📨 Confirm & Send", type="primary", disabled=bool(blockers)):
    status, error = "sent", ""
    try:
        with st.spinner("Sending the email…"):
            send_email(build_email(to, cc, full_subject, email_body, ss.photo, photo_name))
    except EmailError as e:
        status, error = "failed", str(e)
    complaint_log.append({
        "ref_id": ref_id,
        "created_at": datetime.now(IST).isoformat(timespec="seconds"),
        "department": dept["name"],
        "to_email": to,
        "severity": check["severity"],
        "latitude": pothole[0] if pothole else "",
        "longitude": pothole[1] if pothole else "",
        "location_source": source or "",
        "accuracy_m": round(device["accuracy_m"]) if source == DEVICE_LOCATION and device["accuracy_m"] else "",
        "address": address,
        "landmark": landmark,
        "city": city,
        "language": language,
        "test_mode": TEST_MODE,
        "status": status,
        "error": error,
    })
    if status == "sent":
        ss.sent = ref_id
        st.rerun()
    st.error(f"Not sent: {error}")

show_log_and_stop()
