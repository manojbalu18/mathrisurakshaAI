import json
from translations import TRANSLATIONS

# Load the new translations
with open("dashboard_translations.json", "r", encoding="utf-8") as f:
    new_data = json.load(f)

# English strings (base)
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
    "stable_health": "Stable maternal health."
}

# Update English
if "English" in TRANSLATIONS:
    TRANSLATIONS["English"].update(new_english_strings)

# Update other languages
for lang, data in new_data.items():
    if lang in TRANSLATIONS:
        TRANSLATIONS[lang].update(data)
    else:
        # If language doesn't exist in TRANSLATIONS for some reason, create it
        TRANSLATIONS[lang] = data

# Write back to translations.py
with open("translations.py", "w", encoding="utf-8") as f:
    f.write("# Centralized Translation Dictionary for Maatri Suraksha AI\n\n")
    f.write("TRANSLATIONS = ")
    # Using json.dumps to get a clean string, then replacing to look like a python dict (mostly just double quotes)
    # Actually, using pprint.pformat is better for readability in a .py file
    import pprint
    f.write(pprint.pformat(TRANSLATIONS, indent=4, width=120))
    f.write("\n")

print("Successfully merged and updated translations.py")
