"""Možnost bezúročné půjčky (NZÚ úvěr) — vyhodnocení eligibility (M3)."""

LOAN_CAP = 750000  # maximální výše půjčky odvozená od dotace C.3


def evaluate_loan(project_params: dict, subsidy_result: dict) -> dict:
    """Eligibilita bezúročné půjčky.

    Eligible, pokud zákazník žádá o dotaci (dotace=ano) a souhlasí s půjčkou
    (pujcka=ano). Amount = min(dotace C.3, LOAN_CAP).
    """
    dotace = str((project_params or {}).get("dotace", "") or "").strip().lower()
    souhlas = str((project_params or {}).get("pujcka", "") or "").strip().lower()
    eligible = dotace == "ano" and souhlas == "ano"

    castka = (subsidy_result or {}).get("castka", 0) or 0
    amount = min(float(castka), LOAN_CAP) if eligible else 0

    if not eligible:
        reason = "Půjčka není dostupná — chybí souhlas s dotací (dotace=ano) a/nebo zájem o půjčku (pujcka=ano)."
    elif castka <= 0:
        reason = "Dotace C.3 je 0 Kč — půjčka se nevztahuje."
    else:
        reason = "Bezúročná půjčka dostupná do výše dotační částky C.3."

    return {"eligible": eligible, "amount_czk": round(amount, 2),
            "dotace_castka": round(float(castka), 2), "cap": LOAN_CAP,
            "reason": reason}