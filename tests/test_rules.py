from pathlib import Path

import pytest
import yaml

from job_radar.companies import Companies
from job_radar.home import Home
from job_radar.rules import Rules, pattern

HOME = Path(__file__).parent / "fixtures" / "home"


@pytest.fixture(scope="module")
def rules():
    return Home(HOME).rules


def hit(entries, text):
    return bool(pattern(entries).search(text))


def test_words_match_whole_words_only():
    assert hit(["india"], "bangalore, india")
    assert not hit(["india"], "indianapolis, indiana")
    assert hit(["ai"], "Director, AI Strategy")
    assert not hit(["ai"], "Chair of the board")


def test_wildcards():
    assert hit(["scien*"], "Data Scientist")
    assert hit(["scien*"], "Life Sciences")
    assert hit(["*health*"], "digital telehealth platform")
    assert hit(["*care"], "Healthcare")
    assert not hit(["*care"], "career")


def test_not_after_and_not_before():
    manager = [{"word": "manager", "not_after": ["product", "program"]}]
    assert hit(manager, "Engineering Manager")
    assert not hit(manager, "Senior Product Manager")
    chief = [{"word": "chief", "not_before": ["of staff"]}]
    assert hit(chief, "Chief Technology Officer")
    assert not hit(chief, "Chief of Staff")


def test_then_sequences():
    seq = [{"then": [["director", "head"], ["product"]]}]
    assert hit(seq, "Head of AI Product")
    assert not hit(seq, "Product Director")   # order matters
    assert not hit(seq, "Directorate of productivity")


def test_regex_escape_hatch_and_phrases():
    assert hit(["/\\bdirector ?(/|or) ?senior director/"], "director/senior director, ai")
    assert hit(["r&d strategy"], "Head of R&D Strategy")
    assert hit(["a.i."], "a.i. lead")
    assert pattern([]) is None


def test_bad_entry_is_reported():
    with pytest.raises(ValueError):
        pattern([{"nonsense": 1}])


@pytest.mark.parametrize("company,title,location,expected", [
    ("Lab Co", "Director, Machine Learning", "New York, NY", (8, None)),            # 4 + 3 + 1
    ("Lab Co", "Machine Learning Engineer", "New York, NY", (None, "hands-on engineering")),
    ("Lab Co", "Machine Learning Engineer, Head of Team", "Remote", (7, None)),       # exempt: head
    ("Lab Co", "Senior Product Manager, AI", "Remote", (None, "low score (4)")),     # 1 + 2 + 1
    ("Lab Co", "Director/Senior Director, AI", "New York", (8, None)),
    ("Lab Co", "Senior Director, AI", "New York", (None, "too senior")),
    ("Example Health", "Chief of Staff", "NYC", (9, None)),                         # 4 + 3 + 2
    ("Example Health", "Chief AI Officer", "NYC", (None, "too senior")),
    ("Example Health", "Associate Director, AI", "NYC", (9, None)),                  # 4 + 3 + 2
    ("Example Health", "Associate, AI", "NYC", (None, "too junior")),
    ("A Fund", "Associate", "New York", (10, None)),                                 # investor 4 + 3 + funder 3
    ("Lab Co", "Associate", "New York", None),                                        # off-topic elsewhere
    ("A Fund", "Partner 3, Principal", "New York", (10, None)),                       # noise stripped
    ("Builder Co", "Principal", "Remote", (8, None)),                                 # investor 4 + 2 + default 2
    ("Lab Co", "AI Sales Lead", "New York", (None, "wrong function")),
    ("Lab Co", "AI Recruiting Partner", "New York", (None, "wrong function")),
    ("Quant Co", "Head of AI", "New York", (7, None)),                   # 4 + 3 + 0
    ("Lab Co", "Head of AI", "Remote - India", (None, "location")),
    ("Lab Co", "Head of AI", "Remote - Indiana", (7, None)),
    ("Lab Co", "Head of AI", "Titusville, NJ", (None, "location")),
    ("Lab Co", "Head of AI", "Princeton, NJ", (None, "low score (6)")),
    ("Lab Co", "Head of AI", "London; New York", (8, None)),
    ("Lab Co", "Head of AI", "3 Locations", (None, "low score (5)")),
    ("Lab Co", "Head of AI", "Remote, Europe", (None, "location")),
    ("Lab Co", "Head of AI", "Remote, European Union", (None, "location")),
    ("Lab Co", "Head of AI", "Remote | European Union", (7, None)),                   # each site counts alone
])
def test_score(rules, company, title, location, expected):
    assert rules.score(company, title, location) == expected


def test_outside_domain_gets_no_employer_bonus(rules):
    assert rules.score("Lab Co", "Director, Machine Learning", "New York") == (8, None)
    assert rules.score("Lab Co", "Director, Machine Learning", "New York", outside_domain=True) == (7, None)


def test_funders_come_from_packs_and_file(rules):
    assert "A Fund" in rules.investors
    assert "Schmidt Sciences" in rules.investors           # from the science-funders pack
    assert "Simons Foundation" not in rules.investors      # excluded in companies.yaml
    assert "Builder Co" in rules.investors                 # listed in rules.yaml
    assert rules.bonus["A Fund"] == 3 and rules.bonus["Lab Co"] == 1


def test_domain(rules):
    assert rules.in_domain("Digital Health  Acme")
    assert rules.in_domain("Biotech Acme")
    assert not rules.in_domain("Fintech Payments Acme")
    assert Rules({}).in_domain("anything")
    assert rules.domain_name == "health"


def test_searches(rules):
    assert rules.searches == ["machine learning"]
    assert rules.portfolio_searches == ["machine learning", "AI"]


def test_template_rules_compile():
    import job_radar
    template = Path(job_radar.__file__).parent / "templates" / "profile" / "rules.yaml"
    r = Rules(yaml.safe_load(template.read_text()), Companies())
    assert r.score("Example", "Director, Machine Learning", "New York, NY")[0] is not None
    assert r.score("Example", "Chief of Staff", "Remote")[1] != "too senior"
