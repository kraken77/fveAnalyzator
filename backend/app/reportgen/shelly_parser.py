import io
import re
import pandas as pd
from datetime import datetime
from typing import List, Dict, Tuple

# Supported block titles (case-insensitive, stripped)
# Consumption: "Fáze A", "Fáze B", "Fáze C", "Total", "Celkem"
# Voltage: "phase A min voltage" etc.
# Also English consumption: "Phase A"

def _normalize_title(t: str) -> str:
    return t.strip().lower()

def _classify_block(title: str):
    # strip BOM and whitespace
    clean = title.strip().lstrip("\ufeff").strip()
    lt = clean.lower()
    # voltage
    if "voltage" in lt:
        m = re.search(r"phase\s*([abc])\s*(min|max)", lt)
        if m:
            phase = m.group(1).upper()
            kind = m.group(2)
            return {"metric": "voltage", "phase": phase, "kind": kind, "raw": clean}
        return {"metric": "voltage", "phase": None, "kind": None, "raw": clean}
    # export / přetok (must check before general consumption)
    is_export = any(x in lt for x in ["přetok", "pretok", "vráceno", "vraceno", "export", "feed", "returned"])
    # consumption
    m = re.search(r"fáze\s*([abc])|phase\s*([abc])", lt)
    if m:
        phase = (m.group(1) or m.group(2)).upper()
        if is_export:
            return {"metric": "export", "phase": phase, "kind": "wh", "raw": clean}
        return {"metric": "consumption", "phase": phase, "kind": "wh", "raw": clean}
    if "total" in lt or "celkem" in lt or "sum" in lt:
        if is_export:
            return {"metric": "export", "phase": "TOTAL", "kind": "wh", "raw": clean}
        return {"metric": "consumption", "phase": "TOTAL", "kind": "wh", "raw": clean}
    return {"metric": "consumption", "phase": None, "kind": None, "raw": clean}

