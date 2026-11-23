import math
import unittest
from unittest.mock import MagicMock, patch

import fpl_api
from fpl_api import (
    calculate_accumulated_ft,
    calculate_match_factors,
    calculate_player_custom_xp,
    calculate_xmins,
    fetch_minileague_eo,
    fetch_user_chips_status,
)
from optimizer import solve_multi_period_fpl


def _make_player(
    pid: int,
    pos_id: int,
    team_id: int,
    price: float,
    xp: float,
    in_team: int = 0,
    xmins: float = 90.0,
    status: str = "a",
    gws=(10, 11, 12),
):
    pos_names = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    return {
        "id": pid,
        "web_name": f"P{pid}",
        "full_name": f"Player {pid}",
        "team": f"T{team_id}",
        "team_id": team_id,
        "position": pos_names[pos_id],
        "pos_id": pos_id,
        "buy_price": price,
        "sell_price": price,
        "status": status,
        "news": "",
        "selected_by_percent": 10.0,
        "total_points": 50,
        "minutes": 900 if status == "a" else 0,
        "form": round(xp, 1),
        "xmins": xmins,
        "risk": "🟢 LOW (ตัวจริง)" if xmins >= 70 else "🔴 OUT (เจ็บ/แบน)",
        "xmins_by_gw": {gw: xmins for gw in gws},
        "risk_by_gw": {gw: "🟢 LOW (ตัวจริง)" for gw in gws},
        "xp_by_gw": {gw: xp for gw in gws},
        "fixtures": {gw: f"vs T99 (H) [FDR 2]" for gw in gws},
        "is_dgw": {gw: False for gw in gws},
        "is_bgw": {gw: False for gw in gws},
        "price_trend": {
            "net_transfers": 0,
            "transfers_in": 0,
            "transfers_out": 0,
            "ownership_pct": 10.0,
            "progress_pct": 0.0,
            "status": "➖ คงที่",
        },
        "in_initial_team": in_team,
    }


def _build_base_universe(gws=(10, 11, 12)):
    """สร้างชุดนักเตะจำลองที่มีทีม 15 คนในทีมเริ่มต้น (Pos: 2 GKP, 5 DEF, 5 MID, 3 FWD) และตลาดนักเตะครบทุกตำแหน่ง"""
    players = []
    my_ids = []
    pid = 1

    # Squad ปัจจุบัน: ใช้ทีม id 1..8 (ไม่มีทีม 15, 16, 17 เพื่อทดสอบดึงทีมที่ชอบ)
    squad_spec = [
        (1, 1, 4.5, 3.5), (1, 2, 4.5, 3.5),
        (2, 3, 4.5, 4.0), (2, 4, 4.5, 4.0), (2, 5, 4.5, 4.0), (2, 6, 4.5, 4.0), (2, 7, 4.5, 4.0),
        (3, 1, 6.0, 4.5), (3, 2, 6.0, 4.5), (3, 3, 6.0, 4.5), (3, 4, 6.0, 4.5), (3, 5, 6.0, 4.5),
        (4, 6, 7.0, 5.0), (4, 7, 7.0, 5.0), (4, 8, 7.0, 5.0),
    ]
    for pos_id, tid, price, xp in squad_spec:
        players.append(_make_player(pid, pos_id, tid, price, xp, in_team=1, gws=gws))
        my_ids.append(pid)
        pid += 1

    # ตลาดกลาง: ทีม 10..17 มีตัวเก่งทุกตำแหน่ง
    for tid in range(10, 18):
        for pos_id, price, xp in [(1, 4.5, 4.2), (2, 4.5, 4.6), (3, 6.0, 5.2), (4, 7.0, 5.6)]:
            players.append(_make_player(pid, pos_id, tid, price, xp, in_team=0, gws=gws))
            pid += 1

    return players, my_ids


