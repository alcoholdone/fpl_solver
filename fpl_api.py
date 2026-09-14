import math
import requests
import urllib3
from config import BASE_URL, HEADERS, POSITION_MAP, HORIZON_WEEKS

# ซ่อนคำเตือน SSL InsecureRequestWarning กรณี fallback บนเครื่องที่ไม่มี Root CA
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# กฎการคิดคะแนนตามตำแหน่งของ Official FPL
GOAL_POINTS = {1: 6, 2: 6, 3: 5, 4: 4}
CS_POINTS = {1: 4, 2: 4, 3: 1, 4: 0}


# ==========================================
# 1. TEAM STRENGTH & MATCH FACTORS ENGINE (Zero-Division Safe)
# ==========================================
def calculate_match_factors(
    player_team_id: int,
    opp_team_id: int,
    is_home: bool,
    teams_data: dict,
    fdr_fallback: int = 3,
) -> tuple[float, float, float]:
    """คำนวณตัวคูณเกมรุกและโอกาสคลีนชีต พร้อมระบบป้องกัน Division by Zero และปรับสเกลสะท้อนความต่างของโปรแกรมจริง"""
    p_team = teams_data.get(player_team_id)
    opp_team = teams_data.get(opp_team_id)

    if not p_team or not opp_team:
        base_mult = {1: 1.35, 2: 1.18, 3: 1.00, 4: 0.82, 5: 0.65}.get(
            fdr_fallback, 1.0
        )
        return base_mult, 0.28, 1.35

    if is_home:
        my_att = float(p_team.get("att_home") or 1100)
        my_def = float(p_team.get("def_home") or 1100)
        opp_att = float(opp_team.get("att_away") or 1100)
        opp_def = float(opp_team.get("def_away") or 1100)
        home_boost = 1.10
    else:
        my_att = float(p_team.get("att_away") or 1100)
        my_def = float(p_team.get("def_away") or 1100)
        opp_att = float(opp_team.get("att_home") or 1100)
        opp_def = float(opp_team.get("def_home") or 1100)
        home_boost = 0.90

    # 1. คำนวณความได้เปรียบเกมรุก (ปรับ Power 1.6 ขยายสเกลระหว่างทีมลุ้นแชมป์กับทีมหนีตกชั้น)
    raw_att_ratio = (my_att / max(100.0, opp_def)) * home_boost
    scaled_att = raw_att_ratio ** 1.6
    # รักษาระดับ Floor ขั้นต่ำ 0.68 เพื่อให้ตัวรุกตัวแบกจากทีมเล็ก-กลางยังมีโอกาสทำแต้มจากจุดโทษ/ลูกนิ่งเมื่อเจอทีมใหญ่
    attack_mult = round(max(0.68, min(1.70, scaled_att)), 2)

    # 2. คำนวณความได้เปรียบเกมรับ (ล็อกตัวหาร opp_att ขั้นต่ำ 100.0)
    def_ratio = (my_def / max(100.0, opp_att)) * (1.15 if is_home else 0.85)
    base_cs = 0.28 * (def_ratio ** 1.4)
    cs_prob = round(max(0.05, min(0.68, base_cs)), 2)

    # 3. คำนวณประตูคาดว่าจะเสีย (ล็อกตัวหาร def_ratio ขั้นต่ำ 0.2 ป้องกัน division by zero)
    safe_def_ratio = max(0.20, def_ratio)
    expected_gc = round(max(0.40, min(3.20, 1.35 / safe_def_ratio)), 2)

    return attack_mult, cs_prob, expected_gc


def sanitize_stat_per_90(
    raw_val: any, minutes: int, default_cap: float = 1.85
) -> float:
    """แปลงสถิติต่อ 90 นาที พร้อม Bayesian Shrinkage ลด Noise"""
    try:
        val = float(raw_val or 0.0)
    except (ValueError, TypeError):
        return 0.0

    if minutes < 270:
        confidence = minutes / 270.0
        val = (val * confidence) + (0.05 * (1.0 - confidence))

    return min(val, default_cap)


