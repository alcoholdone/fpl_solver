import html
import re
import textwrap
from datetime import datetime, timezone, timedelta
import streamlit as st


def inject_custom_css():
    """ฉีด CSS สำหรับสไตล์ Sports Analytics Dashboard แบบเรียบคมและรองรับมือถือ"""
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.main .block-container {
    max-width: 1240px;
    padding-top: 1.25rem;
    padding-bottom: 2.5rem;
}

.mono-num,
div[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
    font-variant-numeric: tabular-nums;
}

/* KPI & Summary surfaces */
.fpl-topbar {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 12px;
    padding: 14px 18px;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
}

.fpl-kpi-strip {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    align-items: center;
}

.fpl-kpi-pill {
    background: #0B0F17;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 8px;
    padding: 6px 12px;
    min-width: 82px;
}

.fpl-kpi-label {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94A3B8;
    font-weight: 600;
}

.fpl-kpi-val {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    font-weight: 700;
    color: #F8FAFC;
    margin-top: 1px;
}

/* Roadmap container */
.fpl-roadmap-wrap {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 16px;
}

.fpl-scroll-x {
    display: flex;
    gap: 10px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scroll-snap-type: x proximity;
    scrollbar-width: thin;
    padding-bottom: 4px;
}
.fpl-scroll-x::-webkit-scrollbar {
    height: 4px;
}
.fpl-scroll-x::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.25);
    border-radius: 4px;
}

.fpl-roadmap-card {
    background: #0B0F17;
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 10px;
    padding: 10px 12px;
    min-width: 165px;
    flex: 1;
    box-sizing: border-box;
}

/* Scrollable tabs */
div[data-baseweb="tab-list"] {
    overflow-x: auto;
    flex-wrap: nowrap !important;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    gap: 4px;
}
div[data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none;
}
button[data-baseweb="tab"] {
    white-space: nowrap !important;
    flex-shrink: 0 !important;
}

/* Transfer cards */
.fpl-transfer-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
    gap: 10px;
    margin: 8px 0 14px 0;
}

.fpl-transfer-card {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 10px;
    padding: 10px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}

.fpl-roll-card {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 10px;
    padding: 10px 14px;
    margin: 8px 0 14px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
}

/* Pitch & Player cards */
.fpl-pitch {
    background:
        repeating-linear-gradient(
            180deg,
            rgba(16, 185, 129, 0.05) 0px,
            rgba(16, 185, 129, 0.05) 36px,
            rgba(6, 78, 59, 0.04) 36px,
            rgba(6, 78, 59, 0.04) 72px
        ),
        linear-gradient(180deg, #0D3321 0%, #092518 100%);
    border: 1px solid rgba(16, 185, 129, 0.28);
    border-radius: 12px;
    padding: 14px 8px 12px 8px;
    position: relative;
    margin-bottom: 10px;
    width: 100%;
    box-sizing: border-box;
    overflow-x: auto;
}

.fpl-pitch-row {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 4px;
    margin: 8px 0;
    width: 100%;
    position: relative;
    z-index: 1;
}

.fpl-bench-wrap {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 10px;
    padding: 10px 8px 8px 8px;
    display: flex;
    justify-content: center;
    gap: 6px;
    width: 100%;
    box-sizing: border-box;
    overflow-x: auto;
}

.fpl-bench-slot {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 68px;
    max-width: 108px;
    flex: 1;
}

.fpl-card {
    position: relative;
    background: #0F172A;
    color: #F8FAFC;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 8px;
    padding: 6px 4px 4px 4px;
    min-width: 72px;
    max-width: 108px;
    flex: 1;
    text-align: center;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.35);
    box-sizing: border-box;
    margin: 2px 3px;
}

.fpl-card-badge {
    font-size: 8.5px;
    padding: 1px 5px;
}

.fpl-card .card-name {
    font-weight: 700;
    font-size: 11px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0 2px;
    color: #F8FAFC;
}

.fpl-card .card-fix {
    font-size: 9.5px;
    color: #94A3B8;
    margin: 2px 0 4px 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
}

.fpl-card .card-xp {
    font-family: 'JetBrains Mono', monospace;
    font-variant-numeric: tabular-nums;
    background: #070B12;
    color: #34D399;
    font-weight: 700;
    font-size: 10.5px;
    border-radius: 4px;
    padding: 2px 0;
    border: 1px solid rgba(16, 185, 129, 0.2);
}

