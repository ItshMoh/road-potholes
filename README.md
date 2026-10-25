This is the project for the server buildathon

# Pothole Complaint Agent (prototype v0.1)

Upload a pothole photo → Sarvam AI checks it, writes a formal complaint (+ Hindi / Hinglish version) →
email with photo, GPS coordinates and a Google Maps link goes to the road department (Varanasi).
Spec: `project.md` · Build phases: `phase.md`

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill SARVAM_API_KEY (+ Gmail app password to send)
.venv/bin/streamlit run app.py
```

Open http://localhost:8501 (location access needs `localhost` or HTTPS).

## Check

```bash
.venv/bin/pytest                                    # offline tests, no API key needed
.venv/bin/python try_sarvam.py test_photos/*.jpg    # real Sarvam calls on your photos
```

`TEST_MODE=true` (default) sends every email to your own `GMAIL_ADDRESS` with `[TEST]` in the subject.
To go live: put real department emails in `departments.json`, then set `TEST_MODE=false`.