def calculate_player_custom_xp(
    el: dict,
    xmins: float,
    attack_mult: float,
    cs_prob: float,
    expected_gc: float,
    xg_weight: float = 1.0,
    cs_weight: float = 1.0,
) -> float:
    """คำนวณแต้มคาดหวัง (xP) พร้อม Elite Finisher Boost, Recent Form และ High-Ceiling BPS"""
    if xmins <= 0.0:
        return 0.0

    pos_id = el["element_type"]
    total_minutes = el.get("minutes", 0)
    mins_ratio = xmins / 90.0

    # Appearance Points (คิดโอกาสลงเล่นจริง ไม่แจก 1 แต้มฟรีให้ตัวสำรองที่แทบไม่ได้ลง)
    p_appear = min(1.0, max(0.0, xmins / 25.0))
    p_play_60 = 1.0 / (1.0 + math.exp(-0.2 * (xmins - 55.0)))
    appearance_xp = p_appear * ((p_play_60 * 2.0) + ((1.0 - p_play_60) * 1.0))

    # ปลดเพดานสถิติ Underlying Stats
    xg90 = sanitize_stat_per_90(
        el.get("expected_goals_per_90"), total_minutes, default_cap=1.85
    )
    xa90 = sanitize_stat_per_90(
        el.get("expected_assists_per_90"), total_minutes, default_cap=0.90
    )

    # Elite Finisher Boost สำหรับดาวยิงตัวเป้า
    finisher_boost = 1.0
    if xg90 >= 0.45:
        finisher_boost += min(0.25, (xg90 - 0.45) * 0.40)
        if pos_id == 4:
            finisher_boost += 0.10

    # Recent Form Weighting Factor (สะท้อนผลงานล่าสุด 30 วัน ผสานกับค่าเฉลี่ยทั้งฤดูกาล)
    try:
        form_val = float(el.get("form") or 0.0)
        ppg_val = float(el.get("points_per_game") or 0.0)
    except (ValueError, TypeError):
        form_val, ppg_val = 0.0, 0.0

    form_multiplier = 1.0
    if total_minutes >= 180:
        form_diff = form_val - ppg_val
        form_multiplier = 1.0 + max(-0.18, min(0.22, form_diff * 0.05))

    # มือสังหารจุดโทษและลูกตั้งเตะ (Penalty & Set-Piece Boost)
    pen_order = el.get("penalties_order")
    pen_xg_boost = 0.10 if pen_order == 1 else (0.04 if pen_order == 2 else 0.0)

    fk_order = el.get("direct_freekicks_order")
    fk_xg_boost = 0.04 if fk_order == 1 else 0.0

    corner_order = el.get("corners_and_indirect_freekicks_order")
    corner_xa_boost = 0.07 if corner_order == 1 else 0.0

    total_xg90 = xg90 + pen_xg_boost + fk_xg_boost
    total_xa90 = xa90 + corner_xa_boost

    match_xg = total_xg90 * mins_ratio * attack_mult * xg_weight * finisher_boost * form_multiplier
    match_xa = total_xa90 * mins_ratio * attack_mult * xg_weight * form_multiplier
    attacking_xp = (match_xg * GOAL_POINTS[pos_id]) + (match_xa * 3.0)

    # Clean Sheet Points
    match_cs_prob = min(0.95, cs_prob * p_play_60 * cs_weight)
    clean_sheet_xp = match_cs_prob * CS_POINTS[pos_id]

    goals_conceded_penalty = 0.0
    if pos_id in [1, 2]:
        match_gc = expected_gc * mins_ratio
        goals_conceded_penalty = (match_gc / 2.0) * -1.0

    # Saves Points (GKP)
    save_xp = 0.0
    if pos_id == 1:
        saves90 = sanitize_stat_per_90(
            el.get("saves_per_90"), total_minutes, default_cap=6.0
        )
        save_xp = (saves90 * mins_ratio) * 0.33

    # High-Ceiling BPS สำหรับตัวรุกและกัปตันทีม
    bps_goal_mult = 1.15 if pos_id == 4 else 0.85
    bonus_xp = (
        (match_xg * bps_goal_mult)
        + (match_xa * 0.40)
        + (match_cs_prob * 0.30)
    )
    if match_xg >= 0.55:
        bonus_xp += 0.60
    if match_xg >= 0.85:
        bonus_xp += 0.75

    cards_deduction = -0.12 * mins_ratio

    total_xp = (
        appearance_xp
        + attacking_xp
        + clean_sheet_xp
        + goals_conceded_penalty
        + save_xp
        + bonus_xp
        + cards_deduction
    )

    return round(max(0.0, total_xp), 2)


