from uuid import uuid4

from diligence.agents import DemoAgents, GeminiAgents, LiveAgents
from diligence.audit import AuditStore, timestamp
from diligence.cases import CASES
from diligence.documents import financial_inputs
from diligence.finance import approved_analysis
from diligence.models import Review
from diligence.workflow import build_graph


def investigate(case, passages, mode="demo", model="", question=None, parent_id=None,
                store=None, on_event=None, agents=None, provider="openai"):
    store = store or AuditStore()
    inputs = financial_inputs()
    if mode not in {"demo", "live"}:
        raise ValueError("Choose demo or live mode.")
    if provider not in {"openai", "gemini"}:
        raise ValueError("Choose OpenAI or Gemini as the live provider.")
    # Never silently substitute the scripted mode for a failed API call.
    factory = GeminiAgents if provider == "gemini" else LiveAgents
    agents = agents or (DemoAgents() if mode == "demo" else factory(model))
    default_question = CASES[case]["question"]
    if mode == "demo" and question and question != default_question:
        raise ValueError("The scripted demo supports only the predefined case question. Use live mode for other questions.")
    if len(passages) > 2000 or sum(len(p.text) for p in passages) > 250_000:
        raise ValueError("The evidence corpus is too large for this bounded prototype.")
    run = {"id": uuid4().hex, "created_at": timestamp(), "case": case, "mode": mode,
           "provider": provider if mode == "live" else None,
           "model": model if mode == "live" else None, "question": question or default_question,
           "parent_id": parent_id, "status": "investigating", "inputs": inputs,
           "proposed_addback": inputs["proposals"][case]["amount"],
           "passages": [p.model_dump() for p in passages], "trace": []}
    store.save(run)
    store.event(run["id"], "investigation_started", {"case": case, "mode": mode, "provider": run["provider"], "model": run["model"],
                "question": run["question"], "parent_id": parent_id, "source_passages": run["passages"],
                "inputs": inputs})

    def record(action, payload):
        metadata = getattr(agents, "last_response_metadata", None)
        if metadata:
            payload["model_response"] = metadata
            agents.last_response_metadata = None
        store.event(run["id"], action, payload)
        if on_event:
            on_event(action, payload)

    try:
        result = build_graph(agents, record).invoke({"case": case, "question": run["question"],
            "passages": passages, "attempt": 0, "trace": []}, config={"recursion_limit": 30})
        for key in ["plan", "findings", "assessment", "critique", "status", "attempt", "trace"]:
            run[key] = result[key]
        run["evidence"] = [p.model_dump() for p in result["evidence"]]
        run["revisions"] = result["attempt"] - 1
        store.save(run)
        return run
    except Exception as error:
        run["status"] = "error"
        run["error_type"] = type(error).__name__
        store.event(run["id"], "investigation_failed", {"error_type": type(error).__name__})
        store.save(run)
        raise


def review_run(run, review: Review, store=None):
    store = store or AuditStore()
    current = store.load(run["id"])
    if current["status"] != "awaiting_review":
        raise ValueError("Only a pending investigation can receive an analyst decision.")
    if not review.reviewer.strip() or not review.rationale.strip():
        raise ValueError("Enter a reviewer name and a substantive rationale or document request.")
    decision = review.model_dump()
    results = None
    if review.action in {"accept_addback", "reject_addback"}:
        results = approved_analysis(current["inputs"]["reported_ebitda"], current["proposed_addback"], decision)
    recommendation = current["assessment"]["recommendation"]
    override = review.action in {"accept_addback", "reject_addback"} and (
        recommendation != review.action or current["critique"]["outcome"] != "PASS")
    current["review"] = {**decision, "timestamp_utc": timestamp(), "research_override": override}
    current["status"] = {"request_information": "information_requested", "defer": "deferred"}.get(review.action, "reviewed")
    current["results"] = results
    if results:
        current["memo"] = make_memo(current)
    store.event(current["id"], "analyst_decision", {"review": current["review"], "results": results,
                                                 "status": current["status"]})
    store.save(current)
    return current


