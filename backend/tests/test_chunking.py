from app.chunking import find_quote_spans, normalize_ar


def test_babs_and_units(corpus):
    assert [b["title"] for b in corpus.books["akhdari"].babs][:2] == ["باب في الطهارة", "باب في التيمم"]
    assert len(corpus.books["risala"].babs) == 15
    # the header with a missing «[» is still detected and cleaned
    assert "باب في الصلاة على الجنائز والدعاء للميت" in [b["title"] for b in corpus.books["risala"].babs]
    assert 100 < len(corpus.chunks) < 250


def test_sections_inherit_parent_topic(corpus):
    sections = {u.section for u in corpus.units.values() if u.book_key == "akhdari"}
    assert "فرائض الوضوء سبع — وسننه" in sections
    assert "فرائض الصلاة" in sections


def test_risala_page_breaks_rejoined(corpus):
    # «وإن كان» / «وحده» were split by a page break in the source file
    first = corpus.units["risala-00-000"].text
    assert "وإن كان وحده لقول النبي" in first


def test_chunks_respect_size(corpus):
    assert max(len(c.text) for c in corpus.chunks) <= 450 + 350


def test_expected_keywords_present(corpus):
    texts = [normalize_ar(c.text) for c in corpus.chunks]
    for kw in ["اربعة برد", "احدى عشرة سجدة", "ما بين السرة والركبة", "فللنقصان سجدتان قبل السلام"]:
        assert any(kw in t for t in texts), kw


def test_find_quote_spans_ignores_diacritics_and_punctuation():
    text = "الوُضُوءُ يجب، لما يخرج من أحد المخرجين. ومن نسي"
    spans = find_quote_spans(text, "الوضوء يجب لما يخرج من احد")
    assert spans and text[spans[0][0]:spans[0][1]] == "الوُضُوءُ يجب، لما يخرج من أحد"
    assert find_quote_spans(text, "كلام غير موجود") is None
    two = find_quote_spans(text, "الوضوء يجب ... ومن نسي")
    assert two and len(two) == 2
