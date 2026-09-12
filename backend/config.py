import os
from dotenv import load_dotenv

# Load the hidden variables from your .env file
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    # --- Core ---
    SECRET_KEY = "change-this-in-production"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'radiology.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Uploads ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    REPORTS_FOLDER = os.path.join(BASE_DIR, "reports_docx")
    ALLOWED_SCAN_EXTENSIONS = {"png", "jpg", "jpeg", "dcm", "pdf"}
    ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "webm", "ogg"}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    # --- Mail ---
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = "your-email@example.com"
    MAIL_PASSWORD = "your-app-password"
    MAIL_DEFAULT_SENDER = MAIL_USERNAME

    PUBLIC_BASE_URL = "http://localhost:8000"

    # --- Voice dictation (Groq) ---
    # This securely grabs the key from your .env file instead of hardcoding it!
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    ASR_MODEL = "whisper-large-v3-turbo"
    LLM_MODEL = "llama-3.3-70b-versatile"