"""
Configuration settings for MathriSurakshaAI.
Manages LM Studio local server settings, voice STT/TTS language mappings, and system prompts.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# ---------------- LM STUDIO CONFIGURATION ----------------
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "")
LM_STUDIO_TIMEOUT = int(os.environ.get("LM_STUDIO_TIMEOUT", "30"))
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")

# ---------------- MULTI-LANGUAGE MAPPINGS ----------------
# Mapping from application language names to Speech-to-Text (BCP-47) codes
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

# Mapping from application language names to Text-to-Speech (gTTS) codes
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

# Mapping from application language names to mtranslate codes
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
5. Do not make definitive medical diagnoses or prescribe prescription medications. Always recommend consulting a healthcare professional."""