def calculate_xmins(
    el: dict,
    team_played: int,
    gw_offset: int = 0,
) -> tuple[float, str]:
    """
    ประเมินนาทีลงเล่นคาดหวัง (xMins) โดยวิเคราะห์บทบาทจริง (Role),
    สถานะตัวจริงเมื่อฟิต (Baseline) และการฟื้นตัวของธงสถานะตามสัปดาห์ (Multi-GW Flag Recovery)
    """
    pos_id = el.get("element_type", 3)
    status = el.get("status", "a")
    chance = el.get("chance_of_playing_next_round")
    now_cost = el.get("now_cost", 50)
    minutes = el.get("minutes", 0)
    starts = el.get("starts", 0)
    news = (el.get("news") or "").lower()

    # 1. คำนวณความพร้อม (Availability Factor) ตาม Gameweek Offset
    if status == "u":
        avail_factor = 0.0
    elif status == "s":
        # โทษแบน: ถ้าติดแบน 3 นัด หรือข่าวระบุมากกว่า 1 นัด
        is_multi_match_ban = "3 matches" in news or "2 matches" in news
        if gw_offset == 0:
            avail_factor = 0.0
        elif gw_offset == 1:
            avail_factor = 0.0 if is_multi_match_ban else 1.0
        else:
            avail_factor = 1.0
    elif status == "i":
        # อาการบาดเจ็บ
        if chance is None or chance == 0:
            # เจ็บยาว หรือไม่มีกำหนดกลับ
            avail_factor = 0.0
        else:
            base_chance = chance / 100.0
            # สัปดาห์ถัดๆ ไป อาการเจ็บเบามักจะฟื้นตัวดีขึ้น
            if gw_offset == 0:
                avail_factor = base_chance
            elif gw_offset == 1:
                avail_factor = min(1.0, base_chance + 0.30)
            else:
                avail_factor = min(1.0, base_chance + 0.50)
    elif status == "d":
        # เช็กฟิต (Doubtful)
        base_chance = (chance / 100.0) if chance is not None else 0.75
        if gw_offset == 0:
            avail_factor = base_chance
        elif gw_offset == 1:
            avail_factor = min(1.0, base_chance + 0.25)
        else:
            avail_factor = 1.0
    else:
        # สถานะปกติ ('a')
        if chance is not None:
            base_chance = chance / 100.0
            if gw_offset == 0:
                avail_factor = base_chance
            elif gw_offset == 1:
                avail_factor = min(1.0, base_chance + 0.25)
            else:
                avail_factor = 1.0
        else:
            avail_factor = 1.0

    if avail_factor <= 0.0:
        return 0.0, "🔴 OUT (เจ็บ/แบน)"

    # 2. คำนวณนาทีพื้นฐานเมื่อฟิตสมบูรณ์ (Baseline Minutes)
    safe_played = max(1, team_played)
    mins_per_start = (minutes / max(1, starts)) if starts > 0 else 0.0
    start_rate = starts / safe_played

    if pos_id == 1:
        # ผู้รักษาประตู: ไม่มีการเปลี่ยนตัวระหว่างเกม เล่น 90 หรือ 0 นาที
        if starts >= 2 or (safe_played <= 3 and now_cost >= 45) or start_rate >= 0.40:
            baseline_mins = 90.0
        elif starts == 1 and safe_played <= 2:
            baseline_mins = 90.0
        else:
            baseline_mins = 0.0
    else:
        # นักเตะเอาต์ฟิลด์ (DEF, MID, FWD)
        is_premium = (now_cost >= 80 and pos_id in [3, 4]) or (now_cost >= 60 and pos_id == 2)
        try:
            form_val = float(el.get("form") or 0.0)
        except (ValueError, TypeError):
            form_val = 0.0

        if is_premium:
            # ผู้เล่นตัวท็อป แม้เจ็บไปนาน เมื่อฟิตจะการันตีตัวจริง 80-90 นาที
            baseline_mins = 85.0
        elif form_val >= 4.0 and starts >= 2:
            # ฟอร์มกำลังร้อนแรง และสตาร์ตตัวจริงช่วงหลัง
            baseline_mins = min(90.0, max(75.0, mins_per_start))
        elif start_rate >= 0.65:
            # ตัวจริงสม่ำเสมอ
            baseline_mins = min(90.0, max(75.0, mins_per_start))
        elif start_rate >= 0.35:
            # กึ่งตัวจริง กึ่งโรเตชัน
            baseline_mins = min(80.0, max(50.0, (minutes / safe_played) * 1.15))
        elif starts >= 1 or minutes >= 180:
            # ตัวสำรองที่มักได้ลงเล่น
            baseline_mins = max(15.0, min(40.0, minutes / safe_played))
        elif now_cost <= 45 and safe_played >= 5:
            # ตัวสำรองราคาถูกแทบไม่ได้ลง
            baseline_mins = 0.0
        else:
            # ช่วงต้นฤดูกาล
            baseline_mins = 65.0 if now_cost >= 60 else 30.0

    raw_xmins = baseline_mins * avail_factor
    xmins = round(min(90.0, max(0.0, raw_xmins)), 1)

    # 3. กำหนดป้ายความเสี่ยง (Risk Label)
    if avail_factor <= 0.5:
        risk = "🔴 HIGH (เช็กฟิต 50%)"
    elif avail_factor <= 0.75:
        risk = "🟡 MED (เช็กฟิต 75%)"
    elif baseline_mins < 45.0:
        risk = "🟠 HIGH (สำรองบ่อย)"
    elif baseline_mins < 70.0:
        risk = "🟡 MED (เสี่ยงโรเตชัน)"
    else:
        risk = "🟢 LOW (ตัวจริง)"

    return xmins, risk


