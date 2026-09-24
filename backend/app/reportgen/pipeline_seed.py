"""Dispečink — typové šablony pipeline, seed a attach k projektu (M1).

Šablony kódují procesní pipeline dle Excelu „PROCESNÍ DISPEČINK" a schváleného
designu. `ensure_pipeline_templates` je idempotentní (upsert dle kódu šablony
a (template_id, step_code)) a volá se z `init_db()`. `attach_template` vytvoří
projektovou instanci šablony (ProjectPipeline + ProjectStep řádky).
"""

import json

from .storage import (PipelineTemplate, PipelineStep, ProjectPipeline,
                      ProjectStep)

# Montážní časy krátkých šablon (work minutes) — PLACEHOLDER, kalibruje se
# s uživatelem po M1 (riziko plánu #2).
MONTAGE_WORK = {"bojler": 120, "rozsireni": 240, "wb": 120, "ostatni": 240}

# allowed_roles se defaultně odvozují od fáze/typu kroku; výjimky se uvádí přímo
ALLOWED_LEAD = ["admin", "antelon", "sales"]
ALLOWED_SALES = ["admin", "sales"]
ALLOWED_DESIGN = ["admin", "antelon", "sales", "designer"]
ALLOWED_EL = ["admin", "electrician"]
ALLOWED_ROOFER = ["admin", "roofer"]
ALLOWED_INSPECTOR = ["admin", "inspector"]
ALLOWED_SUBSIDY = ["admin", "subsidy"]
ALLOWED_CONNECTION = ["admin", "connection"]
ALLOWED_WAREHOUSE = ["admin", "warehouse", "buyer"]
ALLOWED_PREDANI = ["admin", "electrician", "sales"]

COND_STOP = {"project_param_in": {"fve_params.stop_stavy": ["ano"]}}
COND_DOTACE = {"project_param_in": {"fve_params.dotace": ["ano"]}}
COND_PUJCKA = {"project_param_in": {"fve_params.pujcka": ["ano"]}}
COND_SOP = {"requires_step": ["sop"]}


def _s(code, name, phase, order, est_admin=0, est_work=0,
       admin_role="sales", work_role="electrician", state_model="simple",
       allowed=None, condition=None, auto_hook=None, parallel_group=None):
    """Pomocník pro definici kroku šablony."""
    return {
        "code": code, "name": name, "phase": phase, "order": order,
        "est_admin_minutes": est_admin, "est_work_minutes": est_work,
        "admin_rate_role": admin_role, "work_rate_role": work_role,
        "state_model": state_model,
        "allowed_roles_json": json.dumps(allowed or ALLOWED_LEAD),
        "condition_json": json.dumps(condition, ensure_ascii=False) if condition else None,
        "auto_hook": auto_hook, "parallel_group": parallel_group,
    }


