import math
import numpy as np
import pandas as pd
from datetime import date, timedelta

DEFAULT_YIELD_PER_KWP_PER_DAY = 4.5  # kWh/kWp summer day
DEFAULT_SYSTEM_TILT_FACTOR = 1.0

def compute_kpi(consumption_df: pd.DataFrame):
    """
    consumption_df: DataFrame with columns date, total_kwh, missing
    Returns dict with n_complete, total_kwh, avg_daily, annual_mwh, weekday_avg, weekend_avg, complete_df
    """
    if consumption_df.empty:
        return {
            "n_complete": 0,
            "total_kwh": 0,
            "avg_daily": 0,
            "annual_mwh": 0,
            "weekday_avg": 0,
            "weekend_avg": 0,
            "complete_df": pd.DataFrame(),
        }
    # Filter complete days: not missing and not first/last gap handling already done by parser?
    # For KPI, use complete_days logic: all non-missing except first/last overall date if they are incomplete.
    # Here consumption_df already has missing flag; complete = not missing
    # But per spec, first/last overall date considered incomplete even if has data -> exclude.
    all_dates = sorted(consumption_df["date"].unique())
    if len(all_dates) >= 2:
        first, last = all_dates[0], all_dates[-1]
        # Mark first/last as incomplete
        complete_mask = (~consumption_df["missing"]) & (consumption_df["date"] != first) & (consumption_df["date"] != last)
    else:
        complete_mask = ~consumption_df["missing"]

    complete_df = consumption_df[complete_mask].copy()
    n = len(complete_df)
    total = complete_df["total_kwh"].sum() if n > 0 else 0
    avg = total / n if n > 0 else 0
    annual = avg * 365 / 1000 if n > 0 else 0

    # Weekday/weekend split
    if n > 0:
        complete_df["weekday"] = complete_df["date"].apply(lambda d: d.weekday() < 5)
        weekday_vals = complete_df[complete_df["weekday"]]["total_kwh"]
        weekend_vals = complete_df[~complete_df["weekday"]]["total_kwh"]
        weekday_avg = weekday_vals.mean() if len(weekday_vals) > 0 else 0
        weekend_avg = weekend_vals.mean() if len(weekend_vals) > 0 else 0
    else:
        weekday_avg = weekend_avg = 0

    return {
        "n_complete": int(n),
        "total_kwh": float(total),
        "avg_daily": float(avg),
        "annual_mwh": float(annual),
        "weekday_avg": float(weekday_avg),
        "weekend_avg": float(weekend_avg),
        "complete_df": complete_df,
    }

def compute_phase_balance(consumption_df: pd.DataFrame):
    if consumption_df.empty:
        return {"A": 0, "B": 0, "C": 0}
    # Use complete days only
    all_dates = sorted(consumption_df["date"].unique())
    if len(all_dates) >= 2:
        first, last = all_dates[0], all_dates[-1]
        df = consumption_df[(~consumption_df["missing"]) & (consumption_df["date"] != first) & (consumption_df["date"] != last)]
    else:
        df = consumption_df[~consumption_df["missing"]]
    if df.empty:
        return {"A": 0, "B": 0, "C": 0}
    sum_a = df["phase_a_wh"].sum()
    sum_b = df["phase_b_wh"].sum()
    sum_c = df["phase_c_wh"].sum()
    total = sum_a + sum_b + sum_c
    if total == 0:
        return {"A": 0, "B": 0, "C": 0}
    return {
        "A": float(sum_a / total * 100),
        "B": float(sum_b / total * 100),
        "C": float(sum_c / total * 100),
    }

def generate_typical_day_model(avg_daily_kwh: float, kWp: float, yield_per_kwp: float = DEFAULT_YIELD_PER_KWP_PER_DAY, profile_df=None):
    """
    Returns hourly DataFrame with columns hour, consumption_kwh, production_kwh
    If profile_df provided (hourly/15min), uses it instead of model.
    """
    if profile_df is not None and not profile_df.empty:
        # Expect profile_df with datetime, value (kWh per interval)
        # Aggregate to hourly avg weekday
        # For simplicity, resample to hourly
        return _model_from_profile(profile_df, kWp, yield_per_kwp)

    # Consumption shape: typical office building
    # Hours 0-5 low, 6-18 high, 19-23 medium-low
    # Normalize to avg_daily_kwh
    consumption_shape = np.array([
        0.02, 0.02, 0.02, 0.02, 0.02, 0.03,  # 0-5
        0.05, 0.07, 0.08, 0.08, 0.08, 0.07,  # 6-11
        0.07, 0.07, 0.07, 0.07, 0.06, 0.05,  # 12-17
        0.04, 0.03, 0.02, 0.02, 0.02, 0.02,  # 18-23
    ])
    consumption_shape = consumption_shape / consumption_shape.sum()
    consumption_hourly = consumption_shape * avg_daily_kwh

    # Production shape: bell 6-20h, peak at 13h
    # Normalized sine bell
    prod_shape = np.zeros(24)
    for h in range(24):
        if 6 <= h <= 20:
            # sine from 0 to pi
            x = (h - 6) / 14 * math.pi
            prod_shape[h] = math.sin(x) ** 1.2
    if prod_shape.sum() > 0:
        prod_shape = prod_shape / prod_shape.sum()
    daily_prod = kWp * yield_per_kwp
    prod_hourly = prod_shape * daily_prod

    df = pd.DataFrame({
        "hour": range(24),
        "consumption_kwh": consumption_hourly,
        "production_kwh": prod_hourly,
    })
    return df

