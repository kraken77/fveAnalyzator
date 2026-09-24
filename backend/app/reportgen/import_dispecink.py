"""Import historických zakázek z Excelu „PROCESNÍ DISPEČINK" do pipeline (M1.3).

Pozice sloupců listu „Přehled" (0-indexované, pevný layout dle zdrojového
souboru):
  idx 1 = typ zakázky, 2 = technologie, 3 = příjmení, 4 = jméno,
  idx 5 = aktivní/neaktivní, idx 6..68 = kroky pipeline.
Sub-sloupce kontraktních kroků (SoD/plná moc/SOP/sdílení) a AI kroku
„Možnost bezúročné půjčky" (zadáno/hotovo) mají vlastní sloupec.
"""

import re
import unicodedata
from collections import defaultdict
from datetime import datetime, date, timedelta

import openpyxl

from .pipeline_seed import attach_template, TEMPLATE_CODE_BY_TYPE
from .storage import Project, ProjectStep, StepEvent, PipelineStep, generate_share_code

EXCEL_EPOCH = datetime(1899, 12, 30)
YEAR_CEIL = 99  # dvojciferný rok <= 99 -> 2000+

# Mapování sloupců 6..68 -> (step code, substate). Sub-stavy se týkají
# kontraktních kroků (zasláno/podepsáno/vyřízeno) a kroku „Možnost půjčky".
COLUMNS = {
    6: ("lead_zaevidovani", None), 7: ("lead_telefon", None),
    8: ("nabidka_indikativni", None), 9: ("odsouhlaseni_predbezne", None),
    10: ("overeni_vlastnictvi", None), 11: ("rocni_spotreba", None),
    12: ("stop_pamatkari", None), 13: ("stop_strecha", None),
    14: ("stop_azbest", None), 15: ("sber_podkladu", None),
    16: ("tech_posouzeni", None), 17: ("navrh_fve", None),
    18: ("kapacita_baterie", None), 19: ("dotacni_uspora", None),
    20: ("moznost_pujcky", "zadano"), 21: ("moznost_pujcky", "hotovo"),
    22: ("nabidka_podrobna", None), 23: ("vizualizace", None),
    24: ("odeslani_nabidky", None), 25: ("followup_1", None),
    26: ("konzultace_navratnost", None), 27: ("konzultace_znacky", None),
    28: ("planovani_prohlidky", None), 29: ("osobni_schuzka", None),
    30: ("statika_strechy", None), 31: ("trasovani_kabelaze", None),
    32: ("jistice_rozvadec", None), 33: ("teplota_technologie", None),
    34: ("revize_nabidky", None), 35: ("finalni_rozpocet", None),
    36: ("sod", "zaslano"), 37: ("sod", "podepsano"),
    38: ("plna_moc", "zaslano"), 39: ("plna_moc", "podepsano"),
    40: ("zalohova_faktura", None), 41: ("kontrola_zalohy", None),
    42: ("sop", "zaslano"), 43: ("sop", "podepsano"),
    44: ("sledovani_vykonu", None), 45: ("registrace_nzu", None),
    46: ("administrace_pujcky", None), 47: ("priprava_projektu", None),
    48: ("skladova_kontrola", None), 49: ("objednani_dodavatele", None),
    50: ("planovani_montaze", None), 51: ("stavba_montaz", None),
    52: ("elektro_montaz", None), 53: ("elektro_montaz", None),
    54: ("propojeni_test", None), 55: ("predani_zauceni", None),
    56: ("monitorovaci_app", None), 57: ("mereni_revize", None),
    58: ("podklady_revize", None), 59: ("revizni_zprava", None),
    60: ("utp", None), 61: ("vymena_elektromeru", None),
    62: ("prevzeti_odchylky", None), 63: ("kontrola_prevodni_smlouvy", None),
    64: ("povoleni_pretoku", None), 65: ("sdileni_komunita", "zaslano"),
    66: ("sdileni_komunita", "vyrizeno"), 67: ("konecna_faktura", None),
    68: ("dolozeni_sfzp", None),
}
CONTRACT_STEPS = {"sod", "plna_moc", "sop", "sdileni_komunita"}

# Datumové tvary: plné d.m.(r), rozsahy „10-15.9.2026" a „21.9.-22.9."
_DMY = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
_DM_END = re.compile(r"(\d{1,2})\.(\d{1,2})\.?$")


