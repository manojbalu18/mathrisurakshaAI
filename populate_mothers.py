import sqlite3
import random

def populate_mothers():
    conn = sqlite3.connect('maatrisuraksha.db')
    c = conn.cursor()
    
    # Clear existing users to start fresh
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM sqlite_sequence WHERE name='users'")
    
    # Simple 3-letter name components for variety
    vowels = "AEIOU"
    consonants = "BCDFGHJKLMNPQRSTVWXYZ"
    
    names = []
    # Common 3-letter names
    base_names = ["Ada", "Amy", "Ani", "Ann", "Ava", "Bea", "Deb", "Dot", "Eva", "Eve", 
                  "Fay", "Gia", "Ida", "Ivy", "Jan", "Joy", "Kay", "Lea", "Liz", "Lou", 
                  "Mae", "Meg", "Mia", "Nan", "Nia", "Pam", "Peg", "Rae", "Ria", "Sue", 
                  "Tea", "Uma", "Val", "Zoe"]
    
    # Generate 40 names
    for i in range(1, 41):
        if i <= len(base_names):
            name = base_names[i-1]
        else:
            # Generate pseudo 3-letter names by combining
            name = random.choice(consonants) + random.choice(vowels).lower() + random.choice(consonants).lower()
            
        unique_id = str(i).zfill(3) # e.g. 001, 002... 130
        village = "Rampur" if i % 2 == 0 else "Sitapur"
        
        c.execute("""
        INSERT INTO users (unique_id, name, role, phone, village)
        VALUES (?, ?, 'Mother', ?, ?)
        """, (unique_id, name, '9' + str(random.randint(100000000, 999999999)), village))
        
    conn.commit()
    conn.close()
    print(f"Successfully generated 130 mothers with IDs 001-130.")

if __name__ == "__main__":
    populate_mothers()
