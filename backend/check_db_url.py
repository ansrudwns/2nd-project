from app.core.config import settings

url = settings.DATABASE_URL
# Mask password
if "@" in url:
    prefix, suffix = url.split("@", 1)
    # Mask password part in prefix
    if ":" in prefix:
        proto_user, password = prefix.split(":", 1)
        # Handle protocol part
        if "//" in proto_user:
            proto, user = proto_user.split("//", 1)
            print(f"DB URL: {proto}//{user}:****@{suffix}")
        else:
             print(f"DB URL: {settings.DATABASE_URL} (parse failed)")
    else:
        print(f"DB URL: {settings.DATABASE_URL}")
else:
    print(f"DB URL: {settings.DATABASE_URL}")
