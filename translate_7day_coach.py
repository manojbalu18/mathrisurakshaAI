import json
from mtranslate import translate
import concurrent.futures

new_english_strings = {
    # Program Meta
    "prog_7_day_title": "7-Day Pregnancy Exercise Plan",
    "prog_7_day_desc": "Your weekly pregnancy fitness routine. Complete daily safe exercises to improve flexibility, strength, and prepare for delivery.",
    "prog_benefits_title": "Benefits of Daily Exercise",
    "prog_benefits_list": "✅ Improves pelvic flexibility<br>✅ Boosts blood circulation<br>✅ Builds lower body strength<br>✅ Prepares body for delivery",
    
    # Library Meta
    "ex_lib_title": "🧘 Exercise Library & Explanations",
    
    # Exercises
    "ex_butterfly": "Butterfly Exercise",
    "ex_duck_walk": "Duck Walk (Forward & Backward)",
    "ex_squats": "Deep Squats",
    "ex_hip_rotation": "Hip Rotation",
    "ex_side_lunges": "Side Lunges",
    "ex_deep_breathing": "Deep Breathing",
    
    # Explanations
    "expl_butterfly": "Sit with legs bent and feet together. Move knees up and down slowly. Duration: 2–3 minutes.",
    "expl_duck_walk": "Squat slightly and walk slowly forward and backward. Keep back straight. Duration: 1–2 minutes.",
    "expl_squats": "Stand with feet shoulder-width apart. Slowly squat down and come back up. Repeat 8–10 times.",
    "expl_hip_rotation": "Stand straight. Rotate hips slowly in circular motion. Repeat 10 rotations.",
    "expl_side_lunges": "Step to one side and bend that knee. Keep other leg straight. Repeat 6–8 times each side.",
    
    # Days
    "day_1": "Day 1",
    "day_2": "Day 2",
    "day_3": "Day 3",
    "day_4": "Day 4",
    "day_5": "Day 5",
    "day_6": "Day 6",
    "day_7": "Day 7",
    
    # Day Titles
    "title_day_1": "Pelvic Flexibility",
    "title_day_2": "Leg Strength",
    "title_day_3": "Hip Mobility",
    "title_day_4": "Light Strength Training",
    "title_day_5": "Pelvic Strength",
    "title_day_6": "Balance & Movement",
    "title_day_7": "Relaxation & Stretch",
    
    # Day Benefits
    "ben_day_1": "Improves pelvic flexibility, prepares body for delivery",
    "ben_day_2": "Strengthens leg muscles, improves balance",
    "ben_day_3": "Reduces hip stiffness, improves posture",
    "ben_day_4": "Strengthens lower body, improves stability",
    "ben_day_5": "Strengthens pelvic muscles, improves flexibility",
    "ben_day_6": "Improves balance, reduces stiffness",
    "ben_day_7": "Relaxes muscles, reduces stress",
    
    # AI Logic
    "ai_rec_title": "🤖 AI Exercise Recommendation",
    "ai_rec_high": "🚨 Exercise not recommended today due to High Risk level. Please consult your ASHA worker immediately.",
    "ai_rec_low": "🟢 Today's recommended routine: {0} exercises.",
    
    # Tracking
    "track_title": "📊 7-Day Exercise Progress Tracker",
    "track_completed": "✔ Completed",
    "track_pending": "⏳ Pending",
    "track_overall": "Weekly Completion",
    
    # Actions
    "btn_mark_day_comp": "Mark {0} Routine as Completed"
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

with open("exercise_7day_translations.json", "w", encoding="utf-8") as f:
    json.dump(all_new_translations, f, ensure_ascii=False, indent=4)

print("Translation complete. exercise_7day_translations.json generated.")