# ==========================================
# 2. MARKET PRICE PREDICTOR ENGINE
# ==========================================
def calculate_price_trend(el: dict, total_managers: int) -> dict:
    """คำนวณ Net Transfers พร้อมป้องกันตัวหารเป็น 0"""
    tin = el.get("transfers_in_event", 0)
    tout = el.get("transfers_out_event", 0)
    net_transfers = tin - tout
    ownership_pct = float(el.get("selected_by_percent") or 0.0)
    ownership_count = max(2000, int(total_managers * (ownership_pct / 100.0)))

    rise_threshold = max(35000, int(ownership_count * 0.065))
    fall_threshold = max(25000, int(ownership_count * 0.055))

    if net_transfers > 0:
        progress = round((net_transfers / max(1, rise_threshold)) * 100.0, 1)
    else:
        progress = round((net_transfers / max(1, fall_threshold)) * 100.0, 1)

    if progress >= 95.0:
        status = "🚀 เสี่ยงขึ้นคืนนี้"
    elif progress >= 55.0:
        status = "📈 ขาขึ้นแรง"
    elif progress <= -95.0:
        status = "🔻 เสี่ยงตกคืนนี้"
    elif progress <= -55.0:
        status = "📉 ขาลงแรง"
    else:
        status = "➖ คงที่"

    return {
        "net_transfers": net_transfers,
        "transfers_in": tin,
        "transfers_out": tout,
        "ownership_pct": ownership_pct,
        "progress_pct": progress,
        "status": status,
    }


class FPLGameUpdatingError(Exception):
    """Exception เมื่อเซิร์ฟเวอร์ FPL ปิดปรับปรุงระหว่างการแข่งขันจริง (The game is being updated)"""
    pass


