"""
Configuration settings for MathriSurakshaAI.
Manages environment variables, LM Studio local server settings,
voice STT/TTS language mappings, system prompts, and Twilio telephony.
"""

import os
import logging
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Determine absolute path to project root and .env file
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

def load_project_env():
    """Load or reload environment variables from the project .env file reliably."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
    else:
        load_dotenv(override=True)

# Initial load at import time
load_project_env()

# ---------------- LM STUDIO CONFIGURATION ----------------
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/")
LM_STUDIO_CHAT_ENDPOINT = os.environ.get("LM_STUDIO_CHAT_ENDPOINT", f"{LM_STUDIO_BASE_URL}/chat/completions")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-7b-instruct")
LM_STUDIO_TIMEOUT = int(os.environ.get("LM_STUDIO_TIMEOUT", "30"))
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")

# ---------------- MULTI-LANGUAGE MAPPINGS ----------------
STT_LANGUAGE_MAP = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Telugu": "te-IN",
    "Tamil": "ta-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Bengali": "bn-IN",
    "Marathi": "mr-IN",
    "Urdu": "ur-IN",
    "Gujarati": "gu-IN",
    "Odia": "or-IN",
    "Punjabi": "pa-IN",
}

TTS_LANGUAGE_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Urdu": "ur",
    "Gujarati": "gu",
    "Odia": "hi",       # Fallback to Hindi if Odia is unavailable in gTTS
    "Punjabi": "pa",
}

TRANSLATE_LANGUAGE_MAP = {
    "English": "en",
    "Hindi": "hi",
    "Telugu": "te",
    "Tamil": "ta",
    "Kannada": "kn",
    "Malayalam": "ml",
    "Bengali": "bn",
    "Marathi": "mr",
    "Urdu": "ur",
    "Gujarati": "gu",
    "Odia": "or",
    "Punjabi": "pa",
}

# ---------------- MATERNAL HEALTH AI SYSTEM PROMPT ----------------
SYSTEM_PROMPT = """You are MAATRI AI Assistant, a compassionate, supportive, and knowledgeable pregnancy and maternal healthcare companion designed for rural and semi-urban mothers.

Guidelines:
1. Provide warm, clear, simple, and reassuring advice on pregnancy wellness, diet, nutrition (iron, calcium, hydration), safe physical activity, hygiene, and common symptoms.
2. Emphasize the vital role of local ASHA workers, ANMs, and primary healthcare centers. Always encourage regular ANC checkups and adherence to prescribed iron/folic acid (IFA) supplements and TT vaccinations.
3. CRITICAL SAFETY: If the user describes any danger signs (heavy bleeding, sudden decrease in fetal movement, severe persistent headache, blurred vision, high fever, chest pain, or severe abdominal pain), urgently advise them to contact their ASHA worker or proceed to the nearest emergency hospital immediately.
4. Keep answers relatively concise, easy to read on mobile screens, and suitable for spoken voice output.
5. Do not make definitive medical diagnoses or prescribe prescription medications. Always recommend consulting a healthcare professional.
6. LANGUAGE INSTRUCTION: Respond in the exact same language as the user's message (e.g., if user writes/speaks in Telugu, respond in Telugu; if Hindi, respond in Hindi; if English, respond in English). Do not automatically translate the response to English."""

# ---------------- ASHA WORKER & ESCALATION CONFIGURATION ----------------
ASHA_WORKER_NAME = os.environ.get("ASHA_WORKER_NAME", "RAMYA")
ASHA_WORKER_PHONE = os.environ.get("ASHA_WORKER_PHONE", "7075287040")
ASHA_ESCALATION_ENABLED = os.environ.get("ASHA_ESCALATION_ENABLED", "true").lower() in ["true", "1", "yes"]

# ---------------- TWILIO TELEPHONY CONFIGURATION ----------------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
TWILIO_TRIAL_MODE = os.environ.get("TWILIO_TRIAL_MODE", "true").lower() in ["true", "1", "yes"]
TWILIO_TRIAL_SMS_TEMPLATE = os.environ.get("TWILIO_TRIAL_SMS_TEMPLATE", "sms_internal_alerts")
TWILIO_TRIAL_VOICE_URL = os.environ.get("TWILIO_TRIAL_VOICE_URL", "https://webhooks.twilio.com/v1/Voice/Template/voice_text_to_speech")


# ---------------- SAFE CONFIGURATION DIAGNOSTIC ----------------
def get_config_diagnostic() -> Dict[str, str]:
    """
    Returns a safe configuration diagnostic without exposing sensitive credentials.
    """
    load_project_env()

    def is_set(val: str, placeholders=None) -> str:
        if placeholders is None:
            placeholders = []
        if isinstance(placeholders, str):
            placeholders = [placeholders]
        placeholders.extend(["", "your_twilio_account_sid_here", "your_twilio_auth_token_here", "your_twilio_phone_number_here"])
        
        if val and val.strip() and val.strip() not in placeholders:
            return "CONFIGURED"
        return "MISSING"

    return {
        "TWILIO_ACCOUNT_SID": is_set(os.environ.get("TWILIO_ACCOUNT_SID", "")),
        "TWILIO_AUTH_TOKEN": is_set(os.environ.get("TWILIO_AUTH_TOKEN", "")),
        "TWILIO_PHONE_NUMBER": is_set(os.environ.get("TWILIO_PHONE_NUMBER", "")),
        "ASHA_WORKER_PHONE": is_set(os.environ.get("ASHA_WORKER_PHONE", "")),
        "ASHA_ESCALATION_ENABLED": "true" if os.environ.get("ASHA_ESCALATION_ENABLED", "true").lower() in ["true", "1", "yes"] else "false",
        "TWILIO_TRIAL_MODE": "true" if os.environ.get("TWILIO_TRIAL_MODE", "true").lower() in ["true", "1", "yes"] else "false"
    }


def print_config_diagnostic():
    """Print safe configuration status to stdout/logs."""
    diag = get_config_diagnostic()
    print("=== MAATRI SURAKSHA AI CONFIGURATION DIAGNOSTIC ===")
    for k, v in diag.items():
        print(f"{k}: {v}")
    print("===================================================")
