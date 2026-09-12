import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel sets the VERCEL env var automatically on deployed functions.
# Only /tmp is writable there — everything else in the repo is read-only.
IS_VERCEL = os.environ.get("VERCEL") == "1"
WRITABLE_DIR = "/tmp" if IS_VERCEL else BASE_DIR


class Config:
    # --- Core ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(WRITABLE_DIR, 'radiology.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Uploads ---
    # NOTE: /tmp is wiped between cold starts on Vercel, so uploaded scans,
    # generated reports, and the sqlite DB itself will NOT persist. This is
    # fine for demoing the UI, not for real usage — see note in chat.
    UPLOAD_FOLDER = os.path.join(WRITABLE_DIR, "uploads")
    REPORTS_FOLDER = os.path.join(WRITABLE_DIR, "reports_docx")
    ALLOWED_SCAN_EXTENSIONS = {"png", "jpg", "jpeg", "dcm", "pdf"}
    ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "webm", "ogg"}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    # --- Mail ---
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = MAIL_USERNAME

    # Set this to your actual Vercel deployment URL as an env var,
    # e.g. https://your-project.vercel.app
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")

    # --- Voice dictation (Groq) ---
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    ASR_MODEL = os.environ.get("ASR_MODEL", "whisper-large-v3-turbo")
    LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
