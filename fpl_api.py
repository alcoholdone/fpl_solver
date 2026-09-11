import math
import requests
from config import BASE_URL, HEADERS, POSITION_MAP, HORIZON_WEEKS

# กฎการคิดคะแนนทางการของ FPL
GOAL_POINTS = {1: 6, 2: 6, 3: 5, 4: 4}
CS_POINTS   = {1: 4, 2: 4, 3: 1, 4: 0}


# ==========================================
# 1. CUSTOM xP & STATS ENGINE
# ==========================================
def get_fixture_factors(fdr: int, is_home: bool = True) -> tuple[float, float, float]:
    fdr_defensive_table = {
        1: (0.45, 0.85),
        2: (0.38, 1.05),
        3: (0.28, 1.35),
        4: (0.18, 1.75),
        5: (0.10, 2.20)
    }
    base_cs, base_gc = fdr_defensive_table.get(fdr, (0.28, 1.35))

    home_boost = 1.12 if is_home else 0.88
    cs_prob = min(0.60, base_cs * home_boost)
    expected_gc = base_gc / home_boost

    fdr_attack_table = {1: 1.25, 2: 1.15, 3: 1.00, 4: 0.85, 5: 0.70}
    attack_mult = fdr_attack_table.get(fdr, 1.00) * (1.08 if is_home else 0.92)

    return attack_mult, cs_prob, expected_gc


def sanitize_stat_per_90(raw_val: any, minutes: int, default_cap: float = 1.0) -> float:
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
    fdr: int = 3,
    is_home: bool = True,
    xg_weight: float = 1.0,
    cs_weight: float = 1.0
) -> float:
    if xmins <= 0.0:
        return 0.0

    pos_id = el["element_type"]
    total_minutes = el.get("minutes", 0)
    mins_ratio = xmins / 90.0

    attack_mult, cs_prob, expected_gc = get_fixture_factors(fdr, is_home)

    p_play_60 = 1.0 / (1.0 + math.exp(-0.2 * (xmins - 55.0)))
    appearance_xp = (p_play_60 * 2.0) + ((1.0 - p_play_60) * 1.0)

    xg90 = sanitize_stat_per_90(el.get("expected_goals_per_90"), total_minutes, default_cap=1.2)
    xa90 = sanitize_stat_per_90(el.get("expected_assists_per_90"), total_minutes, default_cap=0.8)

    match_xg = xg90 * mins_ratio * attack_mult * xg_weight
    match_xa = xa90 * mins_ratio * attack_mult * xg_weight
    attacking_xp = (match_xg * GOAL_POINTS[pos_id]) + (match_xa * 3.0)

    match_cs_prob = min(0.95, cs_prob * p_play_60 * cs_weight)
    clean_sheet_xp = match_cs_prob * CS_POINTS[pos_id]

    goals_conceded_penalty = 0.0
    if pos_id in [1, 2]:
        match_gc = expected_gc * mins_ratio
        goals_conceded_penalty = (match_gc / 2.0) * -1.0

    save_xp = 0.0
    if pos_id == 1:
        saves90 = sanitize_stat_per_90(el.get("saves_per_90"), total_minutes, default_cap=6.0)
        save_xp = (saves90 * mins_ratio) * 0.33

    bonus_xp = (match_xg * 0.6) + (match_xa * 0.4) + (match_cs_prob * 0.3)
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


