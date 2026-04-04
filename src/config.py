import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BOT_TOKEN: str = os.getenv("8655674139:AAHbp_iUcI80_6twOiIZH1dNANXjG4YYBM4")
    GROUP_ID: str = os.getenv("-1003313006208")
    # ADMIN_ID: int = int(os.getenv("ADMIN_ID", 0))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

settings = Settings()