def resume_run(run, supplemental, model="", store=None, on_event=None):
    from diligence.models import Passage
    store = store or AuditStore()
    current = store.load(run["id"])
    if current["status"] != "information_requested":
        raise ValueError("Request information before resuming an investigation.")
    if not supplemental:
        raise ValueError("Add a supplemental document before resuming.")
    if current["mode"] != "live":
        raise ValueError("Supplemental evidence requires live mode; demo rules cannot assess new documents.")
    passages = [Passage.model_validate(p) for p in current["passages"]]
    existing = {p.id for p in passages}
    added = [p for p in supplemental if p.id not in existing]
    if not added:
        raise ValueError("The supplemental document is already in this investigation.")
    resumed = investigate(current["case"], passages + added, mode="live", model=model or current["model"],
        question=current["question"], parent_id=current["id"], store=store, on_event=on_event,
        provider=current.get("provider") or "openai")
    store.event(current["id"], "resumed_as", {"child_id": resumed["id"]})
    return resumed


def finalize_run(run, store=None):
    store = store or AuditStore()
    current = store.load(run["id"])
    if current["status"] != "reviewed" or not current.get("results"):
        raise ValueError("Approve a treatment and review its results before finalizing.")
    current["status"] = "finalized"
    current["finalized_at"] = timestamp()
    current["memo"] = current["memo"].replace("# Draft diligence summary — analyst review required",
        "# Diligence summary — analyst reviewed", 1) + f"\n\nFinal analyst review recorded: {current['finalized_at']}."
    store.event(current["id"], "memo_final_review", {"reviewer": current["review"]["reviewer"],
                                                 "timestamp_utc": current["finalized_at"]})
    store.save(current)
    return current


def make_memo(run):
    result = run["results"]
    lines = ["# Draft diligence summary — analyst review required", "",
        "Fictional company: Meridian Industrial Supply LLC. Scope: one selected adjustment only.",
        f"Investigation: {run['id']} | Mode: {run['mode']} | Provider: {run.get('provider')} | Model: {run.get('model')}", "", f"Question: {run['question']}",
        f"Provisional research conclusion: {run['assessment']['conclusion']}",
        f"Critic: {run['critique']['outcome']}. " + " ".join(run["critique"]["feedback"]), "",
        f"Analyst: {run['review']['reviewer']} | Decision: {run['review']['action']}",
        f"Rationale: {run['review']['rationale']}", "",
        f"Analyst override of research recommendation or unresolved critique: {run['review']['research_override']}.",
        f"Reported FY2025 EBITDA: USD {result['reported_ebitda']}.",
        f"Proposed add-back: USD {result['proposed_addback']}; approved add-back: USD {result['approved_addback']}.",
        f"Selected-item seller-case EBITDA: USD {result['seller_case_ebitda']}.",
        f"Selected-item reviewed EBITDA: USD {result['reviewed_ebitda']}.",
        f"Assumed multiple: {result['multiple']}x.",
        f"Selected-item reviewed enterprise value: USD {result['reviewed_enterprise_value']}.",
        f"Change from selected-item seller case: USD {result['enterprise_value_change']}.", "",
        "These figures isolate one proposed add-back. They are not the full FAB adjusted-EBITDA bridge or an investment valuation conclusion.",
        "Other accounting corrections, debt, working capital, taxes and run-rate issues are outside this calculation.", "", "## Evidence"]
    lookup = {p["id"]: p for p in run["evidence"]}
    for finding in run["assessment"]["findings"]:
        source = lookup.get(finding["passage_id"])
        if source:
            lines.extend([f"- {finding['stance']} | {source['source']} | {source['location']} | {finding['reporting_period']}",
                          f"  Source excerpt: {finding['quote']}", f"  Inference: {finding['inference']}",
                          f"  SHA-256: {source['sha256']}"])
    lines.extend(["", "## Open evidence gaps"] + [f"- {gap}" for gap in run["assessment"]["gaps"]])
    return "\n".join(lines)