# ==========================================
# 3. DATA PIPELINE & API CALLS
# ==========================================
def fpl_get(url: str, params: dict = None, timeout: int = 10):
    """
    ส่ง HTTP GET ไปยัง FPL API พร้อมระบบ Auto-Fallback SSL และตรวจสอบสถานะ Game Updating
    แก้ปัญหา SSL CERTIFICATE_VERIFY_FAILED บน macOS หรือหลัง Corporate Proxy
    """
    try:
        res = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
    except requests.exceptions.SSLError:
        res = requests.get(url, headers=HEADERS, params=params, timeout=timeout, verify=False)

    if res.status_code in (502, 503):
        raise FPLGameUpdatingError("ระบบ FPL กำลังปิดปรับปรุงระหว่างแข่งขันจริง (The game is being updated)")

    content_type = res.headers.get("Content-Type", "").lower()
    if "application/json" not in content_type and "game is being updated" in res.text.lower():
        raise FPLGameUpdatingError("ระบบ FPL กำลังปิดปรับปรุงระหว่างแข่งขันจริง (The game is being updated)")

    return res


def get_fixture_details(target_gws: list, teams_dict: dict) -> dict:
    fixtures_res = fpl_get(f"{BASE_URL}/fixtures/").json()
    fixture_details = {tid: {gw: [] for gw in target_gws} for tid in teams_dict}

    for fix in fixtures_res:
        gw = fix.get("event")
        if gw in target_gws:
            h_team, a_team = fix["team_h"], fix["team_a"]
            h_diff, a_diff = fix["team_h_difficulty"], fix["team_a_difficulty"]

            fixture_details[h_team][gw].append({
                "opp": teams_dict[a_team],
                "opp_id": a_team,
                "fdr": h_diff,
                "is_home": True,
                "label": f"vs {teams_dict[a_team]} (H) [FDR {h_diff}]",
            })
            fixture_details[a_team][gw].append({
                "opp": teams_dict[h_team],
                "opp_id": h_team,
                "fdr": a_diff,
                "is_home": False,
                "label": f"vs {teams_dict[h_team]} (A) [FDR {a_diff}]",
            })

    return fixture_details


def calculate_accumulated_ft(history_res: dict) -> int:
    """
    คำนวณ Free Transfers สะสมตามกติกา FPL ฤดูกาล 2024/2025 (สะสมได้สูงสุด 5 ใบ)
    โดยแกะรอยจากประวัติการย้ายตัวจริงตลอดทุก Gameweek ในฤดูกาล
    - ทุกทีมเริ่มต้นเข้าสู่ GW2 ด้วย 1 Free Transfer เสมอ (ไม่มีการสะสมจากพรีซีซัน)
    - Free Hit รีเซ็ต FT สัปดาห์ถัดไปเป็น 1 ใบ
    """
    try:
        current_history = history_res.get("current", [])
        if not current_history or len(current_history) <= 1:
            return 1

        played_chips = {c.get("event"): c.get("name") for c in history_res.get("chips", [])}

        ft = 1
        # เริ่มนับตั้งแต่ GW2 เป็นต้นไป (current_history[1:])
        for event in current_history[1:]:
            event_gw = event.get("event")
            chip_used = played_chips.get(event_gw)

            if chip_used == "freehit":
                # หลัง Free Hit สัปดาห์ถัดไปจะได้รับ 1 FT
                ft = 1
                continue

            transfers = event.get("event_transfers", 0)
            cost = event.get("event_transfers_cost", 0)

            if chip_used == "wildcard":
                # Wildcard: การย้ายตัวไม่เสียแต้มและเก็บ FT สะสมไว้
                ft = min(5, ft + 1)
                continue

            hits = cost // 4
            used_ft = max(0, transfers - hits)
            rem_ft = max(0, ft - used_ft)
            ft = min(5, rem_ft + 1)

        return max(1, min(5, ft))
    except Exception:
        return 1


