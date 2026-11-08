import json
import os
from pathlib import Path
import traceback
from uuid import uuid4

from dotenv import load_dotenv
import streamlit as st

from diligence.audit import AuditStore
from diligence.cases import CASES
from diligence.documents import DATA, extract, financial_inputs, load_sources
from diligence.models import Review
from diligence.service import finalize_run, investigate, resume_run, review_run

# Reload explicit local settings when Streamlit reruns after a .env edit.
load_dotenv(Path(__file__).parent / ".env", override=True)
st.set_page_config(page_title="Diligence Workbench", page_icon="🔎", layout="wide")
st.title("Diligence Workbench")
st.caption("MGT 8803 · Fictional Meridian Industrial Supply LLC · Research, analyst judgment, then Python calculations")
store = AuditStore()


def money(value):
    return f"${float(value):,.0f}"


def show_failure(error):
    # Provider exceptions may contain request details; don't print credentials or raw payloads.
    detail = "".join(traceback.format_exception(error))
    for name, value in os.environ.items():
        if name.endswith("_API_KEY") and value:
            detail = detail.replace(value, "[redacted]")
    diagnostics = Path(__file__).parent / "audit" / "errors"
    diagnostics.mkdir(parents=True, exist_ok=True)
    diagnostic_id = uuid4().hex
    (diagnostics / f"{diagnostic_id}.txt").write_text(detail, encoding="utf-8")
    # OpenAI exposes the HTTP status as status_code; Gemini exposes it as code.
    code = getattr(error, "status_code", None) or getattr(error, "code", None)
    if code in {408, 504}:
        st.error("The AI provider timed out before completing its response. Please retry later. No accounting treatment was approved and no valuation was calculated by this failed investigation.")
    elif code == 503:
        st.error("The AI provider is temporarily unavailable or experiencing high demand (HTTP 503). Try again later, or explicitly select another model available to your project. This failed request did not approve a treatment or calculate a valuation.")
    elif code == 429:
        st.error("The AI provider's rate limit or quota was exceeded. For Gemini, check your project's active model limits in Google AI Studio; choosing a model does not guarantee free-tier quota.")
    elif code == 401:
        st.error("The AI provider rejected the API key (HTTP 401). Check OPENAI_API_KEY in your saved .env file for OpenAI, or GEMINI_API_KEY for Gemini. Use a valid active key, then refresh this page. Restarting the server does not fix a rejected key.")
    elif code in {400, 403}:
        st.error("The AI provider rejected the request. Check the API key, its project restrictions, model access, and structured-output support. Credentials have not been displayed.")
    elif code == 404:
        st.error("This model is unavailable for the configured API or project. Choose a model shown in your provider's console.")
    elif isinstance(error, (ValueError, PermissionError, FileNotFoundError)):
        st.error(str(error))
    else:
        st.error(f"Investigation could not finish ({type(error).__name__}). Check the model configuration, API access, and local source files. No automatic demo fallback was used.")
    with st.expander("Technical error details"):
        st.caption(f"Saved locally: audit/errors/{diagnostic_id}.txt")
        st.code(detail, language="text")


if not (DATA / "manifest.json").exists():
    st.error("Download the source subset first: python scripts/fetch_fab.py")
    st.stop()

try:
    passages = load_sources()
    inputs = financial_inputs()
except Exception as error:
    show_failure(error)
    st.stop()

with st.sidebar:
    st.subheader("Investigation setup")
    mode_label = st.radio("Execution mode", ["Offline scripted demo", "Live AI"])
    mode = "demo" if mode_label == "Offline scripted demo" else "live"
    providers = ["gemini", "openai"]
    default_provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    provider = st.selectbox("Live AI provider", providers,
        index=providers.index(default_provider) if default_provider in providers else 0,
        format_func=lambda value: {"gemini": "Google Gemini", "openai": "OpenAI"}[value], disabled=mode == "demo")
    default_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash") if provider == "gemini" else os.getenv("OPENAI_MODEL", "")
    model = st.text_input("Model", value=default_model, key=f"model_{provider}_{default_model}", disabled=mode == "demo")
    if mode == "demo":
        st.info("No LLM calls. Fixed teaching rules inspect the three original cases through the real LangGraph workflow.")
    else:
        provider_name = "Google Gemini" if provider == "gemini" else "OpenAI"
        key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
        st.caption(f"Uses {key_name} from your environment or .env. Source excerpts, including supplements, are sent to {provider_name} when you start. API charges or free-tier quotas may apply.")
        if provider == "gemini":
            st.caption("Default model: gemini-3.8-flash. Free-tier availability and limits depend on your Google project.")
    case = st.selectbox("Selected adjustment", list(CASES), format_func=lambda key: CASES[key]["label"])
    st.caption("Each calculation isolates this one adjustment; the full company's diligence bridge is outside this demo.")
    st.divider()
    history = store.history()
    if history:
        selected = st.selectbox("Saved investigations", [row["id"] for row in history],
            format_func=lambda value: next(f"{r['case']} · {r['status']} · {value[:8]}" for r in history if r["id"] == value))
        if st.button("Open saved investigation"):
            st.session_state["run"] = store.load(selected)
    st.caption("Sources: FAB by SecondState, CC BY 4.0. Local audit records are stored in audit/.")

