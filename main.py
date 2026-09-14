from config import MY_TEAM_ID
from fpl_api import fetch_fpl_data_multi
from optimizer import solve_multi_period_fpl


def display_multi_plan(plans: list):
    print("\n" + "=" * 65)
    print("        FPL STRATEGIC ROADMAP & CHIP ADVISOR")
    print("=" * 65)

    for plan in plans:
        gw = plan["gw"]
        chip_badge = f" [*** USE CHIP: {plan['chip']} ***]" if plan["chip"] else ""
        print(
            f"\n>>> [ GAMEWEEK {gw} ] (Free Transfers: {plan['ft_available']} | Bank: £{plan['bank_remaining']:.1f}M){chip_badge}")
        print("-" * 65)

        if not plan["transfers_in"]:
            print("  [Transfers]: ไม่มีย้ายตัว (Roll Free Transfer)")
        else:
            outs = [f"{p['web_name']} ({p['team']})" for p in plan["transfers_out"]]
            ins = [f"{p['web_name']} ({p['team']})" for p in plan["transfers_in"]]
            print(f"  [Transfers OUT]: {', '.join(outs)}")
            print(f"  [Transfers IN ]: {', '.join(ins)}")
            if plan["hits"] > 0:
                print(f"  * ยอมเสียแต้มลบ (Hits): -{plan['hits'] * 4} pts")

        xi_names = []
        is_tc = plan["chip"] == "TC"
        for p in plan["starters"]:
            tag = ""
            if p["id"] == plan["captain"]["id"]:
                tag = "(TC)" if is_tc else "(C)"
            elif p["id"] == plan["vice_captain"]["id"]:
                tag = "(VC)"
            xi_names.append(f"{p['web_name']}{tag}")

        print(f"  [Starting XI  ]: {', '.join(xi_names)}")

        if plan["chip"] == "BB":
            print("  [Bench        ]: ได้คะแนนครบ 15 คน (เปิดใช้งาน Bench Boost)")
        else:
            bench_names = [f"{p['web_name']}" for p in plan["bench"]]
            print(
                f"  [Bench Order  ]: GK: {bench_names[0]} | B1: {bench_names[1]} | B2: {bench_names[2]} | B3: {bench_names[3]}")

    print("\n" + "=" * 65 + "\n")


def main():
    try:
        players, my_team, bank, initial_ft, target_gws, chips_available = fetch_fpl_data_multi(MY_TEAM_ID)
        plans = solve_multi_period_fpl(players, my_team, bank, initial_ft, target_gws, chips_available, max_hits_per_gw=0)
        display_multi_plan(plans)
    except Exception as err:
        print(f"\n[เกิดข้อผิดพลาดในการรันระบบ]: {err}")


if __name__ == "__main__":
    main()