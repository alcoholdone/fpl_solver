import streamlit as st
import pandas as pd
import textwrap
from datetime import datetime, timezone, timedelta
from config import MY_TEAM_ID, DEFAULT_LEAGUES
from fpl_api import fetch_fpl_data_multi, fetch_minileague_eo
from optimizer import solve_multi_period_fpl

st.set_page_config(
    page_title="FPL Strategist & Transfer Planner",
    layout="wide",
    page_icon="⚽"
)

@st.cache_data(ttl=300)
def load_data(team_id: int, xg_weight: float, cs_weight: float):
    return fetch_fpl_data_multi(team_id, xg_weight=xg_weight, cs_weight=cs_weight)

@st.cache_data(ttl=600)
def load_league_data(league_id: int, pick_gw: int):
    return fetch_minileague_eo(league_id, pick_gw)

# =============================================================================
# PITCH VIEW & CARD GENERATOR
# =============================================================================
def generate_player_card_html(p: dict, gw: int, captain_id: int, vice_id: int, chip: str, locked_ids: list) -> str:
    """การ์ดนักเตะแบบ Compact รองรับหน้าจอมือถือ"""
    badge_html = ""
    if p["id"] == captain_id:
        if chip == "TC":
            badge_html = (
                '<div style="position: absolute; top: -6px; right: -5px; background: #ea580c; color: #fff; '
                'font-weight: 900; font-size: 7.5px; padding: 1px 3px; border-radius: 6px; '
                'border: 1px solid #fff; z-index: 2;">TC</div>'
            )
        else:
            badge_html = (
                '<div style="position: absolute; top: -6px; right: -5px; background: #f59e0b; color: #000; '
                'font-weight: 900; font-size: 8px; width: 15px; height: 15px; border-radius: 50%; '
                'display: flex; align-items: center; justify-content: center; '
                'border: 1px solid #fff; z-index: 2;">C</div>'
            )
    elif p["id"] == vice_id:
        badge_html = (
            '<div style="position: absolute; top: -6px; right: -5px; background: #475569; color: #fff; '
            'font-weight: 800; font-size: 7.5px; padding: 1px 3px; border-radius: 6px; '
            'border: 1px solid #fff; z-index: 2;">VC</div>'
        )

    lock_html = ""
    if locked_ids and p["id"] in locked_ids:
        lock_html = (
            '<div style="position: absolute; top: -6px; left: -4px; background: #1e293b; color: #fff; '
            'font-size: 7.5px; width: 14px; height: 14px; border-radius: 50%; display: flex; '
            'align-items: center; justify-content: center; border: 1px solid #fff; z-index: 2;">🔒</div>'
        )

    dgw_badge = ""
    if p.get("is_dgw", {}).get(gw, False):
        dgw_badge = '<span style="background: #065f46; color: #6ee7b7; font-size: 8px; font-weight: 800; padding: 0 2px; border-radius: 2px; margin-left: 2px;">2x</span>'

    fix = p["fixtures"].get(gw, "-")
    xp = p["xp_by_gw"].get(gw, 0.0)

    pos_colors = {1: "#eab308", 2: "#3b82f6", 3: "#10b981", 4: "#ef4444"}
    border_color = pos_colors.get(p["pos_id"], "#64748b")

    card = (
        f'<div style="position: relative; background: #ffffff; color: #0f172a; border-radius: 6px; '
        f'padding: 4px 2px 3px 2px; min-width: 58px; max-width: 72px; flex: 1; text-align: center; '
        f'box-shadow: 0 2px 4px rgba(0,0,0,0.25); border-top: 3px solid {border_color}; '
        f'font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; box-sizing: border-box; margin: 2px 1px;">'
        f'{badge_html}'
        f'{lock_html}'
        f'<div style="font-weight: 800; font-size: 9.5px; white-space: nowrap; overflow: hidden; '
        f'text-overflow: ellipsis; padding: 0 1px; color: #0f172a;" title="{p["web_name"]}">'
        f'{p["web_name"]}{dgw_badge}'
        f'</div>'
        f'<div style="font-size: 8px; color: #64748b; margin: 1px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{fix}">'
        f'{p["team"]}'
        f'</div>'
        f'<div style="background: #0f172a; color: #38bdf8; font-weight: 700; font-size: 9px; border-radius: 2px; padding: 1px 0;">'
        f'{xp:.1f}'
        f'</div>'
        f'</div>'
    )
    return card

