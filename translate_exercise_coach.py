import json
from mtranslate import translate
import concurrent.futures

new_english_strings = {
    # Menu & Dashboard
    "menu_exercise_coach": "Exercise Coach",
    "exercise_coach_title": "Pregnancy Exercise Coach",
    "exercise_coach_desc": "Safe exercises and breathing practices recommended for pregnant women to improve health and reduce stress.",
    "exercise_safety_warning": "⚠️ Stop exercise immediately if you experience dizziness, pain, or discomfort. Consult a healthcare worker before starting new exercises.",
    
    # Categories
    "exercise_cat_breathing": "Breathing Exercises",
    "exercise_cat_stretching": "Light Stretching",
    "exercise_cat_walking": "Walking Guidance",

    # Details
    "breathing_desc_1": "Inhale slowly through the nose for 4 seconds",
    "breathing_desc_2": "Exhale gently for 6 seconds",
    "breathing_desc_3": "Repeat for 5 minutes",
    "stretch_neck": "Neck Stretch",
    "stretch_shoulder": "Shoulder Rotation",
    "stretch_arm": "Gentle Arm Stretch",
    "stretch_desc": "These exercises help reduce muscle tension.",
    "walk_time": "10–20 minutes daily",
    "walk_surface": "Avoid uneven surfaces",
    "walk_stop": "Stop if dizziness occurs",
    
    # Weekly Recommendations
    "tri_1_tab": "Trimester 1",
    "tri_1_desc_1": "Light walking",
    "tri_1_desc_2": "Breathing exercises",
    "tri_1_desc_3": "Gentle stretching",
    "tri_2_tab": "Trimester 2",
    "tri_2_desc_1": "Pelvic tilts",
    "tri_2_desc_2": "Side leg lifts",
    "tri_2_desc_3": "Prenatal yoga",
    "tri_3_tab": "Trimester 3",
    "tri_3_desc_1": "Relaxation breathing",
    "tri_3_desc_2": "Slow walking",
    "tri_3_desc_3": "Pelvic floor exercises",

    # AI & Voice 
    "ai_ex_rec_title": "AI Recommendation",
    "ai_ex_rec_desc": "Based on your current health logs, light walking and breathing exercises are recommended today.",
    "btn_voice_breathe": "Start Guided Breathing Exercise",
    "voice_inst_1": "Inhale slowly",
    "voice_inst_2": "Hold your breath",
    "voice_inst_3": "Exhale gently",

    # Actions
    "btn_mark_completed": "Mark as Completed",
    "success_ex_logged": "✅ Exercise logged successfully! Great job staying active.",
    "title_recent_ex": "Recent Exercise Activity",
    "no_recent_ex": "No exercises logged yet.",
    
    # ASHA Dashboard
    "asha_ex_activity": "Exercise Activity",
    "asha_ex_last_updated": "Last Updated"
}

languages = {
    "Hindi": "hi", "Telugu": "te", "Tamil": "ta", "Kannada": "kn", "Malayalam": "ml",
    "Bengali": "bn", "Marathi": "mr", "Urdu": "ur", "Gujarati": "gu", "Odia": "or", "Punjabi": "pa"
}

all_new_translations = {}

def translate_task(args):
    lang_name, lang_code, key, text = args
    try:
        translated_text = translate(text, lang_code, 'en')
        return lang_name, key, translated_text
    except Exception as e:
        print(f"Error translating {key} to {lang_name}: {e}")
        return lang_name, key, text

tasks = []
for lang_name, lang_code in languages.items():
    all_new_translations[lang_name] = {}
    for key, text in new_english_strings.items():
        tasks.append((lang_name, lang_code, key, text))

print(f"Starting translation for {len(tasks)} items...")
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(translate_task, tasks))

for lang_name, key, translated_text in results:
    all_new_translations[lang_name][key] = translated_text

with open("exercise_coach_translations.json", "w", encoding="utf-8") as f:
    json.dump(all_new_translations, f, ensure_ascii=False, indent=4)

print("Translation complete. exercise_coach_translations.json generated.")
