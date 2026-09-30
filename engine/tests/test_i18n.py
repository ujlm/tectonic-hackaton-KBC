"""Belgian number and date formats, natural frequencies, and complete translations."""
import re

from app import i18n
from app.assumptions import CATALOGUE
from app.i18n.services import ACTIONS, RESULTS
from app.journeys import HELP_ITEMS
from app.services.registry import SERVICES


def test_money_formats():
    assert i18n.eur(3200, "en") == "€3,200"
    assert i18n.eur(3200, "nl") == "€ 3.200"
    assert i18n.eur(3200, "fr") == "3 200 €"
    assert i18n.eur(-420, "en") == "−€420"
    assert i18n.eur(4.95, "nl", decimals=2) == "€ 4,95"


def test_natural_frequencies_never_show_percentages():
    assert i18n.natural_frequency(0.38, "en") == "about 4 in 10"
    assert i18n.natural_frequency(0.38, "nl") == "ongeveer 4 op de 10"
    assert i18n.natural_frequency(0.04, "fr") == "environ 4 sur 100"
    assert i18n.natural_frequency(0.001, "en") == "fewer than 1 in 100"
    for p in (0.0, 0.03, 0.2, 0.5, 0.97):
        assert "%" not in i18n.natural_frequency(p, "en")


def test_months():
    assert i18n.month_label("2027-02", "fr", long=True) == "février 2027"
    assert i18n.month_label("2027-03", "nl") == "mrt 2027"


def _placeholders(s: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", s))


def test_every_customer_text_is_translated_with_the_same_placeholders():
    for lang in ("nl", "fr"):
        for f, c in CATALOGUE.items():
            t = i18n.features.TEXT[lang][f]
            for key in ("label", "label_zero", "label_one", "label_false", "label_null", "evidence", "evidence_false"):
                if key in c:
                    assert key in t, (lang, f, key)
                    assert _placeholders(t[key]) == _placeholders(c[key]), (lang, f, key)
        for h in HELP_ITEMS:
            title, say = i18n.journeys.HELP[lang][h.id]
            assert _placeholders(title) == _placeholders(h.title), (lang, h.id)
            assert _placeholders(say) == _placeholders(h.say), (lang, h.id)
        for sid, svc in SERVICES.items():
            for a in svc.actions:
                assert f"{sid}.{a.id}" in ACTIONS[lang], (lang, sid, a.id)
        assert set(RESULTS[lang]) == set(RESULTS["en"]), lang
