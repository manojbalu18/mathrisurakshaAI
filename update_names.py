import sqlite3

def update_specific_names():
    conn = sqlite3.connect('maatrisuraksha.db')
    c = conn.cursor()
    
    updates = [
        ("001", "Sath"),
        ("002", "Vika"),
        ("003", "Amu"),
        ("004", "Sonu"),
        ("005", "Priya"),
        ("006", "Jula"),
        ("007", "Rosh"),
        ("008", "Nithu"),
        ("009", "Chikky"),
        ("010", "Cherry"),
        ("011", "Laddu"),
        ("012", "Hasini")
    ]
    
    for uid, name in updates:
        c.execute("UPDATE users SET name = ? WHERE unique_id = ?", (name, uid))
        
    conn.commit()
    conn.close()
    print("Successfully updated specific names for IDs 001-012.")

if __name__ == "__main__":
    update_specific_names()
