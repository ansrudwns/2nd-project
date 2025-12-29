from fastapi.staticfiles import StaticFiles
import os

# ... (existing imports)

# Create static dir if not exists
os.makedirs("uploads", exist_ok=True)

# ... (after app init)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
