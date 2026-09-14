import pulp
from config import (
    HORIZON_WEEKS, DISCOUNT_FACTOR, MAX_FREE_TRANSFERS,
    HIT_PENALTY_COST, MAX_PLAYERS_PER_TEAM, TOTAL_SQUAD_SIZE, STARTING_XI_SIZE
)

def filter_candidate_pool(players: list, my_player_ids: list, locked_player_ids: list = None, max_per_pos: tuple = (12, 35, 45, 25)) -> list:
    locked_set = set(locked_player_ids or [])
    my_set = set(my_player_ids)

    # ผู้เล่นในทีมปัจจุบันและผู้เล่นที่ถูก Lock ต้องอยู่ใน Candidate Pool เสมอ 100%
    must_include = [p for p in players if p["id"] in my_set or p["id"] in locked_set]
    must_ids = {p["id"] for p in must_include}

    candidates_by_pos = {1: [], 2: [], 3: [], 4: []}
    for p in players:
        if p["id"] in must_ids:
            continue
        # ตัดตัวที่เจ็บยาว/โดนแบนยาว และไม่มีโอกาสได้แต้มออก
        if p.get("status") in ["u", "i"] and p.get("xmins", 0) < 15.0:
            continue
        pos = p.get("pos_id", 3)
        if pos in candidates_by_pos:
            candidates_by_pos[pos].append(p)

    selected = list(must_include)
    pos_limits = {1: max_per_pos[0], 2: max_per_pos[1], 3: max_per_pos[2], 4: max_per_pos[3]}

    for pos, cands in candidates_by_pos.items():
        # เรียงลำดับตาม Total xP ตลอดช่วง Gameweek + ฟอร์มปัจจุบัน
        cands.sort(
            key=lambda p: (
                sum(p["xp_by_gw"].values()) if p.get("xp_by_gw") else 0.0
            ) + (p.get("form", 0.0) * 0.5),
            reverse=True
        )
        limit = pos_limits.get(pos, 30)
        top_players = cands[:limit]

        # รับประกันตัวเลือกสายประหยัด (Budget Enablers) ชั้นดีเพื่อให้ระบบหมุนเงินได้ยืดหยุ่น
        budget_cutoff = {1: 4.2, 2: 4.5, 3: 5.2, 4: 5.5}.get(pos, 4.5)
        budget_options = [
            p for p in cands
            if p.get("buy_price", 99.0) <= budget_cutoff and p.get("xmins", 0) >= 45.0
        ][:6]

        combined = {p["id"]: p for p in top_players}
        for b in budget_options:
            combined[b["id"]] = b

        selected.extend(combined.values())

    return selected