class TestFplRulesAndXp(unittest.TestCase):
    def test_accumulated_ft_2024_rules_wc_and_fh_preserve(self):
        # GW1 baseline -> GW2 (0 transfers -> ft=2), GW3 WC (ft stays 2), GW4 (0 transfers -> ft=3),
        # GW5 FH (ft stays 3), GW6 (1 transfer -> rem=2, next=3), GW7 (5 transfers, 2 hits -> rem=0, next=1)
        history = {
            "current": [
                {"event": 1, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 2, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 3, "event_transfers": 8, "event_transfers_cost": 0},
                {"event": 4, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 5, "event_transfers": 11, "event_transfers_cost": 0},
                {"event": 6, "event_transfers": 1, "event_transfers_cost": 0},
            ],
            "chips": [
                {"event": 3, "name": "wildcard"},
                {"event": 5, "name": "freehit"},
            ],
        }
        self.assertEqual(calculate_accumulated_ft(history), 3)

        # ทดสอบกรณีใช้ Hits จนเกลี้ยงแล้ว
        history_hits = {
            "current": history["current"] + [
                {"event": 7, "event_transfers": 5, "event_transfers_cost": 8},
            ],
            "chips": history["chips"],
        }
        self.assertEqual(calculate_accumulated_ft(history_hits), 1)

        # ทดสอบ Cap สูงสุดที่ 5
        history_cap = {
            "current": [{"event": i, "event_transfers": 0, "event_transfers_cost": 0} for i in range(1, 10)],
            "chips": [],
        }
        self.assertEqual(calculate_accumulated_ft(history_cap), 5)

    def test_wildcard_availability_by_half_season_event(self):
        # ไม่ได้ใช้ WC1 แต่ใช้ WC2 ไปแล้วที่ GW 25 -> GW 28 ต้อง WC: False
        hist_wc2_only = {"chips": [{"event": 25, "name": "wildcard"}]}
        self.assertFalse(fetch_user_chips_status(1, 28, hist_wc2_only)["WC"])
        self.assertTrue(fetch_user_chips_status(1, 15, hist_wc2_only)["WC"])

        # ใช้ WC1 ที่ GW 12 -> GW 16 ต้อง False แต่ GW 20 ต้อง True
        hist_wc1_only = {"chips": [{"event": 12, "name": "wildcard"}]}
        self.assertFalse(fetch_user_chips_status(1, 16, hist_wc1_only)["WC"])
        self.assertTrue(fetch_user_chips_status(1, 20, hist_wc1_only)["WC"])

    def test_match_factors_poisson_and_zero_division_safe(self):
        teams = {
            1: {"att_home": 1350, "def_home": 1350, "att_away": 1250, "def_away": 1250},
            2: {"att_home": 900, "def_home": 900, "att_away": 850, "def_away": 850},
            3: {"att_home": 0, "def_home": 0, "att_away": 0, "def_away": 0},
        }
        att, cs, exp_gc = calculate_match_factors(1, 2, True, teams)
        self.assertTrue(0.55 <= att <= 1.75)
        self.assertTrue(0.04 <= cs <= 0.68)
        self.assertAlmostEqual(cs, round(max(0.04, min(0.68, math.exp(-exp_gc))), 2))

        # ทีมที่ข้อมูลเป็น 0 หรือไม่มีข้อมูลต้องไม่ crash
        att0, cs0, gc0 = calculate_match_factors(3, 999, False, teams)
        self.assertGreater(att0, 0)
        self.assertGreater(cs0, 0)
        self.assertGreater(gc0, 0)

    def test_poisson_gc_penalty_and_bps_and_cards_and_benched_premium(self):
        base_def = {
            "element_type": 2,
            "minutes": 1800,
            "starts": 20,
            "now_cost": 55,
            "status": "a",
            "expected_goals_per_90": 0.1,
            "expected_assists_per_90": 0.1,
            "goals_scored": 2,
            "form": "4.0",
            "points_per_game": "4.0",
            "bps": 450,
            "yellow_cards": 1,
            "red_cards": 0,
        }
        low_bps_card_def = dict(base_def, bps=100, yellow_cards=10)
        xp_good = calculate_player_custom_xp(base_def, 90.0, 1.0, 0.37, 1.0)
        xp_bad = calculate_player_custom_xp(low_bps_card_def, 90.0, 1.0, 0.37, 1.0)
        self.assertGreater(xp_good, xp_bad)

        # ผู้เล่นราคาแพง (>=8.0M) ที่ฟิตแต่โดนดร็อปถาวรไม่ควรได้ 85 นาทีอัตโนมัติ
        benched_star = {
            "element_type": 3,
            "status": "a",
            "chance_of_playing_next_round": None,
            "now_cost": 85,
            "minutes": 20,
            "starts": 0,
            "form": "0.5",
        }
        xmins, _ = calculate_xmins(benched_star, team_played=10, gw_offset=0)
        self.assertLess(xmins, 40.0)

        # ทดสอบ Poisson GC penalty ที่ xGC=1.0 (ควรโดนหักประมาณ -0.285 น้อยกว่า linear -0.50)
        base_mid = dict(base_def, element_type=3)
        xp_def = calculate_player_custom_xp(base_def, 90.0, 1.0, 0.37, 1.0)
        xp_mid = calculate_player_custom_xp(base_mid, 90.0, 1.0, 0.37, 1.0)
        # DEF ได้ CS 4 pts vs MID 1 pt (+3*0.37=1.11) หัก Poisson GC (~-0.285) และส่วนต่าง Goal (6 vs 5) + BPS
        self.assertGreater(xp_def, xp_mid)

    def test_tough_fixture_dampens_hot_streak_underdog_captain(self):
        teams = {
            1: {"att_home": 1360, "def_home": 1350, "att_away": 1340, "def_away": 1330},  # ทีมลุ้นแชมป์ (เช่น LIV)
            2: {"att_home": 1020, "def_home": 1000, "att_away": 990, "def_away": 980},   # ทีมกลาง-ล่าง (เช่น EVE)
        }
        # ตัวรุกทีมรองเล่นในบ้านเจอแนวรับแกร่ง (แม้ฟอร์มกำลังฮอต)
        att_underdog, cs_u, gc_u = calculate_match_factors(2, 1, True, teams)
        # ตัวรุกทีมใหญ่เล่นเกมเยือนเจอแนวรับทีมรอง
        att_fav, cs_f, gc_f = calculate_match_factors(1, 2, False, teams)

        hot_underdog_fwd = {
            "element_type": 4,
            "minutes": 900,
            "starts": 10,
            "now_cost": 65,
            "status": "a",
            "expected_goals_per_90": 0.50,
            "expected_assists_per_90": 0.10,
            "goals_scored": 5,
            "form": "7.5",
            "points_per_game": "4.0",
            "bps": 220,
            "yellow_cards": 1,
            "red_cards": 0,
        }
        elite_fav_fwd = {
            "element_type": 4,
            "minutes": 900,
            "starts": 10,
            "now_cost": 105,
            "status": "a",
            "expected_goals_per_90": 0.58,
            "expected_assists_per_90": 0.22,
            "goals_scored": 6,
            "form": "6.5",
            "points_per_game": "6.0",
            "bps": 260,
            "yellow_cards": 1,
            "red_cards": 0,
        }

        xp_underdog = calculate_player_custom_xp(hot_underdog_fwd, 85.0, att_underdog, cs_u, gc_u)
        xp_fav = calculate_player_custom_xp(elite_fav_fwd, 85.0, att_fav, cs_f, gc_f)
        self.assertGreater(xp_fav, xp_underdog)