def calculate_xmins(el: dict, team_played: int) -> tuple[float, str]:
    chance = el.get("chance_of_playing_next_round")
    if el["status"] in ["i", "s", "u"]:
        avail_factor = 0.0 if chance is None else (chance / 100.0)
    elif chance is not None:
        avail_factor = chance / 100.0
    else:
        avail_factor = 1.0

    if avail_factor == 0.0:
        return 0.0, "🔴 OUT (เจ็บ/แบน)"

    minutes = el.get("minutes", 0)
    starts = el.get("starts", 0)

    if team_played >= 2:
        avg_mins = minutes / team_played
        start_rate = starts / team_played
    else:
        avg_mins = 80.0 if el["now_cost"] >= 60 else 55.0
        start_rate = 0.9 if el["now_cost"] >= 60 else 0.5

    raw_xmins = min(90.0, avg_mins)
    xmins = round(raw_xmins * avail_factor, 1)

    if avail_factor <= 0.5:
        risk = "🔴 HIGH (เช็กฟิต 50%)"
    elif start_rate < 0.45 or xmins < 45.0:
        risk = "🟠 HIGH (สำรองบ่อย)"
    elif start_rate < 0.75 or xmins < 65.0:
        risk = "🟡 MED (เสี่ยงโรเตชัน)"
    else:
        risk = "🟢 LOW (ตัวจริง)"

    return xmins, risk


# ==========================================
# 2. MARKET PRICE PREDICTOR ENGINE
# ==========================================
def calculate_price_trend(el: dict, total_managers: int) -> dict:
    """
    คำนวณการย้ายตัวสุทธิ (Net Transfers) และประมาณการโอกาสราคาขึ้น-ลง
    """
    tin = el.get("transfers_in_event", 0)
    tout = el.get("transfers_out_event", 0)
    net_transfers = tin - tout
    ownership_pct = float(el.get("selected_by_percent") or 0.0)
    ownership_count = max(2000, int(total_managers * (ownership_pct / 100.0)))

    # เพดานเป้าหมายสำหรับการปรับราคา (Dynamic Threshold)
    rise_threshold = max(35000, int(ownership_count * 0.065))
    fall_threshold = -max(25000, int(ownership_count * 0.055))

    if net_transfers > 0:
        progress = round((net_transfers / rise_threshold) * 100.0, 1)
    else:
        progress = round((net_transfers / abs(fall_threshold)) * 100.0, 1)

    # จำแนกสถานะ
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
        "status": status
    }


# ==========================================
# 3. DATA PIPELINE & API CALLS
# ==========================================
def get_fixture_details(target_gws: list, teams_dict: dict) -> dict:
    fixtures_res = requests.get(f"{BASE_URL}/fixtures/", headers=HEADERS).json()
    fixture_details = {tid: {gw: [] for gw in target_gws} for tid in teams_dict}

    for fix in fixtures_res:
        gw = fix.get("event")
        if gw in target_gws:
            h_team, a_team = fix["team_h"], fix["team_a"]
            h_diff, a_diff = fix["team_h_difficulty"], fix["team_a_difficulty"]

            fixture_details[h_team][gw].append({
                "opp": teams_dict[a_team],
                "fdr": h_diff,
                "is_home": True,
                "label": f"vs {teams_dict[a_team]} (H) [FDR {h_diff}]"
            })
            fixture_details[a_team][gw].append({
                "opp": teams_dict[h_team],
                "fdr": a_diff,
                "is_home": False,
                "label": f"vs {teams_dict[h_team]} (A) [FDR {a_diff}]"
            })

    return fixture_details


def fetch_user_chips_status(team_id: int, target_gw: int) -> dict:
    try:
        history_res = requests.get(f"{BASE_URL}/entry/{team_id}/history/", headers=HEADERS).json()
        used_chips = [c["name"] for c in history_res.get("chips", [])]
        wc_count = used_chips.count("wildcard")
        wc_avail = (target_gw <= 19 and wc_count == 0) or (target_gw > 19 and wc_count < 2)

        return {
            "TC": "3xc" not in used_chips,
            "BB": "bboost" not in used_chips,
            "WC": wc_avail,
            "FH": "freehit" not in used_chips
        }
    except Exception:
        return {"TC": True, "BB": True, "WC": True, "FH": False}