def solve_multi_period_fpl(
    players, my_player_ids, bank, initial_ft, target_gws, chips_available: dict,
    enable_chips: bool = True, locked_player_ids: list = None, banned_player_ids: list = None,
    dgw_bgw_info: dict = None, max_hits_per_gw: int = None, allowed_chips: list = None,
    forced_chip: str = None
):
    locked_ids = set(locked_player_ids or [])
    banned_ids = set(banned_player_ids or [])

    filtered_players = filter_candidate_pool(players, my_player_ids, locked_ids)
    print(f"[4/4] กำลังประมวลผล Multi-GW (Pool: {len(filtered_players)} คน | DGW Trigger: Active)...")

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

    # 5. Objective Function พร้อม Dynamic Hurdle Rates
    objective_terms = []
    for idx, gw in enumerate(target_gws):
        discount = DISCOUNT_FACTOR ** idx

        # เสริมแต้ม Upside ให้ตัวรุก (+0.12 pts) และการันตีรองกัปตันทีมเป็นตัวที่มี xP สูงสุดอันดับ 2 (+0.10 * vice_vars * xP)
        gw_points = pulp.lpSum([
            start_vars[(p["id"], gw)] * (p["xp_by_gw"][gw] + (0.12 if p["pos_id"] in [3, 4] else 0.0))
            + cap_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + 0.10 * vice_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + 0.05 * (squad_vars[(p["id"], gw)] - start_vars[(p["id"], gw)]) * p["xp_by_gw"][gw]
            for p in filtered_players
        ])

        if "TC" in chip_types:
            gw_points += pulp.lpSum([tc_active[(p["id"], gw)] * p["xp_by_gw"][gw] for p in filtered_players])

        # --- คำนวณ Hurdle Rate แบบไดนามิกตามสภาพ DGW/BGW ---
        dgw_list = dgw_bgw_info.get(gw, {}).get("dgw", []) if dgw_bgw_info else []
        bgw_list = dgw_bgw_info.get(gw, {}).get("bgw", []) if dgw_bgw_info else []
        has_dgw = len(dgw_list) > 0
        has_bgw = len(bgw_list) >= 2

        # TC: ใน DGW ลดเหลือ 7.0 (กระตุ้นให้กดใช้) แต่ใน Single GW ดันขึ้นเป็น 13.0 (กันเผาชิปทิ้ง)
        tc_threshold = 7.0 if has_dgw else 13.0
        # BB: มี DGW หลายทีมลดเหลือ 10.0 ถ้าปกติ 16.0
        bb_threshold = 10.0 if len(dgw_list) >= 2 else 16.0
        # FH: มี Blank GW หลายทีมลดเหลือ 12.0 ถ้าปกติ 22.0
        fh_threshold = 12.0 if has_bgw else 22.0
        wc_threshold = 25.0

        gw_hurdles = {"TC": tc_threshold, "BB": bb_threshold, "FH": fh_threshold, "WC": wc_threshold}

        chip_penalties = pulp.lpSum([
            chip_vars[(c, gw)] * gw_hurdles.get(c, 0.0)
            for c in chip_types
        ])

        # ปรับ Hit Hurdle เป็น 6.5 แต้ม ป้องกันการย้ายตัวพร่ำเพรื่อเพื่อส่วนต่าง xP เล็กน้อย
        effective_hit_penalty = max(HIT_PENALTY_COST, 6.5)
        gw_net_points = gw_points - (effective_hit_penalty * hits_vars[gw]) - chip_penalties
        objective_terms.append(discount * gw_net_points)

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
            # BB Safety Guardrail: หากเปิด Bench Boost ใน GW นั้น สมาชิกในทีมอย่างน้อย 14 คนต้องมี xMins >= 50 นาที
            # เพื่อป้องกันการเผาชิปทิ้งบนตัวสำรอง 0 นาที หรือตัวที่ไม่ได้ลงแข่ง
            prob += pulp.lpSum([
                squad_vars[(p["id"], gw)] * (1 if p.get("xmins_by_gw", {}).get(gw, p.get("xmins", 0)) >= 50.0 else 0)
                for p in filtered_players
            ]) >= 14 * chip_vars[("BB", gw)]

    current_team_value = sum(p["sell_price"] for p in filtered_players if p["id"] in my_player_ids)
    total_budget_cap = bank + current_team_value

    # 7. Constraints รายสัปดาห์
    for idx, gw in enumerate(target_gws):
        prev_gw = target_gws[idx - 1] if idx > 0 else None

        is_wc = chip_vars[("WC", gw)] if "WC" in chip_types else 0
        is_fh = chip_vars[("FH", gw)] if "FH" in chip_types else 0

        # กฎ Lock & Ban
        for pid in locked_ids:
            if (pid, gw) in squad_vars:
                prob += squad_vars[(pid, gw)] == 1

        for pid in banned_ids:
            if (pid, gw) in squad_vars:
                prob += squad_vars[(pid, gw)] == 0

        # Active Squad 15 คน
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players]) == TOTAL_SQUAD_SIZE
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 1]) == 2
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 2]) == 5
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 3]) == 5
        prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["pos_id"] == 4]) == 3

        for tid in set(p["team_id"] for p in filtered_players):
            prob += pulp.lpSum([squad_vars[(p["id"], gw)] for p in filtered_players if p["team_id"] == tid]) <= MAX_PLAYERS_PER_TEAM

        # Dynamic Bank Balance (bank_vars[gw] >= 0) คุมกระแสเงินสดซื้อ-ขายตามจริงโดยไม่ลงโทษนักเตะเดิมที่ราคาขึ้น
        # หากใช้ชิป Free Hit (is_fh = 1) จึงบังคับเพดานราคารวม buy_price ของ 15 คน
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

        # Free Transfers & Hits
        total_in = pulp.lpSum([tin_vars[(p["id"], gw)] for p in filtered_players])

        prob += hits_vars[gw] >= (total_in - ft_vars[gw]) - (20 * is_wc) - (20 * is_fh)
        prob += hits_vars[gw] <= 20 * has_hits_vars[gw]

        # จำกัดจำนวนแต้มลบ (Hits) ตามนโยบายของผู้ใช้ (เช่น 0 = ห้ามติดลบเด็ดขาด)
        if max_hits_per_gw is not None:
            prob += hits_vars[gw] <= max_hits_per_gw

        prob += rem_ft_vars[gw] <= ft_vars[gw] - total_in + (20 * has_hits_vars[gw])
        prob += rem_ft_vars[gw] <= MAX_FREE_TRANSFERS * (1 - has_hits_vars[gw])
        prob += rem_ft_vars[gw] <= MAX_FREE_TRANSFERS * (1 - is_wc)

        if prev_gw is not None:
            prev_fh = chip_vars[("FH", prev_gw)] if "FH" in chip_types else 0
            prob += ft_vars[gw] <= rem_ft_vars[prev_gw] + 1 + (10 * prev_fh)
            prob += ft_vars[gw] <= 1 + 10 * (1 - prev_fh)

    solver_cmd = pulp.PULP_CBC_CMD(msg=False, gapRel=0.01, timeLimit=20)
    prob.solve(solver_cmd)

    status_name = pulp.LpStatus.get(prob.status, "Unknown")
    has_solution = any(pulp.value(start_vars[(p["id"], target_gws[0])]) is not None for p in filtered_players)

    if status_name != "Optimal" and not has_solution:
        if prob.status == -1 or status_name == "Infeasible":
            raise ValueError("ไม่สามารถจัดทีมตามเงื่อนไขได้ (Infeasible) กรุณาตรวจสอบว่า Lock นักเตะเกินงบหรือเกินโควตาทีมหรือไม่")
        else:
            raise ValueError(f"Solver หยุดทำงานก่อนพบผลลัพธ์ (สถานะ: {status_name}) กรุณาลด Horizon หรือปรับผ่อนปรนเงื่อนไข")

    # 8. สรุปแผน
    plans = []
    for idx, gw in enumerate(target_gws):
        prev_gw = target_gws[idx - 1] if idx > 0 else None

        active_chip = None
        for c in chip_types:
            if pulp.value(chip_vars[(c, gw)]) == 1:
                active_chip = c
                break

        if active_chip == "FH":
            prev_team_ids = [
                p["id"] for p in filtered_players
                if (p["in_initial_team"] if prev_gw is None else pulp.value(perm_squad_vars[(p["id"], prev_gw)])) == 1
            ]
            active_team_ids = [p["id"] for p in filtered_players if pulp.value(squad_vars[(p["id"], gw)]) == 1]
            tin = [p for p in filtered_players if p["id"] in active_team_ids and p["id"] not in prev_team_ids]
            tout = [p for p in filtered_players if p["id"] in prev_team_ids and p["id"] not in active_team_ids]
        else:
            tin = [p for p in filtered_players if pulp.value(tin_vars[(p["id"], gw)]) == 1]
            tout = [p for p in filtered_players if pulp.value(tout_vars[(p["id"], gw)]) == 1]

        starters = [p for p in filtered_players if pulp.value(start_vars[(p["id"], gw)]) == 1]
        starters.sort(key=lambda x: x["pos_id"])

        bench = [p for p in filtered_players if pulp.value(squad_vars[(p["id"], gw)]) == 1 and pulp.value(start_vars[(p["id"], gw)]) == 0]
        bench_gkp = [p for p in bench if p["pos_id"] == 1]
        bench_outfield = [p for p in bench if p["pos_id"] != 1]
        # จัดลำดับม้านั่งสำรองอัจฉริยะ:
        # ให้ความสำคัญกับความพร้อมลงสนามจริงก่อน (xMins >= 45.0) แล้วเรียงตาม xP สูงสุด
        # เพื่อให้ Bench 1 เป็นตัวที่ลงมาเปลี่ยนทำแต้มแทนตัวจริงได้แน่นอนเมื่อเกิดเหตุฉุกเฉิน
        bench_outfield.sort(
            key=lambda x: (
                1 if x.get("xmins_by_gw", {}).get(gw, x.get("xmins", 0)) >= 45.0 else 0,
                x["xp_by_gw"][gw]
            ),
            reverse=True
        )

        captain = next(p for p in filtered_players if pulp.value(cap_vars[(p["id"], gw)]) == 1)
        vice = next(p for p in filtered_players if pulp.value(vice_vars[(p["id"], gw)]) == 1)

        cap_multiplier = 2 if active_chip == "TC" else 1
        starters_xp = sum(p["xp_by_gw"][gw] for p in starters) + (captain["xp_by_gw"][gw] * cap_multiplier)
        bench_xp = sum(p["xp_by_gw"][gw] for p in (bench_gkp + bench_outfield)) if active_chip == "BB" else 0.0
        hits_deduction = int(pulp.value(hits_vars[gw])) * 4
        gw_total_xp = round(starters_xp + bench_xp - hits_deduction, 2)

        plans.append({
            "gw": gw,
            "chip": active_chip,
            "bank_remaining": round(pulp.value(bank_vars[gw]), 2),
            "transfers_in": tin,
            "transfers_out": tout,
            "hits": int(pulp.value(hits_vars[gw])),
            "ft_available": int(pulp.value(ft_vars[gw])),
            "starters": starters,
            "captain": captain,
            "vice_captain": vice,
            "bench": bench_gkp + bench_outfield,
            "total_xp": gw_total_xp,
        })

    return plans