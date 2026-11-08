import json
from types import SimpleNamespace

import pytest

from diligence.agents import DemoAgents, GeminiAgents
from diligence.audit import AuditStore
from diligence.documents import load_sources
from diligence.models import Plan, Review
from diligence.service import investigate, resume_run, review_run


def test_gemini_requires_configuration(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiAgents("gemini-3.8-flash")


def test_gemini_uses_structured_json_and_selected_model():
    calls = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(text=json.dumps({"tasks": ["Check source facts"], "queries": ["ERP"]}),
                               model_version="resolved-test-version")
    agents = GeminiAgents.__new__(GeminiAgents)
    agents.model = "gemini-3.8-flash"
    agents.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    result = agents.plan({"question": "ERP add-back?", "passages": []})
    assert isinstance(result, Plan)
    assert calls[0]["model"] == "gemini-3.8-flash"
    assert calls[0]["config"].response_mime_type == "application/json"
    assert calls[0]["config"].response_json_schema == Plan.model_json_schema()
    assert "untrusted data" in calls[0]["config"].system_instruction
    assert agents.last_response_metadata["resolved_model"] == "resolved-test-version"


@pytest.mark.parametrize("text", [None, "not JSON", '{"tasks": [], "queries": []}'])
def test_gemini_invalid_output_is_not_silently_accepted(text):
    agents = GeminiAgents.__new__(GeminiAgents)
    agents.model = "gemini-3.8-flash"
    agents.client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=text)))
    with pytest.raises((ValueError, RuntimeError)):
        agents.plan({"question": "ERP?", "passages": []})


def test_gemini_provider_is_saved_and_used_on_resume(tmp_path, monkeypatch):
    import diligence.service
    from diligence.documents import extract
    requested_models = []
    class MockGemini(DemoAgents):
        def __init__(self, model):
            requested_models.append(model)
    monkeypatch.setattr(diligence.service, "GeminiAgents", MockGemini)
    store = AuditStore(tmp_path)
    run = investigate("owner_pay", load_sources(), mode="live", model="gemini-3.8-flash",
                      provider="gemini", store=store)
    assert run["provider"] == "gemini"
    requested = review_run(run, Review(reviewer="Analyst", rationale="Provide an independent survey.",
                                      action="request_information"), store)
    resumed = resume_run(requested, extract(b"A replacement CEO salary survey.", "Supplemental/survey.txt"), store=store)
    assert resumed["provider"] == "gemini"
    assert resumed["parent_id"] == run["id"]
    assert requested_models == ["gemini-3.8-flash", "gemini-3.8-flash"]


def test_example_file_has_no_keys():
    from dotenv import dotenv_values
    from pathlib import Path
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env.example")
    assert not values.get("GEMINI_API_KEY")
    assert not values.get("OPENAI_API_KEY")


def test_native_gemini_sdk_full_workflow(tmp_path, monkeypatch):
    """Exercise actual SDK request/response conversion, with only HTTP mocked."""
    import httpx
    from google import genai
    from google.genai import types
    import diligence.service
    from diligence.cases import CASES
    calls = []
    case = CASES["erp"]

    def respond(request):
        body = json.loads(request.content)
        schema = body["generationConfig"]["responseJsonSchema"]["title"]
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        calls.append(schema)
        if schema == "Plan":
            output = {"tasks": ["Check implementation against ongoing IT costs"], "queries": case["queries"]}
        elif schema == "Findings":
            passage = next(p for p in payload["evidence"] if case["fact"] in p["text"])
            output = {"findings": [{"claim": payload["question"], "stance": "supports", "passage_id": passage["id"],
                "quote": case["fact"], "reporting_period": "FY2025", "inference": case["inference"]}], "gaps": []}
        elif schema == "Assessment":
            output = {"conclusion": case["inference"], "recommendation": "accept_addback", **payload["investigation"]}
        elif schema == "Critique":
            output = {"outcome": "PASS", "feedback": ["Evidence supports provisional analyst review."]}
        else:
            raise AssertionError(schema)
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"text": json.dumps(output)}]}, "finishReason": "STOP"}], "modelVersion": "gemini-3.8-flash-test"})

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as http_client:
        with genai.Client(api_key="mock-key-not-real", http_options=types.HttpOptions(httpx_client=http_client)) as client:
            agents = GeminiAgents.__new__(GeminiAgents)
            agents.model = "gemini-3.8-flash"
            agents.client = client
            run = investigate("erp", load_sources(), mode="live", model=agents.model, provider="gemini",
                              agents=agents, store=AuditStore(tmp_path))
    assert calls == ["Plan", "Findings", "Assessment", "Critique"]
    assert run["status"] == "awaiting_review"
    assert "results" not in run
    assert run["critique"]["outcome"] == "PASS"
    assert all(event["model_response"]["resolved_model"] == "gemini-3.8-flash-test"
               for event in run["trace"] if event["action"] != "awaiting_analyst")


def test_gemini_busy_response_is_not_retried_or_treated_as_success(tmp_path, monkeypatch):
    import httpx
    from google import genai
    from google.genai import types, errors
    import diligence.service
    requests = []

    def unavailable(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE",
            "message": "This model is currently experiencing high demand."}})

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as http_client:
        with genai.Client(api_key="mock-key-not-real", http_options=types.HttpOptions(
                httpx_client=http_client, retry_options=types.HttpRetryOptions(attempts=1))) as client:
            agents = GeminiAgents.__new__(GeminiAgents)
            agents.model = "gemini-3.8-flash"
            agents.client = client
            store = AuditStore(tmp_path)
            updates = []
            with pytest.raises(errors.ServerError) as failure:
                investigate("erp", load_sources(), mode="live", model=agents.model, provider="gemini",
                    agents=agents, store=store, on_event=lambda action,payload:updates.append((action,payload)))
    assert failure.value.code == 503
    assert len(requests) == 1
    assert updates[0] == ("stage_started", {"stage": "planner", "attempt": 1})
    saved = store.load(store.history()[0]["id"])
    assert saved["status"] == "error"
    assert "results" not in saved
