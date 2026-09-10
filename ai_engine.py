"""
Clinical Risk & Symptom Assessment Engine for MathriSurakshaAI.
Evaluates maternal health risks based on symptoms, mood, and nutrition.
Supports multilingual phrase extraction, negation detection, and emergency interceptor escalations.
"""

from datetime import datetime
import re
from typing import List, Dict, Any, Optional

try:
    from mtranslate import translate
except ImportError:
    translate = None

# Critical / Emergency symptoms that demand immediate high-risk escalation
EMERGENCY_SYMPTOMS = [
    "heart attack", "cardiac arrest", "chest pain", "pain in heart",
    "heavy bleeding", "vaginal bleeding", "bleeding", "blood",
    "convulsion", "seizure", "fits", "unconscious", "faint", "fainting",
    "cannot breathe", "can't breathe", "shortness of breath", "difficulty breathing",
    "reduced fetal movement", "no fetal movement", "no baby movement", "decreased fetal movement",
    "stroke", "severe abdominal pain", "water broke", "water break"
]

# Severe symptoms (Score +40)
SEVERE_SYMPTOMS = [
    "severe headache", "blurred vision", "vision loss", "high fever",
    "continuous vomiting", "high bp", "high blood pressure", "pre-eclampsia",
    "swelling in face", "facial swelling"
]

# Moderate symptoms (Score +20)
MODERATE_SYMPTOMS = [
    "headache", "swelling", "dizziness", "dizzy", "vomiting", "fever",
    "abdominal pain", "stomach pain", "cramp", "cramping", "fatigue",
    "nausea", "backache", "leg pain", "burning urination"
]

# Mild symptoms (Score +10)
MILD_SYMPTOMS = [
    "mild fatigue", "tired", "constipation", "heartburn", "mild nausea",
    "gas", "sleepy", "mild backache"
]

# Negation words across supported languages
NEGATION_WORDS = [
    "no", "not", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't",
    "without", "never", "free of", "neither", "nor", "nothing", "zero",
    "లేదు", "లేవు", "రావట్లేదు", "లేదుగా",
    "नहीं", "ना", "बिना"
]