def parse_shelly_csv(content: bytes) -> Dict:
    """
    Parse Shelly CSV with BOM and block structure.
    Returns dict with blocks, gaps, complete_days, warnings.
    """
    text = content.decode("utf-8-sig")  # strips BOM
    lines = text.splitlines()
    blocks = []
    i = 0
    n = len(lines)
    warnings = []
    all_dates = set()

    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # Detect title row: not "Time" and not "Čas" and contains letters
        # Title rows are like " phase A min voltage" or " Fáze A"
        # Header rows are " Time, V " or " Čas, Wh "
        low = line.lower()
        if "time" in low and (" v " in low or ",v" in low or "wh" in low or " v" in low):
            # This is header but we expected title before — skip
            i += 1
            continue
        # Check if line looks like header: contains "Time" or "Čas" and comma
        is_header = ("time" in low or "čas" in low) and "," in line
        if is_header:
            # Missing title — treat previous as unknown
            warnings.append(f"Blok bez titulku na řádku {i+1}")
            i += 1
            continue
        # Potential title
        # Look ahead: next non-empty line should be header
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        if j < n and (("time" in lines[j].lower() or "čas" in lines[j].lower()) and "," in lines[j]):
            title = line
            header = lines[j].strip()
            meta = _classify_block(title)
            # Parse data rows until next title or EOF
            data_rows = []
            k = j + 1
            while k < n:
                row = lines[k].strip()
                if not row:
                    k += 1
                    continue
                # Peek if this looks like a title for next block
                # Titles don't contain comma+number pattern typical of data? Titles have no comma+value? Voltage titles no comma? Actually voltage title has no comma. So we check.
                # Data rows are like " 14/07/2026 00:00 , 235.34 "
                # Titles never match dd/mm/yyyy
                if re.match(r"\s*\d{1,2}/\d{1,2}/\d{4}", row):
                    # data row
                    parts = row.split(",")
                    if len(parts) >= 2:
                        date_str = parts[0].strip()
                        val_str = parts[1].strip()
                        try:
                            dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                        except ValueError:
                            try:
                                dt = datetime.strptime(date_str, "%d.%m.%Y %H:%M")
                            except:
                                warnings.append(f"Neplatné datum '{date_str}' v bloku '{title.strip()}'")
                                k += 1
                                continue
                        try:
                            val = float(val_str.replace(" ", "")) if val_str else 0.0
                        except:
                            val = 0.0
                        # 0 = missing if metric is voltage/consumption daily? Keep as is but flag
                        is_missing = (val == 0)
                        data_rows.append({"datetime": dt, "value": val, "missing": is_missing})
                        all_dates.add(dt.date())
                    k += 1
                else:
                    # Might be next title
                    # Check if next line after this is header-like
                    peek = k + 1
                    while peek < n and not lines[peek].strip():
                        peek += 1
                    if peek < n and ("time" in lines[peek].lower() or "čas" in lines[peek].lower()) and "," in lines[peek]:
                        # This row is title of next block
                        break
                    else:
                        # Unknown line, skip
                        warnings.append(f"Neočekávaný řádek '{row[:50]}' v bloku '{title.strip()}'")
                        k += 1
            df = pd.DataFrame(data_rows)
            if not df.empty:
                df = df.sort_values("datetime")
            blocks.append({
                "title": title.strip(),
                "meta": meta,
                "header": header,
                "df": df,
            })
            i = k
        else:
            # Not a block start, skip
            i += 1

    # Analyze completeness
    # Determine date range
    if all_dates:
        sorted_dates = sorted(all_dates)
        first = sorted_dates[0]
        last = sorted_dates[-1]
        # Detect gaps: dates with all blocks missing
        # For simplicity, gaps = dates where every block has missing or no entry
        date_to_has_data = {}
        for d in sorted_dates:
            has = False
            for b in blocks:
                df = b["df"]
                if df.empty:
                    continue
                row = df[df["datetime"].dt.date == d]
                if not row.empty and not row.iloc[0]["missing"]:
                    has = True
                    break
            date_to_has_data[d] = has
        gaps = [d for d, has in date_to_has_data.items() if not has]
        # Complete days: has data and not first/last (incomplete per spec)
        complete_days = [d for d, has in date_to_has_data.items() if has and d != first and d != last]
        # If only one date, no complete days
        warnings_gaps = []
        if gaps:
            warnings.append(f"Chybějící měření (0) ve dnech: {', '.join(str(d) for d in gaps)}")
    else:
        gaps = []
        complete_days = []
        first = last = None

    return {
        "blocks": blocks,
        "gaps": gaps if all_dates else [],
        "complete_days": complete_days if all_dates else [],
        "warnings": warnings,
        "all_dates": sorted(all_dates) if all_dates else [],
    }

