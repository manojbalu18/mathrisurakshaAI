import json
import pprint

with open("new_translations_generated.json", "r", encoding="utf-8") as f:
    new_langs = json.load(f)

# Read the original translations.py
with open("translations.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove the trailing '}' of the TRANSLATIONS dict
# Find the last '}'
last_brace_idx = content.rfind('}')
if last_brace_idx != -1:
    content = content[:last_brace_idx]

# Format the new languages
formatted_new = ""
for lang, data in new_langs.items():
    formatted_new += f",\n    \"{lang}\": "
    formatted_new += pprint.pformat(data, indent=4, width=120)

formatted_new += "\n}"

with open("translations.py", "w", encoding="utf-8") as f:
    f.write(content + formatted_new)

print("Appended new languages to translations.py")
