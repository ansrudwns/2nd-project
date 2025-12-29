from passlib.context import CryptContext
import sys

print("Testing passlib...")
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hash = pwd_context.hash("demo1234")
    print(f"Success! Hash: {hash}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting long password...")
try:
    long_pw = "a" * 80
    hash = pwd_context.hash(long_pw)
    print(f"Long Hash: {hash}")
except Exception as e:
    print(f"Long PW Error: {e}")
