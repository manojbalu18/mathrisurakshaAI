import translations
import json
import concurrent.futures
from mtranslate import translate
import pprint

# Keys to add
new_keys_en = {
    "daily_task_list_title": "📋 ASHA Worker Daily Task List",
    "priority_tasks_header": "Today's Generated Priority Tasks",
    "task_followup_high_risk": "Follow-up for High Risk case ({0} - {1})",
    "task_vax_today": "Vaccination Due: {1} for {0} ({2})",
    "task_routine_visit": "Routine Check-up: {0} ({1})",
    "task_no_critical": "✅ No critical tasks today. Follow routine village visits.",
    "upcoming_vax_title": "📅 Upcoming Vaccinations (Next 7 Days)",
    "no_upcoming_vax": "No vaccinations due in the next 7 days."
}

languages_codes = {
    "Tamil": "ta", "Kannada": "kn", "Malayalam": "ml",
    "Bengali": "bn", "Marathi": "mr", "Urdu": "ur",
    "Gujarati": "gu", "Odia": "or", "Punjabi": "pa",
    "Hindi": "hi", "Telugu": "te"
}

def translate_task(lang_name, lang_code):
    translated = {}
    for key, text in new_keys_en.items():
        try:
            val = translate(text, lang_code, 'en')
            # Fix placeholder formatting issues often caused by translation
            val = val.replace(' {0}', '{0}').replace('{ 0 }', '{0}').replace('{0} ', '{0}')
            val = val.replace(' {1}', '{1}').replace('{ 1 }', '{1}').replace('{1} ', '{1}')
            val = val.replace(' {2}', '{2}').replace('{ 2 }', '{2}').replace('{2} ', '{2}')
            translated[key] = val
        except Exception as e:
            print(f"Error translating {key} to {lang_name}: {e}")
            translated[key] = text
    return lang_name, translated

print("Translating new ASHA task keys...")
updated_translations = translations.TRANSLATIONS.copy()

# Add English directly
for k, v in new_keys_en.items():
    updated_translations["English"][k] = v

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(lambda lang: translate_task(lang[0], lang[1]), languages_codes.items()))

for lang_name, translated_dict in results:
    if lang_name in updated_translations:
        updated_translations[lang_name].update(translated_dict)

# Write back to translations.py
print("Writing back to translations.py...")
with open("translations.py", "w", encoding="utf-8") as f:
    f.write("# Centralized Translation Dictionary for Maatri Suraksha AI\n\n")
    f.write("TRANSLATIONS = ")
    # Use pprint for nice indentation
    f.write(pprint.pformat(updated_translations, indent=4, width=120))
    f.write("\n")

print("Done!")
