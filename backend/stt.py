"""
stt.py - Speech-to-text provider module.
"""

import os
import io
from flask import current_app
from openai import (
    OpenAI,
    AuthenticationError,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    BadRequestError,
    APIError,
)


class TranscriptionError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mpeg", ".mpga", ".ogg", ".flac",
}


def _get_client() -> OpenAI:
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "paste-your-groq-api-key-here":
        raise TranscriptionError(
            "Missing API key. Set GROQ_API_KEY in config.py",
            status_code=401,
        )
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def transcribe_audio(audio_bytes: bytes, filename: str = "chunk.webm") -> dict:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise TranscriptionError(
            f"Unsupported audio format '{ext or 'unknown'}'. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
            status_code=415,
        )

    client = _get_client()
    model_name = current_app.config.get("ASR_MODEL", "whisper-large-v3-turbo")

    file_like = io.BytesIO(audio_bytes)
    file_like.name = filename

    try:
        result = client.audio.transcriptions.create(model=model_name, file=file_like)
    except AuthenticationError:
        raise TranscriptionError("Invalid API key. Check GROQ_API_KEY in config.py.", status_code=401)
    except RateLimitError:
        raise TranscriptionError("Rate limit reached on the ASR provider. Please wait and try again.", status_code=429)
    except APITimeoutError:
        raise TranscriptionError("The ASR provider timed out. Try a shorter audio file or try again.", status_code=504)
    except APIConnectionError:
        raise TranscriptionError("Could not connect to the ASR provider. Check your network connection.", status_code=502)
    except BadRequestError as e:
        raise TranscriptionError(f"The ASR provider rejected the request (likely unsupported or corrupt audio): {e}", status_code=400)
    except APIError as e:
        raise TranscriptionError(f"The ASR provider returned an error: {e}", status_code=502)

    transcript_text = getattr(result, "text", None)
    if not transcript_text:
        raise TranscriptionError("The ASR provider returned an empty transcript.", status_code=502)

    return {"transcript": transcript_text}