def fetch_fpl_data_multi(team_id: int, xg_weight: float = 1.0, cs_weight: float = 1.0):
    print(f"[1/4] กำลังดึงข้อมูลกลางและสถิติเชิงลึก (xG/xA) จาก FPL API...")
    bootstrap = requests.get(f"{BASE_URL}/bootstrap-static/", headers=HEADERS).json()

    total_managers = bootstrap.get("total_players", 10_500_000)

    next_event = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    if next_event:
        next_gw = next_event["id"]
        deadline_raw = next_event["deadline_time"]
        gw_name = next_event["name"]
    else:
        current_event = next((e for e in bootstrap["events"] if e.get("is_current")), None)
        next_gw = (current_event["id"] + 1) if current_event else 1
        deadline_raw = None
        gw_name = f"Gameweek {next_gw}"

    deadline_info = {
        "gw": next_gw,
        "name": gw_name,
        "deadline_utc": deadline_raw
    }

    target_gws = [min(38, next_gw + w) for w in range(HORIZON_WEEKS)]
    target_gws = sorted(list(set(target_gws)))
    pick_gw = max(1, next_gw - 1)

    teams_dict = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    teams_played = {t["id"]: t.get("played", pick_gw) for t in bootstrap["teams"]}
    element_costs = {el["id"]: el["now_cost"] / 10.0 for el in bootstrap["elements"]}

    fixture_details = get_fixture_details(target_gws, teams_dict)

    dgw_bgw_info = {}
    for gw in target_gws:
        dgw_teams = [teams_dict[tid] for tid in teams_dict if len(fixture_details[tid].get(gw, [])) >= 2]
        bgw_teams = [teams_dict[tid] for tid in teams_dict if len(fixture_details[tid].get(gw, [])) == 0]
        dgw_bgw_info[gw] = {"dgw": dgw_teams, "bgw": bgw_teams}

    print(f"[2/4] กำลังดึงข้อมูลทีมของผู้ใช้ (Team ID: {team_id} จาก GW{pick_gw})...")
    picks_res = requests.get(f"{BASE_URL}/entry/{team_id}/event/{pick_gw}/picks/", headers=HEADERS).json()
    if "picks" not in picks_res:
        raise ValueError(f"ไม่พบข้อมูล Picks สำหรับ Team ID {team_id} ใน Gameweek {pick_gw}")

    bank = picks_res["entry_history"]["bank"] / 10.0
    current_picks = picks_res["picks"]
    my_player_ids = [p["element"] for p in current_picks]

    selling_prices = {
        p["element"]: (p.get("selling_price") / 10.0) if p.get("selling_price") is not None else element_costs.get(p["element"], 0.0)
        for p in current_picks
    }

    transfers_made = picks_res["entry_history"].get("event_transfers", 0)
    initial_ft = max(1, 1 - transfers_made)

    print(f"[3/4] ตรวจสอบสิทธิ์ชิปที่เหลืออยู่จากประวัติการแข่งขัน...")
    chips_available = fetch_user_chips_status(team_id, next_gw)

    print(f"[4/4] กำลังประมวลผล Custom xP และวิเคราะห์ Market Price Trends...")
    players = []
    for el in bootstrap["elements"]:
        pid = el["id"]
        if el["status"] == "u":
            continue

        buy_price = el["now_cost"] / 10.0
        sell_price = selling_prices.get(pid, buy_price)

        t_played = teams_played.get(el["team"], pick_gw)
        xmins, risk_level = calculate_xmins(el, t_played)
        price_trend = calculate_price_trend(el, total_managers)

        xp_by_gw = {}
        next_fixtures = {}
        is_dgw_by_gw = {}
        is_bgw_by_gw = {}

        for gw in target_gws:
            matches = fixture_details.get(el["team"], {}).get(gw, [])
            match_count = len(matches)
            is_dgw_by_gw[gw] = (match_count >= 2)
            is_bgw_by_gw[gw] = (match_count == 0)

            if match_count == 0:
                xp_by_gw[gw] = 0.0
                next_fixtures[gw] = "Blank"
            else:
                total_gw_xp = 0.0
                labels = []
                for m in matches:
                    total_gw_xp += calculate_player_custom_xp(
                        el=el,
                        xmins=xmins,
                        fdr=m["fdr"],
                        is_home=m["is_home"],
                        xg_weight=xg_weight,
                        cs_weight=cs_weight
                    )
                    labels.append(m["label"])

                xp_by_gw[gw] = round(total_gw_xp, 2)
                next_fixtures[gw] = " / ".join(labels)

        players.append({
            "id": pid,
            "web_name": el["web_name"],
            "full_name": f"{el['first_name']} {el['second_name']}",
            "team": teams_dict[el["team"]],
            "team_id": el["team"],
            "position": POSITION_MAP[el["element_type"]],
            "pos_id": el["element_type"],
            "buy_price": buy_price,
            "sell_price": sell_price,
            "form": float(el.get("form") or 0.0),
            "xmins": xmins,
            "risk": risk_level,
            "xp_by_gw": xp_by_gw,
            "fixtures": next_fixtures,
            "is_dgw": is_dgw_by_gw,
            "is_bgw": is_bgw_by_gw,
            "price_trend": price_trend,
            "in_initial_team": 1 if pid in my_player_ids else 0,
        })

    return players, my_player_ids, bank, initial_ft, target_gws, chips_available, deadline_info, dgw_bgw_info

