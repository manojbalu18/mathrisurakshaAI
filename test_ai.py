from ai_engine import calculate_risk

test = calculate_risk(
    ["headache", "swelling"],
    "stressed",
    "low iron diet"
)

print(test)