def render_pitch_view(plan: dict, locked_ids: list = None):
    gw = plan["gw"]
    chip = plan["chip"]
    cap_id = plan["captain"]["id"]
    vice_id = plan["vice_captain"]["id"]
    starters = plan["starters"]
    bench = plan["bench"]

    gkps = [p for p in starters if p["pos_id"] == 1]
    defs = [p for p in starters if p["pos_id"] == 2]
    mids = [p for p in starters if p["pos_id"] == 3]
    fwds = [p for p in starters if p["pos_id"] == 4]

    formation_str = f"{len(defs)}-{len(mids)}-{len(fwds)}"

    def make_row(players):
        cards = "".join([generate_player_card_html(p, gw, cap_id, vice_id, chip, locked_ids) for p in players])
        return f'<div style="display: flex; justify-content: center; align-items: center; gap: 2px; margin: 4px 0; width: 100%;">{cards}</div>'

    pitch_html = textwrap.dedent(f"""
<div style="background: radial-gradient(circle, #1e5e2e 0%, #14401f 100%); border: 1.5px solid rgba(255,255,255,0.25); border-radius: 10px; padding: 10px 4px 8px 4px; position: relative; box-shadow: inset 0 0 14px rgba(0,0,0,0.5); margin-bottom: 8px; width: 100%; box-sizing: border-box; overflow-x: auto;">
<div style="position: absolute; top: 50%; left: 3%; right: 3%; height: 1px; background: rgba(255,255,255,0.15);"></div>
<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 46px; height: 46px; border: 1px solid rgba(255,255,255,0.15); border-radius: 50%;"></div>
{make_row(gkps)}
{make_row(defs)}
{make_row(mids)}
{make_row(fwds)}
</div>
""").strip()

    bench_cards = "".join([
        f'<div style="display: flex; flex-direction: column; align-items: center; min-width: 58px; max-width: 72px; flex: 1;">'
        f'<span style="color: #94a3b8; font-size: 8.5px; font-weight: 600; margin-bottom: 1px;">{label}</span>'
        f'{generate_player_card_html(p, gw, cap_id, vice_id, chip, locked_ids)}'
        f'</div>'
        for label, p in zip(["GK Sub", "Bench 1", "Bench 2", "Bench 3"], bench)
    ])

    bench_html = textwrap.dedent(f"""
<div style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 6px 2px 4px 2px; display: flex; justify-content: center; gap: 2px; width: 100%; box-sizing: border-box; overflow-x: auto;">
{bench_cards}
</div>
""").strip()

    st.caption(f"📐 แผนการเล่น: **{formation_str}**")
    st.markdown(pitch_html, unsafe_allow_html=True)

    if chip == "BB":
        st.info("🎉 **Bench Boost Active:** แต้มจากสำรองทุกคนถูกนับรวมในคะแนนจริง")
    else:
        st.markdown("**🪑 ม้านั่งสำรอง:**")
        st.markdown(bench_html, unsafe_allow_html=True)

