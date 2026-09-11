import os
import streamlit as st


def get_config_val(key, default):
    # ดักจับกรณีที่ไม่มีไฟล์ secrets.toml ในเครื่อง Local
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return os.getenv(key, default)



# ค่า Configuration หลักของระบบ
# MY_TEAM_ID = 6539550  # <-- เปลี่ยนเป็น FPL Team ID ของคุณ
BASE_URL = "https://fantasy.premierleague.com/api"
# HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

HEADERS = {
    "User-Agent": get_config_val("FPL_USER_AGENT", "FPL-Optimizer-Public/1.0")
}
MY_TEAM_ID = int(get_config_val("DEFAULT_TEAM_ID", 0))

# การวางแผนระยะยาว (Multi-Gameweek)
HORIZON_WEEKS = 2          # วางแผนล่วงหน้า 3 สัปดาห์
DISCOUNT_FACTOR = 0.90     # อัตราลดทอนความไม่แน่นอนสัปดาห์ถัดๆ ไป (10%)

# กติกา FPL มาตรฐาน
MAX_FREE_TRANSFERS = 5
HIT_PENALTY_COST = 4.0
MAX_PLAYERS_PER_TEAM = 3
TOTAL_SQUAD_SIZE = 15
STARTING_XI_SIZE = 11

POSITION_MAP = {
    1: "GKP",
    2: "DEF",
    3: "MID",
    4: "FWD"
}
# รายชื่อ Mini-League เริ่มต้น (สามารถเปลี่ยนชื่อป้ายกำกับตามชื่อลีกจริงของคุณได้)
DEFAULT_LEAGUES = {
    # "🏆 Mini-League 1 (ID: 1089641)": 1089641,
    # "🥈 Mini-League 2 (ID: 1433756)": 1433756,
    "✏️ กรอก League ID อื่นๆ เอง": 0
}