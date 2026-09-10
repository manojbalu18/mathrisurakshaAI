"""
AI Service for MathriSurakshaAI.
Orchestrates AI interactions between UI, LM Studio, safety overrides,
patient context, fallback knowledge base, and multi-language translation.
"""

from typing import List, Dict, Any, Optional
from config import SYSTEM_PROMPT, TRANSLATE_LANGUAGE_MAP
from lm_studio_client import LMStudioClient, LMStudioError
from mtranslate import translate


class AIService:
    """Unified AI service orchestrating maternal health queries."""

    # Emergency safety keywords requiring immediate escalation
    EMERGENCY_KEYWORDS = [
        "heart attack", "cardiac arrest", "chest pain", "pain in heart",
        "bleeding", "blood", "dizzy", "dizziness", "faint", "fainting",
        "high swelling", "severe pain", "cannot breathe", "can't breathe",
        "shortness of breath", "convulsion", "seizure", "unconscious",
        "stroke", "severe headache", "blurred vision", "reduced fetal movement",
        "no fetal movement", "high fever", "severe abdominal pain", "water broke"
    ]

    def __init__(self, client: Optional[LMStudioClient] = None):
        self.client = client or LMStudioClient()

    def detect_language(self, text: str, default_lang: str = "English") -> str:
        """
        Detect input language based on Unicode script ranges and character analysis.
        Falls back to default_lang if purely ASCII or undetermined.
        """
        if not text:
            return default_lang or "English"
        for char in text:
            code = ord(char)
            if 0x0C00 <= code <= 0x0C7F:
                return "Telugu"
            elif 0x0B80 <= code <= 0x0BFF:
                return "Tamil"
            elif 0x0C80 <= code <= 0x0CFF:
                return "Kannada"
            elif 0x0D00 <= code <= 0x0D7F:
                return "Malayalam"
            elif 0x0900 <= code <= 0x097F:
                return "Hindi" if default_lang not in ["Marathi", "Hindi"] else default_lang
            elif 0x0980 <= code <= 0x09FF:
                return "Bengali"
            elif 0x0A80 <= code <= 0x0AFF:
                return "Gujarati"
            elif 0x0A00 <= code <= 0x0A7F:
                return "Punjabi"
            elif 0x0B00 <= code <= 0x0B7F:
                return "Odia"
            elif 0x0600 <= code <= 0x06FF:
                return "Urdu"
        return default_lang or "English"

    def check_emergency(self, prompt: str) -> bool:
        """Check if user prompt contains life-critical emergency symptoms across languages."""
        if not prompt:
            return False
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in self.EMERGENCY_KEYWORDS):
            return True

        # Multilingual check: if prompt contains non-ASCII characters, translate to English
        has_non_ascii = any(ord(char) > 127 for char in prompt)
        if has_non_ascii:
            try:
                translated = translate(prompt, "en", "auto").lower()
                if any(kw in translated for kw in self.EMERGENCY_KEYWORDS):
                    return True
            except Exception:
                pass
        return False

    def get_fallback_response(self, prompt: str) -> str:
        """
        Rule-based maternal health knowledge base.
        Ensures the system continues assisting mothers even when LM Studio is offline.
        """
        prompt_lower = prompt.lower()

        if any(kw in prompt_lower for kw in ["iron", "anemia", "weak"]):
            return "To increase iron, eat spinach, jaggery, beetroot, and legumes. Taking Vitamin C (like lemon juice) helps your body absorb iron better. Also remember to take your daily IFA tablets!"
        elif any(kw in prompt_lower for kw in ["calcium", "milk", "bones", "paneer"]):
            return "Calcium is essential for your baby's developing bones. Drink milk daily, and include curd/yogurt, paneer, and ragi in your diet. Do not take calcium and iron tablets at the same time."
        elif any(kw in prompt_lower for kw in ["folic", "acid", "spinach"]):
            return "Folic acid is crucial, especially during early pregnancy, to protect baby's brain and spinal development. Keep taking your supplements and eat green leafy vegetables and lentils."
        elif "papaya" in prompt_lower:
            return "Avoid raw or semi-ripe papaya during pregnancy because it contains latex, which can trigger uterine contractions. Fully ripe papaya is generally safer in moderation, but consult your doctor."
        elif "pineapple" in prompt_lower:
            return "Pineapple in large amounts can sometimes cause softening of the cervix due to the enzyme bromelain. It is best to avoid it early in pregnancy."
        elif any(kw in prompt_lower for kw in ["coffee", "tea", "caffeine"]):
            return "Limit your caffeine intake! Try to have no more than 1 small cup of tea or coffee a day. Excessive caffeine is not advised for baby's heart and growth."
        elif any(kw in prompt_lower for kw in ["water", "drink", "thirsty", "hydration"]):
            return "Drink at least 8 to 10 glasses of clean, boiled water daily. Staying hydrated reduces leg cramps, prevents UTIs, and supports amniotic fluid levels."
        elif any(kw in prompt_lower for kw in ["weight", "gain", "heavy"]):
            return "A steady weight gain is normal and healthy! Most pregnant mothers gain between 10-12 kg overall. Focus on nutritious, balanced meals rather than large quantities."
        elif any(kw in prompt_lower for kw in ["eat", "diet", "food", "nutrition", "hungry"]):
            return "Eat a balanced diet rich in iron, calcium, and protein. Include green leafy vegetables, dairy, lentils, seasonal fruits, and plenty of water."
        elif any(kw in prompt_lower for kw in ["walk", "exercise", "yoga", "workout"]):
            return "Light walking for 20 to 30 minutes daily is beneficial. Gentle prenatal yoga like the butterfly stretch is safe. Avoid heavy lifting and intense exertion."
        elif any(kw in prompt_lower for kw in ["sleep", "tired", "rest", "fatigue"]):
            return "Pregnant mothers should sleep at least 8 hours at night and rest 1-2 hours during the afternoon. Sleeping on your left side improves blood flow to your baby."
        elif any(kw in prompt_lower for kw in ["swell", "feet", "legs"]):
            return "Mild swelling in feet is common. Rest with your feet elevated. If you notice sudden or severe swelling in your hands or face, inform your ASHA worker immediately."
        elif any(kw in prompt_lower for kw in ["vomit", "nausea", "morning sickness"]):
            return "Morning sickness is common in early pregnancy. Eat small, frequent meals. Ginger tea, lemon water, and dry crackers help. If you cannot retain any fluids, visit the health center."
        elif any(kw in prompt_lower for kw in ["headache", "dizzy", "spin"]):
            return "Rest in a quiet room, hydrate well, and have a light snack. If the headache is severe, accompanied by blurred vision or swelling, visit a clinic immediately."
        elif any(kw in prompt_lower for kw in ["back", "backache"]):
            return "Backache is common as baby grows. Keep good posture, wear comfortable flat footwear, and use a firm mattress. Avoid lifting heavy weights."
        elif any(kw in prompt_lower for kw in ["pain", "ache", "cramp"]):
            if any(kw in prompt_lower for kw in ["chest", "stomach", "severe", "sharp", "heart"]):
                return "Severe pain is a danger sign! Please visit the nearest primary health center or contact your ASHA worker immediately."
            return "Mild abdominal pulling or pelvic aches can be normal as muscles stretch. Rest well, and notify your doctor if pain becomes sharp, frequent, or accompanied by spotting."
        elif any(kw in prompt_lower for kw in ["baby", "kick", "movement"]):
            return "You will usually feel your baby move regularly by 20 to 24 weeks. If you notice a sudden decrease in kicks after 28 weeks, contact your ASHA worker or hospital promptly."
        elif any(kw in prompt_lower for kw in ["vaccine", "injection", "tt"]):
            return "Ensure you receive your Tetanus-Toxoid (TT/Td) injections as scheduled on your MCP card. It protects both mother and newborn against serious infections."
        elif any(kw in prompt_lower for kw in ["danger", "emergency", "warning", "attack"]):
            return "Key danger signs: vaginal bleeding, high fever, severe persistent headache, blurred vision, sudden swelling of face/hands, chest pain, or reduced baby movements. Seek hospital care immediately if any occur."
        
        return "I am your MAATRI AI Assistant. Please ask me any questions regarding your pregnancy diet, daily nutrition, safe exercises, or symptoms."

    def translate_text(self, text: str, language_name: str) -> str:
        """Translate text from English to user's selected language using mtranslate."""
        if not language_name or language_name.lower() == "english":
            return text
        
        target_code = TRANSLATE_LANGUAGE_MAP.get(language_name, "en")
        if target_code == "en":
            return text

        try:
            return translate(text, target_code, "en")
        except Exception:
            # If translation fails, return original English text
            return text

    def process_message(
        self,
        prompt: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        language_name: str = "English",
        custom_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main processing pipeline for user queries (typed or voice-transcribed).
        
        Returns:
            dict: {
                "response": str,
                "is_emergency": bool,
                "source": "emergency_override" | "lm_studio" | "fallback",
                "server_online": bool,
                "detected_language": str,
                "diagnostic": Optional[str]
            }
        """
        user_context = user_context or {}
        risk_level = user_context.get("risk_level", "Normal")
        mother_name = user_context.get("mother_name", "")

        # Detect the true input language (prioritize detected script, fallback to language_name)
        target_lang = self.detect_language(prompt, default_lang=language_name)

        # ---------------- 1. EMERGENCY SAFETY OVERRIDE ----------------
        if self.check_emergency(prompt):
            emergency_text = (
                "⚠ **CRITICAL ALERT:** These symptoms may indicate an urgent high-risk condition. "
                "Please contact your ASHA worker, ANM, or nearest emergency health center (Dial 108) immediately."
            )
            translated_response = self.translate_text(emergency_text, target_lang)
            return {
                "response": translated_response,
                "is_emergency": True,
                "source": "emergency_override",
                "server_online": False,
                "detected_language": target_lang,
                "diagnostic": "Emergency keyword triggered safety escalation."
            }

        # ---------------- 2. LM STUDIO EXECUTION ----------------
        server_status = self.client.check_connection(timeout=2.0)
        is_online = server_status.get("online", False)

        response_text = ""
        source = "fallback"
        diagnostic = None

        if is_online:
            # Build conversation payload with maternal health system prompt and language instructions
            lang_instruction = f"The user is communicating in {target_lang}. You MUST respond in the exact same language as the user's message ({target_lang}). Do not automatically translate the response to English."
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": lang_instruction}
            ]

            # Inject patient context into system prompt if known
            if risk_level != "Normal" or mother_name:
                context_info = f"Context: Patient: {mother_name or 'Mother'}, Current Assessed Risk Level: {risk_level}."
                messages.append({"role": "system", "content": context_info})

            # Append relevant conversation history (up to last 6 turns)
            if chat_history:
                for msg in chat_history[-6:]:
                    if msg.get("role") in ["user", "assistant"] and msg.get("content"):
                        messages.append({"role": msg["role"], "content": msg["content"]})

            # Append current prompt
            messages.append({"role": "user", "content": prompt})

            try:
                response_text = self.client.create_chat_completion(
                    messages=messages,
                    model=custom_model,
                    temperature=0.7,
                    max_tokens=512,
                )
                source = "lm_studio"
                diagnostic = f"Generated by LM Studio using model: {server_status.get('active_model')}"
            except LMStudioError as e:
                # Log error and fall back to local knowledge base
                diagnostic = f"LM Studio call failed ({str(e)}). Used local knowledge base."
                response_text = self.get_fallback_response(prompt)
                source = "fallback"
        else:
            diagnostic = f"LM Studio offline ({server_status.get('message')}). Used local knowledge base."
            response_text = self.get_fallback_response(prompt)
            source = "fallback"

        # ---------------- 3. CONTEXT ENRICHMENT ----------------
        if risk_level == "High" and source != "emergency_override":
            high_risk_note = "\n\n(Note: Your last health log indicated a High Risk level. Please stay in continuous touch with your ASHA worker.)"
            response_text += high_risk_note

        # ---------------- 4. SAME-LANGUAGE ASSURANCE ----------------
        final_response = response_text
        if target_lang != "English":
            # Check if response contains target language script
            has_target_script = False
            for char in final_response:
                code = ord(char)
                if target_lang == "Telugu" and 0x0C00 <= code <= 0x0C7F:
                    has_target_script = True; break
                elif target_lang == "Tamil" and 0x0B80 <= code <= 0x0BFF:
                    has_target_script = True; break
                elif target_lang in ["Hindi", "Marathi"] and 0x0900 <= code <= 0x097F:
                    has_target_script = True; break
                elif target_lang == "Kannada" and 0x0C80 <= code <= 0x0CFF:
                    has_target_script = True; break
                elif target_lang == "Malayalam" and 0x0D00 <= code <= 0x0D7F:
                    has_target_script = True; break
                elif target_lang == "Bengali" and 0x0980 <= code <= 0x09FF:
                    has_target_script = True; break
                elif target_lang == "Gujarati" and 0x0A80 <= code <= 0x0AFF:
                    has_target_script = True; break
                elif target_lang == "Punjabi" and 0x0A00 <= code <= 0x0A7F:
                    has_target_script = True; break
                elif target_lang == "Odia" and 0x0B00 <= code <= 0x0B7F:
                    has_target_script = True; break
                elif target_lang == "Urdu" and 0x0600 <= code <= 0x06FF:
                    has_target_script = True; break
            
            if not has_target_script:
                final_response = self.translate_text(final_response, target_lang)

        return {
            "response": final_response,
            "is_emergency": False,
            "source": source,
            "server_online": is_online,
            "detected_language": target_lang,
            "diagnostic": diagnostic,
        }
