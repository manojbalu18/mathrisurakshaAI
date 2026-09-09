import json
from mtranslate import translate
import concurrent.futures

# New strings for the Village Health Intelligence Dashboard
new_english_strings = {
    "asha_village_health_title": "🏥 Village Health Intelligence",
    "asha_village_health_desc": "Real-time maternal and child health analytics across your assigned villages.",
    "risk_dist_title": "Maternal Risk Distribution",
    "vax_monitor_title": "Vaccination Coverage Monitor",
    "village_heatmap_title": "Village Risk Heatmap",
    "ai_predictions_title": "AI Village Predictions",
    "high_risk_alerts_title": "High Risk Mother Alerts",
    "baby_health_alerts_title": "Baby Health Alerts",
    "daily_task_list_title": "ASHA Worker Daily Task List",
    "upcoming_vax_title": "Upcoming Vaccines (Next 7 Days)",
    "priority_tasks_header": "Today's Generated Priority Tasks",
    "no_risk_data": "No maternal risk data available yet.",
    "no_vax_data": "No vaccination data registered.",
    "no_village_data": "No active locations mapped for villages yet.",
    "awaiting_data": "Awaiting data...",
    "no_high_risk_flagged": "No High Risk mothers actively flagged.",
    "no_baby_alerts": "No critical baby health logs reported recently.",
    "no_upcoming_vax": "No vaccines scheduled for the next 7 days.",
    "village_label": "Village",
    "avg_score_label": "Avg Risk",
    "mothers_count_label": "Mothers",
    "high_risk_cluster": "High Risk Cluster forming. Prioritize immediately.",
    "medium_risk_cluster": "Elevated risks detected. Schedule routine checks.",
    "stable_health": "Stable maternal health.",
    # Vaccination Status Labels
    "vax_status_done": "Vaccinated",
    "vax_status_pending": "Pending",
    "vax_status_overdue": "Overdue",
    # Task Patterns
    "task_followup_high_risk": "Follow-up for High Risk Case ({0} in {1})",
    "task_vax_today": "Vaccination for Baby of {0} - {1} ({2})",
    "task_routine_visit": "Check BP & Routine Visit for {0} ({1})",
    "task_no_critical": "No critical tasks today. Conduct routine village surveys."
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

# Save to temporary JSON
with open("dashboard_translations.json", "w", encoding="utf-8") as f:
    json.dump(all_new_translations, f, ensure_ascii=False, indent=4)

print("Translation complete. dashboard_translations.json generated.")
