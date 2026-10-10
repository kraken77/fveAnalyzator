"""Registr oddílů reportu — pořadí, základ, rám, filtr ekonomiky."""
from reportgen.report_sections import (
    ALL_IDS, BASE_IDS, FRAME_FIRST, FRAME_LAST, SECTIONS,
    resolve_sections, sections_metadata,
)


def test_canonical_order_ids_unique():
    ids = [s.id for s in SECTIONS]
    assert len(ids) == len(set(ids))
    assert ALL_IDS[0] == "intro"
    assert ALL_IDS[-1] == "glossary"


def test_default_returns_canonical_order():
    assert resolve_sections(None) == list(ALL_IDS)


def test_resolve_ignores_unknown_ids():
    out = resolve_sections(["summary", "neexistuje", "glossary"])
    assert "neexistuje" not in out
    assert "summary" in out and "glossary" in out


def test_resolve_forces_base_when_missing():
    out = resolve_sections(["glossary"])
    for b in BASE_IDS:
        assert b in out
    assert out[0] == "intro"
    assert out[-1] == "glossary"


def test_resolve_keeps_client_order_for_optional():
    out = resolve_sections(
        ["intro", "summary", "recommendations", "input_params",
         "economic_metrics", "investment_composition", "glossary"]
    )
    i = {name: pos for pos, name in enumerate(out)}
    assert i["recommendations"] < i["input_params"]


def test_resolve_drops_economic_sections_without_economic():
    out = resolve_sections(None, has_economic=False)
    assert "economic_metrics" not in out
    assert "investment_composition" not in out
    assert "appendix_d" not in out
    assert "summary" in out


def test_resolve_forces_frame_positions():
    out = resolve_sections(["summary", "glossary", "intro", "economic_metrics",
                            "investment_composition"])
    assert out[0] == "intro"
    assert out[-1] == "glossary"
    assert out.index("intro") == 0
    assert out.index("glossary") == len(out) - 1


def test_resolve_empty_list_is_base_only():
    """Prázdný výběr (uživatel odškrtal vše) = jen pevný základ + rám."""
    out = resolve_sections([])
    assert set(out) == set(BASE_IDS) | set(FRAME_FIRST) | set(FRAME_LAST)


def test_metadata_flags_base():
    by_id = {m["id"]: m for m in sections_metadata()}
    assert by_id["summary"]["base"] is True
    assert by_id["appendix_a"]["base"] is False
    assert by_id["summary"]["label"]
    assert by_id["summary"]["description"]