def render_deadline_banner(deadline_utc_str: str, gw_name: str):
    if not deadline_utc_str:
        return
    utc_time = datetime.fromisoformat(deadline_utc_str.replace("Z", "+00:00"))
    bkk_time = utc_time.astimezone(timezone(timedelta(hours=7)))
    now_bkk = datetime.now(timezone(timedelta(hours=7)))
    diff = bkk_time - now_bkk
    time_str = bkk_time.strftime("%Aที่ %d %b %Y เวลา %H:%M น.")

    if diff.total_seconds() > 0:
        days = diff.days
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        alert_style = "background-color: #2e1065;" if days >= 1 else "background-color: #7f1d1d;"
        st.markdown(
            f"""
            <div style="{alert_style} border-radius: 10px; padding: 12px 20px; margin-bottom: 15px; color: white;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                    <div>
                        <span style="font-size: 1.05rem; font-weight: bold;">⏳ เส้นตายส่งทีม {gw_name}:</span>
                        <span style="font-size: 0.95rem; margin-left: 8px;">{time_str}</span>
                    </div>
                    <div style="font-size: 1.1rem; font-weight: bold; background: rgba(255,255,255,0.15); padding: 3px 10px; border-radius: 6px;">
                        เหลือเวลาอีก: {days} วัน {hours} ชม. {minutes} นาที
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.warning(f"⚠️ เส้นตาย {gw_name} ผ่านพ้นไปแล้ว")

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.title("⚙️ FPL Settings")
input_team_id = st.sidebar.number_input(
    "กรอก Team ID ของคุณ:",
    value=MY_TEAM_ID if MY_TEAM_ID > 0 else 0,
    step=1,
    help="ดู Team ID ได้จาก URL บนเว็บ FPL ในหน้า Points (เช่น /entry/XXXXXX/event/...)"
)
# input_league_id = st.sidebar.number_input("Mini-League ID (ถ้าต้องการดู EO):", value=0, step=1, help="กรอก Classic League ID จากหน้าเว็บ FPL")

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 ปรับแต่งโมเดล")

enable_chips = st.sidebar.checkbox("🤖 อนุญาตให้บอตแนะนำการใช้ชิป", value=True)
xg_slider = st.sidebar.slider("⚡ น้ำหนักเกมรุก (xG & xA):", 0.5, 2.0, 1.15, 0.05)
cs_slider = st.sidebar.slider("🛡️ น้ำหนักเกมรับ (Clean Sheet):", 0.0, 2.0, 0.85, 0.05)

if st.sidebar.button("🔄 ดึงข้อมูลและคำนวณใหม่"):
    st.cache_data.clear()
    st.rerun()

if input_team_id <= 0:
    st.info("👈 กรุณากรอก **Team ID** ของคุณในแถบด้านซ้ายเพื่อเริ่มการวิเคราะห์")
    st.stop()

try:
    players, my_team_ids, bank, initial_ft, target_gws, chips_available, deadline_info, dgw_bgw_info = load_data(
        input_team_id, xg_slider, cs_slider
    )
    my_squad = [p for p in players if p["id"] in my_team_ids]
    squad_value = sum(p["sell_price"] for p in my_squad)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔒 กฎควบคุม (Lock & Ban)")

    player_options = {
        f"{p['web_name']} ({p['position']} - {p['team']}) £{p['buy_price']:.1f}M": p["id"]
        for p in sorted(players, key=lambda x: (x['pos_id'], x['team'], -x['buy_price']))
    }

    selected_locks = st.sidebar.multiselect("🔒 บังคับมีในทีม (Lock):", options=list(player_options.keys()), default=[])
    locked_ids = [player_options[k] for k in selected_locks]

    available_ban_options = [k for k in player_options.keys() if k not in selected_locks]
    selected_bans = st.sidebar.multiselect("🚫 ห้ามมีในทีม (Ban):", options=available_ban_options, default=[])
    banned_ids = [player_options[k] for k in selected_bans]

    st.sidebar.markdown("---")
    st.sidebar.metric("💰 เงินในธนาคาร (Bank)", f"£{bank:.1f}M")
    st.sidebar.metric("🛡️ มูลค่าทีม (Squad Value)", f"£{squad_value:.1f}M")
    st.sidebar.metric("🔄 Free Transfers", f"{initial_ft}")

    # HEADER & DGW/BGW ALERTS
    render_deadline_banner(deadline_info["deadline_utc"], deadline_info["name"])

    alert_messages = []
    for gw, info in dgw_bgw_info.items():
        if info["dgw"]:
            alert_messages.append(f"🔥 **GW {gw} Double Gameweek:** ทีมที่เตะ 2 นัด ได้แก่ **{', '.join(info['dgw'])}**")
        if info["bgw"]:
            alert_messages.append(f"⚠️ **GW {gw} Blank Gameweek:** ทีมที่ไม่มีแข่ง ได้แก่ **{', '.join(info['bgw'])}**")

    if alert_messages:
        with st.expander("📢 **การแจ้งเตือนสัปดาห์พิเศษ (DGW / BGW Alerts)**", expanded=True):
            for msg in alert_messages:
                st.markdown(msg)

    # TABS
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🚀 แผนกลยุทธ์อัตโนมัติ (Roadmap)",
        "🧮 คำนวณการซื้อ-ขาย (Transfer Calc)",
        "📈 แนวโน้มราคาตลาด (Price Tracker)",
        "📋 ขุมกำลังปัจจุบัน (Squad Overview)",
        "🏆 คู่แข่งและ EO ในมินิลีก (Mini-League)"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: ROADMAP & SOLVER (Responsive Single-GW Tabs)
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("🤖 คำแนะนำจากสมองกล MILP Solver")
        if locked_ids or banned_ids:
            st.info(f"📌 มีผลบังคับ: Lock {len(locked_ids)} คน | Ban {len(banned_ids)} คน")

        view_mode = st.radio(
            "รูปแบบการแสดงผล:",
            ["⚽ ผังสนาม (Pitch View)", "📋 ตารางสถิติ (Table View)"],
            horizontal=True
        )

        with st.spinner("กำลังแก้สมการหาส่วนผสมที่ดีที่สุด..."):
            plans = solve_multi_period_fpl(
                players, my_team_ids, bank, initial_ft, target_gws, chips_available,
                enable_chips=enable_chips, locked_player_ids=locked_ids, banned_player_ids=banned_ids,
                dgw_bgw_info=dgw_bgw_info
            )

        # สลับเป็น Sub-Tabs แทน st.columns เพื่อให้แสดงผลเต็มหน้าจอมือถือ
        gw_tab_labels = [
            f"📍 GW {plan['gw']}" + (f" 🔥 {plan['chip']}" if plan['chip'] else "")
            for plan in plans
        ]
        gw_tabs = st.tabs(gw_tab_labels)

        for idx, plan in enumerate(plans):
            gw = plan["gw"]
            with gw_tabs[idx]:
                st.caption(
                    f"Free Transfers: **{plan['ft_available']}** | เงินคงคลัง: **£{plan['bank_remaining']:.1f}M**")

                # การย้ายตัว
                st.markdown("**🔄 แผนการย้ายตัว:**")
                if plan["chip"] == "FH":
                    st.warning("⚡ **Free Hit Active:** ย้ายชั่วคราวสัปดาห์นี้เท่านั้น")

                if not plan["transfers_in"]:
                    st.info("Roll Transfer (ไม่ย้ายตัว)")
                else:
                    for out_p in plan["transfers_out"]:
                        st.error(
                            f"🔴 {'สลับออก' if plan['chip'] == 'FH' else 'ขาย'}: **{out_p['web_name']}** ({out_p['team']})")
                    for in_p in plan["transfers_in"]:
                        st.success(
                            f"🟢 {'ดึงเข้า' if plan['chip'] == 'FH' else 'ซื้อ'}: **{in_p['web_name']}** ({in_p['team']})")
                    if plan["hits"] > 0:
                        st.warning(f"⚠️ เสียแต้มลบ: -{plan['hits'] * 4} pts")

                # แสดงผลตามโหมด
                if view_mode == "⚽ ผังสนาม (Pitch View)":
                    render_pitch_view(plan, locked_ids)
                else:
                    st.markdown("**⚽ 11 ตัวจริง:**")
                    starters_data = []
                    for p in plan["starters"]:
                        role = ""
                        if p["id"] == plan["captain"]["id"]:
                            role = " (TC)" if plan["chip"] == "TC" else " (C)"
                        elif p["id"] == plan["vice_captain"]["id"]:
                            role = " (VC)"
                        lock_badge = " 🔒" if p["id"] in locked_ids else ""
                        dgw_str = " (2x)" if p.get("is_dgw", {}).get(gw, False) else ""
                        starters_data.append({
                            "ตำแหน่ง": p["position"],
                            "นักเตะ": f"{p['web_name']}{role}{lock_badge}{dgw_str}",
                            "ทีม": p["team"],
                            "คู่แข่ง": p["fixtures"].get(gw, "-"),
                            "xMins": f"{p['xmins']} น.",
                            "ความเสี่ยง": p["risk"],
                            "xP": p["xp_by_gw"][gw]
                        })
                    st.dataframe(pd.DataFrame(starters_data), hide_index=True, width='stretch')

                    if plan["chip"] == "BB":
                        st.info("🎉 เปิดใช้ Bench Boost แต้มสำรองทุกคนถูกนับรวม")
                    else:
                        st.markdown("**🪑 ลำดับตัวสำรอง:**")
                        bench_labels = ["GK Sub", "Bench 1", "Bench 2", "Bench 3"]
                        bench_data = []
                        for label, p in zip(bench_labels, plan["bench"]):
                            lock_badge = " 🔒" if p["id"] in locked_ids else ""
                            dgw_str = " (2x)" if p.get("is_dgw", {}).get(gw, False) else ""
                            bench_data.append({
                                "ลำดับ": label,
                                "นักเตะ": f"{p['web_name']}{lock_badge}{dgw_str}",
                                "คู่แข่ง": p["fixtures"].get(gw, "-"),
                                "xMins": f"{p['xmins']} น.",
                                "ความเสี่ยง": p["risk"],
                                "xP": p["xp_by_gw"][gw]
                            })
                        st.dataframe(pd.DataFrame(bench_data), hide_index=True, width='stretch')

    # -------------------------------------------------------------------------
    # TAB 2: TRANSFER CALCULATOR
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("💡 เครื่องมือจำลองการซื้อตัว")
        next_gw = target_gws[0]
        available_market = [p for p in players if p["id"] not in my_team_ids]
        available_market.sort(key=lambda x: x["buy_price"], reverse=True)

        target_player_name = st.selectbox(
            "🔎 เลือกนักเตะที่สนใจซื้อเข้าทีม:",
            options=[f"{p['web_name']} ({p['position']} - {p['team']}) - £{p['buy_price']}M" for p in available_market]
        )

        selected_idx = [
            f"{p['web_name']} ({p['position']} - {p['team']}) - £{p['buy_price']}M" for p in available_market
        ].index(target_player_name)
        target_p = available_market[selected_idx]

        p_col1, p_col2, p_col3, p_col4, p_col5 = st.columns(5)
        p_col1.metric("ราคาซื้อ", f"£{target_p['buy_price']}M")
        p_col2.metric("xMins / นัด", f"{target_p['xmins']} น.")
        p_col3.metric("ความเสี่ยง", target_p["risk"])
        p_col4.metric(f"นัดถัดไป (GW {next_gw})", target_p["fixtures"].get(next_gw, "-"))
        p_col5.metric(f"xP นัดถัดไป", target_p["xp_by_gw"][next_gw])

        squad_same_pos = [p for p in my_squad if p["position"] == target_p["position"]]
        squad_same_pos.sort(key=lambda x: (x["xp_by_gw"][next_gw], x["form"]))

        st.markdown(f"#### 📊 วิเคราะห์นักเตะตำแหน่ง **{target_p['position']}** ในทีมคุณที่ควรพิจารณาขาย:")

        swap_candidates = []
        for p in squad_same_pos:
            remaining_bank = bank + p["sell_price"] - target_p["buy_price"]
            is_affordable = remaining_bank >= 0
            xp_gain = target_p["xp_by_gw"][next_gw] - p["xp_by_gw"][next_gw]

            swap_candidates.append({
                "แนะนำขาย": p["web_name"],
                "ทีม": p["team"],
                "xMins ปัจจุบัน": f"{p['xmins']} น.",
                "ความเสี่ยง": p["risk"],
                "ราคาขายได้": f"£{p['sell_price']:.1f}M",
                "โปรแกรมนัดถัดไป": p["fixtures"].get(next_gw, "-"),
                "xP ปัจจุบัน": p["xp_by_gw"][next_gw],
                "ส่วนต่าง xP": f"{xp_gain:+.2f}",
                "เงินคงเหลือหลังย้าย": f"£{remaining_bank:.1f}M",
                "สถานะการเงิน": "✅ เงินพอซื้อ" if is_affordable else "❌ เงินไม่พอ"
            })

        st.dataframe(pd.DataFrame(swap_candidates), width='stretch', hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 3: MARKET PRICE TRACKER
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("📈 แนวโน้มราคาตลาดและการย้ายตัวสุทธิ (Daily Price Tracker)")
        my_squad_fall_risk = [p for p in my_squad if p["price_trend"]["progress_pct"] <= -50.0]
        solver_target_rise_risk = [p for p in plans[0]["transfers_in"] if p["price_trend"]["progress_pct"] >= 50.0]

        warn_col1, warn_col2 = st.columns(2)
        with warn_col1:
            if my_squad_fall_risk:
                st.error("🚨 **นักเตะในทีมของคุณที่เสี่ยงราคาตกเร็วๆ นี้:**")
                for p in my_squad_fall_risk:
                    st.write(f"- **{p['web_name']}** ({p['team']}) — Net: `{p['price_trend']['net_transfers']:,}` ({p['price_trend']['status']})")
            else:
                st.success("✅ **นักเตะในทีมคุณทุกคนปลอดภัย:** ไม่มีใครเสี่ยงราคาตกในระยะประชิด")

        with warn_col2:
            if solver_target_rise_risk:
                st.warning("⚡ **เป้าหมายที่บอตแนะนำซื้อ กำลังจะราคาขึ้น:**")
                for p in solver_target_rise_risk:
                    st.write(f"- **{p['web_name']}** ({p['team']}) — Net: `+{p['price_trend']['net_transfers']:,}` ({p['price_trend']['status']}) ควรรีบซื้อก่อนราคาขึ้น")
            else:
                st.info("ℹ️ นักเตะเป้าหมายที่แนะนำซื้อในสัปดาห์นี้ราคายังคงที่")

        st.markdown("---")
        col_risers, col_fallers = st.columns(2)

        with col_risers:
            st.markdown("#### 🔥 Top 10 นักเตะที่มีแนวโน้มราคาขึ้นสูงสุด (Risers)")
            risers = sorted(players, key=lambda x: x["price_trend"]["net_transfers"], reverse=True)[:10]
            riser_data = [{
                "นักเตะ": p["web_name"], "ทีม": p["team"], "ตำแหน่ง": p["position"],
                "ราคาปัจจุบัน": f"£{p['buy_price']:.1f}M", "Net Transfers": f"+{p['price_trend']['net_transfers']:,}",
                "ถือครอง": f"{p['price_trend']['ownership_pct']}%", "สถานะ": p["price_trend"]["status"]
            } for p in risers]
            st.dataframe(pd.DataFrame(riser_data), hide_index=True, width='stretch')

        with col_fallers:
            st.markdown("#### ❄️ Top 10 นักเตะที่มีแนวโน้มราคาตกสูงสุด (Fallers)")
            fallers = sorted(players, key=lambda x: x["price_trend"]["net_transfers"])[:10]
            faller_data = [{
                "นักเตะ": p["web_name"], "ทีม": p["team"], "ตำแหน่ง": p["position"],
                "ราคาปัจจุบัน": f"£{p['buy_price']:.1f}M", "Net Transfers": f"{p['price_trend']['net_transfers']:,}",
                "ถือครอง": f"{p['price_trend']['ownership_pct']}%", "สถานะ": p["price_trend"]["status"]
            } for p in fallers]
            st.dataframe(pd.DataFrame(faller_data), hide_index=True, width='stretch')

    # -------------------------------------------------------------------------
    # TAB 4: CURRENT SQUAD OVERVIEW
    # -------------------------------------------------------------------------
    with tab4:
        st.subheader("📋 รายชื่อ 15 ขุมกำลังปัจจุบัน และโปรแกรมแข่งล่วงหน้า")
        overview_list = []
        for p in my_squad:
            row = {
                "ตำแหน่ง": p["position"], "ชื่อ": p["web_name"], "ทีม": p["team"],
                "ราคาขาย": f"£{p['sell_price']:.1f}M", "xMins": f"{p['xmins']} น.",
                "ความเสี่ยง": p["risk"], "สถานะราคา": p["price_trend"]["status"], "ฟอร์ม": p["form"]
            }
            for gw in target_gws:
                row[f"GW {gw} Match"] = p["fixtures"].get(gw, "-")
                row[f"GW {gw} xP"] = p["xp_by_gw"].get(gw, 0.0)
            overview_list.append(row)

        df_overview = pd.DataFrame(overview_list)
        df_overview.sort_values(by=["ตำแหน่ง"], inplace=True)
        st.dataframe(df_overview, width='stretch', hide_index=True)

        # -------------------------------------------------------------------------
        # TAB 5: MINI-LEAGUE & EO ANALYSIS (รองรับ Multi-League)
        # -------------------------------------------------------------------------
        with tab5:
            st.subheader("🏆 วิเคราะห์คู่แข่งใน Mini-League และ Effective Ownership (EO)")

            # ตัวเลือกสลับมินิลีก
            sel_col1, sel_col2 = st.columns([2, 1])
            with sel_col1:
                selected_league_label = st.selectbox(
                    "🎯 เลือก Mini-League ที่ต้องการวิเคราะห์:",
                    options=list(DEFAULT_LEAGUES.keys()),
                    index=0
                )

            active_league_id = DEFAULT_LEAGUES[selected_league_label]

            # กรณีเลือก "กรอก League ID อื่นๆ เอง"
            if active_league_id == 0:
                with sel_col2:
                    active_league_id = st.number_input("ระบุ League ID:", value=0, step=1)

            if active_league_id <= 0:
                st.info("💡 กรุณาระบุ Mini-League ID ที่ถูกต้องเพื่อเริ่มการวิเคราะห์")
            else:
                pick_gw = max(1, target_gws[0] - 1)
                with st.spinner(f"กำลังดึงข้อมูลไลน์อัปคู่แข่งจาก League ID {active_league_id}..."):
                    league_data = load_league_data(active_league_id, pick_gw)

                if not league_data:
                    st.error(
                        f"❌ ไม่สามารถดึงข้อมูล League ID {active_league_id} ได้ (อาจเป็นลีกส่วนตัวแบบล็อก หรือไม่มีข้อมูลคะแนน)")
                else:
                    st.success(
                        f"📊 วิเคราะห์ข้อมูล: **{league_data['league_name']}** (ประมวลผลจากคู่แข่งชั้นนำ {league_data['total_analyzed']} ทีม)")

                    eo_map = league_data["eo_dict"]
                    players_dict = {p["id"]: p for p in players}

                    # 1. จำแนกประเภทนักเตะ: Shield Threats vs Differentials
                    my_starter_ids = [p["id"] for p in plans[0]["starters"]]
                    shield_threats = []
                    my_differentials = []

                    for pid, stat in eo_map.items():
                        p_info = players_dict.get(pid)
                        if not p_info:
                            continue

                        # Threat: ในลีกมี EO สูงมาก (>= 60%) แต่เราไม่มีใน 11 ตัวจริง
                        if stat["eo_pct"] >= 60.0 and pid not in my_starter_ids:
                            shield_threats.append({
                                "นักเตะ": p_info["web_name"],
                                "ทีม": p_info["team"],
                                "ตำแหน่ง": p_info["position"],
                                "League EO": f"{stat['eo_pct']}%",
                                "คนในลีกเลือก (C)": f"{stat['captain_pct']}%",
                                "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0)
                            })

                        # Differential: เราส่งลงตัวจริง แต่ในลีกมี EO ต่ำ (<= 35%)
                        if stat["eo_pct"] <= 35.0 and pid in my_starter_ids:
                            my_differentials.append({
                                "นักเตะ": p_info["web_name"],
                                "ทีม": p_info["team"],
                                "ตำแหน่ง": p_info["position"],
                                "League EO": f"{stat['eo_pct']}%",
                                "คนในลีกถือ": f"{stat['ownership_pct']}%",
                                "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0)
                            })

                    col_eo1, col_eo2 = st.columns(2)
                    with col_eo1:
                        st.markdown("#### 🛡️ ความเสี่ยงสูงสุด (High EO Threats)")
                        st.caption(
                            "นักเตะที่คู่แข่งในลีกถือและตั้งกัปตัน **แต่เราไม่มีใน 11 ตัวจริง** (ถ้ายิง อันดับจะตกแรง)")
                        if shield_threats:
                            st.dataframe(pd.DataFrame(shield_threats), hide_index=True, width='stretch')
                        else:
                            st.success("✅ ปลอดภัย! คุณถือตัวหลักของลีกนี้ครบถ้วน ไม่มีตัวความเสี่ยงสูง")

                    with col_eo2:
                        st.markdown("#### ⚡ อาวุธลับฉีกแต้ม (Your Differentials)")
                        st.caption("นักเตะตัวจริงของคุณที่ **คนในลีกถือน้อย** (ถ้าทำแต้มได้ อันดับจะพุ่งขึ้นทันที)")
                        if my_differentials:
                            st.dataframe(pd.DataFrame(my_differentials), hide_index=True, width='stretch')
                        else:
                            st.info("ℹ️ 11 ตัวจริงของคุณอิงตามตัวมาตรฐานของลีกนี้ ไม่มีตัวฉีกแต้มชัดเจน")

                    st.markdown("---")

                    # 2. ตาราง EO รวมทั้งหมดของลีก
                    st.markdown(f"#### 📋 สถิติ Effective Ownership (EO) ทั้งหมดใน **{league_data['league_name']}**")
                    all_eo_list = []
                    for pid, stat in sorted(eo_map.items(), key=lambda x: x[1]["eo_pct"], reverse=True):
                        p_info = players_dict.get(pid)
                        if not p_info:
                            continue

                        status_in_my_team = "⚽ 11 ตัวจริง" if pid in my_starter_ids else (
                            "🪑 สำรอง" if pid in my_team_ids else "❌ ไม่มี")

                        all_eo_list.append({
                            "นักเตะ": p_info["web_name"],
                            "ทีม": p_info["team"],
                            "ตำแหน่ง": p_info["position"],
                            "สถานะทีมเรา": status_in_my_team,
                            "Effective Ownership (EO)": f"{stat['eo_pct']}%",
                            "คนในลีกมีชื่อ": f"{stat['ownership_pct']}%",
                            "คนในลีกเลือกเป็น (C)": f"{stat['captain_pct']}%",
                            "ราคา": f"£{p_info['buy_price']:.1f}M",
                            "xP นัดถัดไป": p_info["xp_by_gw"].get(target_gws[0], 0.0)
                        })

                    st.dataframe(pd.DataFrame(all_eo_list), hide_index=True, width='stretch')

except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการคำนวณ: {e}")