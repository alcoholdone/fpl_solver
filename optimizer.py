import pulp
from config import (
    HORIZON_WEEKS,
    DISCOUNT_FACTOR,
    MAX_FREE_TRANSFERS,
    HIT_PENALTY_COST,
    MAX_PLAYERS_PER_TEAM,
    TOTAL_SQUAD_SIZE,
    STARTING_XI_SIZE,
    FT_ROLL_VALUE,
    CAPTAIN_DEF_CONFLICT_PENALTY,
)


def _val(var) -> float:
    v = pulp.value(var)
    return float(v) if v is not None else 0.0


def _is_one(var) -> bool:
    return _val(var) >= 0.5


def filter_candidate_pool(
    players: list,
    my_player_ids: list,
    locked_player_ids: list = None,
    banned_player_ids: list = None,
    liked_team_ids: list = None,
    banned_team_ids: list = None,
    max_per_pos: tuple = (12, 35, 45, 25),
) -> list:
    locked_set = set(locked_player_ids or [])
    banned_set = set(banned_player_ids or []) - locked_set
    liked_team_set = set(liked_team_ids or [])
    banned_team_set = set(banned_team_ids or []) - liked_team_set
    my_set = set(my_player_ids)

    # ผู้เล่นในทีมปัจจุบันและผู้เล่นที่ถูก Lock ต้องอยู่ใน Candidate Pool เสมอ 100%
    must_include = [p for p in players if p["id"] in my_set or p["id"] in locked_set]
    must_ids = {p["id"] for p in must_include}

    candidates_by_pos = {1: [], 2: [], 3: [], 4: []}
    candidates_by_liked_team = {tid: [] for tid in liked_team_set}

    for p in players:
        if p["id"] in must_ids:
            continue
        # ตัดผู้เล่นที่ถูกแบนและทีมที่ถูกแบนออกก่อนจัดอันดับ Candidate Pool
        if p["id"] in banned_set or p.get("team_id") in banned_team_set:
            continue
        # ตัดตัวที่เจ็บยาว/ไม่พร้อมลงสนาม และไม่มีโอกาสได้แต้มออก
        if p.get("status") in ["u", "i"] and p.get("xmins", 0) < 15.0:
            continue

        pos = p.get("pos_id", 3)
        if pos in candidates_by_pos:
            candidates_by_pos[pos].append(p)
        if p.get("team_id") in candidates_by_liked_team:
            candidates_by_liked_team[p["team_id"]].append(p)

    selected_map = {p["id"]: p for p in must_include}
    pos_limits = {1: max_per_pos[0], 2: max_per_pos[1], 3: max_per_pos[2], 4: max_per_pos[3]}

    def _score_key(p: dict) -> float:
        total_xp = sum(p["xp_by_gw"].values()) if p.get("xp_by_gw") else 0.0
        return total_xp + (p.get("form", 0.0) * 0.5)

    for pos, cands in candidates_by_pos.items():
        cands.sort(key=_score_key, reverse=True)
        limit = pos_limits.get(pos, 30)
        top_players = cands[:limit]

        # รับประกันตัวเลือกสายประหยัด (Budget Enablers) ชั้นดีเพื่อให้ระบบหมุนเงินได้ยืดหยุ่น
        budget_cutoff = {1: 4.2, 2: 4.5, 3: 5.2, 4: 5.5}.get(pos, 4.5)
        budget_options = [
            p for p in cands
            if p.get("buy_price", 99.0) <= budget_cutoff and p.get("xmins", 0) >= 45.0
        ][:6]

        for p in top_players:
            selected_map[p["id"]] = p
        for b in budget_options:
            selected_map[b["id"]] = b

    # การันตีตัวเลือกตัวท็อปจากแต่ละทีมที่ชอบ (Top 8 ต่อทีม)
    for _tid, tcands in candidates_by_liked_team.items():
        tcands.sort(key=_score_key, reverse=True)
        for p in tcands[:8]:
            selected_map[p["id"]] = p

    return list(selected_map.values())


