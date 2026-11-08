from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from diligence.models import Passage


class Retriever:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
        self.matrix = self.vectorizer.fit_transform([f"{p.source} {p.text}" for p in passages]) if passages else None

    def search(self, query: str, k: int = 6) -> list[Passage]:
        if self.matrix is None:
            return []
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        indexes = sorted(range(len(scores)), key=lambda i: (-scores[i], self.passages[i].id))[:k]
        return [self.passages[i].model_copy(update={"score": float(scores[i])})
                for i in indexes if scores[i] > 0]


def citation_errors(assessment, evidence: list[Passage]) -> list[str]:
    lookup = {p.id: p for p in evidence}
    errors = []
    for finding in assessment.findings:
        passage = lookup.get(finding.passage_id)
        if passage is None or finding.quote not in passage.text:
            errors.append(f"Invalid source or non-exact quote: {finding.passage_id}")
    if not assessment.findings and assessment.recommendation != "unresolved":
        errors.append("A resolved recommendation needs cited evidence.")
    return errors
