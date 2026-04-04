import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BOT_TOKEN: str = os.getenv("token")
    GROUP_ID: str = os.getenv("id")
    # ADMIN_ID: int = int(os.getenv("ADMIN_ID", 0))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

settings = Settings()