st.subheader("1. Diligence question")
question = st.text_area("Question to investigate", value=CASES[case]["question"], key=f"question_{case}_{mode}", disabled=mode == "demo")
with st.expander("Source documents and financial inputs"):
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    st.write(f"Eight original FAB documents · pinned revision {manifest['revision'][:12]}")
    st.dataframe([{"Document": item["path"], "Bytes": item["bytes"], "SHA-256": item["sha256"]} for item in manifest["files"]], hide_index=True)
    selected_source = st.selectbox("Preview extracted source", sorted({p.source for p in passages}))
    preview = [f"[{p.location}]\n{p.text}" for p in passages if p.source == selected_source]
    st.text_area("Extracted passages (read-only)", "\n\n".join(preview), height=240, disabled=True)
    st.write(f"Reported EBITDA: {money(inputs['reported_ebitda'])}")
    st.caption(inputs["baseline_source"])
    st.write(f"Selected proposed add-back: {money(inputs['proposals'][case]['amount'])}")
    st.caption(inputs["proposals"][case]["source"])

if st.button("Start investigation", type="primary"):
    try:
        with st.status("Investigating source evidence…", expanded=True) as progress:
            def update(action, payload):
                if action == "stage_started":
                    progress.write(f"{payload['stage'].title()} · request in progress · attempt {payload['attempt']}")
                else:
                    progress.write(f"{action.replace('_', ' ').title()} · attempt {payload.get('attempt', 'review')}")
            st.session_state["run"] = investigate(case, passages, mode, model, question, store=store, on_event=update, provider=provider)
            progress.update(label="Investigation ready for analyst review", state="complete", expanded=False)
    except Exception as error:
        show_failure(error)

run = st.session_state.get("run")
if not run:
    st.info("Start with ERP, severance, or owner pay. You will review the evidence before choosing an accounting treatment.")
    st.stop()

st.divider()
st.subheader("2. Investigation and critique")
st.caption(f"Run {run['id'][:12]} · {run['mode']} · {run['case']} · {run['status']} · {run.get('revisions', 0)} revisions")
if run["mode"] == "live":
    st.caption(f"Saved run provider: {run.get('provider') or 'openai'} · model: {run['model']}")
st.write(run["question"])
if run["status"] == "error":
    st.error(f"This saved investigation failed: {run.get('error_type')}. Start a new run after resolving the configuration or source issue.")
    st.stop()
if run["status"] == "investigating":
    st.info("This saved investigation has not finished. Its partial actions remain in the audit ledger; start a new run to investigate again.")
    with st.expander("Recorded actions"):
        st.json(store.events(run["id"]), expanded=False)
    st.stop()
with st.expander("Planner tasks and workflow trace"):
    for task in run["plan"]["tasks"]:
        st.write(f"• {task}")
    for event in run["trace"]:
        st.json(event, expanded=False)

assessment = run["assessment"]
st.write(assessment["conclusion"])
st.caption(f"Provisional research recommendation: {assessment['recommendation'].replace('_', ' ')}. Final treatment is the analyst's decision.")
lookup = {p["id"]: p for p in run["evidence"]}
for finding in assessment["findings"]:
    source = lookup.get(finding["passage_id"])
    with st.expander(f"{finding['stance'].title()} · {source['source'] if source else 'Invalid source'}", expanded=True):
        if source:
            st.caption(f"{source['location']} · {finding['reporting_period']} · retrieval relevance {source['score']:.3f}")
            st.text(finding["quote"])
            st.write("Inference: " + finding["inference"])
            st.caption(f"Passage {source['id']} · SHA-256 {source['sha256']}")
            if source["url"]:
                st.link_button("Original source", source["url"])
        else:
            st.error("Citation integrity check failed. Do not rely on this finding.")
outcome = run["critique"]["outcome"]
{"PASS": st.success, "FAIL": st.error, "UNRESOLVED": st.warning}[outcome](f"Critic: {outcome}")
for feedback in run["critique"]["feedback"]:
    st.write(feedback)