def _nfc(s):
    return unicodedata.normalize("NFC", (s or "")).strip()


def map_zakazka_type(v):
    """Typ zakázky -> template code; diakritika a velikost robustně.
    Chybějící/neznámý typ -> 'ostatni' (pravidlo plánu)."""
    if v is None:
        return "ostatni"
    s = _nfc(str(v)).lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\s+", "", s)
    known = {"rd", "byt", "firma", "bojler", "rozsireni", "wb", "ostatni",
             "reklamace", "elektroprace", "carport", "kontrola"}
    if s in known:
        return s
    return "ostatni"


def _map_status(v):
    s = _nfc(str(v)).lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    if s in ("n", "ne", "no", "neaktivni"):
        return "cancelled"
    return "active"  # '', 'a', 'aktivni', atd.


def _extract_date(s):
    """Vrátí (date | None, zbytek_textu). Bere POSLEDNÍ datum v řetězci
    (konec rozsahu), zbytek textu jde do poznámky."""
    matches = list(_DMY.finditer(s))
    if matches:
        d, m, y = matches[-1].groups()
        d, m, y = int(d), int(m), int(y)
        if y <= YEAR_CEIL:
            y += 2000
        if 1 <= d <= 31 and 1 <= m <= 12:
            try:
                return date(y, m, d), s[matches[-1].end():].strip()
            except ValueError:
                pass
    m2 = list(_DM_END.finditer(s))
    if m2:
        d, m = m2[-1].groups()
        d, m = int(d), int(m)
        if 1 <= d <= 31 and 1 <= m <= 12:
            try:
                return date(2026, m, d), ""
            except ValueError:
                pass
    return None, s.strip()


def _parse_cell(v):
    """Interpretuje buňku kroku -> (action, done_at | None, note | None).

    action: 'done' (datum/marker 'a'/'x'), 'sent', 'signed', 'note', 'none'.
    Datum může být text (d.m.(r), rozsah), Excel serial datum (číslo)
    nebo datetime objekt.
    """
    if v is None:
        return ("none", None, None)
    if isinstance(v, datetime):
        return ("done", v.date(), None)
    if isinstance(v, date):
        return ("done", v, None)
    if isinstance(v, bool):
        return ("none", None, None)
    if isinstance(v, (int, float)):
        if 30000 <= float(v) <= 70000:  # Excel serial datum
            return ("done", (EXCEL_EPOCH + timedelta(days=int(v))).date(), None)
        return ("none", None, None)
    s = _nfc(str(v))
    if not s:
        return ("none", None, None)
    low = s.lower()
    if low in ("a", "x"):
        return ("done", None, None)
    if low in ("z", "zasláno", "zaslano"):
        return ("sent", None, None)
    if low in ("p", "podepsáno", "podepsano"):
        return ("signed", None, None)
    d, rest = _extract_date(s)
    if d is not None:
        return ("done", d, rest or None)
    return ("note", None, s)


def _join_note(existing, add):
    if not add:
        return existing
    if existing and add not in existing.split("; "):
        return existing + "; " + add
    return existing or add


