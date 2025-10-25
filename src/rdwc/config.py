from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    env: str = os.getenv("ENV", "dev")
    i2c_bus: int = int(os.getenv("I2C_BUS", "1"))
    ph_addr: int = int(os.getenv("PH_ADDR", "0x63"), 16)
    ec_addr: int = int(os.getenv("EC_ADDR", "0x64"), 16)
    rtd_addr: int = int(os.getenv("RTD_ADDR", "0x66"), 16)

    ph_setpoint: float = float(os.getenv("PH_SETPOINT", "5.9"))
    ph_deadband: float = float(os.getenv("PH_DEADBAND", "0.1"))

    ph_up_max_sec: int = int(os.getenv("PH_UP_MAX_SEC", "2"))
    ph_up_cooldown_sec: int = int(os.getenv("PH_UP_COOLDOWN_SEC", "90"))

    relay: dict = {
        "ph_up": int(os.getenv("RELAY_PH_UP", "5")),
        "grow": int(os.getenv("RELAY_GROW", "6")),
        "micro": int(os.getenv("RELAY_MICRO", "13")),
        "bloom": int(os.getenv("RELAY_BLOOM", "19")),
        "main_pump": int(os.getenv("RELAY_MAIN_PUMP", "26")),
        "chiller_pump": int(os.getenv("RELAY_CHILLER_PUMP", "16")),
        "chiller": int(os.getenv("RELAY_CHILLER", "20")),
        "lights": int(os.getenv("RELAY_LIGHTS", "21")),
    }

    main_pump_on: bool = os.getenv("MAIN_PUMP_ON", "1") == "1"
    chiller_pump_on: bool = os.getenv("CHILLER_PUMP_ON", "1") == "1"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))

settings = Settings()