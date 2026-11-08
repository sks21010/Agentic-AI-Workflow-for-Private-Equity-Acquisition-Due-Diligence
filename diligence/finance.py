"""Decimal arithmetic. No model-generated arithmetic or accounting approvals."""
from decimal import Decimal, InvalidOperation


def number(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid financial number.") from None
    if not result.is_finite():
        raise ValueError("Financial inputs must be finite.")
    return result


def adjusted_ebitda(reported, approved_addback) -> Decimal:
    return number(reported) + number(approved_addback)


def enterprise_value(ebitda, multiple) -> Decimal:
    factor = number(multiple)
    if factor <= 0:
        raise ValueError("The valuation multiple must be positive.")
    return number(ebitda) * factor


def approved_analysis(reported, proposed, review: dict | None) -> dict:
    if not review or review.get("action") not in {"accept_addback", "reject_addback"}:
        raise PermissionError("An explicit analyst treatment is required before valuation.")
    if not review.get("reviewer", "").strip() or not review.get("rationale", "").strip():
        raise PermissionError("Record the analyst and rationale before valuation.")
    baseline, proposal = number(reported), number(proposed)
    if proposal < 0:
        raise ValueError("The proposed add-back cannot be negative.")
    approved = proposal if review["action"] == "accept_addback" else Decimal(0)
    seller = adjusted_ebitda(baseline, proposal)
    reviewed = adjusted_ebitda(baseline, approved)
    seller_ev = enterprise_value(seller, review["multiple"])
    reviewed_ev = enterprise_value(reviewed, review["multiple"])
    # Strings preserve exact decimal values in JSON audit records.
    return {key: str(value) for key, value in {
        "reported_ebitda": baseline, "proposed_addback": proposal, "approved_addback": approved,
        "seller_case_ebitda": seller, "reviewed_ebitda": reviewed,
        "multiple": number(review["multiple"]), "seller_enterprise_value": seller_ev,
        "reviewed_enterprise_value": reviewed_ev, "enterprise_value_change": reviewed_ev - seller_ev,
    }.items()}