def _full_template_steps():
    """Full pipeline pro RD (57 kroků, admin časy z Excelu — totál 553 min)."""
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    # --- LEAD ---
    add("lead_zaevidovani", "Zaevidování poptávky - LEAD, OP", "lead", est_admin=1)
    add("lead_telefon", "První telefonát (do 24h)", "lead", est_admin=20)
    add("nabidka_indikativni", "první indikativní nabídka dle telefonátu - tel/email", "lead", est_admin=10)
    add("odsouhlaseni_predbezne", "odsouhlasení předběžné nabídky - pokračujeme", "lead",
        est_admin=0, auto_hook="invoice_2500", allowed=ALLOWED_SALES)
    add("overeni_vlastnictvi", "Ověření vlastnictví", "lead", est_admin=5)
    add("rocni_spotreba", "Zjištění roční spotřeby", "lead", est_admin=5)
    add("stop_pamatkari", "Prověření stop-stavů (Památkáři, CHKO)", "lead", est_admin=5,
        condition=COND_STOP)
    add("stop_strecha", "Prověření stop-stavů (Střecha)", "lead", est_admin=5,
        condition=COND_STOP)
    add("stop_azbest", "Prověření stop-stavů (Azbest)", "lead", est_admin=5,
        condition=COND_STOP)
    add("sber_podkladu", "Sběr podkladů od zákazníka", "lead", est_admin=5)
    add("tech_posouzeni", "Technické posouzení na dálku", "lead", est_admin=10,
        allowed=ALLOWED_DESIGN, auto_hook="ai_chain")

    # --- PRÍPRAVA ---
    add("navrh_fve", "Návrh velikosti FVE", "priprava", est_admin=10,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("kapacita_baterie", "Návrh kapacity baterie", "priprava", est_admin=0,
        state_model="ai", allowed=ALLOWED_DESIGN, condition=COND_DOTACE)
    add("dotacni_uspora", "Výpočet dotační úspory", "priprava", est_admin=5,
        state_model="ai", allowed=ALLOWED_SUBSIDY)
    add("moznost_pujcky", "Možnost bezúročné půjčky", "priprava", est_admin=20,
        state_model="ai", allowed=ALLOWED_DESIGN, condition=COND_DOTACE)
    add("nabidka_podrobna", "Vytvoření podrobnější nabídky", "priprava", est_admin=10,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("vizualizace", "Příprava vizualizace", "priprava", est_admin=0,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("odeslani_nabidky", "Odeslání nabídky", "priprava", est_admin=10)
    add("followup_1", "První follow-up (po 3 dnech)", "sledovani", est_admin=10)
    add("konzultace_navratnost", "Konzultace návratnosti", "sledovani", est_admin=5)
    add("konzultace_znacky", "Konzultace značek komponentů", "sledovani", est_admin=5)
    add("planovani_prohlidky", "Plánování osobní prohlídky", "sledovani", est_admin=5)
    add("osobni_schuzka", "Osobní schůzka na místě", "sledovani", est_admin=120)
    add("statika_strechy", "Kontrola statiky střechy", "priprava", est_admin=5,
        allowed=ALLOWED_DESIGN)
    add("trasovani_kabelaze", "Trasování kabeláže", "priprava", est_admin=10,
        allowed=ALLOWED_DESIGN)
    add("jistice_rozvadec", "Kontrola jističů a rozvaděče", "priprava", est_admin=10,
        allowed=ALLOWED_DESIGN)
    add("teplota_technologie", "Prověření teploty pro technologii", "priprava", est_admin=5,
        allowed=ALLOWED_DESIGN)
    add("revize_nabidky", "Revize a úprava nabídky", "priprava", est_admin=10,
        allowed=ALLOWED_DESIGN)
    add("finalni_rozpocet", "Finální schválení rozpočtu", "priprava", est_admin=10,
        allowed=ALLOWED_SALES)

    # --- SMLOUVA ---
    add("sod", "Podpis Smlouvy o dílo (SoD)", "smlouva", est_admin=10,
        state_model="contract", auto_hook="sod_signed", allowed=ALLOWED_SALES)
    add("plna_moc", "Podpis plná moc pro Distributora (ČEZ,PRE)", "smlouva", est_admin=10,
        state_model="contract", allowed=ALLOWED_SALES)
    add("zalohova_faktura", "Vystavení zálohové faktury", "finance", est_admin=5,
        parallel_group="smlouva_after", allowed=ALLOWED_SALES)
    add("kontrola_zalohy", "Kontrola připsání zálohy", "finance", est_admin=5,
        parallel_group="smlouva_after", allowed=ALLOWED_SALES)
    add("sop", "Žádost o připojení (Smlouva) SOP", "pripojeni", est_admin=20,
        state_model="contract", auto_hook="sop_signed", parallel_group="smlouva_after",
        allowed=ALLOWED_CONNECTION)
    add("sledovani_vykonu", "Sledování schválení rezervovaného výkonu", "pripojeni", est_admin=20,
        allowed=ALLOWED_CONNECTION)
    add("registrace_nzu", "Podání registrace do NZÚ", "dotace", est_admin=20,
        allowed=ALLOWED_SUBSIDY, condition=COND_DOTACE)
    add("administrace_pujcky", "Administrace bezúročné půjčky", "dotace", est_admin=5,
        allowed=ALLOWED_SUBSIDY, condition=COND_PUJCKA)

    # --- REALIZACE ---
    add("priprava_projektu", "Příprava projektu", "realizace", est_admin=30,
        allowed=ALLOWED_DESIGN)
    add("skladova_kontrola", "Skladová kontrola materiálu", "realizace", est_admin=20,
        allowed=ALLOWED_WAREHOUSE)
    add("objednani_dodavatele", "Objednání u dodavatelů", "realizace", est_admin=30,
        allowed=ALLOWED_WAREHOUSE)
    add("planovani_montaze", "Plánování termínu montáže střecha", "realizace", est_admin=5)
    add("stavba_montaz", "Stavební a střešní montáž", "realizace", est_admin=0,
        est_work=480, work_role="roofer", allowed=ALLOWED_ROOFER)
    add("elektro_montaz", "Elektro-montáž komponentů", "realizace", est_admin=2,
        est_work=360, work_role="electrician", auto_hook="elektro_done", allowed=ALLOWED_EL)
    add("propojeni_test", "Propojení a ostrovní test", "realizace", est_admin=0,
        est_work=120, work_role="electrician", allowed=ALLOWED_EL)

    # --- PŘEDÁNÍ ---
    add("predani_zauceni", "Předání a zaškolení", "predani", est_admin=0,
        est_work=90, work_role="electrician", allowed=ALLOWED_PREDANI)
    add("monitorovaci_app", "Instalace monitorovací aplikace", "predani", est_admin=0,
        est_work=30, work_role="electrician", allowed=ALLOWED_EL)

    # --- REVIZE ---
    add("mereni_revize", "Měření a revize systému", "revize", est_admin=0,
        est_work=60, work_role="electrician", allowed=ALLOWED_EL,
        condition={"requires_step": ["elektro_montaz"]})
    add("podklady_revize", "Zaslání podkladů pro revizní zprávu", "revize", est_admin=0,
        allowed=ALLOWED_EL)
    add("revizni_zprava", "Vystavení Výchozí revizní zprávy (Revize FVE)", "revize", est_admin=5,
        work_role="inspector", allowed=ALLOWED_INSPECTOR,
        condition={"requires_step": ["mereni_revize"]})

    # --- PŘETOKY ---
    add("utp", "Žádost o umožnění ÚTP", "pretoky", est_admin=10,
        allowed=ALLOWED_CONNECTION, condition=COND_SOP)
    add("vymena_elektromeru", "Výměna elektroměru", "pretoky", est_admin=0,
        allowed=ALLOWED_EL, condition=COND_SOP)
    add("prevzeti_odchylky", "Získání odběratele na přetoky", "pretoky", est_admin=0,
        allowed=ALLOWED_CONNECTION, condition=COND_SOP)
    add("kontrola_prevodni_smlouvy", "Kontrola smlouvy na přetoky", "pretoky", est_admin=5,
        allowed=ALLOWED_CONNECTION, condition=COND_SOP)
    add("povoleni_pretoku", "Povolení přetoků na střídači", "pretoky", est_admin=5,
        allowed=ALLOWED_EL, condition=COND_SOP)
    add("sdileni_komunita", "Nastavení sdílení v komunitě", "pretoky", est_admin=5,
        state_model="contract", allowed=ALLOWED_CONNECTION, condition=COND_SOP)

    # --- FINÁL ---
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)
    add("dolozeni_sfzp", "Doložení realizace na SFŽP", "dotace", est_admin=10,
        allowed=ALLOWED_SUBSIDY, condition=COND_DOTACE)

    return steps


def _short_template_steps(zakazka_type):
    """Krátká pipeline (bojler, rozšíření, WB, ostatní) — 16 kroků."""
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    add("lead_zaevidovani", "Zaevidování poptávky - LEAD, OP", "lead", est_admin=1)
    add("lead_telefon", "První telefonát (do 24h)", "lead", est_admin=20)
    add("nabidka_indikativni", "první indikativní nabídka dle telefonátu - tel/email", "lead", est_admin=10)
    add("odsouhlaseni_predbezne", "odsouhlasení předběžné nabídky - pokračujeme", "lead",
        est_admin=0, auto_hook="invoice_2500", allowed=ALLOWED_SALES)
    add("sber_podkladu", "Sběr podkladů od zákazníka", "lead", est_admin=5)
    add("tech_posouzeni", "Technické posouzení na dálku", "lead", est_admin=10,
        allowed=ALLOWED_DESIGN, auto_hook="ai_chain")
    add("nabidka_podrobna", "Vytvoření podrobnější nabídky", "priprava", est_admin=10,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("odeslani_nabidky", "Odeslání nabídky", "priprava", est_admin=10)
    add("sod", "Podpis Smlouvy o dílo (SoD)", "smlouva", est_admin=10,
        state_model="contract", auto_hook="sod_signed", allowed=ALLOWED_SALES)
    add("zalohova_faktura", "Vystavení zálohové faktury", "smlouva", est_admin=5,
        allowed=ALLOWED_SALES)
    add("kontrola_zalohy", "Kontrola připsání zálohy", "smlouva", est_admin=5,
        allowed=ALLOWED_SALES)
    add("objednani_dodavatele", "Objednání u dodavatelů", "realizace", est_admin=30,
        allowed=ALLOWED_WAREHOUSE)
    add("planovani_montaze", "Plánování termínu montáže", "realizace", est_admin=5)
    add("montaz", "Montáž", "realizace", est_admin=0,
        est_work=MONTAGE_WORK.get(zakazka_type, 240), work_role="electrician",
        allowed=ALLOWED_EL)
    add("predani_zauceni", "Předání a zaškolení", "predani", est_admin=0,
        est_work=90, work_role="electrician", allowed=ALLOWED_PREDANI)
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)

    return steps


def _reklamace_steps():
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    add("rekl_prijeti", "První kontakt zákazníka", "lead", est_admin=10, allowed=ALLOWED_SALES)
    add("rekl_diagnostika", "Diagnostika závady", "diagnoza", est_admin=30, est_work=60,
        work_role="electrician", allowed=ALLOWED_EL)
    add("rekl_oprava", "Oprava", "oprava", est_admin=0, est_work=240,
        work_role="electrician", allowed=ALLOWED_EL)
    add("rekl_predani", "Předání a zaevidování", "predani", est_admin=15, est_work=60,
        work_role="electrician", allowed=ALLOWED_PREDANI)
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)

    return steps


def _elektroprace_steps():
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    add("lead_zaevidovani", "Zaevidování poptávky - LEAD, OP", "lead", est_admin=1)
    add("tech_posouzeni", "Technické posouzení na dálku", "lead", est_admin=10,
        allowed=ALLOWED_DESIGN, auto_hook="ai_chain")
    add("nabidka_podrobna", "Vytvoření podrobnější nabídky", "priprava", est_admin=10,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("sod", "Podpis Smlouvy o dílo (SoD)", "smlouva", est_admin=10,
        state_model="contract", auto_hook="sod_signed", allowed=ALLOWED_SALES)
    add("elektro_montaz", "Elektro-montáž", "realizace", est_admin=2, est_work=480,
        work_role="electrician", auto_hook="elektro_done", allowed=ALLOWED_EL)
    add("mereni_revize", "Měření a revize systému", "revize", est_admin=0, est_work=120,
        work_role="electrician", allowed=ALLOWED_EL)
    add("revizni_zprava", "Vystavení Výchozí revizní zprávy", "revize", est_admin=5,
        est_work=120, work_role="inspector", allowed=ALLOWED_INSPECTOR)
    add("predani_zauceni", "Předání a zaškolení", "predani", est_admin=0, est_work=60,
        work_role="electrician", allowed=ALLOWED_PREDANI)
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)

    return steps


def _carport_steps():
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    add("lead_zaevidovani", "Zaevidování poptávky - LEAD, OP", "lead", est_admin=1)
    add("tech_posouzeni", "Technické posouzení na dálku", "lead", est_admin=10,
        allowed=ALLOWED_DESIGN, auto_hook="ai_chain")
    add("nabidka_podrobna", "Vytvoření podrobnější nabídky", "priprava", est_admin=10,
        state_model="ai", allowed=ALLOWED_DESIGN)
    add("sod", "Podpis Smlouvy o dílo (SoD)", "smlouva", est_admin=10,
        state_model="contract", auto_hook="sod_signed", allowed=ALLOWED_SALES)
    add("priprava_pozemku", "Příprava pozemku", "realizace", est_admin=0, est_work=240,
        work_role="roofer", allowed=ALLOWED_ROOFER)
    add("montaz_streseni", "Montáž střechy", "realizace", est_admin=0, est_work=480,
        work_role="roofer", allowed=ALLOWED_ROOFER)
    add("elektro_montaz", "Elektro-montáž", "realizace", est_admin=2, est_work=240,
        work_role="electrician", auto_hook="elektro_done", allowed=ALLOWED_EL)
    add("revizni_zprava", "Vystavení Výchozí revizní zprávy", "revize", est_admin=5,
        est_work=120, work_role="inspector", allowed=ALLOWED_INSPECTOR)
    add("predani_zauceni", "Předání a zaškolení", "predani", est_admin=0, est_work=60,
        work_role="electrician", allowed=ALLOWED_PREDANI)
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)

    return steps