def fetch_user_chips_status(team_id: int, target_gw: int, history_res: dict = None) -> dict:
    try:
        if history_res is None or not history_res:
            history_res = fpl_get(
                f"{BASE_URL}/entry/{team_id}/history/"
            ).json()
        used_chips = [c["name"] for c in history_res.get("chips", [])]
        wc_count = used_chips.count("wildcard")
        wc_avail = (target_gw <= 19 and wc_count == 0) or (
            target_gw > 19 and wc_count < 2
        )

        return {
            "TC": "3xc" not in used_chips,
            "BB": "bboost" not in used_chips,
            "WC": wc_avail,
            "FH": "freehit" not in used_chips,
        }
    except Exception:
        return {"TC": True, "BB": True, "WC": True, "FH": False}


def fetch_fpl_global_market(
    xg_weight: float = 1.0, cs_weight: float = 1.0, horizon_weeks: int = HORIZON_WEEKS
) -> dict:
    """
    ดึงข้อมูลกลางของทั้งลีก (Market Data) ได้แก่ Bootstrap, Fixtures, ค่าพลังทีม และคำนวณ Custom xP ทุกตัว
    แคชร่วมกันระดับ Global เพื่อป้องกัน FPL API Rate Limit (429) เมื่อมีผู้ใช้หลายคน
    """
    print("[1/2] กำลังดึงข้อมูลกลางตลาดนักเตะและโปรแกรมแข่งขันจาก FPL API...")
    bootstrap = fpl_get(f"{BASE_URL}/bootstrap-static/").json()
    total_managers = bootstrap.get("total_players", 10_500_000)

    next_event = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    if next_event:
        next_gw = next_event["id"]
        deadline_raw = next_event["deadline_time"]
        gw_name = next_event["name"]
    else:
        current_event = next(
            (e for e in bootstrap["events"] if e.get("is_current")), None
        )
        next_gw = (current_event["id"] + 1) if current_event else 1
        deadline_raw = None
        gw_name = f"Gameweek {next_gw}"

    deadline_info = {
        "gw": next_gw,
        "name": gw_name,
        "deadline_utc": deadline_raw,
    }

    target_gws = [min(38, next_gw + w) for w in range(horizon_weeks)]
    target_gws = sorted(list(set(target_gws)))
    pick_gw = max(1, next_gw - 1)

    teams_dict = {t["id"]: t["short_name"] for t in bootstrap["teams"]}

    teams_strength = {}
    for t in bootstrap["teams"]:
        teams_strength[t["id"]] = {
            "att_home": max(500, int(t.get("strength_attack_home") or 1100)),
            "att_away": max(500, int(t.get("strength_attack_away") or 1100)),
            "def_home": max(500, int(t.get("strength_defence_home") or 1100)),
            "def_away": max(500, int(t.get("strength_defence_away") or 1100)),
        }

    teams_played = {
        t["id"]: max(0, int(t.get("played") or pick_gw)) for t in bootstrap["teams"]
    }
    element_costs = {
        el["id"]: el["now_cost"] / 10.0 for el in bootstrap["elements"]
    }

    fixture_details = get_fixture_details(target_gws, teams_dict)

    dgw_bgw_info = {}
    for gw in target_gws:
        dgw_teams = [
            teams_dict[tid]
            for tid in teams_dict
            if len(fixture_details[tid].get(gw, [])) >= 2
        ]
        bgw_teams = [
            teams_dict[tid]
            for tid in teams_dict
            if len(fixture_details[tid].get(gw, [])) == 0
        ]
        dgw_bgw_info[gw] = {"dgw": dgw_teams, "bgw": bgw_teams}

    # ประมวลผล Custom xP นักเตะทุกคนในลีก
    market_players = []
    for el in bootstrap["elements"]:
        pid = el["id"]
        if el["status"] == "u":
            continue

        buy_price = el["now_cost"] / 10.0
        t_played = teams_played.get(el["team"], pick_gw)
        price_trend = calculate_price_trend(el, total_managers)

        xmins_by_gw = {}
        risk_by_gw = {}
        xp_by_gw = {}
        next_fixtures = {}
        is_dgw_by_gw = {}
        is_bgw_by_gw = {}

        for idx, gw in enumerate(target_gws):
            gw_xmins, gw_risk = calculate_xmins(el, t_played, gw_offset=idx)
            xmins_by_gw[gw] = gw_xmins
            risk_by_gw[gw] = gw_risk

            matches = fixture_details.get(el["team"], {}).get(gw, [])
            match_count = len(matches)
            is_dgw_by_gw[gw] = match_count >= 2
            is_bgw_by_gw[gw] = match_count == 0

            if match_count == 0:
                xp_by_gw[gw] = 0.0
                next_fixtures[gw] = "Blank"
            else:
                total_gw_xp = 0.0
                labels = []
                for m in matches:
                    att_mult, cs_p, exp_gc = calculate_match_factors(
                        player_team_id=el["team"],
                        opp_team_id=m["opp_id"],
                        is_home=m["is_home"],
                        teams_data=teams_strength,
                        fdr_fallback=m["fdr"],
                    )

                    total_gw_xp += calculate_player_custom_xp(
                        el=el,
                        xmins=gw_xmins,
                        attack_mult=att_mult,
                        cs_prob=cs_p,
                        expected_gc=exp_gc,
                        xg_weight=xg_weight,
                        cs_weight=cs_weight,
                    )
                    labels.append(m["label"])

                xp_by_gw[gw] = round(total_gw_xp, 2)
                next_fixtures[gw] = " / ".join(labels)

        first_gw = target_gws[0] if target_gws else 1
        curr_xmins = xmins_by_gw.get(first_gw, 0.0)
        curr_risk = risk_by_gw.get(first_gw, "🟢 LOW (ตัวจริง)")

        market_players.append({
            "id": pid,
            "web_name": el["web_name"],
            "full_name": f"{el['first_name']} {el['second_name']}",
            "team": teams_dict[el["team"]],
            "team_id": el["team"],
            "position": POSITION_MAP[el["element_type"]],
            "pos_id": el["element_type"],
            "buy_price": buy_price,
            "sell_price": buy_price,
            "form": float(el.get("form") or 0.0),
            "xmins": curr_xmins,
            "risk": curr_risk,
            "xmins_by_gw": xmins_by_gw,
            "risk_by_gw": risk_by_gw,
            "xp_by_gw": xp_by_gw,
            "fixtures": next_fixtures,
            "is_dgw": is_dgw_by_gw,
            "is_bgw": is_bgw_by_gw,
            "price_trend": price_trend,
            "in_initial_team": 0,
        })

    return {
        "players": market_players,
        "element_costs": element_costs,
        "target_gws": target_gws,
        "deadline_info": deadline_info,
        "dgw_bgw_info": dgw_bgw_info,
        "pick_gw": pick_gw,
        "next_gw": next_gw,
    }


