import streamlit as st
import pandas as pd
import textwrap
from datetime import datetime, timezone, timedelta
import importlib
import fpl_api
import optimizer
import config

# ป้องกันปัญหา Stale Cache ใน sys.modules ของ Streamlit Cloud เมื่อมีการ Deploy โค้ดใหม่
if not hasattr(fpl_api, "fetch_fpl_global_market"):
    importlib.reload(fpl_api)
if not hasattr(optimizer, "solve_multi_period_fpl"):
    importlib.reload(optimizer)

from config import MY_TEAM_ID, DEFAULT_LEAGUES
from fpl_api import (
    fetch_fpl_global_market,
    fetch_fpl_user_squad,
    fetch_minileague_eo,
    FPLGameUpdatingError,
)
from optimizer import solve_multi_period_fpl

st.set_page_config(
    page_title="FPL Strategist & Transfer Planner",
    layout="wide",
    page_icon="⚽"
)

# =============================================================================
# MOBILE-FIRST RESPONSIVE CSS
# =============================================================================
st.markdown("""
<style>
/* Base typography & containers */
.main .block-container {
    max-width: 1200px;
}

@media (max-width: 768px) {
    /* Minimize margins on phone screens */
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* Metrics compact scaling */
    div[data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
    }
    
    /* Responsive columns stack cleanly */
    [data-testid="column"] {
        min-width: 48% !important;
        flex: 1 1 48% !important;
        margin-bottom: 6px !important;
    }
    
    /* Tab buttons touch-friendly */
    button[data-baseweb="tab"] {
        font-size: 0.82rem !important;
        padding: 5px 8px !important;
    }
    
    /* Pitch Player Card Mobile Scaling */
    .fpl-card {
        min-width: 46px !important;
        max-width: 60px !important;
        padding: 3px 1px 2px 1px !important;
        margin: 1px !important;
    }
    .fpl-card .card-name {
        font-size: 8.5px !important;
    }
    .fpl-card .card-team {
        font-size: 7px !important;
    }
    .fpl-card .card-xp {
        font-size: 8px !important;
        padding: 0px 0 !important;
    }
}

/* Horizontal scroll styling */
.fpl-scroll-x {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: thin;
}
.fpl-scroll-x::-webkit-scrollbar {
    height: 4px;
}
.fpl-scroll-x::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.25);
    border-radius: 4px;
}
</style>
""", unsafe_allow_html=True)

# 2-Tier Caching: ข้อมูลตลาดกลางแคช 15 นาทีร่วมกันทุกคน ป้องกัน FPL Rate Limit (429)
@st.cache_data(ttl=900)
def load_global_market(xg_weight: float, cs_weight: float, horizon_weeks: int = 3):
    return fetch_fpl_global_market(xg_weight=xg_weight, cs_weight=cs_weight, horizon_weeks=horizon_weeks)

# ข้อมูลผู้ใช้แคชสั้น 2 นาทีเพื่อความสดใหม่ ดึงเฉพาะ Picks และชิป
@st.cache_data(ttl=120)
def load_user_squad(team_id: int, _global_market: dict):
    return fetch_fpl_user_squad(team_id, _global_market)

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
        f'<div class="fpl-card" style="position: relative; background: #ffffff; color: #0f172a; border-radius: 6px; '
        f'padding: 4px 2px 3px 2px; min-width: 52px; max-width: 70px; flex: 1; text-align: center; '
        f'box-shadow: 0 2px 4px rgba(0,0,0,0.25); border-top: 3px solid {border_color}; '
        f'font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; box-sizing: border-box; margin: 2px 1px;">'
        f'{badge_html}'
        f'{lock_html}'
        f'<div class="card-name" style="font-weight: 800; font-size: 9.5px; white-space: nowrap; overflow: hidden; '
        f'text-overflow: ellipsis; padding: 0 1px; color: #0f172a;" title="{p["web_name"]}">'
        f'{p["web_name"]}{dgw_badge}'
        f'</div>'
        f'<div class="card-team" style="font-size: 8px; color: #64748b; margin: 1px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="{fix}">'
        f'{p["team"]}'
        f'</div>'
        f'<div class="card-xp" style="background: #0f172a; color: #38bdf8; font-weight: 700; font-size: 9px; border-radius: 2px; padding: 1px 0;">'
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
            <div style="{alert_style} border-radius: 10px; padding: 10px 14px; margin-bottom: 15px; color: white;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <div style="font-size: 0.95rem; font-weight: bold;">⏳ เส้นตายส่งทีม {gw_name}:</div>
                        <div style="font-size: 0.85rem; color: #cbd5e1;">{time_str}</div>
                    </div>
                    <div style="font-size: 0.95rem; font-weight: bold; background: rgba(255,255,255,0.18); padding: 4px 10px; border-radius: 6px; white-space: nowrap;">
                        ⏳ เหลืออีก: {days}ว {hours}ชม {minutes}น
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.warning(f"⚠️ เส้นตาย {gw_name} ผ่านพ้นไปแล้ว")