def _kontrola_steps():
    steps = []
    n = 0
    def add(*args, **kw):
        nonlocal n
        n += 1
        steps.append(_s(*args, order=n, **kw))

    add("knt_planovani", "Plánování kontroly", "lead", est_admin=30, allowed=ALLOWED_SALES)
    add("knt_provedeni", "Provedení kontroly", "kontrola", est_admin=30, est_work=90,
        work_role="inspector", allowed=ALLOWED_INSPECTOR)
    add("knt_zavady", "Vyřešení závad", "kontrola", est_admin=0, est_work=90,
        work_role="electrician", allowed=ALLOWED_EL)
    add("knt_predani", "Předání výsledků", "predani", est_admin=20,
        allowed=ALLOWED_INSPECTOR)
    add("konecna_faktura", "Vystavení konečné faktury", "final", est_admin=10,
        allowed=ALLOWED_SALES)

    return steps


PIPELINE_TEMPLATES = [
    {"code": "rd", "name": "Rodinný dům (FVE + baterie + dotace)", "zakazka_type": "rd",
     "steps": _full_template_steps()},
    {"code": "byt", "name": "Bytový dům", "zakazka_type": "byt",
     "steps": _full_template_steps()},
    {"code": "firma", "name": "Firma / provozovna", "zakazka_type": "firma",
     "steps": _full_template_steps()},
    {"code": "bojler", "name": "Bojler", "zakazka_type": "bojler",
     "steps": _short_template_steps("bojler")},
    {"code": "rozsireni", "name": "Rozšíření stávající FVE", "zakazka_type": "rozsireni",
     "steps": _short_template_steps("rozsireni")},
    {"code": "wb", "name": "Wallbox (WB)", "zakazka_type": "wb",
     "steps": _short_template_steps("wb")},
    {"code": "ostatni", "name": "Ostatní", "zakazka_type": "ostatni",
     "steps": _short_template_steps("ostatni")},
    {"code": "reklamace", "name": "Reklamace", "zakazka_type": "reklamace",
     "steps": _reklamace_steps()},
    {"code": "elektroprace", "name": "Elektropráce", "zakazka_type": "elektroprace",
     "steps": _elektroprace_steps()},
    {"code": "carport", "name": "Carport", "zakazka_type": "carport",
     "steps": _carport_steps()},
    {"code": "kontrola", "name": "Roční kontrola", "zakazka_type": "kontrola",
     "steps": _kontrola_steps()},
]

