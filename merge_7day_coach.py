import json
import ast
import os

translation_file_path = "translations.py"
new_translations_path = "exercise_7day_translations.json"

# Load the new translations
try:
    with open(new_translations_path, "r", encoding="utf-8") as f:
        new_translations = json.load(f)
except FileNotFoundError:
    print(f"Error: {new_translations_path} not found.")
    exit(1)

# Hardcode English new strings since mtranslate script doesn't output English natively
new_english_strings = {
    "prog_7_day_title": "7-Day Pregnancy Exercise Plan",
    "prog_7_day_desc": "Your weekly pregnancy fitness routine. Complete daily safe exercises to improve flexibility, strength, and prepare for delivery.",
    "prog_benefits_title": "Benefits of Daily Exercise",
    "prog_benefits_list": "✅ Improves pelvic flexibility<br>✅ Boosts blood circulation<br>✅ Builds lower body strength<br>✅ Prepares body for delivery",
    "ex_lib_title": "🧘 Exercise Library & Explanations",
    "ex_butterfly": "Butterfly Exercise",
    "ex_duck_walk": "Duck Walk (Forward & Backward)",
    "ex_squats": "Deep Squats",
    "ex_hip_rotation": "Hip Rotation",
    "ex_side_lunges": "Side Lunges",
    "ex_deep_breathing": "Deep Breathing",
    "expl_butterfly": "Sit with legs bent and feet together. Move knees up and down slowly. Duration: 2–3 minutes.",
    "expl_duck_walk": "Squat slightly and walk slowly forward and backward. Keep back straight. Duration: 1–2 minutes.",
    "expl_squats": "Stand with feet shoulder-width apart. Slowly squat down and come back up. Repeat 8–10 times.",
    "expl_hip_rotation": "Stand straight. Rotate hips slowly in circular motion. Repeat 10 rotations.",
    "expl_side_lunges": "Step to one side and bend that knee. Keep other leg straight. Repeat 6–8 times each side.",
    "day_1": "Day 1",
    "day_2": "Day 2",
    "day_3": "Day 3",
    "day_4": "Day 4",
    "day_5": "Day 5",
    "day_6": "Day 6",
    "day_7": "Day 7",
    "title_day_1": "Pelvic Flexibility",
    "title_day_2": "Leg Strength",
    "title_day_3": "Hip Mobility",
    "title_day_4": "Light Strength Training",
    "title_day_5": "Pelvic Strength",
    "title_day_6": "Balance & Movement",
    "title_day_7": "Relaxation & Stretch",
    "ben_day_1": "Improves pelvic flexibility, prepares body for delivery",
    "ben_day_2": "Strengthens leg muscles, improves balance",
    "ben_day_3": "Reduces hip stiffness, improves posture",
    "ben_day_4": "Strengthens lower body, improves stability",
    "ben_day_5": "Strengthens pelvic muscles, improves flexibility",
    "ben_day_6": "Improves balance, reduces stiffness",
    "ben_day_7": "Relaxes muscles, reduces stress",
    "ai_rec_title": "🤖 AI Exercise Recommendation",
    "ai_rec_high": "🚨 Exercise not recommended today due to High Risk level. Please consult your ASHA worker immediately.",
    "ai_rec_low": "🟢 Today's recommended routine: {0} exercises.",
    "track_title": "📊 7-Day Exercise Progress Tracker",
    "track_completed": "✔ Completed",
    "track_pending": "⏳ Pending",
    "track_overall": "Weekly Completion",
    "btn_mark_day_comp": "Mark {0} Routine as Completed"
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

# Write back to translations.py
import pprint
with open(translation_file_path, "w", encoding="utf-8") as f:
    f.write("TRANSLATIONS = ")
    pprint.pprint(existing_translations, stream=f, indent=4, width=120)

print("Successfully merged and updated translations.py")
