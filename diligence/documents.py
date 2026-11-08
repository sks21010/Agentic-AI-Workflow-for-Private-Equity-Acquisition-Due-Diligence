"""Extract source-located passages without executing document content."""
import hashlib
import io
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

from openpyxl import load_workbook
from pypdf import PdfReader

from diligence.models import Passage

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "fab"


def extract(content: bytes, source: str, url: str = "") -> list[Passage]:
    if len(content) > 5_000_000:
        raise ValueError("Use a document smaller than 5 MB for this prototype.")
    digest = hashlib.sha256(content).hexdigest()
    chunks = []
    suffix = Path(source).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                chunks.append((f"page {page_number}", text.strip()))
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20_000_000:
                raise ValueError("Expanded DOCX is too large.")
            root = ET.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for number, paragraph in enumerate(root.findall(".//w:p", ns), 1):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
            if text.strip():
                chunks.append((f"paragraph {number}", text.strip()))
    elif suffix == ".xlsx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 20_000_000:
                raise ValueError("Expanded spreadsheet is too large.")
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        try:
            for sheet in workbook:
                if sheet.max_row > 5000 or sheet.max_column > 100:
                    raise ValueError("Use a smaller spreadsheet for this prototype.")
                # FAB uses row 4 for headers. Preserve all cells and their coordinates.
                header = " | ".join(str(c.value) for c in sheet[4] if c.value is not None)
                for row in sheet.iter_rows():
                    populated = [c for c in row if c.value is not None]
                    cells = [f"{c.coordinate}: {c.value}" for c in populated]
                    if cells:
                        location = f"'{sheet.title}'!{populated[0].coordinate}:{populated[-1].coordinate}"
                        chunks.append((location, f"Headers: {header}\n" + " | ".join(cells)))
        finally:
            workbook.close()
    elif suffix in {".txt", ".md"}:
        for number, line in enumerate(content.decode("utf-8-sig").splitlines(), 1):
            if line.strip():
                chunks.append((f"line {number}", line.strip()))
    else:
        raise ValueError("Supported formats: PDF, DOCX, XLSX, UTF-8 TXT and MD.")
    if not chunks:
        raise ValueError(f"No readable text in {source}. Scanned PDFs need OCR, which is not included.")
    if len(chunks) > 6000:
        raise ValueError("Too many passages for this prototype.")
    source_key = hashlib.sha256(source.encode()).hexdigest()[:8]
    return [Passage(id=f"{source_key}-{digest[:12]}-{i}", source=source, location=loc,
                    text=text, sha256=digest, url=url)
            for i, (loc, text) in enumerate(chunks, 1)]


def load_sources() -> list[Passage]:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    passages = []
    for record in manifest["files"]:
        content = (DATA / record["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"Source hash mismatch: {record['path']}")
        passages.extend(extract(content, record["path"], record["url"]))
    return passages


def financial_inputs() -> dict:
    """Read the reported baseline and management proposals from their source cells."""
    baseline_book = load_workbook(DATA / "01 Financial/Management_accounts_2025-12.xlsx", data_only=True)
    try:
        sheet = baseline_book["2025-12 YTD"]
        if sheet["A21"].value != "EBITDA":
            raise ValueError("Unexpected baseline layout; review source cells.")
        baseline = str(sheet["B21"].value)
    finally:
        baseline_book.close()
    proposals_book = load_workbook(DATA / "01 Financial/Earnings_schedule.xlsx", data_only=True)
    try:
        proposals = {}
        expected = {"erp": (5, "ERP implementation"), "severance": (6, "Severance"),
                    "owner_pay": (7, "Salaries")}
        for key, (row, label) in expected.items():
            sheet = proposals_book["Adjustments"]
            if sheet.cell(row, 1).value != label:
                raise ValueError("Unexpected earnings schedule layout; review source cells.")
            proposals[key] = {"amount": str(sheet.cell(row, 2).value),
                              "source": f"Earnings_schedule.xlsx · 'Adjustments'!B{row}"}
    finally:
        proposals_book.close()
    return {"reported_ebitda": baseline, "proposals": proposals,
            "baseline_source": "Management_accounts_2025-12.xlsx · '2025-12 YTD'!B21"}