TEMPLATE_CODE_BY_TYPE = {
    "rd": "rd", "byt": "byt", "firma": "firma", "bojler": "bojler",
    "rozsireni": "rozsireni", "wb": "wb", "ostatni": "ostatni",
    "reklamace": "reklamace", "elektroprace": "elektroprace",
    "carport": "carport", "kontrola": "kontrola",
}


def ensure_pipeline_templates(db):
    """Idempotentní upsert šablon + kroků. Volá se z init_db()."""
    for tpl in PIPELINE_TEMPLATES:
        t = db.query(PipelineTemplate).filter(PipelineTemplate.code == tpl["code"]).first()
        if not t:
            t = PipelineTemplate(code=tpl["code"], name=tpl["name"],
                                 zakazka_type=tpl["zakazka_type"], version=1, active=True)
            db.add(t)
            db.flush()
        for step in tpl["steps"]:
            exists = db.query(PipelineStep).filter(
                PipelineStep.template_id == t.id,
                PipelineStep.code == step["code"]).first()
            if not exists:
                db.add(PipelineStep(template_id=t.id, **step))
    db.commit()


def attach_template(db, project, template_code):
    """Vytvoří ProjectPipeline + ProjectStep instance pro projekt."""
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.code == template_code).first()
    if not tpl:
        raise ValueError(f"Neexistující šablona pipeline: {template_code!r}")

    pp = db.query(ProjectPipeline).filter(ProjectPipeline.project_id == project.id).first()
    if not pp:
        pp = ProjectPipeline(project_id=project.id, template_id=tpl.id)
        db.add(pp)
        db.flush()

    steps = (db.query(PipelineStep)
             .filter(PipelineStep.template_id == tpl.id)
             .order_by(PipelineStep.order).all())
    for s in steps:
        exists = db.query(ProjectStep).filter(
            ProjectStep.project_id == project.id,
            ProjectStep.step_id == s.id).first()
        if not exists:
            db.add(ProjectStep(project_id=project.id, step_id=s.id,
                               status="not_started", real_admin_minutes=0,
                               real_work_minutes=0))
    db.commit()
    return pp