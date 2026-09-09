"""
Validation script for LM Studio Client, AI Service, Voice Service, and TTS Service.
"""

import unittest
from lm_studio_client import LMStudioClient
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService


class TestIntegrationModules(unittest.TestCase):

    def test_lm_studio_client_offline_behavior(self):
        client = LMStudioClient(base_url="http://127.0.0.1:54321/v1", timeout=1)
        status = client.check_connection(timeout=0.5)
        self.assertFalse(status["online"])
        self.assertTrue("Cannot connect" in status["message"] or "timed out" in status["message"])

    def test_emergency_override(self):
        service = AIService()
        self.assertTrue(service.check_emergency("I have severe bleeding and chest pain"))
        self.assertFalse(service.check_emergency("Can I drink milk with almonds?"))

        result = service.process_message("I am experiencing bleeding and feeling dizzy", language_name="English")
        self.assertTrue(result["is_emergency"])
        self.assertEqual(result["source"], "emergency_override")
        self.assertIn("CRITICAL ALERT", result["response"])

    def test_fallback_knowledge_base(self):
        service = AIService()
        resp = service.get_fallback_response("Can I eat papaya?")
        self.assertIn("papaya", resp.lower())

        resp_diet = service.get_fallback_response("What food should I eat for iron?")
        self.assertIn("iron", resp_diet.lower())

    def test_tts_service(self):
        tts = TTSService()
        cleaned = tts.clean_text_for_speech("### Hello **World**! 👶 [Link](http://example.com)")
        self.assertEqual(cleaned, "Hello World! Link")

        # Test synthesis of simple sentence
        audio = tts.synthesize("Drink plenty of clean water every day.", "English")
        self.assertIsNotNone(audio)
        self.assertGreater(len(audio), 100)

    def test_voice_service_language_mapping(self):
        vs = VoiceService()
        self.assertEqual(vs.get_stt_language_code("Hindi"), "hi-IN")
        self.assertEqual(vs.get_stt_language_code("Telugu"), "te-IN")
        self.assertEqual(vs.get_stt_language_code("English"), "en-IN")

    def test_service_with_context(self):
        service = AIService()
        # High risk context should append warning note
        result = service.process_message(
            "What can I eat today?",
            user_context={"risk_level": "High", "mother_name": "Pooja"},
            language_name="English"
        )
        self.assertIn("High Risk", result["response"])

    def test_translation_integration(self):
        service = AIService()
        translated = service.translate_text("Hello mother", "Hindi")
        self.assertTrue(len(translated) > 0)


if __name__ == "__main__":
    unittest.main()