for gap in assessment["gaps"]:
    st.warning("Evidence gap: " + gap)

st.subheader("3. Analyst review")
if run["status"] == "awaiting_review":
    with st.form(f"review_{run['id']}"):
        reviewer = st.text_input("Analyst name")
        action = st.selectbox("Your decision", ["defer", "accept_addback", "reject_addback", "request_information"],
            format_func=lambda value: {"defer": "Defer — leave the issue open", "accept_addback": "Approve adding back this expense",
                "reject_addback": "Keep this expense in EBITDA", "request_information": "Request additional information"}[value])
        rationale = st.text_area("Decision rationale or specific document request")
        multiple = st.number_input("Assumed enterprise-value / EBITDA multiple", min_value=0.1, max_value=50.0, value=10.0, step=0.5)
        confirmed = st.checkbox("I reviewed the evidence and approve recording this decision.")
        submitted = st.form_submit_button("Record analyst decision")
    if submitted:
        if not confirmed:
            st.error("Review and confirm the decision before submitting.")
        else:
            try:
                st.session_state["run"] = review_run(run, Review(reviewer=reviewer, rationale=rationale, action=action, multiple=str(multiple)), store)
                st.rerun()
            except Exception as error:
                show_failure(error)
else:
    review = run.get("review")
    if review:
        st.write(f"{review['reviewer']} · {review['action'].replace('_', ' ')}")
        st.write(review["rationale"])

if run["status"] == "information_requested":
    st.info("The request is recorded locally. It has not been sent to a seller.")
    if run["mode"] == "demo":
        st.caption("The scripted demo cannot assess new evidence. Start a live investigation to enable document upload and reinvestigation.")
    else:
        st.caption(f"Resuming sends all evidence to this run's saved provider ({run.get('provider') or 'openai'}) and model ({run['model']}). Sidebar settings apply to new investigations.")
        upload = st.file_uploader("Add supplemental evidence (max 5 MB)", type=["pdf", "docx", "xlsx", "txt", "md"], key=f"upload_{run['id']}")
        if st.button("Resume with supplemental evidence", disabled=upload is None):
            try:
                supplemental = extract(upload.getvalue(), "Supplemental/" + Path(upload.name).name)
                with st.status("Reviewing new evidence…", expanded=True) as progress:
                    st.session_state["run"] = resume_run(run, supplemental, store=store,
                        on_event=lambda action, payload: progress.write(action.replace("_", " ").title()))
                    progress.update(label="Supplemental review complete", state="complete")
                st.rerun()
            except Exception as error:
                show_failure(error)

st.subheader("4. Approved financial scenario")
result = run.get("results")
if not result:
    st.info("Valuation will be calculated only after the analyst approves a specific treatment.")
else:
    columns = st.columns(3)
    columns[0].metric("Reported EBITDA", money(result["reported_ebitda"]))
    columns[1].metric("Approved add-back", money(result["approved_addback"]))
    columns[2].metric("Reviewed EBITDA", money(result["reviewed_ebitda"]))
    st.dataframe([{"Scenario": "Seller proposal for selected item", "EBITDA": money(result["seller_case_ebitda"]),
                   "Multiple": result["multiple"] + "×", "Enterprise value": money(result["seller_enterprise_value"])},
                  {"Scenario": "Analyst-approved selected item", "EBITDA": money(result["reviewed_ebitda"]),
                   "Multiple": result["multiple"] + "×", "Enterprise value": money(result["reviewed_enterprise_value"])}], hide_index=True)
    st.write("Enterprise-value change: " + money(result["enterprise_value_change"]))
    st.caption("Deterministic Decimal calculations. This sensitivity isolates one adjustment; other FAB corrections, debt and working capital are excluded.")

st.subheader("5. Memo and audit trail")
if run.get("memo"):
    st.text_area("Draft diligence memo", run["memo"], height=280, disabled=True)
    st.download_button("Download memo", run["memo"], file_name=f"diligence-{run['id'][:8]}.md")
    if run["status"] == "reviewed":
        if st.button("Confirm final review of memo and calculations"):
            st.session_state["run"] = finalize_run(run, store)
            st.rerun()
    elif run["status"] == "finalized":
        st.success("Final analyst review recorded in the memo and audit ledger.")
events = store.events(run["id"])
with st.expander(f"Audit ledger · {len(events)} events"):
    st.json(events, expanded=False)
export = {"investigation": run, "events": events}
st.download_button("Download full audit JSON", json.dumps(export, ensure_ascii=False, indent=2), file_name=f"audit-{run['id'][:8]}.json")
