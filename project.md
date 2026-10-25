# Pothole Complaint Agent — Prototype v0.1

Upload a photo of a pothole, add the location, and the app writes a formal complaint and **emails it to the road department** with the photo, the exact GPS coordinates and a Google Maps link.

Sarvam AI models do the AI work: checking the photo, writing the complaint and translating it.

---

## 1. Goal

> A citizen should be able to report a pothole **in under 2 minutes** and the department should be able to **find the exact spot** from the email alone.

---

## 2. Scope

### In scope (v0.1)

| # | Feature | Summary |
|---|---|---|
| F1 | Photo upload | Upload one JPG/PNG photo of the pothole |
| F2 | Pothole check | Sarvam `gemma4` confirms it is a pothole and rates severity |
| F3 | Location | Auto-fetch **current device coordinates** + read photo GPS + user-typed address/landmark |
| F4 | Write complaint | Sarvam `sarvam-105b` writes a formal complaint letter |
| F5 | Translate | Sarvam `mayura:v1` adds a regional-language version (optional) |
| F6 | Review & send email | User reviews, clicks **Confirm & Send**, email goes to the department (photo attached) |
| F7 | Complaint log | Every send attempt is saved to `data/complaints.csv` |

### Out of scope (later versions)

- Voice notes (Sarvam Saaras), AI phone calls (Sarvam Voice Agents)
- Filing on government portals (CPGRAMS, Rajmargyatra, city portals)
- Auto-detecting which department owns the road (OpenStreetMap)
- Duplicate-complaint detection, complaint status tracking
- Telegram/WhatsApp bot, user accounts, database, deployment

---

## 3. Sarvam in this project

