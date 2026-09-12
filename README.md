# RadConnect — Radiology Platform Scaffold

A minimal but complete starting point covering:

- **Login / Sign up** (doctor or patient role, patients auto-assigned to a doctor)
- **Home page** showing the logged-in user's assigned doctor
- **Scan upload** (image/DICOM/PDF)
- **History** of uploaded scans
- **Voice recording → transcription → editable Word (.docx) report**
- **Email a secure download link (API key) to the patient**

⚠️ This is a functional scaffold for you to build on, not a HIPAA/GDPR-compliant
production system. Before handling real patient data you'll need: HTTPS everywhere,
encrypted storage, audit logging, proper key rotation, a compliant email/SMS provider,
and a signed BAA with any cloud vendor you use.

## Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Optional: real email sending (Gmail example — use an App Password, not your real password)
export MAIL_USERNAME="you@gmail.com"
export MAIL_PASSWORD="app-password"
export MAIL_DEFAULT_SENDER="you@gmail.com"
export SECRET_KEY="something-random"

python app.py
```

The API runs on `http://localhost:5000`.

### Speech-to-text
`reports.py` has a single `transcribe_audio()` function. It currently uses the
free `speech_recognition` package (Google Web Speech API) for a quick demo —
swap it for OpenAI Whisper, Azure Speech, or Google Cloud Speech-to-Text in
production; nothing else in the app needs to change.

## Frontend setup

The frontend is plain HTML/CSS/JS — no build step needed. Just serve the folder:

```bash
cd frontend
python -m http.server 8000
```

Open `http://localhost:8000/signup.html`.

`static/js/main.js` has `API_BASE` pointing at `http://localhost:5000/api` — update
it if you deploy the backend elsewhere. CORS is already enabled with credentials
in `app.py` for cross-origin session cookies.

## Typical flow

1. Sign up as a **doctor** first (so patients have someone to be assigned to),
   then sign up a **patient** — they're auto-assigned to the doctor with the
   fewest patients.
2. Log in as the patient → **Upload Scan**.
3. Log in as the doctor → **History** to see the patient's scan → note its ID.
4. Doctor → **Voice Report** → enter the scan ID → record → **Transcribe**.
5. Review/correct the transcript → **Save correction** (regenerates the .docx).
6. **Send report to patient** → emails a link like:
   `http://localhost:5000/api/reports/public-download/<id>?key=<api_key>`
   which lets the patient download the report **without logging in**, since the
   key itself is the credential. Treat this exactly like a password reset link:
   single-purpose, long, random, and only ever sent over a trusted channel.

## Key files

```
backend/
  app.py        - app factory, blueprint registration
  config.py     - all environment-driven settings
  extensions.py - db / login / mail singletons
  models.py     - User, Scan, Report
  auth.py       - signup / login / logout / me
  scans.py      - upload / history / file retrieval
  reports.py    - transcribe / correct / docx generation / email+API key

frontend/
  login.html, signup.html, home.html,
  upload.html, history.html, voice.html
  static/css/style.css, static/js/main.js
```

## Suggested next steps
- Replace the naive "fewest patients" doctor-assignment with real scheduling logic.
- Add role-based routing/guards more thoroughly (e.g., prevent patients hitting doctor-only endpoints beyond the current checks).
- Move report file storage to cloud object storage (S3/GCS) with signed URLs instead of local disk.
- Add rate-limiting to `/public-download` and expire API keys after first use or after N days.
- Add pagination to history for patients/doctors with many scans.
