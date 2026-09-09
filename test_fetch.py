from database import init_db, get_all_logs, get_active_alerts

init_db()

logs = get_all_logs()
alerts = get_active_alerts()

print("All Logs:")
print(logs)

print("\nActive Alerts:")
print(alerts)