# Initial validation

Verified on Windows with Python 3.13.9. Exact installed dependency versions are in `requirements-lock.txt`.

- `python -m pytest -q --tb=short`: **38 passed**, including Gemini structured-output validation, provider persistence on resume, secret-free example configuration, the full native-SDK workflow with mocked HTTP, and a single-attempt HTTP 503 failure with no financial results.
- `python -m pip check`: **No broken requirements found**.
- All eight original documents passed SHA-256 checks against the pinned source manifest.
- Extracted 482 source-located passages, including both pages of the ERP project statement.
- Streamlit's test harness exercised starting an investigation, reviewing evidence, approving an add-back, calculating the scenario, and recording final memo review.
- Workflow tests exercised PASS, UNRESOLVED, critic-driven FAIL/retry, the two-revision cap, fabricated-quote rejection, missing evidence, analyst overrides, approval gating, information requests, and deferred decisions.
- The OpenAI and Gemini API adapters and supplemental-evidence resume paths were tested using mocked model responses. A short live Gemini test was attempted using `gemini-3.8-flash`. After fixing local certificate trust, Google returned HTTP 504 (deadline expired). Successful live generation and live reasoning quality remain unvalidated.
- A subsequent live metadata request successfully recognized `models/gemini-3.8-flash` in 0.2 seconds. A minimal generation prompt returned HTTP 503 after 3.5 seconds with an explicit high-demand message. This establishes a current provider-capacity failure even without documents or LangGraph; it does not prove the cause of every prior timeout.

The offline demo is scripted. These checks establish software behavior for the bounded prototype, not general financial accuracy, model performance, or improvement from adding a critic.
