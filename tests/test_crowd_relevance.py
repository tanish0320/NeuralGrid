from __future__ import annotations

from apps.api.app.modules.event_intelligence.relevance import score_crowd_relevance


def test_rejects_crime_legal_and_human_interest_articles() -> None:
    rejected_titles = [
        "Bengaluru autorickshaw driver lures boy with iPhone, motorcycle to steal ₹39 lakh valuables",
        "Woman’s bid to discipline son over matrimonial matter turns fatal in Tumakuru",
        "Lawyer drags sister out of house in Bengaluru, beats her to death with cricket bat",
        "Fake bills, forged entries: Bengaluru police book 21 in BMTC spare parts scam",
        "Bengaluru-based sari boutique pays homage to MS Subbulakshmi with archival collection",
        "‘Don’t bring children’: Diljit Dosanjh’s Bengaluru concert gets bomb threat",
        "22-year-old killed by friends for trying to cut ties following daughter’s birth in Bengaluru",
    ]
    for title in rejected_titles:
        res = score_crowd_relevance(title=title, domain="www.thehindu.com", source_type="news_article")
        assert res.is_relevant is False, f"Expected irrelevant for: {title} (got {res})"
        assert res.category == "irrelevant"
        assert res.score == 0


def test_accepts_and_ranks_mass_crowd_gatherings() -> None:
    concert = score_crowd_relevance(
        title="Echoes of Earth 2026: The Hills come alive",
        text="Two-day music festival in Bengaluru with thousands of attendees",
        domain="www.thehindu.com",
        source_type="news_article",
    )
    jatre = score_crowd_relevance(
        title="Over 200 events, 500 folk artists, Sunidhi Chauhan live: Inside Bengaluru Jatre",
        text="Cultural festival hosted at Palace Grounds",
        domain="indianexpress.com",
        source_type="news_article",
    )
    aero = score_crowd_relevance(
        title="Aero India 2027 expands exhibition space in Bengaluru amid rising demand",
        text="Major airshow and exhibition at Yelahanka Air Force Station",
        domain="timesofindia.indiatimes.com",
        source_type="news_article",
    )
    indusfood = score_crowd_relevance(
        title="Indusfood 2026 Bengaluru",
        text="Food trade fair and expo at BIEC",
        domain="allevents.in",
        source_type="ticketing_page",
    )
    food_fest = score_crowd_relevance(
        title="Bengaluru gallery’s food festival takes sustainability science beyond exhibits",
        text="Weekend food festival at Science Gallery Bengaluru",
        domain="indianexpress.com",
        source_type="news_article",
    )
    protest = score_crowd_relevance(
        title="Rain or shine, ASHAs continue their protest seeking better pay",
        text="Workers gather at Freedom Park for protest",
        domain="www.thehindu.com",
        source_type="news_article",
    )

    for label, res in [
        ("concert", concert),
        ("jatre", jatre),
        ("aero", aero),
        ("indusfood", indusfood),
        ("food_fest", food_fest),
        ("protest", protest),
    ]:
        assert res.is_relevant is True, f"Expected relevant for {label}: {res}"
        assert res.score >= 30

    assert jatre.estimated_attendance >= 28000
    assert aero.estimated_attendance == 38000
    assert concert.score > 30


def test_word_boundary_safety_no_false_positives() -> None:
    # "art" inside "articleshow" / "department", "match" inside "matrimonial" etc. must never match
    tricky = [
        "Department releases quarterly municipal audit report in Bengaluru",
        "Metro phase update delivered in articleshow portal",
        "Matrimonial portal launches new mobile app feature",
        "Startup delivers smart meter update across apartments",
    ]
    for title in tricky:
        res = score_crowd_relevance(title=title, domain="timesofindia.indiatimes.com", source_type="news_article")
        assert res.is_relevant is False, f"False positive for tricky title: {title} ({res})"