def solve_multi_period_fpl(
    players,
    my_player_ids,
    bank,
    initial_ft,
    target_gws,
    chips_available: dict,
    enable_chips: bool = True,
    locked_player_ids: list = None,
    banned_player_ids: list = None,
    dgw_bgw_info: dict = None,
    max_hits_per_gw: int = None,
    allowed_chips: list = None,
    forced_chip: str = None,
    liked_team_ids: list = None,
    banned_team_ids: list = None,
    min_per_liked_team: int = 1,
):
    locked_ids = set(locked_player_ids or [])
    liked_team_set = set(liked_team_ids or [])
    banned_team_set = set(banned_team_ids or []) - liked_team_set
    my_set = set(my_player_ids)

    filtered_players = filter_candidate_pool(
        players,
        my_player_ids,
        locked_player_ids=locked_ids,
        banned_player_ids=banned_player_ids,
        liked_team_ids=liked_team_set,
        banned_team_ids=banned_team_set,
    )
    print(f"[4/4] กำลังประมวลผล Multi-GW (Pool: {len(filtered_players)} คน | DGW Trigger: Active)...")

    # ตรวจสอบเงื่อนไข Lock เบื้องต้นก่อนสร้างตัวแปร
    if locked_ids:
        locked_players = [p for p in filtered_players if p["id"] in locked_ids]
        pos_names = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
        pos_quotas_lock = {1: 2, 2: 5, 3: 5, 4: 3}
        lock_team_counts = {}
        lock_pos_counts = {}
        for lp in locked_players:
            tid = lp["team_id"]
            pid_pos = lp["pos_id"]
            lock_team_counts[tid] = lock_team_counts.get(tid, 0) + 1
            if lock_team_counts[tid] > MAX_PLAYERS_PER_TEAM:
                raise ValueError(
                    f"ไม่สามารถ Lock นักเตะจากทีม {lp['team']} เกิน {MAX_PLAYERS_PER_TEAM} คนได้"
                )
            lock_pos_counts[pid_pos] = lock_pos_counts.get(pid_pos, 0) + 1
            if lock_pos_counts[pid_pos] > pos_quotas_lock[pid_pos]:
                raise ValueError(
                    f"ไม่สามารถ Lock ตำแหน่ง {pos_names[pid_pos]} เกินโควตา {pos_quotas_lock[pid_pos]} คนได้"
                )

    effective_banned_ids = (
        set(banned_player_ids or [])
        | {p["id"] for p in filtered_players if p.get("team_id") in banned_team_set}
    ) - locked_ids
    non_owned_banned_ids = {pid for pid in effective_banned_ids if pid not in my_set}
    owned_banned_ids = {pid for pid in effective_banned_ids if pid in my_set}

    min_liked = max(1, min(MAX_PLAYERS_PER_TEAM, int(min_per_liked_team or 1)))

    prob = pulp.LpProblem("FPL_Multi_Week_Planner", pulp.LpMaximize)

    # 1. นิยามตัวแปร
    squad_vars = {}
    perm_squad_vars = {}
    start_vars = {}
    cap_vars = {}
    vice_vars = {}
    tin_vars = {}
    tout_vars = {}

    for gw in target_gws:
        for p in filtered_players:
            pid = p["id"]
            squad_vars[(pid, gw)] = pulp.LpVariable(f"squad_{pid}_{gw}", cat="Binary")
            perm_squad_vars[(pid, gw)] = pulp.LpVariable(f"perm_{pid}_{gw}", cat="Binary")
            start_vars[(pid, gw)] = pulp.LpVariable(f"start_{pid}_{gw}", cat="Binary")
            cap_vars[(pid, gw)] = pulp.LpVariable(f"cap_{pid}_{gw}", cat="Binary")
            vice_vars[(pid, gw)] = pulp.LpVariable(f"vice_{pid}_{gw}", cat="Binary")
            tin_vars[(pid, gw)] = pulp.LpVariable(f"tin_{pid}_{gw}", cat="Binary")
            tout_vars[(pid, gw)] = pulp.LpVariable(f"tout_{pid}_{gw}", cat="Binary")

    # ตัวแปร Slack สำหรับทีมที่ชอบ เพื่อไม่ให้เกิด Infeasible เมื่อ FT/งบไม่พอใน GW แรก
    liked_slack = {}
    for tid in liked_team_set:
        for gw in target_gws:
            liked_slack[(tid, gw)] = pulp.LpVariable(
                f"liked_slack_{tid}_{gw}", lowBound=0.0, upBound=float(min_liked)
            )

    # ตัวแปรลดความขัดแย้งเมื่อส่ง GKP/DEF ตัวจริงชนกับทีมคู่แข่งของกัปตันตัวเอง
    cap_def_conflict = {}
    team_ids_in_pool = sorted({p["team_id"] for p in filtered_players if p.get("team_id") is not None})
    for gw in target_gws:
        for tid in team_ids_in_pool:
            cap_facing_pids = [
                p["id"] for p in filtered_players
                if tid in p.get("opponents_by_gw", {}).get(gw, [])
            ]
            team_def_pids = [
                p["id"] for p in filtered_players
                if p.get("team_id") == tid and p.get("pos_id") in (1, 2)
            ]
            if cap_facing_pids and team_def_pids:
                conf_var = pulp.LpVariable(
                    f"cap_def_conf_{tid}_{gw}", lowBound=0.0, upBound=float(MAX_PLAYERS_PER_TEAM)
                )
                cap_def_conflict[(tid, gw)] = conf_var
                cap_faces = pulp.lpSum([cap_vars[(pid, gw)] for pid in cap_facing_pids])
                def_starts = pulp.lpSum([start_vars[(pid, gw)] for pid in team_def_pids])
                prob += conf_var >= def_starts - MAX_PLAYERS_PER_TEAM * (1 - cap_faces)

    # 2. ตัวแปร Chips พร้อมควบคุมสิทธิ์เจาะจง
    allowed_chip_set = set(allowed_chips) if allowed_chips is not None else None
    chip_types = [
        c for c, avail in chips_available.items()
        if avail and enable_chips and (allowed_chip_set is None or c in allowed_chip_set)
    ]
    chip_vars = {}
    for c in chip_types:
        for gw in target_gws:
            chip_vars[(c, gw)] = pulp.LpVariable(f"chip_{c}_{gw}", cat="Binary")

    tc_active = {}
    if "TC" in chip_types:
        for gw in target_gws:
            for p in filtered_players:
                tc_active[(p["id"], gw)] = pulp.LpVariable(f"tc_{p['id']}_{gw}", cat="Binary")

    # 3. ตัวแปร Free Transfers และ Hits
    ft_vars = {gw: pulp.LpVariable(f"ft_{gw}", lowBound=1, upBound=MAX_FREE_TRANSFERS) for gw in target_gws}
    rem_ft_vars = {gw: pulp.LpVariable(f"rem_ft_{gw}", lowBound=0, upBound=MAX_FREE_TRANSFERS) for gw in target_gws}
    hits_vars = {gw: pulp.LpVariable(f"hits_{gw}", lowBound=0, cat="Integer") for gw in target_gws}
    has_hits_vars = {gw: pulp.LpVariable(f"has_hits_{gw}", cat="Binary") for gw in target_gws}

    # 4. ตัวแปร Dynamic Bank Balance
    bank_vars = {gw: pulp.LpVariable(f"bank_{gw}", lowBound=0.0) for gw in target_gws}

    prob += ft_vars[target_gws[0]] == initial_ft

    # 5. Objective Function พร้อม Dynamic Hurdle Rates และ FT Roll Value
    objective_terms = []
    for idx, gw in enumerate(target_gws):
        discount = DISCOUNT_FACTOR ** idx

        gw_points = pulp.lpSum([
            start_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + cap_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + 0.10 * vice_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + (
                0.12 if p.get("xmins_by_gw", {}).get(gw, p.get("xmins", 0)) >= 45.0 else 0.02
            ) * (squad_vars[(p["id"], gw)] - start_vars[(p["id"], gw)]) * p["xp_by_gw"][gw]
            for p in filtered_players
        ])

        if liked_team_set:
            gw_points += pulp.lpSum([
                0.25 * squad_vars[(p["id"], gw)]
                for p in filtered_players
                if p.get("team_id") in liked_team_set
            ])

        if "TC" in chip_types:
            gw_points += pulp.lpSum([tc_active[(p["id"], gw)] * p["xp_by_gw"][gw] for p in filtered_players])

        # --- คำนวณ Hurdle Rate แบบไดนามิกตามสภาพ DGW/BGW ---
        dgw_list = dgw_bgw_info.get(gw, {}).get("dgw", []) if dgw_bgw_info else []
        bgw_list = dgw_bgw_info.get(gw, {}).get("bgw", []) if dgw_bgw_info else []
        has_dgw = len(dgw_list) > 0
        has_bgw = len(bgw_list) >= 2

        tc_threshold = 7.0 if has_dgw else 13.0
        bb_threshold = 10.0 if len(dgw_list) >= 2 else 16.0
        fh_threshold = 12.0 if has_bgw else 22.0
        wc_threshold = 25.0

        gw_hurdles = {"TC": tc_threshold, "BB": bb_threshold, "FH": fh_threshold, "WC": wc_threshold}

        chip_penalties = pulp.lpSum([
            chip_vars[(c, gw)] * gw_hurdles.get(c, 0.0)
            for c in chip_types
        ])

        liked_penalty = (
            25.0 * pulp.lpSum([liked_slack[(tid, gw)] for tid in liked_team_set])
            if liked_team_set
            else 0.0
        )
        owned_banned_penalty = (
            30.0 * pulp.lpSum([squad_vars[(pid, gw)] for pid in owned_banned_ids if (pid, gw) in squad_vars])
            if owned_banned_ids
            else 0.0
        )
        cap_def_penalty = (
            CAPTAIN_DEF_CONFLICT_PENALTY
            * pulp.lpSum([var for (_tid, g), var in cap_def_conflict.items() if g == gw])
        )

        # ปรับ Hit Hurdle เป็น 6.5 แต้ม ป้องกันการย้ายตัวพร่ำเพรื่อเพื่อส่วนต่าง xP เล็กน้อย
        effective_hit_penalty = max(HIT_PENALTY_COST, 6.5)
        gw_net_points = (
            gw_points
            + (0.001 * ft_vars[gw])
            - (effective_hit_penalty * hits_vars[gw])
            - chip_penalties
            - liked_penalty
            - owned_banned_penalty
            - cap_def_penalty
        )
        objective_terms.append(discount * gw_net_points)

    # มูลค่าแฝงของการเก็บ Free Transfer ข้าม Horizon
    objective_terms.append((DISCOUNT_FACTOR ** len(target_gws)) * FT_ROLL_VALUE * rem_ft_vars[target_gws[-1]])

    prob += pulp.lpSum(objective_terms)

    # 6. Constraints ของ Chips
    if chip_types:
        for c in chip_types:
            prob += pulp.lpSum([chip_vars[(c, gw)] for gw in target_gws]) <= 1
        for gw in target_gws:
            prob += pulp.lpSum([chip_vars[(c, gw)] for c in chip_types]) <= 1

        if forced_chip and forced_chip in chip_types:
            prob += chip_vars[(forced_chip, target_gws[0])] == 1

    if "TC" in chip_types:
        for gw in target_gws:
            dgw_list = dgw_bgw_info.get(gw, {}).get("dgw", []) if dgw_bgw_info else []
            has_dgw = len(dgw_list) > 0

            for p in filtered_players:
                pid = p["id"]
                prob += tc_active[(pid, gw)] <= cap_vars[(pid, gw)]
                prob += tc_active[(pid, gw)] <= chip_vars[("TC", gw)]
                prob += tc_active[(pid, gw)] >= cap_vars[(pid, gw)] + chip_vars[("TC", gw)] - 1

            # Quality Guardrail: หากไม่ใช่สัปดาห์ DGW กัปตันที่ติด TC ต้องมี xP ไม่น้อยกว่า 9.0 แต้ม
            if not has_dgw:
                prob += pulp.lpSum([cap_vars[(p["id"], gw)] * p["xp_by_gw"][gw] for p in filtered_players]) >= 9.0 * chip_vars[("TC", gw)]

    if "BB" in chip_types:
        for gw in target_gws:
            # BB Safety Guardrail: สมาชิกในทีมอย่างน้อย 14 คนต้องมี xMins >= 50 นาที
            prob += pulp.lpSum([
                squad_vars[(p["id"], gw)] * (1 if p.get("xmins_by_gw", {}).get(gw, p.get("xmins", 0)) >= 50.0 else 0)
                for p in filtered_players
            ]) >= 14 * chip_vars[("BB", gw)]

    current_team_value = sum(p["sell_price"] for p in filtered_players if p["id"] in my_set)
    total_budget_cap = bank + current_team_value

    # 7. Constraints รายสัปดาห์
    for idx, gw in enumerate(target_gws):
        prev_gw = target_gws[idx - 1] if idx > 0 else None

        is_wc = chip_vars[("WC", gw)] if "WC" in chip_types else 0
        is_fh = chip_vars[("FH", gw)] if "FH" in chip_types else 0

        # กฎ Lock & Ban (รายนักเตะ)
        for pid in locked_ids:
            if (pid, gw) in squad_vars:
                prob += squad_vars[(pid, gw)] == 1

        for pid in non_owned_banned_ids:
            if (pid, gw) in squad_vars:
                prob += squad_vars[(pid, gw)] == 0
                prob += perm_squad_vars[(pid, gw)] == 0

        # กฎทีมที่ชอบ (Soft constraint พร้อม Slack กัน Infeasible)
        for tid in liked_team_set:
            prob += (
                pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p.get("team_id") == tid])
                + liked_slack[(tid, gw)]
                >= min_liked
            )

        # Active Squad 15 คน
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players]) == TOTAL_SQUAD_SIZE
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 1]) == 2
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 2]) == 5
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 3]) == 5
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 4]) == 3

        for tid in set(p["team_id"] for p in filtered_players):
            prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["team_id"] == tid]) <= MAX_PLAYERS_PER_TEAM

        # หากใช้ชิป Free Hit (is_fh = 1) บังคับเพดานราคารวม buy_price ของ 15 คน
        if "FH" in chip_types:
            prob += pulp.lpSum([squad_vars[(p["id"], gw)] * p["buy_price"] for p in filtered_players]) <= total_budget_cap + 1000.0 * (1 - is_fh)

        # Permanent Squad 15 คน
        prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players]) == TOTAL_SQUAD_SIZE
        prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 1]) == 2
        prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 2]) == 5
        prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 3]) == 5
        prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 4]) == 3

        for tid in set(p["team_id"] for p in filtered_players):
            prob += pulp.lpSum([perm_squad_vars[(p["id"], gw)] for p in filtered_players if p["team_id"] == tid]) <= MAX_PLAYERS_PER_TEAM

        # เชื่อมโยง Free Hit
        for p in filtered_players:
            pid = p["id"]
            prob += squad_vars[(pid, gw)] - perm_squad_vars[(pid, gw)] <= is_fh
            prob += perm_squad_vars[(pid, gw)] - squad_vars[(pid, gw)] <= is_fh

            prob += tin_vars[(pid, gw)] <= 1 - is_fh
            prob += tout_vars[(pid, gw)] <= 1 - is_fh

            prev_perm = p["in_initial_team"] if prev_gw is None else perm_squad_vars[(pid, prev_gw)]
            prob += perm_squad_vars[(pid, gw)] - prev_perm == tin_vars[(pid, gw)] - tout_vars[(pid, gw)]
            prob += tout_vars[(pid, gw)] <= prev_perm
            prob += tin_vars[(pid, gw)] <= 1 - prev_perm
            prob += tin_vars[(pid, gw)] + tout_vars[(pid, gw)] <= 1

        # Dynamic Bank Balance
        sales_revenue = pulp.lpSum([tout_vars[(p["id"], gw)] * p["sell_price"] for p in filtered_players])
        purchase_cost = pulp.lpSum([tin_vars[(p["id"], gw)] * p["buy_price"] for p in filtered_players])

        if prev_gw is None:
            prob += bank_vars[gw] == bank + sales_revenue - purchase_cost
        else:
            prob += bank_vars[gw] == bank_vars[prev_gw] + sales_revenue - purchase_cost

        # 11 ตัวจริง & กัปตัน
        is_bb = chip_vars[("BB", gw)] if "BB" in chip_types else 0
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players]) == STARTING_XI_SIZE + (4 * is_bb)

        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 1]) >= 1
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 1]) <= 1 + is_bb
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 2]) >= 3
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 2]) <= 5
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 3]) >= 2
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 3]) <= 5
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 4]) >= 1
        prob += pulp.lpSum([start_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 4]) <= 3

        prob += pulp.lpSum([cap_vars[(p["id"], gw)] for p in filtered_players]) == 1
        prob += pulp.lpSum([vice_vars[(p["id"], gw)] for p in filtered_players]) == 1

        for p in filtered_players:
            pid = p["id"]
            prob += start_vars[(pid, gw)] <= squad_vars[(pid, gw)]
            prob += cap_vars[(pid, gw)] <= start_vars[(pid, gw)]
            prob += vice_vars[(pid, gw)] <= start_vars[(pid, gw)]
            prob += cap_vars[(pid, gw)] + vice_vars[(pid, gw)] <= 1

            if "BB" in chip_types:
                prob += start_vars[(pid, gw)] >= squad_vars[(pid, gw)] - (1 - chip_vars[("BB", gw)])

        # Free Transfers & Hits (ตามกติกา 2024/25+: WC และ FH คงจำนวน FT เดิมไว้)
        total_in = pulp.lpSum([tin_vars[(p["id"], gw)] for p in filtered_players])

        prob += hits_vars[gw] >= (total_in - ft_vars[gw]) - (20 * is_wc) - (20 * is_fh)
        prob += hits_vars[gw] <= 20 * has_hits_vars[gw]

        if max_hits_per_gw is not None:
            prob += hits_vars[gw] <= max_hits_per_gw

        prob += rem_ft_vars[gw] <= ft_vars[gw] - total_in + (20 * has_hits_vars[gw]) + (20 * is_wc)
        prob += rem_ft_vars[gw] <= MAX_FREE_TRANSFERS * (1 - has_hits_vars[gw]) + (MAX_FREE_TRANSFERS * is_wc)
        prob += rem_ft_vars[gw] <= ft_vars[gw]

        if prev_gw is not None:
            prev_wc = chip_vars[("WC", prev_gw)] if "WC" in chip_types else 0
            prev_fh = chip_vars[("FH", prev_gw)] if "FH" in chip_types else 0
            prev_preserve = prev_wc + prev_fh
            prob += ft_vars[gw] <= rem_ft_vars[prev_gw] + 1 + (10 * prev_preserve)
            prob += ft_vars[gw] <= ft_vars[prev_gw] + (10 * (1 - prev_preserve))

    solver_cmd = pulp.PULP_CBC_CMD(msg=False, gapRel=0.01, timeLimit=20)
    prob.solve(solver_cmd)

    status_name = pulp.LpStatus.get(prob.status, "Unknown")
    if prob.status == pulp.LpStatusInfeasible or status_name in ("Infeasible", "Unbounded", "Undefined"):
        raise ValueError(
            "ไม่สามารถจัดทีมตามเงื่อนไขได้ (Infeasible) — กรุณาตรวจสอบว่า Lock นักเตะเกินโควตา 3 คน/ทีม, "
            "เกินงบ, เกินจำนวนย้ายตัวฟรี (FT/Hits) หรือบังคับใช้ชิปที่ยังไม่เข้าเงื่อนไขหรือไม่"
        )

    has_solution = any(pulp.value(start_vars[(p["id"], target_gws[0])]) is not None for p in filtered_players)
    if prob.status != pulp.LpStatusOptimal and not has_solution:
        raise ValueError(
            f"Solver หยุดทำงานก่อนพบผลลัพธ์ (สถานะ: {status_name}) กรุณาลด Horizon หรือปรับผ่อนปรนเงื่อนไข"
        )

    # 8. สรุปแผน (Float-safe extraction)
    plans = []
    for idx, gw in enumerate(target_gws):
        prev_gw = target_gws[idx - 1] if idx > 0 else None

        active_chip = None
        for c in chip_types:
            if _is_one(chip_vars[(c, gw)]):
                active_chip = c
                break

        if active_chip == "FH":
            prev_team_ids = {
                p["id"] for p in filtered_players
                if (p["in_initial_team"] == 1 if prev_gw is None else _is_one(perm_squad_vars[(p["id"], prev_gw)]))
            }
            active_team_ids = {p["id"] for p in filtered_players if _is_one(squad_vars[(p["id"], gw)])}
            tin = [p for p in filtered_players if p["id"] in active_team_ids and p["id"] not in prev_team_ids]
            tout = [p for p in filtered_players if p["id"] in prev_team_ids and p["id"] not in active_team_ids]
        else:
            tin = [p for p in filtered_players if _is_one(tin_vars[(p["id"], gw)])]
            tout = [p for p in filtered_players if _is_one(tout_vars[(p["id"], gw)])]

        starters = [p for p in filtered_players if _is_one(start_vars[(p["id"], gw)])]
        starters.sort(key=lambda x: x["pos_id"])

        bench = [
            p for p in filtered_players
            if _is_one(squad_vars[(p["id"], gw)]) and not _is_one(start_vars[(p["id"], gw)])
        ]
        bench_gkp = [p for p in bench if p["pos_id"] == 1]
        bench_outfield = [p for p in bench if p["pos_id"] != 1]
        bench_outfield.sort(
            key=lambda x: (
                1 if x.get("xmins_by_gw", {}).get(gw, x.get("xmins", 0)) >= 45.0 else 0,
                x["xp_by_gw"][gw]
            ),
            reverse=True
        )

        captain = next((p for p in filtered_players if _is_one(cap_vars[(p["id"], gw)])), starters[0])
        vice = next(
            (p for p in filtered_players if _is_one(vice_vars[(p["id"], gw)])),
            starters[1] if len(starters) > 1 else starters[0],
        )

        cap_multiplier = 2 if active_chip == "TC" else 1
        starters_xp = sum(p["xp_by_gw"][gw] for p in starters) + (captain["xp_by_gw"][gw] * cap_multiplier)
        bench_xp = sum(p["xp_by_gw"][gw] for p in (bench_gkp + bench_outfield)) if active_chip == "BB" else 0.0
        hits_count = int(round(_val(hits_vars[gw])))
        hits_deduction = hits_count * 4
        gw_total_xp = round(starters_xp + bench_xp - hits_deduction, 2)

        if active_chip == "FH":
            fh_squad_cost = sum(p["buy_price"] for p in (starters + bench_gkp + bench_outfield))
            plan_bank = round(max(0.0, total_budget_cap - fh_squad_cost), 2)
        else:
            plan_bank = round(_val(bank_vars[gw]), 2)

        plans.append({
            "gw": gw,
            "chip": active_chip,
            "bank_remaining": plan_bank,
            "transfers_in": tin,
            "transfers_out": tout,
            "hits": hits_count,
            "ft_available": int(round(_val(ft_vars[gw]))),
            "starters": starters,
            "captain": captain,
            "vice_captain": vice,
            "bench": bench_gkp + bench_outfield,
            "total_xp": gw_total_xp,
        })

    # 9. ตรวจสอบความถูกต้องตามกติกา FPL ทุกสัปดาห์ก่อนส่งคืนผลลัพธ์
    pos_quotas = {1: 2, 2: 5, 3: 5, 4: 3}
    for plan in plans:
        gw_squad = plan["starters"] + plan["bench"]
        if len(gw_squad) != TOTAL_SQUAD_SIZE:
            raise ValueError("Solver ไม่พบแผนที่ถูกต้องตามกติกา FPL (จำนวนผู้เล่นไม่ครบ 15 คน) กรุณาปรับผ่อนปรนเงื่อนไข")

        team_counts = {}
        pos_counts = {}
        for sp in gw_squad:
            tid = sp["team_id"]
            team_counts[tid] = team_counts.get(tid, 0) + 1
            if team_counts[tid] > MAX_PLAYERS_PER_TEAM:
                raise ValueError(
                    f"Solver ไม่พบแผนที่ถูกต้องตามกติกา FPL (ทีม {sp['team']} เกิน {MAX_PLAYERS_PER_TEAM} คน) กรุณาปรับผ่อนปรนเงื่อนไข"
                )
            pos_counts[sp["pos_id"]] = pos_counts.get(sp["pos_id"], 0) + 1

        if any(pos_counts.get(pos_k, 0) != quota for pos_k, quota in pos_quotas.items()):
            raise ValueError("Solver ไม่พบแผนที่ถูกต้องตามกติกา FPL (สัดส่วนตำแหน่งไม่ถูกต้อง) กรุณาปรับผ่อนปรนเงื่อนไข")

        if plan["bank_remaining"] < -0.05:
            raise ValueError("Solver ไม่พบแผนที่ถูกต้องตามกติกา FPL (งบประมาณติดลบ) กรุณาปรับผ่อนปรนเงื่อนไข")

        expected_starters = TOTAL_SQUAD_SIZE if plan["chip"] == "BB" else STARTING_XI_SIZE
        if len(plan["starters"]) != expected_starters:
            raise ValueError("Solver ไม่พบแผนที่ถูกต้องตามกติกา FPL (จำนวนตัวจริงไม่ถูกต้อง) กรุณาปรับผ่อนปรนเงื่อนไข")

    return plans
