import json
import ast
import os

translation_file_path = "translations.py"
new_translations_path = "exercise_coach_translations.json"

# Load the new translations
with open(new_translations_path, "r", encoding="utf-8") as f:
    new_translations = json.load(f)

# Hardcode English new strings since mtranslate script doesn't output English
new_english_strings = {
    "menu_exercise_coach": "Exercise Coach",
    "exercise_coach_title": "Pregnancy Exercise Coach",
    "exercise_coach_desc": "Safe exercises and breathing practices recommended for pregnant women to improve health and reduce stress.",
    "exercise_safety_warning": "⚠️ Stop exercise immediately if you experience dizziness, pain, or discomfort. Consult a healthcare worker before starting new exercises.",
    "exercise_cat_breathing": "Breathing Exercises",
    "exercise_cat_stretching": "Light Stretching",
    "exercise_cat_walking": "Walking Guidance",
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
    "ai_ex_rec_title": "AI Recommendation",
    "ai_ex_rec_desc": "Based on your current health logs, light walking and breathing exercises are recommended today.",
    "btn_voice_breathe": "Start Guided Breathing Exercise",
    "voice_inst_1": "Inhale slowly",
    "voice_inst_2": "Hold your breath",
    "voice_inst_3": "Exhale gently",
    "btn_mark_completed": "Mark as Completed",
    "success_ex_logged": "✅ Exercise logged successfully! Great job staying active.",
    "title_recent_ex": "Recent Exercise Activity",
    "no_recent_ex": "No exercises logged yet.",
    "asha_ex_activity": "Exercise Activity",
    "asha_ex_last_updated": "Last Updated"
}
new_translations["English"] = new_english_strings

# Read the existing translations.py
with open(translation_file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Parse the TRANSLATIONS dictionary
try:
    tree = ast.parse(content)
    dict_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TRANSLATIONS":
                    dict_node = node.value
                    break
            if dict_node:
                break

    if dict_node:
        existing_translations = ast.literal_eval(node.value)
    else:
        raise ValueError("TRANSLATIONS dictionary not found")
except Exception as e:
    print(f"Failed to parse translations.py: {e}")
    exit(1)

# Merge the new translations
for lang, strings in new_translations.items():
    if lang in existing_translations:
        existing_translations[lang].update(strings)
    else:
        existing_translations[lang] = strings

# Write back to translations.py using pprint to maintain readability
import pprint
with open(translation_file_path, "w", encoding="utf-8") as f:
    f.write("TRANSLATIONS = ")
    pprint.pprint(existing_translations, stream=f, indent=4, width=120)

print("Successfully merged and updated translations.py")