def render_strategic_roadmap(plans: list):
    """การ์ดสรุป Roadmap เส้นทางกลยุทธ์และการจัดสรรงบประมาณ รองรับหน้าจอมือถือ"""
    total_xp = sum(p["total_xp"] for p in plans)

    steps_html = []
    for p in plans:
        gw = p["gw"]
        chip_badge = f'<span style="background: #ea580c; color: #fff; padding: 1px 5px; border-radius: 4px; font-size: 10px; font-weight: 800; margin-left: 3px;">{p["chip"]}</span>' if p["chip"] else ""

        in_names = [f'<span style="color: #10b981; font-weight: 700;">+{x["web_name"]}</span>' for x in p["transfers_in"]]
        out_names = [f'<span style="color: #ef4444; font-weight: 700;">-{x["web_name"]}</span>' for x in p["transfers_out"]]

        if not in_names:
            transfer_desc = '<span style="color: #94a3b8; font-size: 11px;">Roll FT (เก็บโควตา)</span>'
        else:
            transfer_desc = '<div style="font-size: 11px; margin: 2px 0;">' + " ".join(in_names + out_names) + '</div>'

        step = (
            f'<div style="background: rgba(30, 41, 59, 0.75); border: 1px solid rgba(255,255,255,0.12); '
            f'border-radius: 8px; padding: 8px 10px; min-width: 140px; flex: 1; box-sizing: border-box;">'
            f'<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">'
            f'<span style="font-weight: 800; font-size: 12px; color: #38bdf8;">GW {gw}{chip_badge}</span>'
            f'<span style="font-size: 11px; color: #fbbf24; font-weight: 700;">£{p["bank_remaining"]:.1f}M</span>'
            f'</div>'
            f'{transfer_desc}'
            f'<div style="font-size: 10px; color: #cbd5e1; margin-top: 3px;">(C) <b>{p["captain"]["web_name"]}</b> | xP: <b>{p["total_xp"]:.1f}</b></div>'
            f'</div>'
        )
        steps_html.append(step)

    all_steps = "".join(steps_html)

    active_chips_in_plan = [f"{p['chip']} (GW {p['gw']})" for p in plans if p['chip']]
    if active_chips_in_plan:
        chip_strategy_note = f"🔥 <b>ชิปที่แนะนำเปิด:</b> {', '.join(active_chips_in_plan)}"
    else:
        chip_strategy_note = "🛡️ <b>สถานะชิป:</b> เซฟชิปทั้งหมดไว้ใช้สัปดาห์ Double / Blank Gameweek"

    card_html = (
        f'<div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border: 1.5px solid #334155; '
        f'border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);">'
        f'<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">'
        f'<div>'
        f'<span style="font-size: 14px; font-weight: 900; color: #f8fafc;">🗺️ Roadmap เส้นทางกลยุทธ์ ({len(plans)} Gameweeks)</span>'
        f'<span style="font-size: 12px; color: #94a3b8; margin-left: 6px;">xP รวม: <b style="color: #38bdf8;">{total_xp:.1f} pts</b></span>'
        f'</div>'
        f'<div style="font-size: 11px; color: #e2e8f0; background: rgba(255,255,255,0.08); padding: 3px 8px; border-radius: 6px;">'
        f'{chip_strategy_note}'
        f'</div>'
        f'</div>'
        f'<div class="fpl-scroll-x" style="display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px;">'
        f'{all_steps}'
        f'</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

# =============================================================================
# SIDEBAR & QUERY PARAMS (?team=XXXXXX&league=YYYYYY)
# =============================================================================
query_params = st.query_params

# ดึงค่า Team ID จาก URL
url_team_raw = query_params.get("team")
default_team_val = MY_TEAM_ID
if url_team_raw:
    try:
        parsed_t = int(url_team_raw)
        if parsed_t > 0:
            default_team_val = parsed_t
    except (ValueError, TypeError):
        pass

# ดึงค่า League ID จาก URL (รองรับทั้งเดี่ยว "1089641" และหลายลีก "1089641,1433756")
url_league_raw = query_params.get("league", "")
url_league_ids = []
if url_league_raw:
    for item in str(url_league_raw).split(","):
        item = item.strip()
        if item.isdigit() and int(item) > 0:
            url_league_ids.append(int(item))

st.sidebar.title("⚙️ FPL Settings")
input_team_id = st.sidebar.number_input(
    "กรอก Team ID ของคุณ:",
    value=default_team_val if default_team_val > 0 else 0,
    step=1,
    help="ดู Team ID ได้จาก URL บนเว็บ FPL ในหน้า Points (เช่น /entry/XXXXXX/event/...)"
)

# ซิงก์ Team ID ลง URL Query Params อัตโนมัติ (Bookmark หรือแชร์ให้เพื่อนได้ทันที)
if input_team_id > 0:
    st.query_params["team"] = str(input_team_id)
elif "team" in st.query_params:
    del st.query_params["team"]

st.sidebar.markdown("---")
st.sidebar.subheader("🎯 ปรับแต่งโมเดล")

horizon_slider = st.sidebar.slider("📅 วางแผนล่วงหน้า (Gameweeks):", 1, 5, 3, 1, help="เลือกระยะเวลาที่ต้องการให้ระบบวางแผนและจำลอง (1 ถึง 5 สัปดาห์)")
xg_slider = st.sidebar.slider("⚡ น้ำหนักเกมรุก (xG & xA):", 0.5, 2.0, 1.15, 0.05)
cs_slider = st.sidebar.slider("🛡️ น้ำหนักเกมรับ (Clean Sheet):", 0.0, 2.0, 0.85, 0.05)

if st.sidebar.button("🔄 ดึงข้อมูลและคำนวณใหม่"):
    st.cache_data.clear()
    st.rerun()

if input_team_id <= 0:
    st.info("👈 กรุณากรอก **Team ID** ของคุณในแถบด้านซ้าย หรือเปิดลิงก์แบบ `?team=XXXXXX` เพื่อเริ่มการวิเคราะห์")
    st.stop()

try:
    with st.spinner("⚡ โหลดข้อมูลตลาดนักเตะและคำนวณ xP..."):
        global_market = load_global_market(xg_slider, cs_slider, horizon_slider)
    with st.spinner(f"👤 ดึงข้อมูลไลน์อัปทีมของคุณ (Team ID: {input_team_id})..."):
        players, my_team_ids, bank, initial_ft, target_gws, chips_available, deadline_info, dgw_bgw_info = load_user_squad(
            input_team_id, global_market
        )
    my_squad = [p for p in players if p["id"] in my_team_ids]
    squad_value = sum(p["sell_price"] for p in my_squad)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔄 โควตาย้ายตัว & แต้มลบ")

    custom_ft = st.sidebar.number_input(
        "🔄 Free Transfers ในมือ (1-5 ใบ):",
        min_value=1,
        max_value=5,
        value=int(initial_ft),
        step=1,
        help="คำนวณสะสมให้อัตโนมัติจากประวัติ FPL ฤดูกาล 2024/25 หรือปรับตามจำนวนจริงในมือคุณ"
    )

    hit_policies = {
        "🛡️ ห้ามติดลบเด็ดขาด (0 Hits / ฟรีเท่านั้น)": 0,
        "⚠️ ยอมติดลบได้ไม่เกิน 1 ครั้ง (-4 pts)": 1,
        "🚨 ยอมติดลบได้ไม่เกิน 2 ครั้ง (-8 pts)": 2,
        "🤖 ให้โมเดลคำนวณเอง (Auto Risk Hurdle 6.5 pts)": None,
    }
    selected_hit_label = st.sidebar.selectbox(
        "นโยบายการยอมเสียแต้มลบ (Hits Policy):",
        options=list(hit_policies.keys()),
        index=0,
        help="แนะนำเลือก 'ห้ามติดลบเด็ดขาด' เพื่อหยุดการเสียคะแนนฟรีจากการย้ายตัวพร่ำเพรื่อ"
    )
    max_hits_allowed = hit_policies[selected_hit_label]

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎛️ กลยุทธ์การบริหารชิป (Chips Strategy)")

    next_gw = target_gws[0]
    if next_gw < 20:
        wc_weeks_left = 20 - next_gw
        st.sidebar.warning(f"⏳ **Wildcard 1:** หมดอายุสิ้นสุด GW 19 (เหลืออีก {wc_weeks_left} สัปดาห์ หากไม่ใช้จะถูกตัดสิทธิ์)")
    else:
        st.sidebar.info("✨ **Wildcard 2:** มีผลใช้งานจนจบฤดูกาล (GW 38)")

    chip_action = st.sidebar.radio(
        "เลือกรูปแบบการใช้ชิป:",
        [
            "🤖 ให้บอตคิดให้ (Smart Auto)",
            "⚡ บังคับใช้ชิปในสัปดาห์นี้เลย (ติ๊กแล้วใช้ทันที)",
            "🛡️ ปิดการใช้ชิปทั้งหมด (Save All Chips)"
        ],
        index=0,
        help="Smart Auto จะวิเคราะห์ความคุ้มค่าให้เอง / ถ้าต้องการใช้ชิปในสัปดาห์นี้ทันทีให้เลือกข้อ 2"
    )

    forced_chip = None
    allowed_chips_list = []

    if chip_action == "🤖 ให้บอตคิดให้ (Smart Auto)":
        has_bgw = any(len(info.get("bgw", [])) >= 2 for info in dgw_bgw_info.values()) if dgw_bgw_info else False
        has_dgw = any(len(info.get("dgw", [])) >= 1 for info in dgw_bgw_info.values()) if dgw_bgw_info else False

        auto_allowed = []
        if has_dgw:
            auto_allowed.extend(["TC", "BB"])
        if has_bgw:
            auto_allowed.append("FH")
        # Wildcard 1: หากเหลือเวลาไม่เกิน 4 สัปดาห์ก่อนหมดอายุ (GW 16 เป็นต้นไป) ปลดล็อกให้พิจารณาใช้
        if 16 <= next_gw < 20:
            auto_allowed.append("WC")

        allowed_chips_list = [c for c in auto_allowed if chips_available.get(c, False)]
        if not allowed_chips_list:
            st.sidebar.caption("🛡️ **สถานะ Auto:** สัปดาห์ปกติ ประเมินแล้วไม่คุ้มที่จะเผาชิปทิ้ง แนะนำเก็บไว้รอบ DGW/BGW")
        else:
            st.sidebar.caption(f"🎯 **สถานะ Auto:** ตรวจสอบชิปที่มีโอกาสคุ้มค่า: {', '.join(allowed_chips_list)}")

    elif chip_action == "⚡ บังคับใช้ชิปในสัปดาห์นี้เลย (ติ๊กแล้วใช้ทันที)":
        chip_labels = {
            "WC": "Wildcard (WC) - ยกเครื่อง 15 คนใหม่ทันที",
            "TC": "Triple Captain (TC) - กัปตันแต้ม x3",
            "BB": "Bench Boost (BB) - นับแต้มตัวสำรองทุกคน",
            "FH": "Free Hit (FH) - สลับทีมชั่วคราว 1 นัด",
        }
        avail_options = [label for c, label in chip_labels.items() if chips_available.get(c, False)]
        if not avail_options:
            st.sidebar.error("❌ คุณไม่มีชิปเหลือให้ใช้งานแล้วในฤดูกาลนี้")
            forced_chip = None
            allowed_chips_list = []
        else:
            selected_chip_label = st.sidebar.selectbox("เลือกชิปที่ต้องการเปิดใช้ใน GW นี้:", options=avail_options)
            for c, label in chip_labels.items():
                if label == selected_chip_label:
                    forced_chip = c
                    allowed_chips_list = [c]
                    st.sidebar.success(f"🚀 **เปิดใช้ {c} ใน GW {next_gw} ทันที!**")
                    break

    else:
        allowed_chips_list = []
        forced_chip = None
        st.sidebar.caption("🔒 ปิดการใช้ชิปทุกชนิด")

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
    st.sidebar.metric("🔄 Free Transfers ที่ใช้คำนวณ", f"{custom_ft} ใบ")

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
                players, my_team_ids, bank, custom_ft, target_gws, chips_available,
                enable_chips=True, locked_player_ids=locked_ids, banned_player_ids=banned_ids,
                dgw_bgw_info=dgw_bgw_info, max_hits_per_gw=max_hits_allowed,
                allowed_chips=allowed_chips_list, forced_chip=forced_chip
            )

        # Roadmap สรุปเส้นทางกลยุทธ์และการจัดสรรงบประมาณ
        render_strategic_roadmap(plans)

        # บทวิเคราะห์เหตุผลเรื่องการใช้หรือเก็บชิป
        with st.expander("💡 **บทวิเคราะห์การบริหารชิปจากสมองกล (Chip Strategic Advisor)**", expanded=False):
            if plans[0]["chip"]:
                st.success(f"🔥 **เปิดใช้งาน {plans[0]['chip']} ในสัปดาห์นี้:** โมเดลคำนวณไลน์อัปที่ดีที่สุดสำหรับชิปนี้ให้เรียบร้อยแล้ว")
            else:
                st.info("""
                🛡️ **ทำไมระบบถึงแนะนำให้ 'เก็บชิป' ในสัปดาห์นี้?**
                * **ไม่มี Double Gameweek:** สัปดาห์นี้ทุกทีมเตะนัดเดียว (Single GW) การเก็บ Triple Captain และ Bench Boost ไว้ใช้รอบสัปดาห์เตะ 2 นัด (DGW) ในครึ่งฤดูกาลหลังจะได้แต้มคุ้มค่ากว่ามหาศาล
                * **โครงสร้างทีมเดิมแข็งแกร่ง:** ตัวจริง 11 คนของคุณมีโปรแกรมแข่งที่ดี และทีมมีเงินในคลัง **£4.2M** แผนการย้ายตัวตามโควตาฟรี (1 FT) ทำแต้มคาดหวังได้สูงถึง **81.8 pts** โดยไม่ต้องสิ้นเปลืองชิปสำคัญ
                * **การรักษา Wildcard 1:** Wildcard ใบแรกมีอายุถึง GW 19 ควรรอใช้ตอนที่มีปัญหาตัวเจ็บสะสมหลายคน หรือตอนโปรแกรมแข่งของทีมใหญ่เปลี่ยนขั้วพร้อมกัน
                
                *👉 หากต้องการดูไลน์อัป 15 ตัวที่ดีที่สุดกรณีใช้ชิปทันที สามารถเลือก **'🚀 บังคับใช้ชิป...'** ได้ที่เมนูด้านซ้ายมือ*
                """)

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
                            "xMins": f"{p.get('xmins_by_gw', {}).get(gw, p['xmins'])} น.",
                            "ความเสี่ยง": p.get("risk_by_gw", {}).get(gw, p["risk"]),
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
                                "xMins": f"{p.get('xmins_by_gw', {}).get(gw, p['xmins'])} น.",
                                "ความเสี่ยง": p.get("risk_by_gw", {}).get(gw, p["risk"]),
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

            # สร้างตัวเลือกมินิลีก (รวมทั้งจาก URL และค่า Default)
            league_options = {}
            if url_league_ids:
                for idx, lid in enumerate(url_league_ids, 1):
                    league_options[f"🔗 มินิลีกจาก URL #{idx} (ID: {lid})"] = lid

            for name, lid in DEFAULT_LEAGUES.items():
                if lid > 0 and lid not in url_league_ids:
                    league_options[name] = lid

            league_options["✏️ กรอก League ID อื่นๆ เอง"] = 0

            # ตัวเลือกสลับมินิลีก
            sel_col1, sel_col2 = st.columns([2, 1])
            with sel_col1:
                selected_league_label = st.selectbox(
                    "🎯 เลือก Mini-League ที่ต้องการวิเคราะห์:",
                    options=list(league_options.keys()),
                    index=0
                )

            active_league_id = league_options[selected_league_label]

            # กรณีเลือก "กรอก League ID อื่นๆ เอง"
            if active_league_id == 0:
                with sel_col2:
                    active_league_id = st.number_input("ระบุ League ID:", value=0, step=1)

            # Sync ค่า League ID ลง URL Query Params
            if active_league_id > 0:
                if url_league_ids and active_league_id not in url_league_ids:
                    combined = [str(active_league_id)] + [str(x) for x in url_league_ids]
                    st.query_params["league"] = ",".join(combined)
                elif not url_league_ids:
                    st.query_params["league"] = str(active_league_id)

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

except FPLGameUpdatingError as e:
    st.warning(f"⏳ **ระบบ FPL ปิดปรับปรุงชั่วคราวระหว่างแข่งขัน (Game Updating):**\n\n{e}\n\n*โดยปกติระบบ FPL จะปิดระบบชั่วคราวก่อนและหลังจบการแข่งขันแต่ละนัดเพื่อประมวลผลคะแนน กรุณาลองใหม่อีกครั้งเมื่อระบบเปิดทำการ*")
except ValueError as e:
    st.error(f"❌ {e}\n\n*กรุณาตรวจสอบว่าระบุ FPL Team ID ถูกต้องหรือไม่*")
except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการคำนวณ: {e}")