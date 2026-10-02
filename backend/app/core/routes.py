"""Airport route resolution for flight intents (section 13 stage C).

``google_flights`` requires IATA codes, not city names. Nothing in the catalog
produces ``departure_id``, so without this resolution the dependency graph
correctly refuses to plan a flight intent at all - which is right, but useless.

Both endpoints must resolve or nothing is returned. Half a route is not a
usable binding, and refusing to plan beats planning a flight from a real
airport to a guessed one.
"""

from __future__ import annotations

import re

from app.core.text import normalize

AIRPORT_CODES: dict[str, str] = {
    "hyderabad": "HYD",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "mumbai": "BOM",
    "delhi": "DEL",
    "new delhi": "DEL",
    "chennai": "MAA",
    "kolkata": "CCU",
    "goa": "GOI",
    "pune": "PNQ",
    "jaipur": "JAI",
    "kochi": "COK",
    "da nang": "DAD",
    "danang": "DAD",
    "hanoi": "HAN",
    "ho chi minh": "SGN",
    "bangkok": "BKK",
    "singapore": "SIN",
    "kuala lumpur": "KUL",
    "jakarta": "CGK",
    "bali": "DPS",
    "manila": "MNL",
    "tokyo": "HND",
    "osaka": "KIX",
    "seoul": "ICN",
    "busan": "PUS",
    "beijing": "PEK",
    "shanghai": "PVG",
    "hong kong": "HKG",
    "taipei": "TPE",
    "dubai": "DXB",
    "abu dhabi": "AUH",
    "doha": "DOH",
    "riyadh": "RUH",
    "istanbul": "IST",
    "tel aviv": "TLV",
    "cairo": "CAI",
    "nairobi": "NBO",
    "lagos": "LOS",
    "johannesburg": "JNB",
    "cape town": "CPT",
    "london": "LHR",
    "manchester": "MAN",
    "edinburgh": "EDI",
    "dublin": "DUB",
    "paris": "CDG",
    "lyon": "LYS",
    "marseille": "MRS",
    "berlin": "BER",
    "munich": "MUC",
    "hamburg": "HAM",
    "frankfurt": "FRA",
    "madrid": "MAD",
    "barcelona": "BCN",
    "lisbon": "LIS",
    "porto": "OPO",
    "rome": "FCO",
    "milan": "MXP",
    "florence": "FLR",
    "amsterdam": "AMS",
    "brussels": "BRU",
    "zurich": "ZRH",
    "geneva": "GVA",
    "vienna": "VIE",
    "prague": "PRG",
    "warsaw": "WAW",
    "budapest": "BUD",
    "stockholm": "ARN",
    "oslo": "OSL",
    "copenhagen": "CPH",
    "helsinki": "HEL",
    "moscow": "SVO",
    "athens": "ATH",
    "new york": "JFK",
    "san francisco": "SFO",
    "los angeles": "LAX",
    "chicago": "ORD",
    "seattle": "SEA",
    "austin": "AUS",
    "boston": "BOS",
    "miami": "MIA",
    "denver": "DEN",
    "toronto": "YYZ",
    "vancouver": "YVR",
    "montreal": "YUL",
    "mexico city": "MEX",
    "sao paulo": "GRU",
    "rio de janeiro": "GIG",
    "buenos aires": "EZE",
    "santiago": "SCL",
    "bogota": "BOG",
    "lima": "LIM",
    "sydney": "SYD",
    "melbourne": "MEL",
    "brisbane": "BNE",
    "auckland": "AKL",
}

# Words that end the destination phrase. Everything after one of these belongs
# to the date, cabin class or filters, not to the place name.
_TAIL_WORDS = (
    " in ",
    " on ",
    " for ",
    " next ",
    " late ",
    " early ",
    " mid ",
    " this ",
    " departing ",
    " returning ",
    " around ",
    " with ",
    " under ",
    " before ",
    " after ",
    " leaving ",
    " arriving ",
    " during ",
    " economy ",
    " business ",
)

# Longest names first, so "new york" wins over a bare "york" substring.
_SORTED_NAMES = sorted(AIRPORT_CODES, key=len, reverse=True)


def _code_for(phrase: str) -> str | None:
    cleaned = phrase.strip(" ,.")
    direct = AIRPORT_CODES.get(cleaned)
    if direct:
        return direct
    for name in _SORTED_NAMES:
        if re.search(r"\b" + re.escape(name) + r"\b", cleaned):
            return AIRPORT_CODES[name]
    return None


def _trim_tail(phrase: str) -> str:
    padded = " " + phrase + " "
    cut = len(padded)
    for word in _TAIL_WORDS:
        position = padded.find(word)
        if position > 0:
            cut = min(cut, position)
    return padded[:cut].strip()


def resolve_route(text: str) -> dict[str, str]:
    """``flights from Hyderabad to Da Nang`` -> ``{departure_id: HYD, arrival_id: DAD}``.

    The word "from" is optional. "Sydney to Auckland flight options" is the
    same request, and refusing to parse it would push an ordinary flight
    intent into NO_VIABLE_PLAN for no good reason.
    """
    haystack = " " + normalize(text) + " "
    to_at = haystack.find(" to ")
    if to_at < 0:
        return {}

    from_at = haystack.rfind(" from ", 0, to_at)
    if from_at >= 0:
        departure_raw = haystack[from_at + len(" from ") : to_at]
    else:
        # No "from": take the words immediately before "to" as the origin.
        departure_raw = " ".join(haystack[:to_at].split()[-4:])

    departure = _trim_tail(departure_raw)
    arrival = _trim_tail(haystack[to_at + len(" to ") :])

    departure_code = _code_for(departure)
    arrival_code = _code_for(arrival)
    if not departure_code or not arrival_code:
        return {}
    return {"departure_id": departure_code, "arrival_id": arrival_code}


__all__ = ["AIRPORT_CODES", "resolve_route"]