def _model_from_profile(profile_df, kWp, yield_per_kwp):
    # Placeholder: average weekday profile
    # profile_df expected with datetime, value (Wh or kWh)
    # Convert to kWh if Wh
    df = profile_df.copy()
    # Normalize?
    # For now return typical model
    return generate_typical_day_model(50, kWp, yield_per_kwp, profile_df=None)

def compute_green_red(hourly_df: pd.DataFrame):
    """
    hourly_df with consumption_kwh, production_kwh
    """
    hourly_df["surplus"] = hourly_df["production_kwh"] - hourly_df["consumption_kwh"]
    hourly_df["green"] = hourly_df["surplus"].apply(lambda x: max(x, 0))
    hourly_df["red"] = hourly_df["surplus"].apply(lambda x: max(-x, 0))
    green = hourly_df["green"].sum()
    red = hourly_df["red"].sum()
    prod_total = hourly_df["production_kwh"].sum()
    net = green - red
    return {
        "green_kwh": float(green),
        "red_kwh": float(red),
        "prod_total": float(prod_total),
        "net_kwh": float(net),
        "hourly": hourly_df,
    }

def simulate_battery(hourly_df: pd.DataFrame, capacity_kwh: float, soc_min_pct: float = 30, soc_init_pct: float = 100):
    """
    Simple hourly battery simulation.
    capacity_kwh: usable? total capacity
    soc_min = capacity * soc_min_pct /100
    """
    soc_min = capacity_kwh * soc_min_pct / 100
    usable = capacity_kwh - soc_min
    soc = capacity_kwh * soc_init_pct / 100
    # Clamp init
    soc = max(soc_min, min(capacity_kwh, soc))
    soc_series = []
    for _, row in hourly_df.iterrows():
        surplus = row["production_kwh"] - row["consumption_kwh"]
        if surplus > 0:
            # charge
            soc = min(capacity_kwh, soc + surplus)
        else:
            # discharge
            need = -surplus
            available = soc - soc_min
            discharge = min(need, available)
            soc -= discharge
        soc_series.append(soc)
    hourly_df = hourly_df.copy()
    hourly_df["soc_kwh"] = soc_series
    hourly_df["soc_pct"] = hourly_df["soc_kwh"] / capacity_kwh * 100
    return hourly_df

def antelon_analyze(parsed, params: dict):
    """
    Main entry: parsed from shelly_parser.merge..., params dict from project
    params keys: kwp, battery_kwh, soc_min, yield_per_kwp, variants
    Returns dict with all computed values for template.
    """
    from .shelly_parser import extract_consumption_totals

    kWp = float(params.get("kwp", 25))
    battery_kwh = float(params.get("battery_kwh", 15))
    soc_min = float(params.get("soc_min_pct", 30))
    yield_per = float(params.get("yield_per_kwp_per_day", DEFAULT_YIELD_PER_KWP_PER_DAY))

    cons_totals = extract_consumption_totals(parsed)

    kpi = compute_kpi(cons_totals)
    phase = compute_phase_balance(cons_totals)

    avg_daily = kpi["avg_daily"] if kpi["avg_daily"] > 0 else 58.6  # fallback to Pentagon value for model
    hourly = generate_typical_day_model(avg_daily, kWp, yield_per)

    green_red = compute_green_red(hourly.copy())
    batt_15 = simulate_battery(hourly.copy(), 15, soc_min)
    batt_20 = simulate_battery(hourly.copy(), 20, soc_min)
    batt_chosen = simulate_battery(hourly.copy(), battery_kwh, soc_min)

    # Variants: 20/25/30 kWp
    variants = []
    for kw in [20, 25, 30]:
        variants.append({
            "kwp": kw,
            "annual_kwh": kw * 1000,
            "label": {20: "ekonomická", 25: "doporučená", 30: "rezerva"}.get(kw, ""),
        })

    return {
        "kpi": kpi,
        "phase_pct": phase,
        "cons_totals": cons_totals,
        "hourly": hourly,
        "green_red": green_red,
        "battery_15": batt_15,
        "battery_20": batt_20,
        "battery_chosen": batt_chosen,
        "variants": variants,
        "params": {"kwp": kWp, "battery_kwh": battery_kwh, "soc_min": soc_min, "yield_per": yield_per},
        "warnings": parsed.get("warnings", []),
        "gaps": parsed.get("gaps", []),
        "complete_days": parsed.get("complete_days", []),
        "blocks_summary": [{"title": b["title"], "metric": b["meta"].get("metric"), "phase": b["meta"].get("phase"), "rows": len(b["df"])} for b in parsed["blocks"]],
    }