def merge_parsed_results(results: List[Dict]) -> Dict:
    """
    Merge multiple parsed CSV results (multiple files).
    Checks duplicates.
    """
    merged_blocks = {}  # key: (metric, phase, kind) -> DataFrame
    all_warnings = []
    all_gaps_set = set()
    all_complete = set()
    all_dates_set = set()

    for res in results:
        all_warnings.extend(res.get("warnings", []))
        for b in res["blocks"]:
            key = (b["meta"]["metric"], b["meta"]["phase"], b["meta"]["kind"])
            # Use title as fallback key if phase None
            if key[1] is None:
                key = (b["meta"]["metric"], b["title"], b["meta"]["kind"])
            df = b["df"]
            if key not in merged_blocks:
                merged_blocks[key] = df.copy() if not df.empty else df
            else:
                # Check duplicates
                existing = merged_blocks[key]
                if not existing.empty and not df.empty:
                    dup_dates = set(existing["datetime"].dt.date) & set(df["datetime"].dt.date)
                    if dup_dates:
                        raise ValueError(f"Duplicitní data pro {key} ve dnech: {sorted(dup_dates)[:5]}")
                    merged_blocks[key] = pd.concat([existing, df], ignore_index=True).sort_values("datetime")
                elif not df.empty:
                    merged_blocks[key] = df.copy()
        all_gaps_set.update(res.get("gaps", []))
        all_complete.update(res.get("complete_days", []))
        all_dates_set.update(res.get("all_dates", []))

    # Re-sort merged blocks
    blocks_list = []
    for key, df in merged_blocks.items():
        # recover meta
        # Find original meta by looking up one of the results
        meta = None
        title = str(key)
        for res in results:
            for b in res["blocks"]:
                k2 = (b["meta"]["metric"], b["meta"]["phase"], b["meta"]["kind"])
                if b["meta"]["phase"] is None:
                    k2 = (b["meta"]["metric"], b["title"], b["meta"]["kind"])
                if k2 == key:
                    meta = b["meta"]
                    title = b["title"]
                    break
            if meta:
                break
        df_sorted = df.sort_values("datetime") if not df.empty else df
        blocks_list.append({"title": title, "meta": meta or {}, "df": df_sorted, "header": ""})

    sorted_dates = sorted(all_dates_set)
    if sorted_dates:
        first, last = sorted_dates[0], sorted_dates[-1]
        # Recompute gaps/complete based on merged data
        date_to_has = {}
        for d in sorted_dates:
            has = False
            for b in blocks_list:
                df = b["df"]
                if df.empty:
                    continue
                row = df[df["datetime"].dt.date == d]
                if not row.empty and not row.iloc[0]["missing"]:
                    has = True
                    break
            date_to_has[d] = has
        gaps = [d for d, has in date_to_has.items() if not has]
        complete_days = [d for d, has in date_to_has.items() if has and d != first and d != last]
    else:
        gaps = []
        complete_days = []

    return {
        "blocks": blocks_list,
        "gaps": gaps,
        "complete_days": complete_days,
        "warnings": all_warnings,
        "all_dates": sorted_dates,
    }

def extract_consumption_totals(parsed: Dict):
    """
    Extract consumption totals (Wh -> kWh) for KPI calculation.
    Prefers TOTAL block if exists, otherwise sum of phases.
    Returns DataFrame with columns date, total_kwh, phase_a, phase_b, phase_c, missing
    """
    # Find consumption blocks
    cons_blocks = [b for b in parsed["blocks"] if b["meta"].get("metric") == "consumption"]
    if not cons_blocks:
        return pd.DataFrame()

    # Map phase -> df
    phase_map = {}
    for b in cons_blocks:
        ph = b["meta"].get("phase")
        if ph:
            phase_map[ph] = b["df"]

    # Collect all dates
    all_dates = set()
    for df in phase_map.values():
        if not df.empty:
            all_dates.update(df["datetime"].dt.date)

    rows = []
    for d in sorted(all_dates):
        vals = {}
        missing = False
        for ph in ["A", "B", "C", "TOTAL"]:
            df = phase_map.get(ph)
            if df is not None and not df.empty:
                row = df[df["datetime"].dt.date == d]
                if not row.empty:
                    v = row.iloc[0]["value"]
                    m = row.iloc[0]["missing"]
                    vals[ph] = v
                    if m:
                        missing = True
                else:
                    vals[ph] = None
            else:
                vals[ph] = None

        # Determine total_kwh
        # Values are in Wh (per spec "Čas, Wh"), convert to kWh; but voltage values are V - not consumption
        # Only use if we have consumption metric
        # If TOTAL exists, use it
        total_wh = vals.get("TOTAL")
        if total_wh is not None and total_wh != 0:
            total_kwh = total_wh / 1000.0
        else:
            # Sum phases A/B/C if available and not missing
            s = 0
            has_any = False
            for ph in ["A", "B", "C"]:
                v = vals.get(ph)
                if v is not None:
                    s += v
                    has_any = True
            total_kwh = s / 1000.0 if has_any else None

        rows.append({
            "date": d,
            "total_kwh": total_kwh,
            "phase_a_wh": vals.get("A"),
            "phase_b_wh": vals.get("B"),
            "phase_c_wh": vals.get("C"),
            "missing": missing,
        })

    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.sort_values("date")
    return df_out
