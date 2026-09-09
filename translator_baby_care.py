import os
import pprint
import concurrent.futures
from mtranslate import translate

# Base English strings to be translated
baby_strings = {
    # Baby Dashboard
    "baby_portal_title": "👶 Baby Care Portal",
    "err_no_baby_profile": "No baby profile found for this Mother ID. Please contact ASHA Worker.",
    "baby_nav_title": "🍼 Baby Navigation",
    "nav_baby_profile": "Baby Profile",
    "nav_nutrition": "Nutrition Guidance",
    "nav_vaccination": "Vaccination Tracker",
    "nav_growth": "Growth & Development",
    "nav_health_log": "Health Log",
    "nav_emergency": "Emergency Help",
    "baby_profile_sec": "📋 Baby Profile Section",
    "mother_name": "Mother Name",
    "mother_id": "Mother ID",
    "baby_age": "Baby Age",
    "baby_gender": "Gender",
    "delivery_date": "Delivery Date",
    "months_label": "Months",
    "days_label": "Days",
    
    # Nutrition
    "nutri_guide_title": "🍼 Baby Nutrition Guidance",
    "age_0_6_title": "Age 0–6 Months",
    "age_0_6_desc": "- Exclusive breastfeeding recommended\n- Feed every 2–3 hours\n- No solid foods\n- Ensure mother maintains proper nutrition",
    "age_6_12_title": "Age 6–12 Months",
    "age_6_12_desc": "- Breast milk + soft foods\n- Mashed rice\n- Dal\n- Vegetable puree\n- Banana mash",

    # Vaccination Tracker
    "vax_tracker_title": "💉 Vaccination Schedule System",
    "vax_overdue_msg": "### Next Vaccination Due: {0} - OVERDUE by {1} days!",
    "vax_due_msg": "### Next Vaccination Due: {0} in {1} Days",
    "vax_all_done": "### All vaccinations up to date!",
    "col_vaccine": "Vaccine",
    "col_due_date": "Due Date",
    "col_status": "Status",

    # Growth & Dev
    "growth_title": "👶 Baby Growth & Development",
    "milestone_1": "Baby recognizes mother's voice.",
    "milestone_3": "Baby begins smiling and lifting head.",
    "milestone_6": "Baby begins sitting with support.",
    "milestone_9": "Baby starts crawling.",
    "milestone_12": "Baby begins standing.",
    "month_label": "Month {0}",
    "upcoming_label": "(Upcoming)",

    # Health Log
    "health_log_title": "📝 Baby Health Log",
    "fever_label": "Fever",
    "cough_label": "Cough",
    "weight_label": "Baby Weight (kg)",
    "feeding_label": "Feeding Frequency",
    "sleep_label": "Sleep Hours",
    "btn_submit_log": "Submit Log",
    "success_log_saved": "✅ Log saved successfully!",
    "ai_rec_label": "### AI Recommendation:",
    "err_baby_fever": "🚨 Baby health alert: Fever detected or low weight. Please consult ASHA worker or visit nearest PHC immediately.",
    "info_baby_healthy": "Continue exclusive breastfeeding and ensure the baby receives the next scheduled vaccination.",
    
    # Emergency Help
    "baby_emergency_title": "🚨 Baby Emergency",
    "baby_emergency_desc": "⚠️ Press only in case of serious symptoms (High Fever, Difficulty Breathing).",
    "btn_trigger_baby_sos": "🆘 TRIGGER BABY EMERGENCY HELP NOW",
    "success_baby_sos": "✅ Baby Emergency SMS Alert dispatched to your ASHA worker.",

    # ASHA Dashboard - Baby Monitoring
    "nav_baby_monitoring": "Baby Monitoring",
    "asha_baby_monitoring_title": "👶 Baby Monitoring",
    "asha_baby_monitoring_desc": "Complete directory of babies registered in the district.",
    "err_no_baby_records": "No baby records found.",
    "col_next_vaccine": "Next Vaccine",
    "vax_overdue_table": "{0} (OVERDUE)",
    "send_sms_reminders": "Send SMS Reminders",
    "enter_mother_id_rem": "Enter Mother ID to send vaccination reminder:",
    "btn_send_fast2sms": "Send Fast2SMS Reminder",
    "success_reminder_sent": "Reminder sent to {0}",
    "err_enter_mother_id": "Please enter a Mother ID.",
    
    # Form choices
    "choice_no": "No",
    "choice_mild": "Mild",
    "choice_severe": "Severe",
    "choice_high": "High",
    "choice_feed_2h": "Every 2 hours",
    "choice_feed_3h": "Every 3 hours",
    "choice_feed_4h": "Every 4+ hours"
}

languages_to_translate = {
    "Hindi": "hi", "Telugu": "te", "Tamil": "ta", "Kannada": "kn", "Malayalam": "ml",
    "Bengali": "bn", "Marathi": "mr", "Urdu": "ur", "Gujarati": "gu", "Odia": "or", "Punjabi": "pa"
}

all_translations = {"English": baby_strings}

def translate_pair(args):
    lang_name, lang_code, key, text = args
    if not text:
        return lang_name, key, text
    try:
        val = translate(text, lang_code, 'en')
        val = val.replace(' {0}', '{0}').replace('{ 0 }', '{0}').replace('{0} ', '{0}')
        return lang_name, key, val
    except Exception as e:
        print(f"Error {lang_name} {key}: {e}")
        return lang_name, key, text

# Generate tasks
tasks = []
for lang_name, lang_code in languages_to_translate.items():
    all_translations[lang_name] = {}
    for k, v in baby_strings.items():
        tasks.append((lang_name, lang_code, k, v))

print(f"Translating {len(tasks)} phrases across {len(languages_to_translate)} languages...")

# Parallel execution for speed
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    results = list(executor.map(translate_pair, tasks))

for lang_name, key, val in results:
    all_translations[lang_name][key] = val

print("Done translating. Now rewriting translations.py...")

# Import current translations
import sys
sys.path.append(os.getcwd())
from translations import TRANSLATIONS

# Append new translations
for lang, dictionary in all_translations.items():
    if lang in TRANSLATIONS:
        TRANSLATIONS[lang].update(dictionary)
    else:
        TRANSLATIONS[lang] = dictionary

# Write the new TRANSLATIONS dict back to translations.py
with open("translations.py", "w", encoding="utf-8") as f:
    f.write("# Centralized Translation Dictionary for Maatri Suraksha AI\n\n")
    f.write("TRANSLATIONS = {\n")
    for lang, dic in TRANSLATIONS.items():
        f.write(f'    "{lang}": {{\n')
        for k, v in dic.items():
            # escape double quotes and backslashes properly
            escaped_v = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            f.write(f'        "{k}": "{escaped_v}",\n')
        f.write("    },\n")
    f.write("}\n")
    
print("Successfully updated translations.py!")
