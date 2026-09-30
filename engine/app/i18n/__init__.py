"""Customer-facing language: NL / FR / EN strings and Belgian number and date formats.

English lives next to the logic (assumption catalogue, help items, service registry); this package holds the Dutch and
French versions, keyed by the same ids. Anything a customer can read goes through here. The jury's
under-the-hood panel stays in English.
"""
from . import features, journeys, services, ui

LANGS = ("en", "nl", "fr")
NBSP, NNBSP = " ", " "
MINUS = "−"

MONTHS_SHORT = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "nl": ["jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec"],
    "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
}
MONTHS_LONG = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"],
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
           "november", "december"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
}


def norm(lang: str | None) -> str:
    lang = (lang or "en").lower()[:2]
    return lang if lang in LANGS else "en"


def month_label(ym: str, lang: str = "en", long: bool = False) -> str:
    y, m = ym.split("-")[:2]
    names = (MONTHS_LONG if long else MONTHS_SHORT)[norm(lang)]
    return f"{names[int(m) - 1]} {y}"


def _group(n: int, sep: str) -> str:
    return f"{n:,}".replace(",", sep)


def number(v: float, lang: str = "en", decimals: int = 0) -> str:
    lang = norm(lang)
    whole = _group(int(abs(v)), {"en": ",", "nl": ".", "fr": NNBSP}[lang])
    if decimals:
        frac = f"{abs(v):.{decimals}f}".split(".")[1]
        whole += ("." if lang == "en" else ",") + frac
    return whole


def eur(v: float, lang: str = "en", signed: bool = False, decimals: int = 0) -> str:
    """€3,200 (en) · € 3.200 (nl) · 3 200 € (fr); negative amounts use a real minus sign."""
    lang = norm(lang)
    if decimals == 0:
        v = round(v)
    body = number(v, lang, decimals)
    s = f"{body}{NBSP}€" if lang == "fr" else (f"€{NBSP}{body}" if lang == "nl" else f"€{body}")
    if v < 0:
        return MINUS + s
    return "+" + s if signed else s


def pct(p: float, lang: str = "en") -> str:
    v = f"{p * 100:.0f}"
    return f"{v}{NBSP}%" if norm(lang) == "fr" else f"{v}%"


def natural_frequency(p: float, lang: str = "en") -> str:
    """'about 4 in 10' rather than '38%'. Small chances use 'in 100'."""
    lang = norm(lang)
    about = {"en": "about {k} in {n}", "nl": "ongeveer {k} op de {n}", "fr": "environ {k} sur {n}"}[lang]
    if p >= 0.095:
        k = min(10, max(1, round(p * 10)))
        if k == 10:
            return {"en": "almost everyone", "nl": "bijna iedereen", "fr": "presque tout le monde"}[lang]
        return about.format(k=k, n=10)
    k = round(p * 100)
    if k < 1:
        return {"en": "fewer than 1 in 100", "nl": "minder dan 1 op de 100", "fr": "moins de 1 sur 100"}[lang]
    return about.format(k=k, n=100)


def t(key: str, lang: str = "en", **kw) -> str:
    """A UI string from ui.TEXT, formatted; falls back to English."""
    lang = norm(lang)
    s = ui.TEXT.get(lang, {}).get(key) or ui.TEXT["en"][key]
    return s.format(**kw) if kw else s


def plural(n: int, key: str, lang: str = "en") -> str:
    """'1 payment' / '3 payments' via ui.PLURALS[lang][key] = (one, many)."""
    one, many = ui.PLURALS[norm(lang)][key]
    return (one if n == 1 else many).format(n=n)


__all__ = ["LANGS", "norm", "month_label", "number", "eur", "pct", "natural_frequency", "t", "plural",
           "features", "journeys", "services", "ui"]
