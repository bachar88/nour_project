"""Lightweight stand-ins for the real models (no download, no GPU, no API key).
Used by the tests and by demo mode: NOUR_FAKE_MODELS=1 uvicorn app.main:app
Answers in demo mode are NOT real — they only quote retrieved text to exercise the UI."""
import hashlib
import re

import numpy as np

from .chunking import normalize_ar


def _words(t):
    return re.findall(r"\w+", normalize_ar(t))


class FakeEmbedder:
    """Bag of character trigrams hashed into 512 dims, L2-normalized."""
    def encode(self, texts):
        out = np.zeros((len(texts), 512), dtype=np.float32)
        for i, t in enumerate(texts):
            t = normalize_ar(t)
            for j in range(len(t) - 2):
                h = int(hashlib.md5(t[j:j + 3].encode()).hexdigest(), 16) % 512
                out[i, h] += 1
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class FakeReranker:
    """Share of the question's words (len > 2) found in the text."""
    def score(self, query, texts):
        q = {w for w in _words(query) if len(w) > 2}
        return [len(q & set(_words(t))) / max(1, len(q)) for t in texts]


class FakeLLM:
    """mode='quote': quotes 6 words of passage [1]; 'invent': quotes text that is not there;
    'abstain': returns the abstention sentence."""
    def __init__(self, mode="quote"):
        self.mode = mode
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        user = messages[-1]["content"]
        first = user.split("[1]", 1)[1].split(")\n", 1)[1].split("\n\n")[0]
        if self.mode == "abstain":
            return "لم يرد في النص ما يجيب عن هذا السؤال.", 10
        if self.mode == "invent":
            return "الجواب: حكم مخترع.\nالدليل: «هذا كلام غير موجود في المقطع أصلا» [1]", 50
        quote = " ".join(first.split()[:12])
        return (f"الجواب: (وضع تجريبي) هذا جواب مولَّد آليًا من المقطع الأول دون نموذج لغوي.\n"
                f"الدليل: «{quote}» [1]"), 50
