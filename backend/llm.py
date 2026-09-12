"""
llm.py - Clinical cleanup pass for raw ASR transcripts.
"""

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


class RefinementError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


SYSTEM_PROMPT = (
    "You are a radiology documentation assistant. Your job is to clean raw "
    "speech-to-text output from a radiologist's dictation.\n"
    "Rules:\n"
    "1. Remove ALL filler words, hesitations, false starts, and noise "
    "(e.g. 'ah', 'um', 'hmm', 'ok', 'hello', 'testing', incomplete phrases).\n"
    "2. Keep and format ALL clinical content exactly as dictated — including "
    "clinical history, technique, findings, impressions, comparisons to prior "
    "studies, anatomy descriptions, measurements, laterality, drug names, and "
    "dosages.\n"
    "3. Add proper sentence punctuation and capitalize correctly.\n"
    "4. Normalize obvious phonetic ASR mishears of standard medical terms "
    "(e.g. 'bi-basinal' -> 'bibasilar') without changing clinical meaning.\n"
    "5. If the input is ENTIRELY non-medical (greetings, noise, testing): "
    "respond with exactly the word SKIP and nothing else.\n"
    "Return only the cleaned text or SKIP. No explanation or preamble."
)


def _get_client() -> OpenAI:
    api_key = current_app.config.get("GROQ_API_KEY")
    if not api_key or api_key.strip() == "" or api_key == "paste-your-groq-api-key-here":
        raise RefinementError("Missing API key. Set GROQ_API_KEY in config.py", status_code=401)
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def refine_transcript(raw_text: str):
    if not raw_text or not raw_text.strip():
        return None

    client = _get_client()
    model_name = current_app.config.get("LLM_MODEL", "llama-3.3-70b-versatile")

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            max_tokens=400,
            temperature=0.0,
        )
    except AuthenticationError:
        raise RefinementError("Invalid API key for the clinical cleanup LLM. Check GROQ_API_KEY.", status_code=401)
    except RateLimitError:
        raise RefinementError("Rate limit reached on the clinical cleanup LLM. Please wait and try again.", status_code=429)
    except APITimeoutError:
        raise RefinementError("The clinical cleanup LLM timed out.", status_code=504)
    except APIConnectionError:
        raise RefinementError("Could not connect to the clinical cleanup LLM provider.", status_code=502)
    except BadRequestError as e:
        raise RefinementError(f"The clinical cleanup LLM rejected the request: {e}", status_code=400)
    except APIError as e:
        raise RefinementError(f"The clinical cleanup LLM returned an error: {e}", status_code=502)

    text = (response.choices[0].message.content or "").strip()

    if not text or text.upper() == "SKIP":
        return None

    return text