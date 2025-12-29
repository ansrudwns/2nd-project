from app.db.session import SessionLocal
from app.models.tables import User

db = SessionLocal()
users = db.query(User).all()

print(f"Total Users: {len(users)}")
for user in users:
    print(f"ID: {user.id}, Email: {user.email}, Name: {user.full_name}, Active: {user.is_active}")

db.close()
