from operator import add
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from diligence.agents import checked_critique
from diligence.models import Passage
from diligence.retrieval import Retriever


class InvestigationState(TypedDict, total=False):
    case: str
    question: str
    passages: list[Passage]
    attempt: int
    plan: dict
    evidence: list[Passage]
    findings: dict
    assessment: dict
    critique: dict
    status: str
    trace: Annotated[list[dict], add]


def build_graph(agents, record=lambda action, payload: None):
    def logged(action, payload):
        record(action, payload)
        return {"action": action, **payload}

    def planner(state):
        attempt = state.get("attempt", 0) + 1
        record("stage_started", {"stage": "planner", "attempt": attempt})
        plan = agents.plan(state).model_dump()
        event = logged("planner", {"attempt": attempt, "plan": plan})
        return {"plan": plan, "attempt": attempt, "trace": [event]}

    def investigator(state):
        record("stage_started", {"stage": "investigator", "attempt": state["attempt"]})
        retriever = Retriever(state["passages"])
        evidence = {}
        for query in state["plan"]["queries"]:
            for passage in retriever.search(query):
                if passage.id not in evidence or passage.score > evidence[passage.id].score:
                    evidence[passage.id] = passage
        found = list(evidence.values())
        findings = agents.investigate({**state, "evidence": found}).model_dump()
        event = logged("investigator", {"attempt": state["attempt"], "queries": state["plan"]["queries"],
            "retrieval_tool": "TF-IDF / cosine similarity", "evidence": [p.model_dump() for p in found],
            "findings": findings})
        return {"evidence": found, "findings": findings, "trace": [event]}

    def synthesizer(state):
        record("stage_started", {"stage": "synthesizer", "attempt": state["attempt"]})
        assessment = agents.synthesize(state).model_dump()
        event = logged("synthesizer", {"attempt": state["attempt"], "assessment": assessment})
        return {"assessment": assessment, "trace": [event]}

    def critic(state):
        record("stage_started", {"stage": "critic", "attempt": state["attempt"]})
        critique = checked_critique(agents, state).model_dump()
        event = logged("critic", {"attempt": state["attempt"], "critique": critique})
        return {"critique": critique, "trace": [event]}

    def route(state):
        return "planner" if state["critique"]["outcome"] == "FAIL" and state["attempt"] < 3 else "analyst_review"

    def analyst_review(state):
        critique = state["critique"]
        if critique["outcome"] == "FAIL":
            critique = {"outcome": "UNRESOLVED", "feedback": critique["feedback"] +
                        ["Maximum two revisions reached. Escalated with unresolved investigative defects."]}
        event = logged("awaiting_analyst", {"critique": critique, "revisions": state["attempt"] - 1})
        return {"status": "awaiting_review", "critique": critique, "trace": [event]}

    graph = StateGraph(InvestigationState)
    for name, node in [("planner", planner), ("investigator", investigator),
                       ("synthesizer", synthesizer), ("critic", critic), ("analyst_review", analyst_review)]:
        graph.add_node(name, node)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "investigator")
    graph.add_edge("investigator", "synthesizer")
    graph.add_edge("synthesizer", "critic")
    graph.add_conditional_edges("critic", route, {"planner": "planner", "analyst_review": "analyst_review"})
    graph.add_edge("analyst_review", END)
    return graph.compile()
