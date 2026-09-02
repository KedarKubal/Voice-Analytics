"""
seed_users.py  —  Heya AI Voice Analytics
Create test users for the platform.

Run once (from backend/ with heya_pipeline env active):
    python seed_users.py

Creates three users:
    admin@heya.au          heya_admin_2026   → Heya AI God View (all clients)
    admin@artel.com        artel_2026        → Artel Apartments client view
    admin@mvaallegal.com   mvaa_2026         → MVAA Legal client view
"""

from dotenv import load_dotenv
load_dotenv()

import bcrypt as _bcrypt
from database import create_tables, get_db, User

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

USERS = [
    {
        "id":        "user_heya_admin",
        "email":     "admin@heya.au",
        "password":  "heya_admin_2026",
        "role":      "heya_admin",
        "client_id": None,              # admins have no client restriction
    },
    {
        "id":        "user_artel_001",
        "email":     "admin@artel.com",
        "password":  "artel_2026",
        "role":      "client",
        "client_id": "client_heya_001",  # Artel Apartments
    },
    {
        "id":        "user_mvaa_001",
        "email":     "admin@mvaallegal.com",
        "password":  "mvaa_2026",
        "role":      "client",
        "client_id": "client_heya_002",  # MVAA Legal
    },
]

if __name__ == "__main__":
    create_tables()
    print("\nSeeding users...\n")

    with get_db() as db:
        for u in USERS:
            existing = db.query(User).filter(User.id == u["id"]).first()
            if existing:
                print(f"  ⏭  Already exists: {u['email']}")
                continue
            db.add(User(
                id              = u["id"],
                email           = u["email"],
                hashed_password = hash_password(u["password"]),
                role            = u["role"],
                client_id       = u["client_id"],
            ))
            print(f"  ✅ Created: {u['email']}  ({u['role']})")

    print("\n── Login credentials ─────────────────────────────")
    print(f"  {'Email':<30} {'Password':<20} {'Role'}")
    print(f"  {'-'*30} {'-'*20} {'-'*12}")
    for u in USERS:
        print(f"  {u['email']:<30} {u['password']:<20} {u['role']}")
    print()
