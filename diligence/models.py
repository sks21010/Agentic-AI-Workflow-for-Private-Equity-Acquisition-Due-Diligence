from typing import Literal
from pydantic import BaseModel, Field


class Passage(BaseModel):
    id: str
    source: str
    location: str
    text: str
    sha256: str
    url: str
    score: float = 0.0


class Plan(BaseModel):
    tasks: list[str] = Field(min_length=1, max_length=6)
    queries: list[str] = Field(min_length=1, max_length=6)


class Finding(BaseModel):
    claim: str
    stance: Literal["supports", "challenges", "insufficient"]
    passage_id: str
    quote: str = Field(min_length=1)
    reporting_period: str
    inference: str


class Findings(BaseModel):
    findings: list[Finding]
    gaps: list[str]


class Assessment(BaseModel):
    conclusion: str
    recommendation: Literal["accept_addback", "reject_addback", "unresolved"]
    findings: list[Finding]
    gaps: list[str]


class Critique(BaseModel):
    outcome: Literal["PASS", "FAIL", "UNRESOLVED"]
    feedback: list[str] = Field(min_length=1)


class Review(BaseModel):
    reviewer: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    action: Literal["accept_addback", "reject_addback", "request_information", "defer"]
    multiple: str = "10"