def fetch_fpl_user_squad(team_id: int, global_market: dict) -> tuple:
    """
    ดึงเฉพาะข้อมูลส่วนตัวของผู้ใช้ (Picks, Bank, History, ชิป) แล้วประกบกับ Global Market Data
    ทำงานได้เร็วมาก (<0.3 วินาที) และยิง FPL API เพียง 2 endpoints สั้นๆ
    """
    pick_gw = global_market["pick_gw"]
    next_gw = global_market["next_gw"]
    element_costs = global_market["element_costs"]

    print(f"[2/2] ดึงข้อมูลทีมส่วนบุคคล (Team ID: {team_id})...")
    picks_res = fpl_get(f"{BASE_URL}/entry/{team_id}/event/{pick_gw}/picks/").json()
    if "picks" not in picks_res:
        raise ValueError(
            f"ไม่พบข้อมูล Picks สำหรับ Team ID {team_id} ใน Gameweek {pick_gw} (กรุณาตรวจสอบว่ากรอก Team ID ถูกต้อง)"
        )

    bank = picks_res["entry_history"]["bank"] / 10.0
    current_picks = picks_res["picks"]
    my_player_ids = [p["element"] for p in current_picks]

    selling_prices = {
        p["element"]: (
            (p.get("selling_price") / 10.0)
            if p.get("selling_price") is not None
            else element_costs.get(p["element"], 0.0)
        )
        for p in current_picks
    }

    history_res = {}
    try:
        history_res = fpl_get(f"{BASE_URL}/entry/{team_id}/history/").json()
    except Exception:
        pass

    chips_available = fetch_user_chips_status(team_id, next_gw, history_res=history_res)
    initial_ft = calculate_accumulated_ft(history_res)

    # ปรับ selling_price และ in_initial_team ให้เฉพาะผู้เล่น 15 คนในทีมของผู้ใช้
    my_ids_set = set(my_player_ids)
    user_players = []
    for p in global_market["players"]:
        pid = p["id"]
        if pid in my_ids_set:
            p_copy = p.copy()
            p_copy["in_initial_team"] = 1
            p_copy["sell_price"] = selling_prices.get(pid, p["buy_price"])
            user_players.append(p_copy)
        else:
            user_players.append(p)

    return (
        user_players,
        my_player_ids,
        bank,
        initial_ft,
        global_market["target_gws"],
        chips_available,
        global_market["deadline_info"],
        global_market["dgw_bgw_info"],
    )


