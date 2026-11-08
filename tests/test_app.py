from streamlit.testing.v1 import AppTest
from pathlib import Path


def test_streamlit_review_flow(tmp_path, monkeypatch):
    import diligence.audit
    # App constructs AuditStore without arguments, so redirect its default for this test.
    original = diligence.audit.AuditStore.__init__
    monkeypatch.setattr(diligence.audit.AuditStore, "__init__", lambda self, root=None: original(self, tmp_path))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    next(button for button in app.button if button.label == "Start investigation").click().run()
    assert not app.exception
    assert app.session_state["run"]["status"] == "awaiting_review"
    next(item for item in app.text_input if item.label == "Analyst name").set_value("Demo Analyst")
    next(item for item in app.text_area if item.label == "Decision rationale or specific document request").set_value("Implementation is separate from ongoing IT costs.")
    next(item for item in app.selectbox if item.label == "Your decision").select("accept_addback")
    next(item for item in app.checkbox if item.label.startswith("I reviewed")).check()
    next(button for button in app.button if button.label == "Record analyst decision").click().run()
    assert not app.exception
    assert app.session_state["run"]["results"]["reviewed_ebitda"] == "22366000"
    next(button for button in app.button if button.label == "Confirm final review of memo and calculations").click().run()
    assert not app.exception
    assert app.session_state["run"]["status"] == "finalized"


def test_openai_authentication_error_is_explained(tmp_path, monkeypatch):
    import diligence.service
    import httpx
    from openai import AuthenticationError
    original = diligence.audit.AuditStore.__init__
    monkeypatch.setattr(diligence.audit.AuditStore, "__init__", lambda self, root=None: original(self, tmp_path))
    def rejected(*args, **kwargs):
        raise AuthenticationError("Invalid API key", response=httpx.Response(401,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
            body={"error": {"code": "invalid_api_key"}})
    monkeypatch.setattr(diligence.service, "investigate", rejected)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(button for button in app.button if button.label == "Start investigation").click().run()
    assert not app.exception
    assert any("HTTP 401" in item.value and "rejected the API key" in item.value for item in app.error)
