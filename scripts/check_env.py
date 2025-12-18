import os
from dotenv import load_dotenv

load_dotenv()

def check_env():
    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")
    
    print(f"CLIENT_ID: {'Set' if client_id else 'Missing'}")
    print(f"CLIENT_SECRET: {'Set' if client_secret else 'Missing'}")

if __name__ == "__main__":
    check_env()