/* Mobile refinements */
@media (max-width: 768px) {
    .main .block-container,
    .block-container,
    .stMainBlockContainer {
        padding-top: 0.7rem !important;
        padding-left: 0.55rem !important;
        padding-right: 0.55rem !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
    }
    .fpl-topbar {
        flex-direction: column;
        align-items: stretch;
        padding: 12px;
        gap: 10px;
    }
    .fpl-kpi-strip {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 8px;
        width: 100%;
    }
    .fpl-kpi-pill {
        min-width: 0;
        padding: 8px 10px;
    }
    .fpl-roadmap-card {
        min-width: 155px;
        flex: 0 0 auto;
        scroll-snap-align: start;
    }
    button[data-baseweb="tab"] {
        font-size: 0.82rem !important;
        padding: 8px 10px !important;
        min-height: 40px !important;
    }
    .fpl-pitch {
        padding: 10px 4px 8px 4px;
        overflow-x: hidden;
    }
    .fpl-pitch-row {
        gap: 3px !important;
        margin: 6px 0 !important;
    }
    .fpl-bench-wrap {
        gap: 4px !important;
        padding: 8px 4px 6px 4px !important;
        overflow-x: hidden;
    }
    .fpl-bench-slot {
        min-width: 0 !important;
        max-width: 24% !important;
        flex: 1 1 0 !important;
    }
    .fpl-card {
        min-width: 0 !important;
        max-width: 19.5% !important;
        width: 100%;
        padding: 5px 2px 3px 2px !important;
        margin: 1px 0 !important;
    }
    .fpl-bench-slot .fpl-card {
        max-width: 100% !important;
    }
    .fpl-card .card-name {
        font-size: 9px !important;
        padding: 0 1px !important;
    }
    .fpl-card .card-fix {
        font-size: 7.5px !important;
        gap: 2px !important;
    }
    .fpl-card .card-xp {
        font-size: 8.5px !important;
        padding: 1px 0 !important;
    }
    .fpl-card-badge {
        font-size: 7px !important;
        padding: 0 3px !important;
    }
}

@media (max-width: 640px) {
    [data-testid="column"],
    [data-testid="stColumn"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
        margin-bottom: 6px !important;
    }
    .fpl-transfer-grid {
        grid-template-columns: 1fr !important;
    }
    button[kind] {
        min-height: 40px !important;
    }
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #0E1420 !important;
    border-right: 1px solid rgba(148, 163, 184, 0.14) !important;
}

section[data-testid="stSidebar"] > div:first-child,
div[data-testid="stSidebarContent"] {
    padding-top: 1rem !important;
}

.fpl-sb-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 2px 14px 2px;
    margin-bottom: 6px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.fpl-sb-mark {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: linear-gradient(135deg, #10B981 0%, #059669 100%);
    color: #06281B;
    font-weight: 800;
    font-size: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
    letter-spacing: -0.02em;
    flex-shrink: 0;
}

.fpl-sb-section {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748B;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
    padding-top: 12px;
    margin-top: 12px;
    margin-bottom: 8px;
}

section[data-testid="stSidebar"] div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] div[data-baseweb="input"] > div {
    background-color: #131926 !important;
    border: 1px solid rgba(148, 163, 184, 0.2) !important;
    border-radius: 8px !important;
}

section[data-testid="stSidebar"] span[data-baseweb="tag"] {
    background-color: rgba(16, 185, 129, 0.15) !important;
    border: 1px solid rgba(16, 185, 129, 0.35) !important;
    color: #6EE7B7 !important;
    border-radius: 6px !important;
}

section[data-testid="stSidebar"] span[data-baseweb="tag"] svg {
    fill: #6EE7B7 !important;
}

section[data-testid="stSidebar"] div[data-testid="stExpander"] {
    background-color: #131926 !important;
    border: 1px solid rgba(148, 163, 184, 0.14) !important;
    border-radius: 10px !important;
}

section[data-testid="stSidebar"] button[kind="secondary"] {
    background-color: #131926 !important;
    border: 1px solid rgba(148, 163, 184, 0.24) !important;
    border-radius: 8px !important;
    color: #F1F5F9 !important;
    font-weight: 600 !important;
    transition: border-color 0.15s ease, background-color 0.15s ease;
}

section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    border-color: #10B981 !important;
    background-color: rgba(16, 185, 129, 0.1) !important;
    color: #6EE7B7 !important;
}

/* Top 3 Captains */
.fpl-cap-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin: 4px 0 12px 0;
}

.fpl-cap-card {
    background: #131926;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 10px;
    padding: 9px 11px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
}

@media (max-width: 640px) {
    .fpl-cap-grid {
        grid-template-columns: 1fr;
    }
}

/* Fixture Ticker */
.fpl-ticker-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 10px;
    background: #0E1420;
}

.fpl-ticker-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    min-width: 520px;
}

