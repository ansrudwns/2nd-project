from passlib.context import CryptContext

print("Testing pbkdf2_sha256...")
try:
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    hash = pwd_context.hash("demo1234")
    print(f"Success! Hash: {hash}")
except Exception as e:
    print(f"Error: {e}")
