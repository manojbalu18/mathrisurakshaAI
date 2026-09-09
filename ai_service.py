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
        "bleeding", "dizzy", "dizziness", "chest pain", "faint", "fainting",
        "high swelling", "pain in heart", "severe pain", "cannot breathe",
        "shortness of breath", "convulsion", "seizure", "unconscious"
    ]

    def __init__(self, client: Optional[LMStudioClient] = None):
        self.client = client or LMStudioClient()

    def check_emergency(self, prompt: str) -> bool:
        """Check if user prompt contains life-critical emergency symptoms."""
        prompt_lower = prompt.lower()
        return any(kw in prompt_lower for kw in self.EMERGENCY_KEYWORDS)

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
            if any(kw in prompt_lower for kw in ["chest", "stomach", "severe", "sharp"]):
                return "Severe pain is a danger sign! Please visit the nearest primary health center or contact your ASHA worker immediately."
            return "Mild abdominal pulling or pelvic aches can be normal as muscles stretch. Rest well, and notify your doctor if pain becomes sharp, frequent, or accompanied by spotting."
        elif any(kw in prompt_lower for kw in ["baby", "kick", "movement"]):
            return "You will usually feel your baby move regularly by 20 to 24 weeks. If you notice a sudden decrease in kicks after 28 weeks, contact your ASHA worker or hospital promptly."
        elif any(kw in prompt_lower for kw in ["vaccine", "injection", "tt"]):
            return "Ensure you receive your Tetanus-Toxoid (TT/Td) injections as scheduled on your MCP card. It protects both mother and newborn against serious infections."
        elif any(kw in prompt_lower for kw in ["danger", "emergency", "warning"]):
            return "Key danger signs: vaginal bleeding, high fever, severe persistent headache, blurred vision, sudden swelling of face/hands, or reduced baby movements. Seek hospital care immediately if any occur."
        
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
        except Exception as e:
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
                "diagnostic": Optional[str]
            }
        """
        user_context = user_context or {}
        risk_level = user_context.get("risk_level", "Normal")
        mother_name = user_context.get("mother_name", "")

        # ---------------- 1. EMERGENCY SAFETY OVERRIDE ----------------
        if self.check_emergency(prompt):
            emergency_text = (
                "⚠ **CRITICAL ALERT:** These symptoms may indicate a high-risk pregnancy condition. "
                "Please contact your ASHA worker, ANM, or nearest health center (Dial 108) immediately."
            )
            translated_response = self.translate_text(emergency_text, language_name)
            return {
                "response": translated_response,
                "is_emergency": True,
                "source": "emergency_override",
                "server_online": False,
                "diagnostic": "Emergency keyword triggered safety escalation."
            }

        # ---------------- 2. LM STUDIO EXECUTION ----------------
        server_status = self.client.check_connection(timeout=2.0)
        is_online = server_status.get("online", False)

        response_text = ""
        source = "fallback"
        diagnostic = None

        if is_online:
            # Build conversation payload with maternal health system prompt and context
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]

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

        # ---------------- 4. TRANSLATION ----------------
        translated_response = self.translate_text(response_text, language_name)

        return {
            "response": translated_response,
            "is_emergency": False,
            "source": source,
            "server_online": is_online,
            "diagnostic": diagnostic,
        }