def parse_dispecink_xlsx(path):
    """Přečte list „Přehled" -> seznam řádků projektu.

    Každý řádek: {name, customer_name, type, status, tech, prijmeni, jmeno,
    aktivni, steps: {code: {done, done_at, note, events}}}
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb["Přehled"] if "Přehled" in wb.sheetnames else wb[wb.sheetnames[0]]

    raw_rows = []
    for row in ws.iter_rows(values_only=True):
        cells = list(row) if row is not None else []
        cells = cells + [None] * (69 - len(cells))
        raw_rows.append(cells)

    # hlavičkový řádek = řádek se sloupcem „Příjmení"
    hdr = next(i for i, r in enumerate(raw_rows)
               if i < len(raw_rows) and _nfc(r[3]) == "Příjmení")
    # hdr+1 = sub-stavy, hdr+2 = „vzor", hdr+3 dál = data
    data_rows = raw_rows[hdr + 3:]

    result = []
    for cells in data_rows:
        typ_raw = cells[1]
        tech = _nfc(cells[2]) if cells[2] is not None else None
        prijmeni = _nfc(cells[3]) if cells[3] is not None else ""
        jmeno = _nfc(cells[4]) if cells[4] is not None else ""
        aktivni = _nfc(cells[5]) if cells[5] is not None else ""
        # vzor/tečkový řádek vynecháváme
        typ_raw_s = _nfc(typ_raw) if typ_raw is not None else ""
        if typ_raw_s == "vzor" or (tech or "").lower() == "vzor":
            continue
        if not typ_raw and not prijmeni and not jmeno:
            continue

        typ = map_zakazka_type(typ_raw)
        status = _map_status(aktivni)
        name = f"{prijmeni} {jmeno}".strip()
        customer_name = name or None
        if not name:
            name = f"Zakazka - {typ}"

        steps = defaultdict(lambda: {"done": False, "done_at": None,
                                     "note": None, "events": []})
        for idx, (code, substate) in COLUMNS.items():
            v = cells[idx] if idx < len(cells) else None
            if v is None or (isinstance(v, str) and not _nfc(v)):
                continue
            action, at, note = _parse_cell(v)
            if action == "none":
                continue
            acc = steps[code]
            if note:
                acc["note"] = _join_note(acc["note"], note)
            if action == "note":
                continue
            acc["done"] = True
            if at and acc["done_at"] is None:
                acc["done_at"] = at
            if note:
                acc["note"] = _join_note(acc["note"], note)
            if substate and code in CONTRACT_STEPS:
                acc["events"].append("signed" if substate in ("podepsano", "vyrizeno") else "sent")
            elif action == "signed":
                acc["events"].append("signed")
            elif action == "sent":
                acc["events"].append("sent")
            else:
                acc["events"].append("done")

        for acc in steps.values():
            if acc["done"] and "done" not in acc["events"]:
                acc["events"].append("done")

        result.append({
            "name": name,
            "customer_name": customer_name,
            "type": typ,
            "status": status,
            "tech": tech,
            "prijmeni": prijmeni,
            "jmeno": jmeno,
            "aktivni": aktivni,
            "steps": {k: dict(v) for k, v in steps.items()},
        })
    wb.close()
    return result


def _as_datetime(d):
    if d is None:
        return datetime.utcnow()
    return datetime(d.year, d.month, d.day)


def import_dispecink(path, db):
    """Import zakázek z XLSX. Idempotentní: duplicita se pozná podle
    (name, type) — dvě různé zakázky stejného jména s odlišným typem
    (např. „Kvízová" RD vs rozšíření) se přeimportují obě."""
    rows = parse_dispecink_xlsx(path)
    imported = 0
    skipped = 0
    # Snapshot existujících (name, type) PŘED během: řádky se stejným jménem
    # v jednom souboru (anonymní „Zakazka - …") jsou rozdílné historické
    # záznamy a mají se přeimportovat všechny; duplicita se pozná jen proti
    # obsahu DB před importem (idempotence při opakovaném importu).
    existing = set((r[0], r[1])
                   for r in db.query(Project.name, Project.type).all())
    for row in rows:
        key = (row["name"], row["type"])
        if key in existing:
            skipped += 1
            continue

        project = Project(
            name=row["name"],
            customer_name=row["customer_name"],
            type=row["type"],
            status=row["status"],
            tech=row["tech"],
            share_code=generate_share_code(),
        )
        db.add(project)
        db.flush()

        template_code = TEMPLATE_CODE_BY_TYPE.get(row["type"], "ostatni")
        attach_template(db, project, template_code)

        joined = (db.query(ProjectStep, PipelineStep)
                  .join(PipelineStep, ProjectStep.step_id == PipelineStep.id)
                  .filter(ProjectStep.project_id == project.id).all())
        by_code = {s.code: ps for ps, s in joined}

        for code, acc in row["steps"].items():
            ps = by_code.get(code)
            if not ps:
                continue
            if acc["done"]:
                ps.status = "done"
                ps.done_at = _as_datetime(acc["done_at"])
            if acc["note"]:
                ps.note = acc["note"]
            for ev_action in dict.fromkeys(acc["events"]):
                db.add(StepEvent(
                    project_id=project.id,
                    step_id=ps.id,
                    action=ev_action,
                    from_status=None,
                    to_status="done" if ev_action != "sent" else None,
                    user_id=None,
                    at=_as_datetime(acc["done_at"]),
                ))
        imported += 1

    db.commit()
    return {"imported": imported, "skipped": skipped}