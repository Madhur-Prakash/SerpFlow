"""Deterministic text primitives shared by the planner and the cache guard.

Everything here is rule-based on purpose. Section 17 is explicit that the
entity/numeral guard must be a mechanism, not a vague model judgment, and
section 13 stage C wants freshness inference that is reproducible across runs
and explainable in the Run Inspector.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z0-9]+(?:[.'’-][A-Za-z0-9]+)*")


def strip_accents(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in folded if not unicodedata.combining(c))


def normalize(value: str) -> str:
    """Whitespace-collapsed, case-folded, accent-stripped."""
    return _WS.sub(" ", strip_accents(value or "").strip().lower())


def words(value: str) -> list[str]:
    return _WORD.findall(value or "")


# --------------------------------------------------------------------------
# entity / numeral extraction - the section 17 guard material
# --------------------------------------------------------------------------
# Model and version identifiers: v3, 4K, M2, iPhone16, GPT-4, Mk II.
_VERSION = re.compile(
    r"\b(?:v|ver|version|mk|gen|rev)[.\s-]?\d+(?:\.\d+)*\b"
    r"|\b\d+(?:\.\d+)+\b"
    r"|\b\d{1,4}\s?[kK]\b"
    r"|\b[A-Za-z]{1,4}\d{1,4}[A-Za-z]?\b",
    re.IGNORECASE,
)
_NUMERAL = re.compile(r"\b\d+(?:[.,]\d+)*\b")

_NUMBER_WORDS: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "twenty": "20",
    "fifty": "50",
    "hundred": "100",
}

# Words that look like proper nouns in a search query but carry no entity
# meaning, so they must not count toward entity-set equality.
_ENTITY_STOPWORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "in",
        "on",
        "at",
        "for",
        "from",
        "to",
        "with",
        "near",
        "around",
        "best",
        "top",
        "new",
        "latest",
        "current",
        "today",
        "tonight",
        "now",
        "recent",
        "reviews",
        "review",
        "rating",
        "ratings",
        "price",
        "prices",
        "cheap",
        "open",
        "hours",
        "menu",
        "find",
        "show",
        "me",
        "list",
        "search",
        "results",
        "about",
        "how",
        "what",
        "where",
        "when",
        "which",
        "who",
        "why",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "my",
        "our",
        "your",
        "their",
        "coordinated",
        "ring",
        "rings",
        "among",
        "between",
        "across",
        "within",
        "good",
        "great",
        "popular",
    ]
)

# Capitalised words plus multi-word proper-noun runs.
_PROPER_RUN = re.compile(r"\b(?:[A-Z][\w'’-]*)(?:\s+(?:[A-Z][\w'’-]*|de|di|van|von|al))*")
# Quoted spans are always entities regardless of casing.
_QUOTED = re.compile(r"[\"'“‘]([^\"'”’]{2,60})[\"'”’]")


def extract_numerals(text: str) -> set[str]:
    """Every numeric token, including spelled-out small numbers.

    ``iphone 16`` and ``iphone 17`` differ here, which is what makes the guard
    reject them regardless of cosine score.
    """
    found = {m.group(0).replace(",", "") for m in _NUMERAL.finditer(text or "")}
    for word in words(normalize(text)):
        if word in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[word])
    return {f.rstrip(".") for f in found if f.strip(".")}


def extract_versions(text: str) -> set[str]:
    """Model and version identifiers: v3, 4K, M2, 14.5."""
    out: set[str] = set()
    for match in _VERSION.finditer(text or ""):
        token = match.group(0).strip().lower().replace(" ", "")
        if token.isalpha():
            continue
        out.add(token)
    return out


def extract_entities(text: str) -> set[str]:
    """Named entities: products, brands, places, people, organisations.

    Deterministic by construction - quoted spans, proper-noun runs, and
    multi-word title-case sequences. No model is consulted, because a model
    that is right 95% of the time still serves Indiranagar results for an
    Indiranagar-adjacent Koramangala query one time in twenty.
    """
    if not text:
        return set()
    out: set[str] = set()

    for match in _QUOTED.finditer(text):
        token = normalize(match.group(1))
        if token:
            out.add(token)

    for match in _PROPER_RUN.finditer(text):
        raw = match.group(0).strip()
        token = normalize(raw)
        if not token or token in _ENTITY_STOPWORDS:
            continue
        parts = [p for p in token.split() if p not in _ENTITY_STOPWORDS]
        if not parts:
            continue
        out.add(" ".join(parts))

    # An all-lowercase query still names places and brands. Any word that is not
    # a stopword, is not a bare numeral, and is at least four characters counts
    # as a weak entity so lowercase queries are guarded too.
    if not out:
        for word in words(normalize(text)):
            if word in _ENTITY_STOPWORDS or word.isdigit() or len(word) < 4:
                continue
            out.add(word)

    return out


@dataclass(slots=True)
class GuardTokens:
    numerals: set[str] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)
    versions: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "numerals": sorted(self.numerals),
            "entities": sorted(self.entities),
            "versions": sorted(self.versions),
        }

    def all_tokens(self) -> list[str]:
        return sorted(self.numerals | self.entities | self.versions)


def guard_tokens(text: str) -> GuardTokens:
    return GuardTokens(
        numerals=extract_numerals(text),
        entities=extract_entities(text),
        versions=extract_versions(text),
    )


# --------------------------------------------------------------------------
# locale inference (section 13 stage C)
# --------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Locale:
    gl: str
    hl: str
    country: str


# City / region -> country code. Deliberately explicit: locale inference is a
# benchmark discriminator, and a wrong gl silently changes the result set.
CITY_LOCALES: dict[str, str] = {
    "seoul": "kr",
    "busan": "kr",
    "incheon": "kr",
    "tokyo": "jp",
    "osaka": "jp",
    "kyoto": "jp",
    "bangalore": "in",
    "bengaluru": "in",
    "koramangala": "in",
    "indiranagar": "in",
    "hyderabad": "in",
    "mumbai": "in",
    "delhi": "in",
    "new delhi": "in",
    "chennai": "in",
    "pune": "in",
    "kolkata": "in",
    "jaipur": "in",
    "goa": "in",
    "beijing": "cn",
    "shanghai": "cn",
    "shenzhen": "cn",
    "hong kong": "hk",
    "taipei": "tw",
    "singapore": "sg",
    "bangkok": "th",
    "hanoi": "vn",
    "da nang": "vn",
    "danang": "vn",
    "ho chi minh": "vn",
    "jakarta": "id",
    "bali": "id",
    "kuala lumpur": "my",
    "manila": "ph",
    "dubai": "ae",
    "abu dhabi": "ae",
    "riyadh": "sa",
    "doha": "qa",
    "istanbul": "tr",
    "tel aviv": "il",
    "cairo": "eg",
    "nairobi": "ke",
    "lagos": "ng",
    "johannesburg": "za",
    "cape town": "za",
    "london": "uk",
    "manchester": "uk",
    "edinburgh": "uk",
    "dublin": "ie",
    "paris": "fr",
    "lyon": "fr",
    "marseille": "fr",
    "berlin": "de",
    "munich": "de",
    "hamburg": "de",
    "frankfurt": "de",
    "madrid": "es",
    "barcelona": "es",
    "lisbon": "pt",
    "porto": "pt",
    "rome": "it",
    "milan": "it",
    "florence": "it",
    "amsterdam": "nl",
    "rotterdam": "nl",
    "brussels": "be",
    "zurich": "ch",
    "geneva": "ch",
    "vienna": "at",
    "prague": "cz",
    "warsaw": "pl",
    "budapest": "hu",
    "stockholm": "se",
    "oslo": "no",
    "copenhagen": "dk",
    "helsinki": "fi",
    "moscow": "ru",
    "saint petersburg": "ru",
    "kyiv": "ua",
    "athens": "gr",
    "new york": "us",
    "san francisco": "us",
    "los angeles": "us",
    "chicago": "us",
    "seattle": "us",
    "austin": "us",
    "boston": "us",
    "miami": "us",
    "denver": "us",
    "toronto": "ca",
    "vancouver": "ca",
    "montreal": "ca",
    "mexico city": "mx",
    "sao paulo": "br",
    "rio de janeiro": "br",
    "buenos aires": "ar",
    "santiago": "cl",
    "bogota": "co",
    "lima": "pe",
    "sydney": "au",
    "melbourne": "au",
    "brisbane": "au",
    "auckland": "nz",
}

# Districts, neighbourhoods and landmarks.
#
# Local search intents name these far more often than they name the city:
# "omakase in Ginza" and "a clinic in Gangnam" carry their locale in a word
# that is not a city name. Without this table those queries silently fall back
# to gl=us, which returns a different result set rather than an error - the
# kind of failure a benchmark catches and a user never reports.
DISTRICT_LOCALES: dict[str, str] = {
    # Tokyo
    "ginza": "jp",
    "shibuya": "jp",
    "shinjuku": "jp",
    "harajuku": "jp",
    "akihabara": "jp",
    "roppongi": "jp",
    "asakusa": "jp",
    "ikebukuro": "jp",
    "nakameguro": "jp",
    "daikanyama": "jp",
    "shimokitazawa": "jp",
    "dotonbori": "jp",
    "shinsaibashi": "jp",
    "namba": "jp",
    "gion": "jp",
    "pontocho": "jp",
    "sangenjaya": "jp",
    "ebisu": "jp",
    "nakano": "jp",
    # Seoul and Busan
    "gangnam": "kr",
    "hongdae": "kr",
    "itaewon": "kr",
    "myeongdong": "kr",
    "seongsu": "kr",
    "insadong": "kr",
    "haeundae": "kr",
    "seomyeon": "kr",
    # India
    "koramangala": "in",
    "indiranagar": "in",
    "whitefield": "in",
    "hsr layout": "in",
    "jayanagar": "in",
    "bandra": "in",
    "andheri": "in",
    "colaba": "in",
    "connaught place": "in",
    "hauz khas": "in",
    "gachibowli": "in",
    "banjara hills": "in",
    "jubilee hills": "in",
    # London
    "shoreditch": "uk",
    "soho": "uk",
    "camden": "uk",
    "mayfair": "uk",
    "hackney": "uk",
    "peckham": "uk",
    "notting hill": "uk",
    "brixton": "uk",
    "canary wharf": "uk",
    "clerkenwell": "uk",
    # New York
    "manhattan": "us",
    "brooklyn": "us",
    "queens": "us",
    "williamsburg": "us",
    "soho manhattan": "us",
    "tribeca": "us",
    "harlem": "us",
    "bushwick": "us",
    "lower east side": "us",
    "upper west side": "us",
    "prince street": "us",
    # Other US
    "mission district": "us",
    "the mission": "us",
    "silver lake": "us",
    "venice beach": "us",
    "wicker park": "us",
    "capitol hill": "us",
    "south congress": "us",
    "east austin": "us",
    # Europe
    "kreuzberg": "de",
    "neukolln": "de",
    "prenzlauer berg": "de",
    "mitte": "de",
    "alexanderplatz": "de",
    "schwabing": "de",
    "montmartre": "fr",
    "le marais": "fr",
    "saint germain": "fr",
    "la latina": "es",
    "malasana": "es",
    "gracia": "es",
    "el born": "es",
    "trastevere": "it",
    "navigli": "it",
    "brera": "it",
    "jordaan": "nl",
    "de pijp": "nl",
    # Elsewhere
    "sham shui po": "hk",
    "causeway bay": "hk",
    "tsim sha tsui": "hk",
    "tiong bahru": "sg",
    "kampong glam": "sg",
    "jurong": "sg",
    "thonglor": "th",
    "sukhumvit": "th",
    "ari": "th",
    "palermo soho": "ar",
    "vila madalena": "br",
    "ipanema": "br",
    "polanco": "mx",
    "roma norte": "mx",
    "condesa": "mx",
    "surry hills": "au",
    "newtown sydney": "au",
    "fitzroy": "au",
    "yaletown": "ca",
    "kensington market": "ca",
    "le plateau": "ca",
}


COUNTRY_NAMES: dict[str, str] = {
    "korea": "kr",
    "south korea": "kr",
    "japan": "jp",
    "india": "in",
    "china": "cn",
    "taiwan": "tw",
    "singapore": "sg",
    "thailand": "th",
    "vietnam": "vn",
    "indonesia": "id",
    "malaysia": "my",
    "philippines": "ph",
    "uae": "ae",
    "united arab emirates": "ae",
    "saudi arabia": "sa",
    "turkey": "tr",
    "israel": "il",
    "egypt": "eg",
    "kenya": "ke",
    "nigeria": "ng",
    "south africa": "za",
    "uk": "uk",
    "united kingdom": "uk",
    "england": "uk",
    "scotland": "uk",
    "ireland": "ie",
    "france": "fr",
    "germany": "de",
    "spain": "es",
    "portugal": "pt",
    "italy": "it",
    "netherlands": "nl",
    "belgium": "be",
    "switzerland": "ch",
    "austria": "at",
    "czechia": "cz",
    "poland": "pl",
    "hungary": "hu",
    "sweden": "se",
    "norway": "no",
    "denmark": "dk",
    "finland": "fi",
    "russia": "ru",
    "ukraine": "ua",
    "greece": "gr",
    "usa": "us",
    "united states": "us",
    "america": "us",
    "canada": "ca",
    "mexico": "mx",
    "brazil": "br",
    "argentina": "ar",
    "chile": "cl",
    "colombia": "co",
    "peru": "pe",
    "australia": "au",
    "new zealand": "nz",
}

COUNTRY_LANGUAGE: dict[str, str] = {
    "kr": "ko",
    "jp": "ja",
    "in": "en",
    "cn": "zh-cn",
    "hk": "zh-tw",
    "tw": "zh-tw",
    "sg": "en",
    "th": "th",
    "vn": "vi",
    "id": "id",
    "my": "ms",
    "ph": "en",
    "ae": "ar",
    "sa": "ar",
    "qa": "ar",
    "tr": "tr",
    "il": "he",
    "eg": "ar",
    "ke": "en",
    "ng": "en",
    "za": "en",
    "uk": "en",
    "ie": "en",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "pt": "pt",
    "it": "it",
    "nl": "nl",
    "be": "nl",
    "ch": "de",
    "at": "de",
    "cz": "cs",
    "pl": "pl",
    "hu": "hu",
    "se": "sv",
    "no": "no",
    "dk": "da",
    "fi": "fi",
    "ru": "ru",
    "ua": "uk",
    "gr": "el",
    "us": "en",
    "ca": "en",
    "mx": "es",
    "br": "pt",
    "ar": "es",
    "cl": "es",
    "co": "es",
    "pe": "es",
    "au": "en",
    "nz": "en",
}

DEFAULT_LOCALE = Locale(gl="us", hl="en", country="us")


def infer_locale(text: str) -> tuple[Locale, str | None]:
    """``Seoul -> gl=kr, hl=ko``. Returns the locale and the matched token."""
    haystack = normalize(text)
    best: tuple[str, str] | None = None
    # Districts first: they are more specific than any city name they contain.
    for name, code in DISTRICT_LOCALES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", haystack) and (
            best is None or len(name) > len(best[0])
        ):
            best = (name, code)
    if best is not None:
        name, code = best
        return Locale(gl=code, hl=COUNTRY_LANGUAGE.get(code, "en"), country=code), name
    for name, code in CITY_LOCALES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", haystack) and (
            best is None or len(name) > len(best[0])
        ):
            best = (name, code)
    if best is None:
        for name, code in COUNTRY_NAMES.items():
            if re.search(r"\b" + re.escape(name) + r"\b", haystack) and (
                best is None or len(name) > len(best[0])
            ):
                best = (name, code)
    if best is None:
        return DEFAULT_LOCALE, None
    name, code = best
    return Locale(gl=code, hl=COUNTRY_LANGUAGE.get(code, "en"), country=code), name


def extract_location_phrase(text: str) -> str | None:
    """The ``in <place>`` / ``near <place>`` span, used as the location param."""
    match = re.search(
        r"\b(?:in|near|around|at|within|among|across|throughout)\s+([A-Za-zÀ-ɏ][\w'’-]*(?:\s+[A-Za-zÀ-ɏ][\w'’-]*){0,3})",
        text or "",
    )
    if not match:
        return None
    phrase = match.group(1).strip()
    tokens = [t for t in phrase.split() if normalize(t) not in _ENTITY_STOPWORDS]
    return " ".join(tokens) if tokens else None


# --------------------------------------------------------------------------
# freshness inference (section 13 stage C)
# --------------------------------------------------------------------------
REALTIME_SIGNALS = (
    "right now",
    "right this",
    "as of now",
    "live",
    "currently",
    "at this moment",
    "real time",
    "realtime",
    "breaking",
    "price now",
    "today's price",
)
FRESH_SIGNALS = (
    "today",
    "tonight",
    "current",
    "latest",
    "as of",
    "this morning",
    "this evening",
    "just now",
    "newest",
    "up to date",
    "up-to-date",
    "now open",
    "open now",
    "this week",
    "last 24 hours",
)
RECENT_SIGNALS = (
    "recent",
    "recently",
    "this month",
    "past week",
    "last week",
    "lately",
    "new ",
    "trending",
    "upcoming",
)

# Query classes whose answers move faster than the engine's own prior.
VOLATILE_QUERY_CLASSES = {
    "finance": "realtime",
    "flights": "realtime",
    "news": "fresh",
    "events": "fresh",
    "hotels": "fresh",
    "jobs": "fresh",
    "trends": "fresh",
    "shopping": "fresh",
}

QUERY_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "finance": ("stock", "share price", "ticker", "nasdaq", "nyse", "market cap", "earnings"),
    "flights": ("flight", "flights", "airfare", "one way", "round trip", "layover"),
    "hotels": ("hotel", "hotels", "stay", "airbnb", "resort", "check-in", "accommodation"),
    "news": ("news", "headline", "headlines", "coverage", "reported", "announcement"),
    "events": ("event", "events", "concert", "festival", "meetup", "conference"),
    "jobs": ("job", "jobs", "hiring", "vacancy", "vacancies", "role", "salary"),
    "shopping": ("buy", "price", "cheapest", "deal", "discount", "in stock", "shopping"),
    "reviews": ("review", "reviews", "rating", "ratings", "testimonial", "complaints"),
    "local": ("near me", "nearby", "cafe", "cafes", "restaurant", "restaurants", "bar", "shop"),
    "academic": ("paper", "papers", "citation", "scholar", "publication", "journal", "doi"),
    "patents": ("patent", "patents", "prior art", "uspto"),
    "images": ("image", "images", "photo", "photos", "picture", "pictures"),
    "video": ("video", "videos", "youtube", "clip", "footage"),
    "trends": ("trend", "trends", "interest over time", "popularity"),
}


def classify_query(text: str) -> str:
    haystack = normalize(text)
    best = ("general", 0)
    for name, keywords in QUERY_CLASS_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in haystack)
        if score > best[1]:
            best = (name, score)
    return best[0]


def infer_freshness(
    text: str, *, volatility_prior: str = "7d", query_class: str | None = None
) -> tuple[str, list[str]]:
    """Classify the freshness requirement from the intent (section 13 stage C).

        realtime  < 15m
        fresh     < 24h
        recent    < 7d
        stable    any valid TTL

    Three signal families, as the spec requires: temporal language, the
    engine's ``volatility_prior``, and the query class. The result is persisted
    on the step, and section 14 consumes it to decide whether a warm entry is
    ACCEPTABLE rather than merely AVAILABLE. Without it, marginal cost is
    computed against an undefined acceptability bar.
    """
    haystack = normalize(text)
    signals: list[str] = []
    level = "stable"

    def tighten(candidate: str, reason: str) -> None:
        nonlocal level
        order = ["realtime", "fresh", "recent", "stable"]
        if order.index(candidate) < order.index(level):
            level = candidate
        signals.append(reason)

    for phrase in REALTIME_SIGNALS:
        if phrase in haystack:
            tighten("realtime", "temporal language: " + phrase.strip())
            break
    for phrase in FRESH_SIGNALS:
        if phrase in haystack:
            tighten("fresh", "temporal language: " + phrase.strip())
            break
    for phrase in RECENT_SIGNALS:
        if phrase in haystack:
            tighten("recent", "temporal language: " + phrase.strip())
            break

    klass = query_class or classify_query(text)
    if klass in VOLATILE_QUERY_CLASSES:
        tighten(VOLATILE_QUERY_CLASSES[klass], "query class: " + klass)

    prior_level = {
        "15m": "realtime",
        "1h": "fresh",
        "24h": "fresh",
        "7d": "recent",
        "30d": "stable",
        "365d": "stable",
    }.get(volatility_prior, "stable")
    if prior_level != "stable":
        tighten(prior_level, "engine volatility_prior: " + volatility_prior)

    if not signals:
        signals.append("no temporal signal; engine prior " + volatility_prior + " permits any TTL")
    return level, signals


# --------------------------------------------------------------------------
# date normalisation (section 13 stage C)
# --------------------------------------------------------------------------
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def normalize_dates(text: str, *, today: date | None = None) -> dict[str, str]:
    """Resolve relative and partial dates into ISO ``YYYY-MM-DD``.

    Handles the shapes that actually show up in search intents: "late
    November", "next Friday", "in 3 weeks", "2026-03-04", "March 4".
    """
    now = today or datetime.now(UTC).date()
    haystack = normalize(text)
    out: dict[str, str] = {}

    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", haystack)
    if iso:
        out["date"] = iso.group(0)
        return out

    if "tomorrow" in haystack:
        out["date"] = (now + timedelta(days=1)).isoformat()
        return out
    if "today" in haystack or "tonight" in haystack:
        out["date"] = now.isoformat()
        return out

    weekday = re.search(
        r"\b(?:next|this|on|coming)?\s*"
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        haystack,
    )
    if weekday:
        target = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ].index(weekday.group(1))
        ahead = (target - now.weekday()) % 7
        # "next Friday" on a Friday means the following one, not today.
        if ahead == 0 or "next" in haystack:
            ahead = ahead or 7
        out["date"] = (now + timedelta(days=ahead)).isoformat()
        out["date_precision"] = "day"
        return out

    weeks = re.search(r"\bin\s+(\d{1,2})\s+weeks?\b", haystack)
    if weeks:
        out["date"] = (now + timedelta(weeks=int(weeks.group(1)))).isoformat()
        return out
    days = re.search(r"\bin\s+(\d{1,3})\s+days?\b", haystack)
    if days:
        out["date"] = (now + timedelta(days=int(days.group(1)))).isoformat()
        return out

    qualifier = None
    for word in ("early", "mid", "middle of", "late", "end of", "start of", "beginning of"):
        if word + " " in haystack:
            qualifier = word
            break

    for name, month in _MONTHS.items():
        match = re.search(r"\b" + name + r"\b(?:\s+(\d{1,2})(?:st|nd|rd|th)?)?", haystack)
        if not match:
            continue
        year = now.year if month >= now.month else now.year + 1
        year_hint = re.search(r"\b(20\d{2})\b", haystack)
        if year_hint:
            year = int(year_hint.group(1))
        day_token = match.group(1)
        if day_token:
            day = max(1, min(28, int(day_token)))
        elif qualifier in ("early", "start of", "beginning of"):
            day = 5
        elif qualifier in ("mid", "middle of"):
            day = 15
        elif qualifier in ("late", "end of"):
            day = 25
        else:
            day = 15
        out["date"] = date(year, month, day).isoformat()
        out["date_precision"] = "day" if day_token else "approximate"
        if qualifier:
            out["date_qualifier"] = qualifier
        return out

    return out


def stable_param_order(params: dict[str, object]) -> dict[str, object]:
    """Deterministic ordering for cache-key hashing (section 17)."""
    return {k: params[k] for k in sorted(params)}


__all__ = [
    "CITY_LOCALES",
    "COUNTRY_LANGUAGE",
    "COUNTRY_NAMES",
    "DEFAULT_LOCALE",
    "DISTRICT_LOCALES",
    "GuardTokens",
    "Locale",
    "QUERY_CLASS_KEYWORDS",
    "classify_query",
    "extract_entities",
    "extract_location_phrase",
    "extract_numerals",
    "extract_versions",
    "guard_tokens",
    "infer_freshness",
    "infer_locale",
    "normalize",
    "normalize_dates",
    "stable_param_order",
    "strip_accents",
    "words",
]
