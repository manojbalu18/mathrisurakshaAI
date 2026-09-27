from ai_engine import calculate_risk
from database import save_daily_log, create_alert, init_db

# VERY IMPORTANT → initialize database first
init_db()

user_id = 1

symptoms = ["headache", "swelling"]
mood = "stressed"
nutrition = "low iron diet"

result = calculate_risk(symptoms, mood, nutrition)

save_daily_log(
    user_id,
    symptoms,
    mood,
    nutrition,
    result["risk_score"],
    result["risk_level"],
    result["timestamp"]
)

if result["risk_level"] == "High":
    create_alert(user_id, result["risk_level"], result["timestamp"])

print("Saved Successfully")