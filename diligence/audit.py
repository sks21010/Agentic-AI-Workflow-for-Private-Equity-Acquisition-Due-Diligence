"""Local JSON snapshots and an append-only event ledger (not tamper-proof storage)."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1] / "audit"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class AuditStore:
    def __init__(self, root: Path = ROOT):
        self.root = Path(root)

    def folder(self, run_id):
        # Only application-generated UUIDs may become filesystem paths.
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid investigation ID.")
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def event(self, run_id, action, payload):
        record = {"investigation_id": run_id, "event_id": uuid4().hex,
                  "timestamp_utc": timestamp(), "action": action, "payload": payload}
        with (self.folder(run_id) / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def save(self, run):
        folder = self.folder(run["id"])
        temporary = folder / f"{uuid4().hex}.tmp"
        temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(folder / "state.json")

    def load(self, run_id):
        return json.loads((self.folder(run_id) / "state.json").read_text(encoding="utf-8"))

    def events(self, run_id):
        path = self.folder(run_id) / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def history(self):
        if not self.root.exists():
            return []
        result = []
        for path in self.root.glob("*/state.json"):
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
                result.append({key: run[key] for key in ["id", "created_at", "case", "mode", "status"]})
            except (ValueError, KeyError):
                continue
        return sorted(result, key=lambda row: row["created_at"], reverse=True)
