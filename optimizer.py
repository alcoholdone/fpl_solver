import pulp
from config import (
    HORIZON_WEEKS, DISCOUNT_FACTOR, MAX_FREE_TRANSFERS,
    HIT_PENALTY_COST, MAX_PLAYERS_PER_TEAM, TOTAL_SQUAD_SIZE, STARTING_XI_SIZE
)

def filter_candidate_pool(players: list, my_player_ids: list, locked_player_ids: list = None) -> list:
    locked_set = set(locked_player_ids or [])
    active_pool = []

    for p in players:
        if p["id"] in my_player_ids or p["id"] in locked_set:
            active_pool.append(p)
            continue

        total_xp = sum(p["xp_by_gw"].values())
        is_viable_scorer = (total_xp >= 2.5 and p["xmins"] >= 20.0)
        is_budget_enabler = (p["buy_price"] <= 4.5 and p["xmins"] >= 45.0)

        if is_viable_scorer or is_budget_enabler:
            active_pool.append(p)

    return active_pool

def solve_multi_period_fpl(
    players, my_player_ids, bank, initial_ft, target_gws, chips_available: dict,
    enable_chips: bool = True, locked_player_ids: list = None, banned_player_ids: list = None,
    dgw_bgw_info: dict = None
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

    # 2. ตัวแปร Chips
    chip_types = [c for c, avail in chips_available.items() if avail and enable_chips]
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

        gw_points = pulp.lpSum([
            start_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
            + cap_vars[(p["id"], gw)] * p["xp_by_gw"][gw]
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

        gw_net_points = gw_points - (HIT_PENALTY_COST * hits_vars[gw]) - chip_penalties
        objective_terms.append(discount * gw_net_points)

    prob += pulp.lpSum(objective_terms)

    # 6. Constraints ของ Chips
    if chip_types:
        for c in chip_types:
            prob += pulp.lpSum([chip_vars[(c, gw)] for gw in target_gws]) <= 1
        for gw in target_gws:
            prob += pulp.lpSum([chip_vars[(c, gw)] for c in chip_types]) <= 1

    if "TC" in chip_types:
        for gw in target_gws:
            dgw_list = dgw_bgw_info.get(gw, {}).get("dgw", []) if dgw_bgw_info else []
            has_dgw = len(dgw_list) > 0

            for p in filtered_players:
                pid = p["id"]
                prob += tc_active[(pid, gw)] <= cap_vars[(pid, gw)]
                prob += tc_active[(pid, gw)] <= chip_vars[("TC", gw)]
                prob += tc_active[(pid, gw)] >= cap_vars[(pid, gw)] + chip_vars[("TC", gw)] - 1

                # DGW Captain Lockout: หากสัปดาห์นั้นมี DGW บังคับว่า TC ต้องติดให้นักเตะที่เตะเบิ้ลเท่านั้น
                if has_dgw and not p.get("is_dgw", {}).get(gw, False):
                    prob += tc_active[(pid, gw)] == 0

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

        prob += pulp.lpSum([squad_vars[(p["id"], gw)] * p["buy_price"] for p in filtered_players]) <= total_budget_cap

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

        prob += rem_ft_vars[gw] <= ft_vars[gw] - total_in + (20 * has_hits_vars[gw])
        prob += rem_ft_vars[gw] <= MAX_FREE_TRANSFERS * (1 - has_hits_vars[gw])
        prob += rem_ft_vars[gw] <= MAX_FREE_TRANSFERS * (1 - is_wc)

        if prev_gw is not None:
            prev_fh = chip_vars[("FH", prev_gw)] if "FH" in chip_types else 0
            prob += ft_vars[gw] <= rem_ft_vars[prev_gw] + 1 + (10 * prev_fh)
            prob += ft_vars[gw] <= 1 + 10 * (1 - prev_fh)

    solver_cmd = pulp.PULP_CBC_CMD(msg=False, gapRel=0.005, timeLimit=12)
    prob.solve(solver_cmd)

    if pulp.LpStatus[prob.status] != "Optimal":
        raise ValueError("ไม่สามารถจัดทีมตามเงื่อนไขได้ (Infeasible) กรุณาตรวจสอบว่า Lock นักเตะเกินงบหรือเกินโควตาทีมหรือไม่")

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
        bench_outfield.sort(key=lambda x: x["xp_by_gw"][gw], reverse=True)

        captain = next(p for p in filtered_players if pulp.value(cap_vars[(p["id"], gw)]) == 1)
        vice = next(p for p in filtered_players if pulp.value(vice_vars[(p["id"], gw)]) == 1)

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
        })

    return plans