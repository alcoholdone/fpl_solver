import importlib
import pandas as pd
import streamlit as st

import config
import fpl_api
import optimizer
import ui_components

# ป้องกันปัญหา Stale Cache ใน sys.modules ของ Streamlit Cloud เมื่อมีการ Deploy โค้ดใหม่
if not hasattr(fpl_api, "fetch_fpl_global_market"):
    importlib.reload(fpl_api)
if not hasattr(optimizer, "solve_multi_period_fpl"):
    importlib.reload(optimizer)
if not hasattr(ui_components, "render_top_bar"):
    importlib.reload(ui_components)

from config import MY_TEAM_ID, DEFAULT_LEAGUES, MAX_PLAYERS_PER_TEAM
from fpl_api import (
    fetch_fpl_global_market,
    fetch_fpl_user_squad,
    fetch_minileague_eo,
    FPLGameUpdatingError,
)
from optimizer import solve_multi_period_fpl
from ui_components import (
    inject_custom_css,
    render_sidebar_brand,
    render_sidebar_section,
    render_top_bar,
    render_strategic_roadmap,
    render_transfer_cards,
    render_top_captains,
    render_pitch_view,
    render_chip_advisor,
    render_fixture_ticker,
)

st.set_page_config(
    page_title="FPL Strategist · Transfer & Squad Planner",
    layout="wide",
    page_icon="⚽",
    initial_sidebar_state="auto",
)

inject_custom_css()


# 2-Tier Caching: ข้อมูลตลาดกลางแคช 15 นาทีร่วมกันทุกคน ป้องกัน FPL Rate Limit (429)
@st.cache_data(ttl=900)
def load_global_market(xg_weight: float, cs_weight: float, horizon_weeks: int = 3):
    return fetch_fpl_global_market(
        xg_weight=xg_weight, cs_weight=cs_weight, horizon_weeks=horizon_weeks
    )


# ข้อมูลผู้ใช้แคชสั้น 2 นาทีเพื่อความสดใหม่ ดึงเฉพาะ Picks และชิป
@st.cache_data(ttl=120)
def load_user_squad(team_id: int, _global_market: dict):
    return fetch_fpl_user_squad(team_id, _global_market)


@st.cache_data(ttl=600)
def load_league_data(league_id: int, pick_gw: int):
    return fetch_minileague_eo(league_id, pick_gw)


# =============================================================================
# SIDEBAR & QUERY PARAMS (?team=XXXXXX&league=YYYYYY)
# =============================================================================
query_params = st.query_params

url_team_raw = query_params.get("team")
default_team_val = MY_TEAM_ID
if url_team_raw:
    try:
        parsed_t = int(url_team_raw)
        if parsed_t > 0:
            default_team_val = parsed_t
    except (ValueError, TypeError):
        pass

url_league_raw = query_params.get("league", "")
url_league_ids = []
if url_league_raw:
    for item in str(url_league_raw).split(","):
        item = item.strip()
        if item.isdigit() and int(item) > 0:
            url_league_ids.append(int(item))

render_sidebar_brand()
input_team_id = st.sidebar.number_input(
    "Team ID",
    value=default_team_val if default_team_val > 0 else 0,
    step=1,
    help="ดู Team ID ได้จาก URL หน้า Points บนเว็บ FPL (เช่น /entry/XXXXXX/event/...)",
)

if input_team_id > 0:
    st.query_params["team"] = str(input_team_id)
elif "team" in st.query_params:
    del st.query_params["team"]

if st.sidebar.button("อัปเดตข้อมูลและคำนวณใหม่", width="stretch"):
    st.cache_data.clear()
    st.rerun()

# จองลำดับ Sidebar Containers ตามลำดับการใช้งานจริง
pref_box = st.sidebar.container()
transfer_box = st.sidebar.container()
chip_box = st.sidebar.container()
model_box = st.sidebar.container()

with model_box:
    render_sidebar_section("ตั้งค่าโมเดล")
    with st.expander("ปรับแต่งโมเดล (ขั้นสูง)", expanded=False):
        horizon_slider = st.slider(
            "ระยะวางแผน (Gameweeks)",
            min_value=1,
            max_value=5,
            value=3,
            step=1,
            help="จำนวนสัปดาห์ล่วงหน้าที่นำมาจำลองการย้ายตัวและชิป (1–5 สัปดาห์)",
        )
        xg_slider = st.slider("น้ำหนักเกมรุก (xG & xA)", 0.5, 2.0, 1.10, 0.05)
        cs_slider = st.slider("น้ำหนักเกมรับ (Clean Sheet)", 0.0, 2.0, 0.90, 0.05)

