"""Scoped teaching questions, not benchmark grading criteria."""
CASES = {
    "erp": {
        "label": "ERP implementation · $900,000",
        "question": "Does the evidence support management's $900,000 ERP implementation EBITDA add-back for FY2025? Look for ongoing costs and counterevidence.",
        "proposed": "900000",
        "queries": ["ERP implementation 900000 ongoing support subscriptions", "Northstar project implementation fee recurring", "Earnings schedule ERP"],
        "fact": "The conversion to the new inventory and finance system was completed on 31 October 2025.",
        "inference": "Completion and the exclusion of ongoing subscriptions support considering this implementation fee separately from recurring IT costs.",
        "recommendation": "accept_addback",
    },
    "severance": {
        "label": "Recurring severance · $480,000",
        "question": "Does the evidence support management's $480,000 severance EBITDA add-back for FY2025 as nonrecurring? Compare prior-year personnel costs.",
        "proposed": "480000",
        "queries": ["severance annual territory review 2024 2025", "Personnel movements 360000 480000", "Earnings schedule severance"],
        "fact": "Six employees received $360,000 in 2024 and eight received $480,000 in 2025 as part of the annual territory review.",
        "inference": "Personnel exit costs appear in both years; that challenges describing the full current-year amount as nonrecurring.",
        "recommendation": "reject_addback",
    },
    "owner_pay": {
        "label": "Owner-pay saving · $300,000",
        "question": "Does the evidence substantiate management's proposed $300,000 owner-pay EBITDA add-back for FY2025? Is the replacement-role salary independently benchmarked?",
        "proposed": "300000",
        "queries": ["CEO replacement salary compensation benchmarking owner pay", "Executive terms CEO salary", "Earnings schedule owner pay"],
        "fact": "No compensation benchmarking report has been commissioned.",
        "inference": "Management's proposed replacement salary lacks independent support; the saving remains unresolved.",
        "recommendation": "unresolved",
    },
}