# ==========================================
# 4. MINI-LEAGUE & EO ANALYSIS ENGINE
# ==========================================
def fetch_minileague_eo(league_id: int, pick_gw: int, max_managers: int = 25):
    """
    ดึงรายชื่อทีมในมินิลีก และคำนวณ Effective Ownership (EO) จากไลน์อัปและกัปตันจริง
    """
    if not league_id or league_id <= 0:
        return None

    try:
        # 1. ดึงตารางคะแนนมินิลีก
        league_res = requests.get(
            f"{BASE_URL}/leagues-classic/{league_id}/standings/",
            headers=HEADERS,
            timeout=8
        ).json()

        if "standings" not in league_res:
            return None

        league_name = league_res.get("league", {}).get("name", "Mini-League")
        managers = league_res["standings"].get("results", [])[:max_managers]

        if not managers:
            return None

        total_mgrs = len(managers)
        eo_counts = {}   # เก็บผลรวม multiplier ของนักเตะแต่ละคน
        own_counts = {}  # เก็บจำนวนคนถือใน 15 คน
        cap_counts = {}  # เก็บจำนวนคนเลือกเป็นกัปตัน

        # 2. ดึง 15 ตัวจริงของแต่ละคนใน Gameweek ล่าสุด
        for mgr in managers:
            entry_id = mgr["entry"]
            picks_url = f"{BASE_URL}/entry/{entry_id}/event/{pick_gw}/picks/"
            p_res = requests.get(picks_url, headers=HEADERS, timeout=5).json()

            if "picks" not in p_res:
                continue

            for pick in p_res["picks"]:
                pid = pick["element"]
                multiplier = pick.get("multiplier", 1)  # 0=สำรอง, 1=ตัวจริง, 2=กัปตัน, 3=ทริปเปิลกัปตัน
                is_cap = pick.get("is_captain", False)

                eo_counts[pid] = eo_counts.get(pid, 0) + multiplier
                own_counts[pid] = own_counts.get(pid, 0) + (1 if multiplier > 0 or multiplier == 0 else 0)
                if is_cap:
                    cap_counts[pid] = cap_counts.get(pid, 0) + 1

        # 3. คำนวณเป็นเปอร์เซ็นต์
        league_eo_data = {}
        for pid, total_mult in eo_counts.items():
            league_eo_data[pid] = {
                "eo_pct": round((total_mult / total_mgrs) * 100.0, 1),
                "ownership_pct": round((own_counts.get(pid, 0) / total_mgrs) * 100.0, 1),
                "captain_pct": round((cap_counts.get(pid, 0) / total_mgrs) * 100.0, 1),
            }

        return {
            "league_name": league_name,
            "total_analyzed": total_mgrs,
            "standings": managers,
            "eo_dict": league_eo_data
        }

    except Exception as e:
        print(f"[Mini-League Error] ไม่สามารถดึงข้อมูลลีก {league_id} ได้: {e}")
        return None