| Step | Sarvam model | Endpoint / SDK call | Why |
|---|---|---|---|
| Pothole check (F2) | `gemma4` (open model hosted on Sarvam, reads images) | `POST /v2/chat/completions` → `client.chat.completions_v2(...)` | Verify photo + severity |
| Write complaint (F4) | `sarvam-105b` (Sarvam's flagship LLM) | `POST /v1/chat/completions` → `client.chat.completions(...)` | Formal, Indian-context complaint letter |
| Translate (F5) | `mayura:v1` (Sarvam translation) | `POST /translate` → `client.text.translate(...)` | Regional-language version for local offices |

- One API key: `SARVAM_API_KEY` (header `api-subscription-key`).
- Cost: a few paise of Sarvam credits per complaint.
- Note: `gemma4` is an open-weight model **served by** Sarvam. The Sarvam-built models used are `sarvam-105b` and `mayura:v1`.

---

## 4. User flow (single Streamlit page)

```
1. Upload photo ──► preview
2. [Check photo] ──► gemma4 ──► ✅ Pothole (Severity: High) "Deep pothole in left lane, water-filled"
                              ──► ❌ Not a pothole → stop, ask for another photo
3. Location
   ├─ [📍 Get my current location] ──► lat, lon, accuracy (browser asks permission) + small map
   ├─ Photo GPS (auto, if the photo has it)
   └─ Text: Address / area, Landmark, City, PIN code
4. Reporter: Name, Phone (prefilled from .env)
5. Department: dropdown (from departments.json)
6. Language: English only / Hindi / Kannada / Tamil / Telugu / ...
7. [Write complaint] ──► sarvam-105b ──► editable Subject + Body
                     ──► mayura (if language chosen) ──► translated body
8. Email preview: To, CC, Subject, Body, Location block, Attachment
   (Yellow banner if TEST MODE: "Email will go to YOU, not the department")
9. [Confirm & Send] ──► Gmail SMTP ──► ✅ Sent (Ref: PH-20261025-1042) ──► row added to complaints.csv
10. Bottom section: table of past complaints
```

---

## 5. Feature details

### F1. Photo upload
- `st.file_uploader`, types: `jpg`, `jpeg`, `png`. One photo.
- **Read EXIF GPS first**, then resize (resizing with Pillow drops EXIF).
- Resize to max **1024 px** on the longest side, JPEG quality 85, used for both the Sarvam call and the email attachment.

### F2. Pothole check — `gemma4`
- Send the resized image as a **base64 data URI** (`data:image/jpeg;base64,...`). Remote URLs are not supported, and the request body must be under 10 MB.
- Use `response_format` with a JSON schema. **Do not also ask for JSON in the prompt**, because Sarvam docs warn this produces an empty output.
- Output schema:

```json
{
  "is_pothole": true,
  "severity": "low | medium | high",
  "description": "1–2 sentences: size, depth, water, position on road"
}
```

- Prompt:

```
You are inspecting a road photo for a civic complaint.
Decide if the photo clearly shows a pothole or damaged road surface.
Severity: low = small/shallow, medium = noticeable/slows traffic,
high = deep or large, dangerous for two-wheelers or pedestrians.
Describe only what is visible. Do not guess the location.
```

- If `is_pothole` is false → show a message and stop.

### F3. Location
Three sources, all shown to the user and all included in the email:

| Source | How | Notes |
|---|---|---|
| **Current device location** | `streamlit-js-eval` → `get_geolocation()` → `coords.latitude`, `coords.longitude`, `coords.accuracy`, `timestamp` | Browser asks permission. Best when the user is standing at the pothole |
| **Photo GPS** | Pillow EXIF GPS tags → decimal lat/lon | Missing if the photo came via WhatsApp or camera location was off |
| **User-typed** | Address/area, Landmark, City, PIN | Required: at least Landmark + City |

Rules:
- **Pothole coordinates** = photo GPS if available, otherwise current device location.
- If both exist and are **more than 100 m apart** → show a warning: "Your current location is far from where the photo was taken. Which one is the pothole?" (radio choice).
- If neither exists → allowed, but show a warning that the department may struggle to find the spot.
- Coordinates are rounded to **6 decimals** (~0.1 m).
- Google Maps link: `https://www.google.com/maps?q={lat},{lon}`
- Show a small map (`st.map`) with the pin so the user can confirm visually.

Geolocation gotchas:
- Works on `http://localhost`. Opening the app from a phone via `http://192.168.x.x` will **block** location (browsers require HTTPS). For phone testing use an HTTPS tunnel (e.g. cloudflared/ngrok) or Streamlit Community Cloud.
- On a Mac laptop, location comes from Wi-Fi (±20–100 m). On a phone it's GPS-accurate.
- macOS: enable Location Services for the browser in System Settings → Privacy & Security.
- Call `get_geolocation()` behind an `st.checkbox`/toggle (not inside an `st.button` branch, which is a known issue) and store the result in `st.session_state`. It returns `None` on the first render and the value after a rerun.
- Handle errors: `{"error": {"code": 1}}` = permission denied, 2 = unavailable, 3 = timeout.

### F4. Write complaint — `sarvam-105b`
- Input: JSON of facts (description, severity, address, landmark, city, PIN, date/time, department name, reporter name/phone).
- Output via `response_format` JSON schema: `{"subject": "...", "body": "..."}`
- Settings: `temperature=0.3`, `reasoning_effort=None` (thinking off: faster, and avoids empty replies when `max_tokens` is used up by reasoning), `max_tokens=1024`.
- Read only `message.content` (ignore `reasoning_content`).
- System prompt:

```
You write formal, polite and concise complaint emails from Indian citizens
to municipal or highway authorities about road potholes.
Use ONLY the facts given. Never invent names, complaint numbers,
officer names, dates or locations.
Do NOT write GPS coordinates or links; they are added separately.
Body under 180 words. Include: the problem, where it is (address + landmark),
severity and safety risk, a clear request for repair, and the reporter's
name and phone. End with "Yours sincerely, <name>".
```

- **The location block is added by code, not by the LLM**, so coordinates and links can never be altered or hallucinated.
- Subject is editable. Default format: `Pothole complaint – {landmark}, {city} (Severity: {severity})`

### F5. Translate — `mayura:v1`
- Dropdown: English only (default), Hindi `hi-IN`, Kannada `kn-IN`, Tamil `ta-IN`, Telugu `te-IN`, Malayalam `ml-IN`, Marathi `mr-IN`, Bengali `bn-IN`, Gujarati `gu-IN`, Punjabi `pa-IN`, Odia `od-IN`.
- `client.text.translate(input=..., source_language_code="en-IN", target_language_code=..., model="mayura:v1", mode="formal")`
- Max **1,000 characters per request** → translate **paragraph by paragraph** and join.
- Translate **only the letter body**. The location block stays in English (numbers and links must not change).

### F6. Review & send email
- Gmail SMTP: `smtplib.SMTP_SSL("smtp.gmail.com", 465)`, login with `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD`.
- Email built with `email.message.EmailMessage`, photo attached as `pothole_{YYYYMMDD_HHMM}.jpg`.
- **TEST_MODE=true (default):** To = your own email, subject prefixed with `[TEST]`. No department receives anything.
- **TEST_MODE=false:** To = department email, CC = your email.
- **Never sends automatically.** Sending happens only on the **Confirm & Send** click.
- Disable the button after a successful send to prevent duplicates (re-enabled after a new photo is uploaded).

Email layout:

```
Subject: Pothole complaint – Near XYZ Bus Stop, <City> (Severity: High)

<English letter from sarvam-105b>

──────── Location details ────────
Address (reported): <address>, <city> - <PIN>
Landmark: <landmark>
Pothole coordinates: 12.971599, 77.594566  (source: photo GPS)
Reporter's current location: 12.971620, 77.594540  (±15 m, 25 Oct 2026 10:42 IST)
Google Maps: https://www.google.com/maps?q=12.971599,77.594566

──────── <Language> version ────────
<translated letter>

Photo attached: pothole_20261025_1042.jpg
Reference: PH-20261025-1042
```

### F7. Complaint log
- File: `data/complaints.csv` (auto-created).
- Columns: `ref_id, created_at, department, to_email, severity, latitude, longitude, location_source, accuracy_m, address, landmark, city, language, test_mode, status, error`
- `status`: `sent` or `failed`. Failed attempts are logged too.
- `ref_id` format: `PH-YYYYMMDD-HHMM`.

---

## 6. Configuration

### `.env` (never commit)

```
SARVAM_API_KEY=
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
TEST_MODE=true
REPORTER_NAME=
REPORTER_PHONE=
DEFAULT_LANGUAGE=en-IN
```

Gmail app password: Google Account → Security → turn on 2-Step Verification → App passwords → create one.

### `departments.json`

Fill with real grievance emails from official websites. Placeholders only, so nothing goes out by mistake:

```json
[
  {
    "id": "city_corp",
    "name": "<City> Municipal Corporation – Roads",
    "email": "replace-me@example.com",
    "covers": "City roads"
  },
  {
    "id": "nhai",
    "name": "NHAI – <Region> Regional Office",
    "email": "replace-me@example.com",
    "covers": "National Highways (NH)"
  },
  {
    "id": "state_pwd",
    "name": "<State> PWD – <District>",
    "email": "replace-me@example.com",
    "covers": "State Highways (SH)"
  }
]
```

The app must refuse to send in non-test mode if the selected email still ends with `@example.com`.

---

## 7. Tech stack & structure

- Python 3.11+, Streamlit, `sarvamai`, `streamlit-js-eval`, Pillow, python-dotenv

```
pothole_prototype/
├── project.md            # this file
├── app.py                # Streamlit UI and flow
├── sarvam_client.py      # check_pothole(), write_complaint(), translate()
├── location.py           # gps_from_photo(), distance_m(), maps_link(), format_location_block()
├── emailer.py            # build_email(), send_email()
├── complaint_log.py      # append(), read_all()
├── departments.json
├── requirements.txt
├── .env.example
├── .gitignore            # .env, data/
└── data/
    └── complaints.csv    # auto-created
```

### Function contracts

```python
# sarvam_client.py
check_pothole(image_bytes: bytes) -> dict        # {is_pothole, severity, description}
write_complaint(facts: dict) -> dict              # {subject, body}
translate(text: str, target_lang: str) -> str     # paragraph-by-paragraph, ≤1000 chars each

# location.py
gps_from_photo(image_bytes: bytes) -> tuple[float, float] | None
distance_m(a: tuple, b: tuple) -> float           # haversine
maps_link(lat: float, lon: float) -> str
format_location_block(loc: dict) -> str           # fixed English block for the email

# emailer.py
build_email(to, cc, subject, body, photo_bytes, photo_name) -> EmailMessage
send_email(msg: EmailMessage) -> None             # raises on failure

# complaint_log.py
append(record: dict) -> None
read_all() -> list[dict]
```

---

## 8. Error handling

| Situation | Behaviour |
|---|---|
| Missing `SARVAM_API_KEY` / Gmail creds | Clear message at the top of the page, disable buttons |
| Sarvam `403` (bad key) / `402` (no credits) / `429` (rate limit) / `503` | Friendly message; retry once with backoff for 429/503 |
| `gemma4` returns invalid JSON | Retry once, then show "Couldn't check the photo, try again" |
| Location permission denied | Info message; manual address still works |
| Gmail login fails | "Check GMAIL_APP_PASSWORD (2-Step Verification must be on)"; log as `failed` |
| Department email is a placeholder (non-test mode) | Block sending with a message |

---

## 9. Done when (acceptance tests)

- [ ] A pothole photo → `is_pothole: true` with a severity and description.
- [ ] A non-pothole photo (e.g. a cat, a clean road) → rejected.
- [ ] **Get my current location** shows lat, lon, accuracy and a map pin. Denying permission doesn't break the app.
- [ ] A photo with GPS → used as pothole coordinates. A >100 m mismatch with the device location → warning + choice.
- [ ] The complaint letter contains no coordinates or links. The location block is added by code and matches the shown values exactly.
- [ ] The translated version appears when a language is selected and is skipped for "English only".
- [ ] `TEST_MODE=true` → email arrives **only in your inbox** with `[TEST]` in the subject, photo attached, Maps link opens the right spot.
- [ ] `TEST_MODE=false` → email goes to the department, CC to you.
- [ ] Every send attempt (success or failure) appears in `complaints.csv` and in the table on the page.

---

## 10. Build milestones

1. **M1 – Sarvam calls:** `sarvam_client.py`, tested from the terminal with 2 pothole photos and 1 non-pothole photo.
2. **M2 – Location:** `location.py` (EXIF GPS, distance, Maps link) + geolocation in Streamlit.
3. **M3 – Write flow:** `app.py` from upload → check → location → complaint → translation (no sending yet).
4. **M4 – Email + log:** `emailer.py`, `complaint_log.py`, test mode end-to-end.
5. **M5 – Go live:** fill real emails in `departments.json`, set `TEST_MODE=false`, send one real complaint.

---

## 11. Safety & privacy

- No email is sent without the user clicking **Confirm & Send**.
- Test mode is on by default.
- Only the reporter's own name, phone and location are shared, with the reporter's consent.
- `.env` and `data/` are git-ignored.
- Photos may show faces or number plates. Blurring is a possible later feature.

---

## 12. Open items

- [ ] City/state, plus the real department grievance emails for `departments.json`
- [ ] Default translation language
- [ ] Sarvam API key and Gmail app password ready in `.env`