class TestOptimizerPreferencesAndRealism(unittest.TestCase):
    def test_liked_team_pulls_player_and_never_infeasible(self):
        players, my_ids = _build_base_universe()
        chips = {"TC": False, "BB": False, "WC": False, "FH": False}

        # ขอทีมที่ชอบ 3 ทีม (15, 16, 17) แม้มีแค่ 1 FT และห้ามติดลบ (max_hits_per_gw=0) ก็ต้องไม่ Infeasible
        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=2.0,
            initial_ft=1,
            target_gws=[10, 11, 12],
            chips_available=chips,
            enable_chips=False,
            max_hits_per_gw=0,
            liked_team_ids=[15, 16, 17],
            min_per_liked_team=1,
        )
        self.assertEqual(len(plans), 3)
        final_squad = plans[-1]["starters"] + plans[-1]["bench"]
        final_teams = {p["team_id"] for p in final_squad}
        # ตลอด 3 สัปดาห์ มีอย่างน้อย 3 FT ต้องดึงครบทั้ง 3 ทีมที่ชอบได้
        self.assertTrue({15, 16, 17}.issubset(final_teams))

    def test_banned_team_never_bought_and_owned_phased_out(self):
        players, my_ids = _build_base_universe()
        chips = {"TC": False, "BB": False, "WC": False, "FH": False}

        # ทีม 6 มีอยู่ใน squad เดิม 2 คน (DEF id=6 และ FWD id=14), ทีม 12 ไม่อยู่ใน squad แต่แต้มสูงกว่า
        for p in players:
            if p["team_id"] == 12:
                for gw in p["xp_by_gw"]:
                    p["xp_by_gw"][gw] = 9.0  # จูงใจมากแต่ถูกแบน

        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=2.0,
            initial_ft=1,
            target_gws=[10, 11, 12],
            chips_available=chips,
            enable_chips=False,
            max_hits_per_gw=0,
            banned_team_ids=[6, 12],
        )
        # ทีม 12 ต้องไม่ถูกซื้อเข้ามาเลยสักสัปดาห์
        for pl in plans:
            sq = pl["starters"] + pl["bench"]
            self.assertFalse(any(p["team_id"] == 12 for p in sq))

        # ทีม 6 ทั้ง 2 คนในทีมเดิมต้องถูกขายออกหมดภายใน horizon
        last_sq = plans[-1]["starters"] + plans[-1]["bench"]
        self.assertFalse(any(p["team_id"] == 6 for p in last_sq))

    def test_owned_unavailable_player_does_not_crash_and_sells(self):
        players, my_ids = _build_base_universe()
        # ทำให้ FWD id=15 ในทีมเดิมเป็น status='u', xmins=0, xp=0
        for p in players:
            if p["id"] == 15:
                p["status"] = "u"
                p["xmins"] = 0.0
                for gw in p["xp_by_gw"]:
                    p["xp_by_gw"][gw] = 0.0
                    p["xmins_by_gw"][gw] = 0.0

        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=1.0,
            initial_ft=1,
            target_gws=[10, 11, 12],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
            enable_chips=False,
            max_hits_per_gw=0,
        )
        gw1_out_ids = {p["id"] for p in plans[0]["transfers_out"]}
        self.assertIn(15, gw1_out_ids)

    def test_ft_roll_value_avoids_tiny_upgrade(self):
        players, my_ids = _build_base_universe(gws=(10, 11))
        # ทำให้ตลาดดีกว่าทีมเดิมแค่ +0.2 xP ต่อสัปดาห์ (2 สัปดาห์ = +0.4 xP < FT_ROLL_VALUE 1.5)
        for p in players:
            if p["in_initial_team"] == 0:
                base_xp = 3.7 if p["pos_id"] == 1 else (4.2 if p["pos_id"] == 2 else (4.7 if p["pos_id"] == 3 else 5.2))
                for gw in p["xp_by_gw"]:
                    p["xp_by_gw"][gw] = base_xp

        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=1.0,
            initial_ft=1,
            target_gws=[10, 11],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
            enable_chips=False,
            max_hits_per_gw=0,
        )
        self.assertEqual(len(plans[0]["transfers_in"]), 0)

    def test_bb_chip_and_wc_ft_preservation(self):
        players, my_ids = _build_base_universe(gws=(10, 11, 12))
        # ทดสอบ BB
        bb_plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=2.0,
            initial_ft=2,
            target_gws=[10, 11, 12],
            chips_available={"TC": False, "BB": True, "WC": False, "FH": False},
            enable_chips=True,
            allowed_chips=["BB"],
            forced_chip="BB",
            max_hits_per_gw=0,
        )
        self.assertEqual(bb_plans[0]["chip"], "BB")
        self.assertEqual(len(bb_plans[0]["starters"]), 15)
        self.assertEqual(len(bb_plans[0]["bench"]), 0)

        # ทดสอบ WC คงจำนวน FT (initial_ft=3 -> ใช้ WC ใน GW10 -> GW11 ต้องมี ft_available == 3 ไม่รีเซ็ตและไม่บวกเป็น 4)
        wc_plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=2.0,
            initial_ft=3,
            target_gws=[10, 11, 12],
            chips_available={"TC": False, "BB": False, "WC": True, "FH": False},
            enable_chips=True,
            allowed_chips=["WC"],
            forced_chip="WC",
            max_hits_per_gw=0,
        )
        self.assertEqual(wc_plans[0]["chip"], "WC")
        self.assertEqual(wc_plans[1]["ft_available"], 3)

    def test_player_lock_and_ban_combined_with_team_preferences(self):
        players, my_ids = _build_base_universe(gws=(10, 11, 12))
        # Lock ผู้เล่น id=20 (team 11, DEF) และ Ban ผู้เล่น id=19 (team 11, GKP) พร้อมชอบทีม 15
        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=5.0,
            initial_ft=2,
            target_gws=[10, 11, 12],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
            enable_chips=False,
            locked_player_ids=[20],
            banned_player_ids=[19],
            liked_team_ids=[15],
            banned_team_ids=[12],
            max_hits_per_gw=0,
        )
        gw1_ids = {p["id"] for p in plans[0]["starters"] + plans[0]["bench"]}
        self.assertIn(20, gw1_ids)
        self.assertNotIn(19, gw1_ids)
        self.assertFalse(any(p["team_id"] == 12 for p in plans[0]["starters"] + plans[0]["bench"]))
        self.assertTrue(any(p["team_id"] == 15 for p in plans[-1]["starters"] + plans[-1]["bench"]))

    def test_captain_vs_own_def_conflict_prefers_non_conflicting_starter(self):
        players, my_ids = _build_base_universe(gws=(10,))
        for p in players:
            if p["in_initial_team"] == 0:
                p["xp_by_gw"][10] = 1.0  # ไม่ต้องย้ายตัวเพื่อโฟกัสการจัด 11 ตัวจริง
            if p["id"] == 15:
                # กัปตัน (team 8) เจอ team 3
                p["xp_by_gw"][10] = 12.0
                p["opponents_by_gw"] = {10: [3]}
            elif p["id"] == 3:
                # DEF ของ team 3 มี xP สูงกว่า DEF คนอื่น 0.2 (น้อยกว่า penalty 0.6)
                p["xp_by_gw"][10] = 4.2
                p["opponents_by_gw"] = {10: [8]}
            elif p["pos_id"] == 2 and p["in_initial_team"] == 1:
                p["xp_by_gw"][10] = 4.0
                p["opponents_by_gw"] = {10: [99]}
            else:
                p["opponents_by_gw"] = {10: [99]}

        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=0.0,
            initial_ft=1,
            target_gws=[10],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
            enable_chips=False,
            max_hits_per_gw=0,
        )
        self.assertEqual(plans[0]["captain"]["id"], 15)
        starter_ids = {p["id"] for p in plans[0]["starters"]}
        bench_ids = {p["id"] for p in plans[0]["bench"]}
        self.assertNotIn(3, starter_ids)
        self.assertIn(3, bench_ids)

    def test_infeasible_lock_raises_instead_of_illegal_squad(self):
        players, my_ids = _build_base_universe(gws=(10, 11))
        # กรณี A: Lock นักเตะทีมเดียวกัน (team 10) 4 คน ต้อง raise ValueError ทันที
        team10_ids = [p["id"] for p in players if p["team_id"] == 10]
        self.assertEqual(len(team10_ids), 4)
        with self.assertRaises(ValueError):
            solve_multi_period_fpl(
                players,
                my_ids,
                bank=20.0,
                initial_ft=5,
                target_gws=[10, 11],
                chips_available={"TC": False, "BB": False, "WC": True, "FH": False},
                enable_chips=True,
                locked_player_ids=team10_ids,
                max_hits_per_gw=0,
            )

        # กรณี B: Lock นักเตะใหม่ 2 คน (team 11) แต่ตั้ง 0 Hits และมีแค่ 1 FT ใน GW แรก -> Infeasible ต้อง raise ValueError
        new_t11_ids = [p["id"] for p in players if p["team_id"] == 11][:2]
        with self.assertRaises(ValueError):
            solve_multi_period_fpl(
                players,
                my_ids,
                bank=10.0,
                initial_ft=1,
                target_gws=[10, 11],
                chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
                enable_chips=False,
                locked_player_ids=new_t11_ids,
                max_hits_per_gw=0,
            )

    def test_all_plans_never_exceed_three_per_team(self):
        players, my_ids = _build_base_universe(gws=(10, 11, 12))
        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=5.0,
            initial_ft=2,
            target_gws=[10, 11, 12],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": False},
            enable_chips=False,
            liked_team_ids=[15],
            min_per_liked_team=3,
            max_hits_per_gw=1,
        )
        for pl in plans:
            counts = {}
            for p in pl["starters"] + pl["bench"]:
                counts[p["team_id"]] = counts.get(p["team_id"], 0) + 1
            self.assertLessEqual(max(counts.values()), 3)

    def test_free_hit_bank_remaining_reflects_fh_budget(self):
        players, my_ids = _build_base_universe(gws=(10, 11))
        bank = 5.0
        current_team_value = sum(p["sell_price"] for p in players if p["id"] in my_ids)
        total_budget_cap = bank + current_team_value

        plans = solve_multi_period_fpl(
            players,
            my_ids,
            bank=bank,
            initial_ft=1,
            target_gws=[10, 11],
            chips_available={"TC": False, "BB": False, "WC": False, "FH": True},
            enable_chips=True,
            allowed_chips=["FH"],
            forced_chip="FH",
            max_hits_per_gw=0,
        )
        self.assertEqual(plans[0]["chip"], "FH")
        fh_squad = plans[0]["starters"] + plans[0]["bench"]
        fh_cost = sum(p["buy_price"] for p in fh_squad)
        expected_bank = round(max(0.0, total_budget_cap - fh_cost), 2)
        self.assertAlmostEqual(plans[0]["bank_remaining"], expected_bank, places=2)

    def test_minileague_eo_ignores_failed_manager_in_denominator(self):
        standings_payload = {
            "league": {"name": "Test League"},
            "standings": {
                "results": [{"entry": 101}, {"entry": 102}, {"entry": 103}],
            },
        }
        picks_payload = {
            "picks": [
                {"element": 10, "multiplier": 2, "is_captain": True},
                {"element": 20, "multiplier": 1, "is_captain": False},
            ]
        }

        def fake_fpl_get(url, params=None, timeout=10):
            resp = MagicMock()
            if "leagues-classic" in url:
                resp.json.return_value = standings_payload
            elif "/entry/102/" in url:
                raise RuntimeError("timeout")
            else:
                resp.json.return_value = picks_payload
            return resp

        with patch.object(fpl_api, "fpl_get", side_effect=fake_fpl_get):
            res = fetch_minileague_eo(999, pick_gw=9, max_managers=10)

        self.assertIsNotNone(res)
        # 1 จาก 3 ทีมดึงไม่สำเร็จ -> total_analyzed ต้องเป็น 2 และ % ของ element 20 ที่ทุกคนถือต้องเป็น 100.0% (ไม่ใช่ 66.7%)
        self.assertEqual(res["total_analyzed"], 2)
        self.assertEqual(res["eo_dict"][20]["eo_pct"], 100.0)
        self.assertEqual(res["eo_dict"][10]["eo_pct"], 200.0)
        self.assertEqual(res["eo_dict"][10]["captain_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
