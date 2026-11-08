"""Fetch a small, revision-pinned public FAB subset. Never fetch answer rubrics."""
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "SecondState-ai/finance-agents-benchmark"
FILES = [
    "01 Financial/Earnings_schedule.xlsx",
    "01 Financial/Management_accounts_2025-12.xlsx",
    "03 Operations/Payroll_summary_2024.xlsx",
    "03 Operations/Payroll_summary_2025.xlsx",
    "03 Operations/Personnel_movements.xlsx",
    "03 Operations/Northstar_project_statement.pdf",
    "04 Legal/Executive_terms.docx",
    "05 Management/Board_minutes_2025-12.docx",
]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MGT8803-Diligence-Prototype"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def main():
    target = ROOT / "data" / "fab"
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        revision = json.loads(manifest_path.read_text(encoding="utf-8"))["revision"]
    else:
        revision = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/main"))["sha"]
    base = f"https://raw.githubusercontent.com/{REPO}/{revision}/"
    records = []
    for relative in FILES:
        remote = "tasks/meridian/data-room/" + relative
        url = base + urllib.parse.quote(remote)
        content = fetch(url)
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        records.append({"path": relative, "url": url, "sha256": hashlib.sha256(content).hexdigest(),
                        "bytes": len(content)})
        print(f"Fetched {relative} ({len(content):,} bytes)")
    (target / "LICENSE-DATA").write_bytes(fetch(base + "LICENSE-DATA"))
    manifest_path.write_text(json.dumps({"repository": f"https://github.com/{REPO}",
        "revision": revision, "license": "CC BY 4.0", "fictional": True,
        "files": records}, indent=2), encoding="utf-8")
    print(f"Pinned {len(records)} documents at {revision}")


if __name__ == "__main__":
    main()