def normalize_text(text: str) -> str:
    """Normalize input text: lowercased, punctuation-stripped, and whitespace trimmed."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split())


def is_symptom_negated(norm_text: str, symptom: str) -> bool:
    """
    Check if a symptom in the text is negated (e.g. 'I do not have chest pain', 'no bleeding').
    """
    if not norm_text or not symptom:
        return False
    
    # Check prefix negation (e.g., 'no chest pain', 'do not have chest pain', 'without any bleeding')
    prefix_pattern = (
        r'\b(?:' + '|'.join(re.escape(w) for w in NEGATION_WORDS) + r')\b'
        r'(?:\s+\w+){0,3}\s+' + re.escape(symptom)
    )
    if re.search(prefix_pattern, norm_text, re.IGNORECASE):
        return True

    # Check postfix negation (e.g., 'chest pain is not there', 'bleeding ledu', 'dard nahi hai')
    postfix_pattern = (
        re.escape(symptom) +
        r'(?:\s+\w+){0,2}\s+\b(?:' + '|'.join(re.escape(w) for w in NEGATION_WORDS) + r')\b'
    )
    if re.search(postfix_pattern, norm_text, re.IGNORECASE):
        return True

    return False


def extract_symptoms(text: str) -> List[str]:
    """
    Extract clinical symptoms and emergency keywords from user speech or text.
    Supports multilingual input, negation detection, and prioritizes longer phrases.
    """
    if not text or not text.strip():
        return []

    raw_text = text.strip()
    norm_text = normalize_text(raw_text)

    # Multilingual translation for non-ASCII scripts (Telugu, Hindi, Tamil, etc.)
    has_non_ascii = any(ord(char) > 127 for char in raw_text)
    translated_text = ""
    if has_non_ascii and translate:
        try:
            translated = translate(raw_text, "en", "auto")
            translated_text = normalize_text(translated)
        except Exception:
            pass

    combined_text = f"{norm_text} {translated_text}".strip()

    found_symptoms = []

    def is_covered(candidate: str) -> bool:
        return any(candidate in existing for existing in found_symptoms if candidate != existing)

    # 1. Emergency phrases
    for symptom in sorted(EMERGENCY_SYMPTOMS, key=len, reverse=True):
        if symptom in combined_text and not is_covered(symptom):
            if not is_symptom_negated(norm_text, symptom) and not (translated_text and is_symptom_negated(translated_text, symptom)):
                found_symptoms.append(symptom)

    # 2. Severe symptoms
    for symptom in sorted(SEVERE_SYMPTOMS, key=len, reverse=True):
        if symptom in combined_text and not is_covered(symptom):
            if not is_symptom_negated(norm_text, symptom) and not (translated_text and is_symptom_negated(translated_text, symptom)):
                found_symptoms.append(symptom)

    # 3. Mild symptoms (check before moderate to catch 'mild backache', 'mild fatigue')
    for symptom in sorted(MILD_SYMPTOMS, key=len, reverse=True):
        if symptom in combined_text and not is_covered(symptom):
            if not is_symptom_negated(norm_text, symptom) and not (translated_text and is_symptom_negated(translated_text, symptom)):
                found_symptoms.append(symptom)

    # 4. Moderate symptoms
    for symptom in sorted(MODERATE_SYMPTOMS, key=len, reverse=True):
        if symptom in combined_text and not is_covered(symptom):
            if not is_symptom_negated(norm_text, symptom) and not (translated_text and is_symptom_negated(translated_text, symptom)):
                found_symptoms.append(symptom)

    return found_symptoms


def calculate_risk(symptoms: List[str], mood: str = "normal", nutrition: str = "good") -> Dict[str, Any]:
    """
    Calculate maternal clinical risk score, risk level, and recommendations.
    Accurately classifies emergency, severe, moderate, and mild symptoms.
    """
    risk_score = 0
    is_emergency = False

    symptoms_lower = [s.lower().strip() for s in symptoms if s]

    emergency_found = []
    severe_found = []
    moderate_found = []
    mild_found = []

    for symptom in symptoms_lower:
        if any(em in symptom for em in EMERGENCY_SYMPTOMS) or symptom in EMERGENCY_SYMPTOMS:
            emergency_found.append(symptom)
        elif any(sev in symptom for sev in SEVERE_SYMPTOMS) or symptom in SEVERE_SYMPTOMS:
            severe_found.append(symptom)
        elif any(mild in symptom for mild in MILD_SYMPTOMS) or symptom in MILD_SYMPTOMS:
            mild_found.append(symptom)
        elif any(mod in symptom for mod in MODERATE_SYMPTOMS) or symptom in MODERATE_SYMPTOMS:
            moderate_found.append(symptom)
        else:
            if any(k in symptom for k in ["heart", "bleed", "breath", "seiz", "stroke"]):
                emergency_found.append(symptom)
            elif any(k in symptom for k in ["headache", "swell", "dizz", "pain", "fever"]):
                moderate_found.append(symptom)

    # ---------------- 1. SYMPTOM SCORING ----------------
    if emergency_found:
        is_emergency = True
        risk_score += 80
    
    if severe_found:
        risk_score += len(severe_found) * 40

    if moderate_found:
        risk_score += min(len(moderate_found) * 20, 40)

    if mild_found and not severe_found and not emergency_found:
        risk_score += min(len(mild_found) * 10, 20)

    # ---------------- 2. MOOD SCORING ----------------
    mood_str = (mood or "").lower()
    if mood_str in ["very sad", "depressed", "extreme anxiety"]:
        risk_score += 20
    elif mood_str in ["stressed", "anxious", "sad"]:
        risk_score += 15

    # ---------------- 3. NUTRITION SCORING ----------------
    nutri_str = (nutrition or "").lower()
    if "no food" in nutri_str or "starving" in nutri_str:
        risk_score += 20
    elif "low" in nutri_str or "poor" in nutri_str:
        risk_score += 10

    # ---------------- 4. RISK CLASSIFICATION ----------------
    if is_emergency:
        risk_score = max(risk_score, 80)
        risk_level = "High"
        recommendation = "🚨 URGENT: Critical emergency symptoms detected! Immediate emergency medical care required (Dial 108)."
        escalation = True
    elif risk_score >= 60:
        risk_level = "High"
        recommendation = "Urgent medical attention required. Contact ASHA worker promptly."
        escalation = True
    elif risk_score >= 30:
        risk_level = "Medium"
        recommendation = "Monitor symptoms and consult your ASHA worker."
        escalation = False
    else:
        risk_level = "Low"
        recommendation = "Continue regular monitoring and wellness practices."
        escalation = False

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "escalation": escalation,
        "is_emergency": is_emergency,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def calculate_risk_from_text(text: str, mood: str = "normal", nutrition: str = "good") -> Dict[str, Any]:
    """
    Full pipeline: extract symptoms from raw transcribed text and compute risk.
    """
    symptoms = extract_symptoms(text)
    result = calculate_risk(symptoms, mood, nutrition)
    result["extracted_symptoms"] = symptoms
    return result