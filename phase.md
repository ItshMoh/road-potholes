# Build Phases — Pothole Complaint Agent v0.1

Three phases. Each ends with something you can run and check. Spec: `project.md`.

Decisions: City = **Varanasi**. Default translation = **Hindi**, plus a **Hinglish** option
(Mayura `hi-IN`, `mode="code-mixed"`, `output_script="roman"`). Test photos go in `test_photos/` (git-ignored).

---

## Phase 1 — Core engine (no UI)

Setup + all Sarvam calls + location maths, testable from the terminal.

- [ ] Setup: `.venv`, `requirements.txt`, `.env.example`, `.env`, `.gitignore`, `departments.json` (Varanasi placeholders), `test_photos/`
- [ ] `photo.py` — `resize_photo()`: fix EXIF rotation, max 1024 px, JPEG q85
- [ ] `sarvam_client.py`
  - `check_pothole(image_bytes)` → `gemma4`, base64 data URI, JSON-schema `response_format`, retry once on bad JSON
  - `write_complaint(facts)` → `sarvam-105b`, temp 0.3, reasoning off, max_tokens 1024, `{subject, body}`
  - `translate(text, target_lang)` → `mayura:v1`, paragraph by paragraph (≤1000 chars), Hindi / Hinglish / other languages
  - Friendly errors for 403 / 402 / 429 / 503 (SDK retries 429/5xx once)
- [ ] `location.py` — `gps_from_photo()` (read before resize), `distance_m()` (haversine), `maps_link()`, `format_location_block()`
- [ ] `tests/test_location.py` — EXIF GPS, distance, link, location block
- [ ] `try_sarvam.py <photo>` — terminal check of the full AI chain

**Done when:** `pytest` passes; `try_sarvam.py` accepts 2 pothole photos, rejects 1 non-pothole, and prints
an English letter (no coordinates/links) + Hindi + Hinglish versions.

---

## Phase 2 — Streamlit app (everything except sending)

`app.py`, one page, following the user flow in `project.md` §4.

- [ ] Config check at the top (missing keys → message + disabled buttons), yellow TEST MODE banner
- [ ] Upload → preview → **Check photo** (stop if not a pothole)
- [ ] Location: **Get my current location** toggle (`streamlit-js-eval`, stored in `session_state`, error codes 1/2/3),
      photo GPS, typed address/landmark/city/PIN (Landmark + City required), `st.map` pin,
      >100 m mismatch → warning + radio choice, no coordinates → warning
- [ ] Reporter (prefilled from `.env`), Department dropdown, Language dropdown (default Hindi)
- [ ] **Write complaint** → editable Subject + Body → translated body
- [ ] Email preview: To, CC, Subject, Body, Location block, translation, attachment name, Ref ID

**Done when:** the full flow runs on `http://localhost:8501` up to the email preview; denying location permission
doesn't break anything; the mismatch warning shows for a far-away photo.

---

## Phase 3 — Email, log, go live

- [ ] `emailer.py` — `build_email()` (`EmailMessage`, photo attached as `pothole_YYYYMMDD_HHMM.jpg`), `send_email()` (Gmail SMTP_SSL 465)
- [ ] `complaint_log.py` — `append()`, `read_all()` → `data/complaints.csv` (auto-created, all spec columns)
- [ ] **Confirm & Send**: TEST_MODE → only to you + `[TEST]` subject; live → department, CC you;
      block `@example.com` in live mode; disable after success (re-enable on new photo)
- [ ] Log every attempt (`sent` / `failed` + error); past-complaints table at the bottom
- [ ] Gmail login failure → clear message, logged as `failed`
- [ ] Run the acceptance checklist (`project.md` §9)
- [ ] Go live: real Varanasi department emails in `departments.json`, `TEST_MODE=false`, send one real complaint

**Done when:** a test-mode email lands in your inbox with the photo, Maps link opens the right spot, and the
attempt shows in `complaints.csv` and on the page.