.fpl-ticker-table th {
    background: #131926;
    color: #94A3B8;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 9px 10px;
    text-align: center;
    border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.fpl-ticker-table th:first-child,
.fpl-ticker-table td:first-child {
    position: sticky;
    left: 0;
    background: #131926;
    text-align: left;
    z-index: 1;
    border-right: 1px solid rgba(148, 163, 184, 0.14);
}

.fpl-ticker-table td {
    padding: 7px 8px;
    text-align: center;
    border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    color: #E2E8F0;
}

.fpl-fdr-pill {
    display: inline-block;
    padding: 3px 7px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand():
    """หัวข้อ Sidebar แบบ Clean Sports Analytics"""
    st.sidebar.markdown(
        """
        <div class="fpl-sb-brand">
            <div class="fpl-sb-mark">FPL</div>
            <div>
                <div style="font-size:15px; font-weight:800; color:#F8FAFC; line-height:1.15;">FPL Strategist</div>
                <div style="font-size:11px; color:#94A3B8; margin-top:2px;">Squad &amp; Transfer Planner</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_section(title: str):
    """หัวข้อย่อยของ Sidebar แทน st.markdown('---') + st.subheader"""
    st.markdown(
        f'<div class="fpl-sb-section">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def _parse_next_fixture(fix_str: str) -> tuple[str, str]:
    """แปลงข้อความคู่แข่งเป็นรูปแบบย่อพร้อมสีตามระดับความยาก FDR"""
    if not fix_str or fix_str == "-" or fix_str == "Blank":
        return "BLANK", "#64748B"

    matches = re.findall(r"vs\s+([A-Z0-9]+)\s+\(([HA])\)\s+\[FDR\s+(\d+)\]", fix_str)
    if not matches:
        return fix_str[:12], "#94A3B8"

    if len(matches) == 1:
        opp, venue, fdr_s = matches[0]
        fdr = int(fdr_s)
        color = "#10B981" if fdr <= 2 else ("#F59E0B" if fdr == 3 else "#EF4444")
        return f"{opp} ({venue})", color

    short_parts = [f"{opp}({venue})" for opp, venue, _ in matches[:2]]
    avg_fdr = sum(int(f) for _, _, f in matches) / len(matches)
    color = "#10B981" if avg_fdr <= 2.5 else ("#F59E0B" if avg_fdr <= 3.5 else "#EF4444")
    return " + ".join(short_parts), color


def render_top_bar(
    deadline_info: dict,
    bank: float,
    squad_value: float,
    custom_ft: int,
    gw1_xp: float,
    next_gw: int,
):
    """แถบสรุปสถานะทีมและ Deadline แบบ Compact บนสุดของหน้า"""
    gw_name = html.escape(str(deadline_info.get("name") or f"Gameweek {next_gw}"))
    deadline_utc_str = deadline_info.get("deadline_utc")

    if deadline_utc_str:
        utc_time = datetime.fromisoformat(deadline_utc_str.replace("Z", "+00:00"))
        bkk_time = utc_time.astimezone(timezone(timedelta(hours=7)))
        now_bkk = datetime.now(timezone(timedelta(hours=7)))
        diff = bkk_time - now_bkk
        time_str = bkk_time.strftime("%d %b %Y · %H:%M น.")

        if diff.total_seconds() > 0:
            days = diff.days
            hours, remainder = divmod(diff.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            badge_bg = "rgba(16, 185, 129, 0.14)" if days >= 1 else "rgba(239, 68, 68, 0.16)"
            badge_fg = "#34D399" if days >= 1 else "#FCA5A5"
            badge_border = "rgba(16, 185, 129, 0.35)" if days >= 1 else "rgba(239, 68, 68, 0.4)"
            countdown_text = f"เหลือเวลา {days} วัน {hours} ชม. {minutes} น."
        else:
            badge_bg = "rgba(245, 158, 11, 0.14)"
            badge_fg = "#FCD34D"
            badge_border = "rgba(245, 158, 11, 0.35)"
            countdown_text = "เลยเส้นตายแล้ว"
    else:
        time_str = "รอประกาศตารางแข่ง"
        badge_bg = "rgba(148, 163, 184, 0.14)"
        badge_fg = "#CBD5E1"
        badge_border = "rgba(148, 163, 184, 0.25)"
        countdown_text = "-"

    bar_html = textwrap.dedent(
        f"""
<div class="fpl-topbar">
    <div>
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span style="font-size:16px; font-weight:800; color:#F8FAFC; letter-spacing:-0.01em;">FPL Strategist · {gw_name}</span>
            <span style="background:{badge_bg}; color:{badge_fg}; border:1px solid {badge_border}; font-size:11px; font-weight:700; padding:2px 8px; border-radius:999px;">
                {countdown_text}
            </span>
        </div>
        <div style="font-size:12px; color:#94A3B8; margin-top:3px;">Deadline: {html.escape(time_str)} (เวลาไทย)</div>
    </div>
    <div class="fpl-kpi-strip">
        <div class="fpl-kpi-pill">
            <div class="fpl-kpi-label">Bank</div>
            <div class="fpl-kpi-val" style="color:#FBBF24;">£{bank:.1f}m</div>
        </div>
        <div class="fpl-kpi-pill">
            <div class="fpl-kpi-label">Squad Value</div>
            <div class="fpl-kpi-val">£{squad_value:.1f}m</div>
        </div>
        <div class="fpl-kpi-pill">
            <div class="fpl-kpi-label">Free Transfers</div>
            <div class="fpl-kpi-val">{custom_ft}</div>
        </div>
        <div class="fpl-kpi-pill">
            <div class="fpl-kpi-label">GW {next_gw} xP</div>
            <div class="fpl-kpi-val" style="color:#34D399;">{gw1_xp:.1f}</div>
        </div>
    </div>
</div>
        """
    ).strip()
    st.markdown(bar_html, unsafe_allow_html=True)


def render_strategic_roadmap(plans: list):
    """สรุปแผนระยะสั้นหลาย Gameweek แบบ Compact Cards"""
    total_xp = sum(p["total_xp"] for p in plans)
    steps_html = []

    for p in plans:
        gw = p["gw"]
        chip_badge = (
            f'<span style="background:rgba(245, 158, 11, 0.18); color:#FCD34D; border:1px solid rgba(245, 158, 11, 0.38); '
            f'padding:1px 6px; border-radius:4px; font-size:10px; font-weight:700; margin-left:6px;">{html.escape(p["chip"])}</span>'
            if p["chip"]
            else ""
        )

        in_names = [f'<span style="color:#34D399; font-weight:600;">+{html.escape(x["web_name"])}</span>' for x in p["transfers_in"]]
        out_names = [f'<span style="color:#F87171; font-weight:600;">-{html.escape(x["web_name"])}</span>' for x in p["transfers_out"]]

        if not in_names:
            transfer_desc = '<div style="color:#94A3B8; font-size:11.5px; margin:4px 0;">Roll FT (เก็บโควตา)</div>'
        else:
            hit_note = f' <span style="color:#F87171; font-size:10.5px;">(-{p["hits"]*4})</span>' if p["hits"] > 0 else ""
            transfer_desc = (
                '<div style="font-size:11.5px; margin:4px 0; line-height:1.45;">'
                + " · ".join(in_names + out_names)
                + hit_note
                + "</div>"
            )

        cap_name = html.escape(p["captain"]["web_name"])
        step = (
            f'<div class="fpl-roadmap-card">'
            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
            f'<span style="font-weight:700; font-size:12.5px; color:#F8FAFC;">GW {gw}{chip_badge}</span>'
            f'<span class="mono-num" style="font-size:11px; color:#FBBF24; font-weight:600;">£{p["bank_remaining"]:.1f}m</span>'
            f'</div>'
            f'{transfer_desc}'
            f'<div style="display:flex; justify-content:space-between; align-items:center; font-size:11px; color:#94A3B8; margin-top:4px; padding-top:4px; border-top:1px solid rgba(148, 163, 184, 0.1);">'
            f'<span>(C) <strong style="color:#E2E8F0;">{cap_name}</strong></span>'
            f'<span class="mono-num" style="color:#34D399; font-weight:700;">{p["total_xp"]:.1f} xP</span>'
            f'</div>'
            f'</div>'
        )
        steps_html.append(step)

    active_chips = [f"{p['chip']} (GW {p['gw']})" for p in plans if p["chip"]]
    chip_note = (
        f"ชิปตามแผน: <strong style='color:#FCD34D;'>{html.escape(', '.join(active_chips))}</strong>"
        if active_chips
        else "ยังเก็บชิปไว้ใช้ช่วง Double / Blank GW"
    )

    card_html = (
        f'<div class="fpl-roadmap-wrap">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:10px;">'
        f'<div style="display:flex; align-items:baseline; gap:10px;">'
        f'<span style="font-size:14px; font-weight:700; color:#F8FAFC;">แผนระยะ {len(plans)} สัปดาห์</span>'
        f'<span class="mono-num" style="font-size:12.5px; color:#94A3B8;">รวม <strong style="color:#34D399;">{total_xp:.1f} xP</strong></span>'
        f'</div>'
        f'<div style="font-size:11.5px; color:#CBD5E1; background:#0B0F17; border:1px solid rgba(148,163,184,0.14); padding:3px 10px; border-radius:999px;">{chip_note}</div>'
        f'</div>'
        f'<div class="fpl-scroll-x">{"".join(steps_html)}</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def render_transfer_cards(plan: dict):
    """แสดงคู่การย้ายตัวเข้า-ออกแบบ Card เรียงตามตำแหน่ง"""
    gw = plan["gw"]
    t_out = list(plan["transfers_out"])
    t_in = list(plan["transfers_in"])

    if not t_in and not t_out:
        st.markdown(
            """
            <div class="fpl-roll-card">
                <span style="font-size:13px; color:#E2E8F0; font-weight:600;">Roll Free Transfer — ไม่ย้ายตัวในสัปดาห์นี้</span>
                <span style="font-size:11.5px; color:#94A3B8;">เก็บโควตาไปเพิ่มความยืดหยุ่นสัปดาห์ถัดไป</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if plan["chip"] == "FH":
        st.caption("Free Hit ทำงาน: เปลี่ยนผู้เล่นชั่วคราวเฉพาะ Gameweek นี้เท่านั้น")

    # จับคู่ตามตำแหน่งก่อน แล้วค่อยจับคู่ตามลำดับที่เหลือ
    remaining_in = list(t_in)
    pairs = []
    unmatched_out = []
    for pout in t_out:
        match_idx = next((i for i, pin in enumerate(remaining_in) if pin["pos_id"] == pout["pos_id"]), None)
        if match_idx is not None:
            pairs.append((pout, remaining_in.pop(match_idx)))
        else:
            unmatched_out.append(pout)

    for pout, pin in zip(unmatched_out, remaining_in):
        pairs.append((pout, pin))

    cards_html = []
    for pout, pin in pairs:
        xp_diff = pin["xp_by_gw"].get(gw, 0.0) - pout["xp_by_gw"].get(gw, 0.0)
        cost_diff = pin["buy_price"] - pout["sell_price"]
        xp_color = "#34D399" if xp_diff >= 0 else "#F87171"
        cost_str = f"{cost_diff:+.1f}m"

        cards_html.append(
            f'<div class="fpl-transfer-card">'
            f'<div style="flex:1; min-width:0;">'
            f'<div style="font-size:10px; font-weight:700; color:#F87171; letter-spacing:0.04em;">OUT · {html.escape(pout["position"])}</div>'
            f'<div style="font-size:13px; font-weight:700; color:#F8FAFC; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{html.escape(pout["web_name"])}</div>'
            f'<div class="mono-num" style="font-size:11px; color:#94A3B8;">{html.escape(pout["team"])} · £{pout["sell_price"]:.1f}m · {pout["xp_by_gw"].get(gw, 0.0):.1f} xP</div>'
            f'</div>'
            f'<div style="text-align:center; padding:0 6px;">'
            f'<div style="font-size:14px; color:#64748B; font-weight:700;">→</div>'
            f'<div class="mono-num" style="font-size:10.5px; font-weight:700; color:{xp_color};">{xp_diff:+.1f} xP</div>'
            f'<div class="mono-num" style="font-size:10px; color:#94A3B8;">{cost_str}</div>'
            f'</div>'
            f'<div style="flex:1; min-width:0; text-align:right;">'
            f'<div style="font-size:10px; font-weight:700; color:#34D399; letter-spacing:0.04em;">IN · {html.escape(pin["position"])}</div>'
            f'<div style="font-size:13px; font-weight:700; color:#F8FAFC; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{html.escape(pin["web_name"])}</div>'
            f'<div class="mono-num" style="font-size:11px; color:#94A3B8;">{html.escape(pin["team"])} · £{pin["buy_price"]:.1f}m · {pin["xp_by_gw"].get(gw, 0.0):.1f} xP</div>'
            f'</div>'
            f'</div>'
        )

    st.markdown(f'<div class="fpl-transfer-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)

    if plan["hits"] > 0:
        st.caption(f"หมายเหตุ: แผนสัปดาห์นี้มีการย้ายเกินโควตา {plan['hits']} ครั้ง (เสีย -{plan['hits'] * 4} แต้ม)")


def generate_player_card_html(
    p: dict,
    gw: int,
    captain_id: int,
    vice_id: int,
    chip: str,
    locked_ids: list = None,
    liked_team_ids: list = None,
) -> str:
    """การ์ดนักเตะบนผังสนามพร้อมข้อมูลคู่แข่ง, FDR, สัญลักษณ์ Lock/ทีมชอบ และ xP"""
    badge_html = ""
    if p["id"] == captain_id:
        label = "TC" if chip == "TC" else "C"
        bg = "#EA580C" if chip == "TC" else "#F59E0B"
        fg = "#FFFFFF" if chip == "TC" else "#090D16"
        badge_html = (
            f'<div class="fpl-card-badge" style="position:absolute; top:-7px; right:-5px; background:{bg}; color:{fg}; '
            f'font-weight:800; border-radius:999px; border:1px solid #0B0F17; z-index:2;">{label}</div>'
        )
    elif p["id"] == vice_id:
        badge_html = (
            '<div class="fpl-card-badge" style="position:absolute; top:-7px; right:-5px; background:#334155; color:#F8FAFC; '
            'font-weight:700; border-radius:999px; border:1px solid #0B0F17; z-index:2;">VC</div>'
        )

    left_badges = []
    if locked_ids and p["id"] in locked_ids:
        left_badges.append(
            '<span class="fpl-card-badge" style="background:#1D4ED8; color:#DBEAFE; font-weight:700; border-radius:4px;">LOCK</span>'
        )
    elif liked_team_ids and p.get("team_id") in liked_team_ids:
        left_badges.append(
            '<span class="fpl-card-badge" style="background:#065F46; color:#6EE7B7; font-weight:700; border-radius:4px;">FAV</span>'
        )

    if p.get("is_dgw", {}).get(gw, False):
        left_badges.append(
            '<span class="fpl-card-badge" style="background:#7C2D12; color:#FDBA74; font-weight:700; border-radius:4px;">2x</span>'
        )

    left_badge_html = (
        f'<div style="position:absolute; top:-7px; left:-4px; display:flex; gap:2px; z-index:2;">{"".join(left_badges)}</div>'
        if left_badges
        else ""
    )

    fix_full = p["fixtures"].get(gw, "-")
    fix_short, fdr_color = _parse_next_fixture(fix_full)
    xp = p["xp_by_gw"].get(gw, 0.0)

    pos_colors = {1: "#EAB308", 2: "#3B82F6", 3: "#10B981", 4: "#EF4444"}
    border_color = pos_colors.get(p["pos_id"], "#64748B")

    name_esc = html.escape(p["web_name"])
    fix_esc = html.escape(fix_short)
    title_esc = html.escape(f"{p['web_name']} ({p['team']}) | {fix_full}")

    return (
        f'<div class="fpl-card" style="border-top:3px solid {border_color};" title="{title_esc}">'
        f'{badge_html}'
        f'{left_badge_html}'
        f'<div class="card-name">{name_esc}</div>'
        f'<div class="card-fix">'
        f'<span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:{fdr_color}; flex-shrink:0;"></span>'
        f'<span>{fix_esc}</span>'
        f'</div>'
        f'<div class="card-xp">{xp:.1f} xP</div>'
        f'</div>'
    )


def render_pitch_view(plan: dict, locked_ids: list = None, liked_team_ids: list = None):
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

    if chip == "BB":
        formation_caption = "Bench Boost Active — นับคะแนนครบทั้ง 15 คน"
    else:
        formation_caption = f"ระบบการเล่น: **{len(defs)}-{len(mids)}-{len(fwds)}**"

    def make_row(row_players):
        if not row_players:
            return ""
        cards = "".join([
            generate_player_card_html(p, gw, cap_id, vice_id, chip, locked_ids, liked_team_ids)
            for p in row_players
        ])
        return f'<div class="fpl-pitch-row">{cards}</div>'

    pitch_html = textwrap.dedent(
        f"""
<div class="fpl-pitch">
    <div style="position:absolute; top:50%; left:4%; right:4%; height:1px; background:rgba(255,255,255,0.14);"></div>
    <div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:58px; height:58px; border:1px solid rgba(255,255,255,0.14); border-radius:50%;"></div>
    {make_row(gkps)}
    {make_row(defs)}
    {make_row(mids)}
    {make_row(fwds)}
</div>
        """
    ).strip()

    st.caption(formation_caption)
    st.markdown(pitch_html, unsafe_allow_html=True)

    if chip != "BB" and bench:
        bench_labels = ["GK Sub", "Bench 1", "Bench 2", "Bench 3"]
        bench_cards = "".join([
            f'<div class="fpl-bench-slot">'
            f'<span style="color:#94A3B8; font-size:10px; font-weight:600; margin-bottom:4px;">{label}</span>'
            f'{generate_player_card_html(p, gw, cap_id, vice_id, chip, locked_ids, liked_team_ids)}'
            f'</div>'
            for label, p in zip(bench_labels, bench)
        ])

        bench_html = textwrap.dedent(
            f"""
<div class="fpl-bench-wrap">
    {bench_cards}
</div>
            """
        ).strip()
        st.caption("ม้านั่งสำรอง (เรียงตามลำดับ Auto-Sub)")
        st.markdown(bench_html, unsafe_allow_html=True)


def render_chip_advisor(
    plans: list,
    my_squad: list,
    dgw_bgw_info: dict,
    bank: float,
    custom_ft: int,
    next_gw: int,
):
    """วิเคราะห์เหตุผลเรื่องชิปจากข้อมูลจริงของทีม (ไม่มีตัวเลข hardcode)"""
    gw1_plan = plans[0]
    active_chip = gw1_plan.get("chip")
    flagged = [
        p for p in my_squad
        if p.get("status") in ("i", "s", "u", "d") or p.get("xmins", 90.0) < 45.0
    ]
    dgw_gws = [str(gw) for gw, info in (dgw_bgw_info or {}).items() if info.get("dgw")]
    bgw_gws = [str(gw) for gw, info in (dgw_bgw_info or {}).items() if len(info.get("bgw", [])) >= 2]

    with st.expander("คำอธิบายกลยุทธ์ชิป (Chip Advisor)", expanded=False):
        if active_chip:
            st.success(
                f"เปิดใช้งาน **{active_chip}** ใน GW {gw1_plan['gw']} — คาดการณ์คะแนนสุทธิ **{gw1_plan['total_xp']:.1f} xP**"
            )
            return

        notes = []
        if dgw_gws:
            notes.append(f"- พบ **Double Gameweek** ใน GW {', '.join(dgw_gws)} แต่เกณฑ์ความคุ้มค่าในสัปดาห์นี้ยังไม่ผ่านจุดคุ้มทุนของชิป")
        else:
            notes.append("- ในช่วงสัปดาห์ที่ประเมิน **ยังไม่มี Double Gameweek** การเก็บ Triple Captain และ Bench Boost ไว้ใช้รอบที่เตะ 2 นัดจะให้ผลตอบแทนสูงกว่า")

        notes.append(
            f"- ทีมปัจจุบันมีเงินในคลัง **£{bank:.1f}M**, โควตา **{custom_ft} FT** "
            f"และคาดว่าจะทำได้ **{gw1_plan['total_xp']:.1f} xP** ใน GW {gw1_plan['gw']} "
            f"(พบผู้เล่นที่มีความเสี่ยงลงสนาม/เจ็บ **{len(flagged)} คน**)"
        )

        if bgw_gws:
            notes.append(f"- พบ **Blank Gameweek** ใน GW {', '.join(bgw_gws)} — ตรวจสอบจำนวนตัวจริงที่ลงแข่งได้ก่อนตัดสินใจใช้ Free Hit")

        if next_gw < 20:
            wc_left = 20 - next_gw
            notes.append(f"- **Wildcard ใบแรก** หมดเขตสิ้นสุด GW 19 (เหลือเวลาอีก {wc_left} สัปดาห์)")
        else:
            notes.append("- **Wildcard ใบที่สอง** ใช้ได้ถึง GW 38 เหมาะสำหรับจังหวะวางโครงรับช่วงปลายฤดูกาลหรือ DGW ใหญ่")

        st.markdown("\n".join(notes))


def render_top_captains(plan: dict):
    """แสดงตัวเลือกกัปตัน 3 อันดับแรกใน 11 ตัวจริงของสัปดาห์นั้น"""
    gw = plan["gw"]
    starters = plan.get("starters", [])
    if not starters:
        return

    ranked = sorted(
        starters,
        key=lambda p: (
            p["xp_by_gw"].get(gw, 0.0),
            p.get("xmins_by_gw", {}).get(gw, p.get("xmins", 0.0)),
        ),
        reverse=True,
    )[:3]

    cap_id = plan["captain"]["id"]
    vice_id = plan["vice_captain"]["id"]
    is_tc = plan.get("chip") == "TC"
    cap_mult = 3 if is_tc else 2
    mult_label = "3x" if is_tc else "2x"

    cards_html = []
    for idx, p in enumerate(ranked, 1):
        xp = p["xp_by_gw"].get(gw, 0.0)
        cap_xp = xp * cap_mult
        xmins = p.get("xmins_by_gw", {}).get(gw, p.get("xmins", 0.0))
        fix_short, fdr_color = _parse_next_fixture(p["fixtures"].get(gw, "-"))

        if p["id"] == cap_id:
            role_tag = "TC" if is_tc else "C"
            badge_style = "background:rgba(245, 158, 11, 0.18); color:#FCD34D; border:1px solid rgba(245, 158, 11, 0.4);"
        elif p["id"] == vice_id:
            role_tag = "VC"
            badge_style = "background:rgba(148, 163, 184, 0.16); color:#E2E8F0; border:1px solid rgba(148, 163, 184, 0.3);"
        else:
            role_tag = f"#{idx}"
            badge_style = "background:#0B0F17; color:#94A3B8; border:1px solid rgba(148, 163, 184, 0.2);"

        cards_html.append(
            f'<div class="fpl-cap-card">'
            f'<div style="min-width:0;">'
            f'<div style="display:flex; align-items:center; gap:6px;">'
            f'<span style="font-size:10px; font-weight:800; padding:1px 6px; border-radius:999px; {badge_style}">{role_tag}</span>'
            f'<span style="font-size:13px; font-weight:700; color:#F8FAFC; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{html.escape(p["web_name"])}</span>'
            f'</div>'
            f'<div style="font-size:11px; color:#94A3B8; margin-top:3px; display:flex; align-items:center; gap:5px;">'
            f'<span>{html.escape(p["team"])}</span>'
            f'<span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:{fdr_color};"></span>'
            f'<span>{html.escape(fix_short)} · {xmins:.0f} น.</span>'
            f'</div>'
            f'</div>'
            f'<div style="text-align:right; flex-shrink:0;">'
            f'<div class="mono-num" style="font-size:13px; font-weight:700; color:#34D399;">{cap_xp:.1f} xP</div>'
            f'<div class="mono-num" style="font-size:10.5px; color:#94A3B8;">({xp:.1f} × {mult_label})</div>'
            f'</div>'
            f'</div>'
        )

    st.caption("ตัวเลือกกัปตัน Top 3 ประจำสัปดาห์")
    st.markdown(f'<div class="fpl-cap-grid">{"".join(cards_html)}</div>', unsafe_allow_html=True)


def render_fixture_ticker(teams_info: dict, fixture_details: dict, target_gws: list):
    """ตารางความยากโปรแกรมล่วงหน้า (Fixture Difficulty Ticker) เรียงจากง่ายไปยาก"""
    if not teams_info or not fixture_details or not target_gws:
        st.info("ไม่มีข้อมูลโปรแกรมแข่งขันสำหรับสร้าง Fixture Ticker")
        return

    def _fdr_colors(fdr_val: float) -> tuple[str, str, str]:
        if fdr_val <= 2.3:
            return "rgba(16, 185, 129, 0.16)", "#34D399", "rgba(16, 185, 129, 0.35)"
        if fdr_val <= 3.3:
            return "rgba(245, 158, 11, 0.15)", "#FCD34D", "rgba(245, 158, 11, 0.35)"
        return "rgba(239, 68, 68, 0.16)", "#FCA5A5", "rgba(239, 68, 68, 0.35)"

    rows = []
    for tid, tinfo in teams_info.items():
        t_fix = fixture_details.get(tid, {})
        gw_cells = []
        diffs = []

        for gw in target_gws:
            matches = t_fix.get(gw, [])
            if not matches:
                diffs.append(5.5)
                gw_cells.append(
                    '<td><span class="fpl-fdr-pill" style="background:rgba(100,116,139,0.18); color:#94A3B8; border:1px solid rgba(100,116,139,0.3);">BLANK</span></td>'
                )
            elif len(matches) == 1:
                m = matches[0]
                fdr = float(m.get("fdr", 3))
                diffs.append(fdr)
                bg, fg, bd = _fdr_colors(fdr)
                venue = "H" if m.get("is_home") else "A"
                label = f"{m['opp']} ({venue})"
                gw_cells.append(
                    f'<td><span class="fpl-fdr-pill" style="background:{bg}; color:{fg}; border:1px solid {bd};">{html.escape(label)}</span></td>'
                )
            else:
                avg_m_fdr = sum(float(m.get("fdr", 3)) for m in matches) / len(matches)
                diffs.append(max(1.0, avg_m_fdr - 0.4))
                bg, fg, bd = _fdr_colors(avg_m_fdr)
                labels = [f"{m['opp']}({'H' if m.get('is_home') else 'A'})" for m in matches[:2]]
                gw_cells.append(
                    f'<td><span class="fpl-fdr-pill" style="background:{bg}; color:{fg}; border:1px solid {bd};">2x {" + ".join(html.escape(x) for x in labels)}</span></td>'
                )

        avg_diff = sum(diffs) / len(target_gws)
        rows.append((avg_diff, tinfo["name"], tinfo["short_name"], gw_cells))

    rows.sort(key=lambda r: (r[0], r[1]))

    gw_headers = "".join(f"<th>GW {gw}</th>" for gw in target_gws)
    body_rows = []
    for avg_diff, full_name, short_name, gw_cells in rows:
        _, avg_fg, _ = _fdr_colors(avg_diff)
        body_rows.append(
            f"<tr>"
            f"<td><strong style='color:#F8FAFC;'>{html.escape(short_name)}</strong> <span style='color:#94A3B8; font-size:11px;'>{html.escape(full_name)}</span></td>"
            f"{''.join(gw_cells)}"
            f"<td class='mono-num' style='font-weight:700; color:{avg_fg};'>{avg_diff:.2f}</td>"
            f"</tr>"
        )

    table_html = (
        f'<div class="fpl-ticker-wrap">'
        f'<table class="fpl-ticker-table">'
        f'<thead><tr><th>ทีม</th>{gw_headers}<th>เฉลี่ย FDR</th></tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        f'</table>'
        f'</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)