def fetch_fpl_data_multi(
    team_id: int, xg_weight: float = 1.0, cs_weight: float = 1.0, horizon_weeks: int = HORIZON_WEEKS
):
    """ฟังก์ชันรวมสำหรับ backward-compatibility"""
    market = fetch_fpl_global_market(xg_weight, cs_weight, horizon_weeks)
    return fetch_fpl_user_squad(team_id, market)


# ==========================================
# 4. MINI-LEAGUE & EO ANALYSIS ENGINE
# ==========================================
def fetch_minileague_eo(league_id: int, pick_gw: int, max_managers: int = 25):
    """วิเคราะห์ไลน์อัปคู่แข่งและคำนวณ EO จริง"""
    if not league_id or league_id <= 0:
        return None

    try:
        league_res = fpl_get(
            f"{BASE_URL}/leagues-classic/{league_id}/standings/",
            timeout=8,
        ).json()

        if "standings" not in league_res:
            return None

        league_name = league_res.get("league", {}).get("name", "Mini-League")
        managers = league_res["standings"].get("results", [])[:max_managers]

        if not managers:
            return None

        total_mgrs = max(1, len(managers))
        eo_counts = {}
        own_counts = {}
        cap_counts = {}

        for mgr in managers:
            entry_id = mgr["entry"]
            picks_url = f"{BASE_URL}/entry/{entry_id}/event/{pick_gw}/picks/"
            p_res = fpl_get(picks_url, timeout=5).json()

            if "picks" not in p_res:
                continue

            for pick in p_res["picks"]:
                pid = pick["element"]
                multiplier = pick.get("multiplier", 1)
                is_cap = pick.get("is_captain", False)

                eo_counts[pid] = eo_counts.get(pid, 0) + multiplier
                own_counts[pid] = own_counts.get(pid, 0) + (
                    1 if multiplier >= 0 else 0
                )
                if is_cap:
                    cap_counts[pid] = cap_counts.get(pid, 0) + 1

        league_eo_data = {}
        for pid, total_mult in eo_counts.items():
            league_eo_data[pid] = {
                "eo_pct": round((total_mult / total_mgrs) * 100.0, 1),
                "ownership_pct": round(
                    (own_counts.get(pid, 0) / total_mgrs) * 100.0, 1
                ),
                "captain_pct": round(
                    (cap_counts.get(pid, 0) / total_mgrs) * 100.0, 1
                ),
            }

        return {
            "league_name": league_name,
            "total_analyzed": len(managers),
            "standings": managers,
            "eo_dict": league_eo_data,
        }

    except Exception as e:
        print(f"[Mini-League Error] ไม่สามารถดึงข้อมูลลีก {league_id} ได้: {e}")
        return None