if input_team_id <= 0:
    st.info("กรอก **Team ID** ในแถบด้านซ้าย (บนมือถือแตะปุ่มเมนู `>` มุมซ้ายบน) หรือเปิดลิงก์แบบ `?team=XXXXXX` เพื่อเริ่มวิเคราะห์ทีมของคุณ")
    st.stop()

try:
    with st.spinner("กำลังโหลดข้อมูลตลาดนักเตะและคำนวณ xP..."):
        global_market = load_global_market(xg_slider, cs_slider, horizon_slider)
    with st.spinner(f"กำลังดึงข้อมูลทีม (ID: {input_team_id})..."):
        (
            players,
            my_team_ids,
            bank,
            initial_ft,
            target_gws,
            chips_available,
            deadline_info,
            dgw_bgw_info,
        ) = load_user_squad(input_team_id, global_market)

    my_squad = [p for p in players if p["id"] in my_team_ids]
    squad_value = sum(p["sell_price"] for p in my_squad)

    # เตรียมข้อมูลทีมทั้งหมดสำหรับเลือกชอบ / ไม่ชอบ
    teams_info = global_market.get("teams_info") or {
        p["team_id"]: {"id": p["team_id"], "short_name": p["team"], "name": p["team"]}
        for p in players
    }
    sorted_teams = sorted(teams_info.values(), key=lambda t: t["name"])
    team_options = {f"{t['name']} ({t['short_name']})": t["id"] for t in sorted_teams}
    team_short_map = {t["id"]: t["short_name"] for t in teams_info.values()}

    # 1. ความชอบระดับทีม & รายนักเตะ
    with pref_box:
        render_sidebar_section("ทีมและนักเตะที่ชอบ / ไม่ชอบ")

        selected_liked_teams = st.multiselect(
            "ทีมที่ชอบ (ดึงเข้าทีม)",
            options=list(team_options.keys()),
            default=[],
            help="ระบบจะพยายามดึงนักเตะจากทีมที่เลือกเข้าสู่ทีมให้ครบตามจำนวนขั้นต่ำ (ไม่เกิน 3 คน/ทีมตามกติกา)",
        )
        liked_team_ids = [team_options[k] for k in selected_liked_teams]

        if liked_team_ids:
            min_per_liked_team = st.slider(
                "ขั้นต่ำต่อทีมที่ชอบ (คน)",
                min_value=1,
                max_value=MAX_PLAYERS_PER_TEAM,
                value=1,
                step=1,
            )
        else:
            min_per_liked_team = 1

        available_ban_teams = [k for k in team_options.keys() if k not in selected_liked_teams]
        selected_banned_teams = st.multiselect(
            "ทีมที่ไม่ชอบ (ห้ามดึงเข้า / ขายออก)",
            options=available_ban_teams,
            default=[],
            help="ห้ามซื้อผู้เล่นจากทีมเหล่านี้เด็ดขาด และจะทยอยขายตัวที่มีอยู่ในทีมปัจจุบันออกให้เร็วที่สุด",
        )
        banned_team_ids = [team_options[k] for k in selected_banned_teams]

        with st.expander("เจาะจงรายนักเตะ (Lock / Ban รายคน)", expanded=False):
            sorted_players = sorted(players, key=lambda x: (x["pos_id"], x["team"], -x["buy_price"]))
            player_label_map = {
                p["id"]: f"{p['web_name']} ({p['position']} · {p['team']}) £{p['buy_price']:.1f}M"
                for p in sorted_players
            }
            all_player_ids = [p["id"] for p in sorted_players]

            locked_ids = st.multiselect(
                "บังคับมีในทีม (Lock)",
                options=all_player_ids,
                default=[],
                format_func=lambda pid: player_label_map[pid],
            )

            available_ban_ids = [pid for pid in all_player_ids if pid not in locked_ids]
            banned_ids = st.multiselect(
                "ห้ามมีในทีม (Ban)",
                options=available_ban_ids,
                default=[],
                format_func=lambda pid: player_label_map[pid],
            )

    # 2. โควตาย้ายตัว & แต้มลบ
    with transfer_box:
        render_sidebar_section("งบประมาณ & โควตาย้ายตัว")
        custom_bank = st.number_input(
            "เงินในคลังจริง (£M)",
            min_value=0.0,
            max_value=100.0,
            value=round(float(bank), 1),
            step=0.1,
            format="%.1f",
            help="FPL Public API ไม่ส่งราคาขายหักภาษี 50% ของนักเตะในทีม สามารถปรับยอดเงินจริงในคลังได้ที่นี่",
        )
        custom_ft = st.number_input(
            "Free Transfers ในมือ (1–5)",
            min_value=1,
            max_value=5,
            value=int(initial_ft),
            step=1,
            help="คำนวณสะสมจากประวัติย้ายตัวตามกติกา 2024/25+ (ปรับแก้ได้หากต้องการจำลอง)",
        )

        hit_policies = {
            "ไม่ยอมเสียแต้มลบ (0 Hits)": 0,
            "ยอมเสียได้ไม่เกิน 1 ครั้ง (-4 pts)": 1,
            "ยอมเสียได้ไม่เกิน 2 ครั้ง (-8 pts)": 2,
            "ให้โมเดลคำนวณความคุ้มเอง (Auto ≥ 6.5 xP)": None,
        }
        selected_hit_label = st.selectbox(
            "นโยบายแต้มลบ (Hits Policy)",
            options=list(hit_policies.keys()),
            index=0,
        )
        max_hits_allowed = hit_policies[selected_hit_label]

    # 3. กลยุทธ์ชิป
    next_gw = target_gws[0]
    with chip_box:
        render_sidebar_section("กลยุทธ์ชิป (Chips)")
        if next_gw < 20:
            wc_weeks_left = 20 - next_gw
            st.caption(f"Wildcard 1 หมดอายุสิ้นสุด GW 19 (เหลืออีก {wc_weeks_left} สัปดาห์)")
        else:
            st.caption("Wildcard 2 ใช้งานได้ถึงจบฤดูกาล (GW 38)")

        chip_action = st.radio(
            "รูปแบบการใช้ชิป",
            [
                "Smart Auto (ใช้เมื่อคุ้มจริง)",
                "บังคับเปิดใช้ใน GW นี้",
                "ปิดการใช้ชิปทั้งหมด",
            ],
            index=0,
        )

        forced_chip = None
        allowed_chips_list = []

        if chip_action == "Smart Auto (ใช้เมื่อคุ้มจริง)":
            has_bgw = any(len(info.get("bgw", [])) >= 2 for info in dgw_bgw_info.values()) if dgw_bgw_info else False
            has_dgw = any(len(info.get("dgw", [])) >= 1 for info in dgw_bgw_info.values()) if dgw_bgw_info else False

            auto_allowed = []
            if has_dgw:
                auto_allowed.extend(["TC", "BB"])
            if has_bgw:
                auto_allowed.append("FH")
            if 16 <= next_gw < 20:
                auto_allowed.append("WC")

            allowed_chips_list = [c for c in auto_allowed if chips_available.get(c, False)]
            if allowed_chips_list:
                st.caption(f"ชิปที่เปิดให้พิจารณาอัตโนมัติ: {', '.join(allowed_chips_list)}")
            else:
                st.caption("สัปดาห์ปกติ: เก็บชิปไว้ใช้ช่วง Double / Blank GW")

        elif chip_action == "บังคับเปิดใช้ใน GW นี้":
            chip_labels = {
                "WC": "Wildcard (WC) — จัดใหม่ทั้ง 15 คน",
                "TC": "Triple Captain (TC) — กัปตัน x3",
                "BB": "Bench Boost (BB) — นับแต้มสำรองทั้ง 4 คน",
                "FH": "Free Hit (FH) — จัดทีมชั่วคราว 1 สัปดาห์",
            }
            avail_options = [label for c, label in chip_labels.items() if chips_available.get(c, False)]
            if not avail_options:
                st.error("ไม่มีชิปเหลือให้ใช้งานในครึ่งฤดูกาลนี้")
            else:
                selected_chip_label = st.selectbox("เลือกชิปที่ต้องการใช้:", options=avail_options)
                for c, label in chip_labels.items():
                    if label == selected_chip_label:
                        forced_chip = c
                        allowed_chips_list = [c]
                        st.success(f"จำลองเปิดใช้ {c} ใน GW {next_gw}")
                        break
        else:
            st.caption("ปิดการใช้ชิปทุกชนิด")

    # แก้สมการหาแผนที่ดีที่สุดก่อนแสดงผล Top Bar & Tabs
    with st.spinner("กำลังคำนวณแผนการจัดทีมและย้ายตัวที่ดีที่สุด..."):
        try:
            plans = solve_multi_period_fpl(
                players,
                my_team_ids,
                custom_bank,
                custom_ft,
                target_gws,
                chips_available,
                enable_chips=True,
                locked_player_ids=locked_ids,
                banned_player_ids=banned_ids,
                dgw_bgw_info=dgw_bgw_info,
                max_hits_per_gw=max_hits_allowed,
                allowed_chips=allowed_chips_list,
                forced_chip=forced_chip,
                liked_team_ids=liked_team_ids,
                banned_team_ids=banned_team_ids,
                min_per_liked_team=min_per_liked_team,
            )
        except ValueError as solve_err:
            st.error(f"ไม่สามารถจัดทีมตามเงื่อนไขที่เลือกได้: {solve_err}")
            st.stop()

    # TOP SUMMARY BAR
    render_top_bar(
        deadline_info=deadline_info,
        bank=custom_bank,
        squad_value=squad_value,
        custom_ft=custom_ft,
        gw1_xp=plans[0]["total_xp"],
        next_gw=next_gw,
    )

    # DGW / BGW Alerts (แสดงเฉพาะเมื่อมีจริง)
    alert_messages = []
    for gw, info in dgw_bgw_info.items():
        if info["dgw"]:
            alert_messages.append(f"**GW {gw} Double Gameweek:** {', '.join(info['dgw'])}")
        if info["bgw"]:
            alert_messages.append(f"**GW {gw} Blank Gameweek:** {', '.join(info['bgw'])}")

    if alert_messages:
        with st.expander("แจ้งเตือนโปรแกรมพิเศษ (DGW / BGW)", expanded=True):
            for msg in alert_messages:
                st.markdown(f"- {msg}")

    # TABS
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "แผนรายสัปดาห์",
        "จำลองซื้อ-ขาย",
        "ราคาตลาด",
        "ขุมกำลังปัจจุบัน",
        "วิเคราะห์มินิลีก (EO)",
        "ตารางโปรแกรม (FDR)",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: ROADMAP & SOLVER
    # -------------------------------------------------------------------------
    with tab1:
        pref_parts = []
        if liked_team_ids:
            liked_names = ", ".join(team_short_map.get(tid, str(tid)) for tid in liked_team_ids)
            pref_parts.append(f"ทีมที่ชอบ: {liked_names} (ขั้นต่ำ {min_per_liked_team} คน/ทีม)")
        if banned_team_ids:
            banned_names = ", ".join(team_short_map.get(tid, str(tid)) for tid in banned_team_ids)
            pref_parts.append(f"ทีมที่ไม่ชอบ: {banned_names}")
        if locked_ids:
            pref_parts.append(f"Lock รายคน: {len(locked_ids)} คน")
        if banned_ids:
            pref_parts.append(f"Ban รายคน: {len(banned_ids)} คน")

        if pref_parts:
            st.info("เงื่อนไขที่ใช้งาน: " + " | ".join(pref_parts))

        # แจ้งเตือนหากมีนักเตะที่แบนอยู่ในทีมเดิมแต่ยังขายออกไม่หมดใน GW1 เพราะติดเพดาน FT/Hits
        gw1_ids = {p["id"] for p in plans[0]["starters"] + plans[0]["bench"]}
        effective_banned_ids = (
            set(banned_ids)
            | {p["id"] for p in my_squad if p["team_id"] in set(banned_team_ids)}
        ) - set(locked_ids)
        still_banned_gw1 = [p for p in my_squad if p["id"] in effective_banned_ids and p["id"] in gw1_ids]
        if still_banned_gw1:
            phase_notes = []
            for p in still_banned_gw1:
                sold_gw = next(
                    (
                        pl["gw"]
                        for pl in plans[1:]
                        if p["id"] not in {x["id"] for x in pl["starters"] + pl["bench"]}
                    ),
                    None,
                )
                if sold_gw:
                    phase_notes.append(f"{p['web_name']} ({p['team']}) → ขายออกใน GW {sold_gw}")
                else:
                    phase_notes.append(f"{p['web_name']} ({p['team']}) → รอโควตา FT ถัดไป")
            st.warning(
                "ยังมีนักเตะจากกลุ่มที่ไม่ชอบค้างอยู่ใน GW แรกเนื่องจากจำกัดจำนวนย้ายฟรี/แต้มลบ: "
                + ", ".join(phase_notes)
                + " (หากต้องการขายทันที ให้ปรับนโยบายแต้มลบหรือใช้ Wildcard)"
            )

        if liked_team_ids:
            gw1_squad = plans[0]["starters"] + plans[0]["bench"]
            unmet_liked = []
            for tid in liked_team_ids:
                cnt = sum(1 for p in gw1_squad if p["team_id"] == tid)
                if cnt < min_per_liked_team:
                    unmet_liked.append(f"{team_short_map.get(tid, tid)} ({cnt}/{min_per_liked_team} คน)")
            if unmet_liked:
                st.caption(
                    "หมายเหตุทีมที่ชอบใน GW แรก: "
                    + ", ".join(unmet_liked)
                    + " — ระบบจะทยอยดึงเข้าเพิ่มในสัปดาห์ถัดไปตามโควตา FT และงบประมาณ"
                )

        render_strategic_roadmap(plans)
        render_chip_advisor(plans, my_squad, dgw_bgw_info, custom_bank, custom_ft, next_gw)

        view_mode = st.radio(
            "มุมมองแผนผังทีม",
            ["ผังสนาม (Pitch View)", "ตารางสถิติ (Table View)"],
            horizontal=True,
        )

        gw_tab_labels = [
            f"GW {plan['gw']}" + (f" · {plan['chip']}" if plan["chip"] else "")
            for plan in plans
        ]
        gw_tabs = st.tabs(gw_tab_labels)

        for idx, plan in enumerate(plans):
            gw = plan["gw"]
            with gw_tabs[idx]:
                st.caption(
                    f"Free Transfers: **{plan['ft_available']}** · เงินคงคลังหลังจบสัปดาห์: **£{plan['bank_remaining']:.1f}M** · คาดการณ์: **{plan['total_xp']:.1f} xP**"
                )

                render_transfer_cards(plan)
                render_top_captains(plan)

                if view_mode == "ผังสนาม (Pitch View)":
                    render_pitch_view(plan, locked_ids, liked_team_ids)
                else:
                    st.markdown("**11 ตัวจริง**")
                    starters_data = []
                    for p in plan["starters"]:
                        role = ""
                        if p["id"] == plan["captain"]["id"]:
                            role = " (TC)" if plan["chip"] == "TC" else " (C)"
                        elif p["id"] == plan["vice_captain"]["id"]:
                            role = " (VC)"
                        tags = []
                        if p["id"] in locked_ids:
                            tags.append("LOCK")
                        if p.get("team_id") in liked_team_ids:
                            tags.append("FAV")
                        if p.get("is_dgw", {}).get(gw, False):
                            tags.append("2x")
                        tag_str = f" [{' '.join(tags)}]" if tags else ""

                        starters_data.append({
                            "ตำแหน่ง": p["position"],
                            "นักเตะ": f"{p['web_name']}{role}{tag_str}",
                            "ทีม": p["team"],
                            "คู่แข่ง": p["fixtures"].get(gw, "-"),
                            "xMins": f"{p.get('xmins_by_gw', {}).get(gw, p['xmins'])} น.",
                            "ความเสี่ยง": p.get("risk_by_gw", {}).get(gw, p["risk"]),
                            "xP": p["xp_by_gw"][gw],
                        })
                    st.dataframe(pd.DataFrame(starters_data), hide_index=True, width="stretch")

                    if plan["chip"] != "BB" and plan["bench"]:
                        st.markdown("**ตัวสำรอง**")
                        bench_labels = ["GK Sub", "Bench 1", "Bench 2", "Bench 3"]
                        bench_data = []
                        for label, p in zip(bench_labels, plan["bench"]):
                            dgw_str = " [2x]" if p.get("is_dgw", {}).get(gw, False) else ""
                            bench_data.append({
                                "ลำดับ": label,
                                "นักเตะ": f"{p['web_name']}{dgw_str}",
                                "ทีม": p["team"],
                                "คู่แข่ง": p["fixtures"].get(gw, "-"),
                                "xMins": f"{p.get('xmins_by_gw', {}).get(gw, p['xmins'])} น.",
                                "ความเสี่ยง": p.get("risk_by_gw", {}).get(gw, p["risk"]),
                                "xP": p["xp_by_gw"][gw],
                            })
                        st.dataframe(pd.DataFrame(bench_data), hide_index=True, width="stretch")

    # -------------------------------------------------------------------------
    # TAB 2: TRANSFER CALCULATOR
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("จำลองการเปลี่ยนตัวแบบ 1 ต่อ 1")
        available_market = [
            p for p in players
            if p["id"] not in my_team_ids and p.get("status") != "u"
        ]
        available_market.sort(
            key=lambda x: (sum(x["xp_by_gw"].values()), x["buy_price"]),
            reverse=True,
        )

        option_labels = [
            f"{p['web_name']} ({p['position']} · {p['team']}) — £{p['buy_price']:.1f}M | {sum(p['xp_by_gw'].values()):.1f} xP"
            for p in available_market
        ]
        target_idx = st.selectbox(
            "เลือกนักเตะเป้าหมายที่สนใจดึงเข้า:",
            options=list(range(len(available_market))),
            format_func=lambda i: option_labels[i],
        )
        target_p = available_market[target_idx]

        target_horizon_xp = round(sum(target_p["xp_by_gw"].get(g, 0.0) for g in target_gws), 2)

        p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
        p_col1.metric("ราคาซื้อ", f"£{target_p['buy_price']:.1f}M")
        p_col2.metric("xMins / นัด", f"{target_p['xmins']} น.")
        p_col3.metric("ความเสี่ยง", target_p["risk"])
        p_col4.metric(f"คู่แข่ง GW {next_gw}", target_p["fixtures"].get(next_gw, "-"))
        p_col5.metric(f"xP รวม {len(target_gws)} นัด", f"{target_horizon_xp:.1f}")

        squad_same_pos = [p for p in my_squad if p["position"] == target_p["position"]]
        squad_same_pos.sort(key=lambda x: (sum(x["xp_by_gw"].values()), x["form"]))

        team_counts = {}
        for sp in my_squad:
            team_counts[sp["team_id"]] = team_counts.get(sp["team_id"], 0) + 1

        st.markdown(f"#### เปรียบเทียบกับนักเตะตำแหน่ง **{target_p['position']}** ในทีมคุณ")

        swap_candidates = []
        for p in squad_same_pos:
            remaining_bank = custom_bank + p["sell_price"] - target_p["buy_price"]
            is_affordable = remaining_bank >= -1e-9

            new_club_count = team_counts.get(target_p["team_id"], 0) - (
                1 if p["team_id"] == target_p["team_id"] else 0
            ) + 1
            club_limit_ok = new_club_count <= MAX_PLAYERS_PER_TEAM

            xp_diff_next = target_p["xp_by_gw"].get(next_gw, 0.0) - p["xp_by_gw"].get(next_gw, 0.0)
            p_horizon_xp = sum(p["xp_by_gw"].get(g, 0.0) for g in target_gws)
            xp_diff_horizon = target_horizon_xp - p_horizon_xp

            if not club_limit_ok:
                status_str = f"เกินโควตา {MAX_PLAYERS_PER_TEAM} คน/{target_p['team']}"
            elif not is_affordable:
                status_str = "งบไม่พอ"
            else:
                status_str = "พร้อมย้าย"

            swap_candidates.append({
                "ขายออก": p["web_name"],
                "ทีม": p["team"],
                "xMins": f"{p['xmins']} น.",
                "ราคาขาย": f"£{p['sell_price']:.1f}M",
                f"GW {next_gw}": p["fixtures"].get(next_gw, "-"),
                f"ส่วนต่าง GW {next_gw}": f"{xp_diff_next:+.2f}",
                f"ส่วนต่าง {len(target_gws)} นัด": f"{xp_diff_horizon:+.2f}",
                "เงินเหลือ": f"£{remaining_bank:.1f}M",
                "สถานะ": status_str,
            })

        st.dataframe(pd.DataFrame(swap_candidates), width="stretch", hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 3: MARKET PRICE TRACKER
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("แนวโน้มราคาตลาด (Daily Price Tracker)")
        my_squad_fall_risk = [p for p in my_squad if p["price_trend"]["progress_pct"] <= -50.0]
        solver_target_rise_risk = [p for p in plans[0]["transfers_in"] if p["price_trend"]["progress_pct"] >= 50.0]

        warn_col1, warn_col2 = st.columns(2)
        with warn_col1:
            if my_squad_fall_risk:
                st.error("นักเตะในทีมที่เสี่ยงราคาตกเร็วๆ นี้:")
                for p in my_squad_fall_risk:
                    st.write(f"- **{p['web_name']}** ({p['team']}) — Net: `{p['price_trend']['net_transfers']:,}` ({p['price_trend']['status']})")
            else:
                st.success("ผู้เล่นในทีมปัจจุบันยังไม่มีใครเสี่ยงราคาตกในระยะใกล้")

        with warn_col2:
            if solver_target_rise_risk:
                st.warning("เป้าหมายในแผน GW นี้ที่มีแนวโน้มราคาขึ้น:")
                for p in solver_target_rise_risk:
                    st.write(f"- **{p['web_name']}** ({p['team']}) — Net: `+{p['price_trend']['net_transfers']:,}` ({p['price_trend']['status']})")
            else:
                st.info("นักเตะเป้าหมายที่แนะนำซื้อในสัปดาห์นี้ราคายังคงที่")

        st.markdown("---")
        col_risers, col_fallers = st.columns(2)

        with col_risers:
            st.markdown("#### Top 10 แนวโน้มราคาขึ้น (Risers)")
            risers = sorted(players, key=lambda x: x["price_trend"]["net_transfers"], reverse=True)[:10]
            riser_data = [{
                "นักเตะ": p["web_name"],
                "ทีม": p["team"],
                "ตำแหน่ง": p["position"],
                "ราคา": f"£{p['buy_price']:.1f}M",
                "Net Transfers": f"+{p['price_trend']['net_transfers']:,}",
                "ถือครอง": f"{p['price_trend']['ownership_pct']}%",
                "สถานะ": p["price_trend"]["status"],
            } for p in risers]
            st.dataframe(pd.DataFrame(riser_data), hide_index=True, width="stretch")

        with col_fallers:
            st.markdown("#### Top 10 แนวโน้มราคาตก (Fallers)")
            fallers = sorted(players, key=lambda x: x["price_trend"]["net_transfers"])[:10]
            faller_data = [{
                "นักเตะ": p["web_name"],
                "ทีม": p["team"],
                "ตำแหน่ง": p["position"],
                "ราคา": f"£{p['buy_price']:.1f}M",
                "Net Transfers": f"{p['price_trend']['net_transfers']:,}",
                "ถือครอง": f"{p['price_trend']['ownership_pct']}%",
                "สถานะ": p["price_trend"]["status"],
            } for p in fallers]
            st.dataframe(pd.DataFrame(faller_data), hide_index=True, width="stretch")

    # -------------------------------------------------------------------------
    # TAB 4: CURRENT SQUAD OVERVIEW
    # -------------------------------------------------------------------------
    with tab4:
        st.subheader("ขุมกำลัง 15 คนปัจจุบันและโปรแกรมล่วงหน้า")
        sorted_squad = sorted(my_squad, key=lambda p: (p["pos_id"], -p["buy_price"]))
        overview_list = []
        for p in sorted_squad:
            total_horizon_xp = round(sum(p["xp_by_gw"].get(gw, 0.0) for gw in target_gws), 2)
            row = {
                "ตำแหน่ง": p["position"],
                "ชื่อ": p["web_name"],
                "ทีม": p["team"],
                "ราคาขาย": f"£{p['sell_price']:.1f}M",
                "xMins": f"{p['xmins']} น.",
                "ความเสี่ยง": p["risk"],
                "ข่าว/สถานะ": p.get("news") or "-",
                "สถานะราคา": p["price_trend"]["status"],
                "ฟอร์ม": p["form"],
                f"xP รวม ({len(target_gws)} นัด)": total_horizon_xp,
            }
            for gw in target_gws:
                row[f"GW {gw}"] = p["fixtures"].get(gw, "-")
                row[f"GW {gw} xP"] = p["xp_by_gw"].get(gw, 0.0)
            overview_list.append(row)

        st.dataframe(pd.DataFrame(overview_list), width="stretch", hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 5: MINI-LEAGUE & EO ANALYSIS
    # -------------------------------------------------------------------------
    with tab5:
        st.subheader("วิเคราะห์คู่แข่งใน Mini-League และ Effective Ownership (EO)")

        league_options = {}
        if url_league_ids:
            for idx, lid in enumerate(url_league_ids, 1):
                league_options[f"มินิลีกจาก URL #{idx} (ID: {lid})"] = lid

        for name, lid in DEFAULT_LEAGUES.items():
            if lid > 0 and lid not in url_league_ids:
                league_options[name] = lid

        league_options["กรอก League ID เอง"] = 0

        sel_col1, sel_col2 = st.columns([2, 1])
        with sel_col1:
            selected_league_label = st.selectbox(
                "เลือก Mini-League ที่ต้องการวิเคราะห์",
                options=list(league_options.keys()),
                index=0,
            )

        active_league_id = league_options[selected_league_label]
        if active_league_id == 0:
            with sel_col2:
                active_league_id = st.number_input("ระบุ League ID", value=0, step=1)

        if active_league_id > 0:
            if url_league_ids and active_league_id not in url_league_ids:
                combined = [str(active_league_id)] + [str(x) for x in url_league_ids]
                st.query_params["league"] = ",".join(combined)
            elif not url_league_ids:
                st.query_params["league"] = str(active_league_id)

        if active_league_id <= 0:
            st.info("กรุณาระบุ Mini-League ID ที่ถูกต้องเพื่อเริ่มวิเคราะห์คู่แข่ง")
        else:
            pick_gw = max(1, target_gws[0] - 1)
            with st.spinner(f"กำลังดึงข้อมูลไลน์อัปคู่แข่งจาก League ID {active_league_id}..."):
                league_data = load_league_data(active_league_id, pick_gw)

            if not league_data:
                st.error(
                    f"ไม่สามารถดึงข้อมูล League ID {active_league_id} ได้ (อาจเป็นลีกที่ยังไม่มีข้อมูลคะแนน หรือ ID ไม่ถูกต้อง)"
                )
            else:
                st.success(
                    f"วิเคราะห์: **{league_data['league_name']}** (จากคู่แข่งอันดับต้น {league_data['total_analyzed']} ทีม)"
                )

                eo_map = league_data["eo_dict"]
                players_dict = {p["id"]: p for p in players}

                planned_starter_ids = {p["id"] for p in plans[0]["starters"]}
                planned_squad_ids = {p["id"] for p in plans[0]["starters"] + plans[0]["bench"]}

                shield_threats = []
                my_differentials = []

                for pid, stat in eo_map.items():
                    p_info = players_dict.get(pid)
                    if not p_info:
                        continue

                    if stat["eo_pct"] >= 60.0 and pid not in planned_starter_ids:
                        shield_threats.append({
                            "นักเตะ": p_info["web_name"],
                            "ทีม": p_info["team"],
                            "ตำแหน่ง": p_info["position"],
                            "League EO": f"{stat['eo_pct']}%",
                            "คนเลือก (C)": f"{stat['captain_pct']}%",
                            "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0),
                        })

                    if stat["eo_pct"] <= 35.0 and pid in planned_starter_ids:
                        my_differentials.append({
                            "นักเตะ": p_info["web_name"],
                            "ทีม": p_info["team"],
                            "ตำแหน่ง": p_info["position"],
                            "League EO": f"{stat['eo_pct']}%",
                            "คนในลีกถือ": f"{stat['ownership_pct']}%",
                            "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0),
                        })

                col_eo1, col_eo2 = st.columns(2)
                with col_eo1:
                    st.markdown("#### ความเสี่ยง EO สูง (Threats)")
                    st.caption("ผู้เล่นที่คู่แข่งถือหรือตั้งกัปตันสูง แต่ไม่อยู่ใน 11 ตัวจริงตามแผน")
                    if shield_threats:
                        st.dataframe(pd.DataFrame(shield_threats), hide_index=True, width="stretch")
                    else:
                        st.success("ครอบคลุมตัวหลักของลีกนี้ครบแล้ว ไม่มีจุดเสี่ยง EO สูง")

                with col_eo2:
                    st.markdown("#### ตัวทำแต้มฉีกอันดับ (Differentials)")
                    st.caption("11 ตัวจริงตามแผนของคุณที่คู่แข่งในลีกถือน้อย")
                    if my_differentials:
                        st.dataframe(pd.DataFrame(my_differentials), hide_index=True, width="stretch")
                    else:
                        st.info("ตัวจริงส่วนใหญ่สอดคล้องกับค่าเฉลี่ยของลีก")

                st.markdown("---")
                st.markdown(f"#### สถิติ Effective Ownership ทั้งหมดใน {league_data['league_name']}")
                all_eo_list = []
                for pid, stat in sorted(eo_map.items(), key=lambda x: x[1]["eo_pct"], reverse=True):
                    p_info = players_dict.get(pid)
                    if not p_info:
                        continue

                    if pid in planned_starter_ids:
                        status_in_plan = "ตัวจริง (ตามแผน)"
                    elif pid in planned_squad_ids:
                        status_in_plan = "สำรอง (ตามแผน)"
                    else:
                        status_in_plan = "ไม่มีในทีม"

                    all_eo_list.append({
                        "นักเตะ": p_info["web_name"],
                        "ทีม": p_info["team"],
                        "ตำแหน่ง": p_info["position"],
                        "สถานะในแผน": status_in_plan,
                        "EO": f"{stat['eo_pct']}%",
                        "Ownership": f"{stat['ownership_pct']}%",
                        "Captain %": f"{stat['captain_pct']}%",
                        "ราคา": f"£{p_info['buy_price']:.1f}M",
                        "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0),
                    })

                st.dataframe(pd.DataFrame(all_eo_list), hide_index=True, width="stretch")

    # -------------------------------------------------------------------------
    # TAB 6: FIXTURE DIFFICULTY TICKER
    # -------------------------------------------------------------------------
    with tab6:
        st.subheader(f"ตารางความยากโปรแกรมล่วงหน้า (GW {target_gws[0]}–{target_gws[-1]})")
        st.caption("เรียงจากทีมที่โปรแกรมง่ายสุดไปยากสุด เพื่อช่วยตัดสินใจเลือกทีมที่ชอบ / ไม่ชอบใน Sidebar")
        render_fixture_ticker(teams_info, global_market.get("fixture_details", {}), target_gws)

except FPLGameUpdatingError as e:
    st.warning(
        f"**ระบบ FPL ปิดปรับปรุงชั่วคราวระหว่างแข่งขัน (Game Updating)**\n\n{e}\n\n"
        "*กรุณารอสักครู่แล้วกดคำนวณใหม่เมื่อระบบประมวลผลคะแนนเสร็จสิ้น*"
    )
except ValueError as e:
    st.error(f"{e}\n\n*กรุณาตรวจสอบว่ากรอก FPL Team ID ถูกต้อง*")
except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการคำนวณ: {e}")
