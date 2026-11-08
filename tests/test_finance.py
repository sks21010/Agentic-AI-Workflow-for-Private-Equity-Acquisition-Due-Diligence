from decimal import Decimal
import pytest

from diligence.finance import adjusted_ebitda, approved_analysis, enterprise_value


def test_original_handoff_arithmetic():
    assert adjusted_ebitda(12_000_000, -2_000_000) == Decimal("10000000")
    assert enterprise_value(10_000_000, 10) == Decimal("100000000")


@pytest.mark.parametrize("action,approved,change", [
    ("accept_addback", "21946000", "0"),
    ("reject_addback", "21466000", "-4800000"),
])
def test_selected_item_bridge(action, approved, change):
    result = approved_analysis("21466000", "480000", {"action": action, "reviewer": "Analyst",
        "rationale": "Compared prior periods", "multiple": "10"})
    assert result["reviewed_ebitda"] == approved
    assert result["enterprise_value_change"] == change


@pytest.mark.parametrize("review", [None, {}, {"action": "request_information"},
    {"action": "accept_addback", "reviewer": "", "rationale": ""}])
def test_human_gate(review):
    with pytest.raises(PermissionError):
        approved_analysis(100, 20, review)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "not a number"])
def test_invalid_inputs(value):
    with pytest.raises(ValueError):
        enterprise_value(100, value)


def test_invalid_multiple():
    with pytest.raises(ValueError):
        enterprise_value(100, 0)
