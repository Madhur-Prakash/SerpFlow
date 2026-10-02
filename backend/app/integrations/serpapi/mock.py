"""Deterministic SerpApi mock (sections 29, 41).

Two jobs:

1. ``test`` API keys route here unconditionally, consuming zero SerpApi
   credits, so a user can integrate with SerpFlow before connecting a paid
   account. That is an onboarding feature, not a convenience.
2. ``make dev`` and ``make seed`` work with no keys at all.

The generator is seeded from the engine plus the normalised parameters, so the
same request always produces the same payload - including the identifiers that
make chaining work. ``google_maps`` yields stable ``data_id`` values, those
places yield stable reviews, and those reviews yield stable ``contributor_id``
values, with deliberate contributor overlap across venues so the reference
review-ring demo has something real to find.

Nothing here is ever presented as live data: every response carries
``search_metadata.serpflow_mock = true`` and the executor stamps mode=MOCK on
the run.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.text import normalize

MOCK_MARKER = "serpflow_mock"

_CAFE_NAMES = [
    "Third Wave Coffee Roasters",
    "Blue Tokai Coffee",
    "Matteo Coffea",
    "Hole in the Wall Cafe",
    "The Hungry Hogs",
    "Dyu Art Cafe",
    "Cafe Max",
    "Brahmin's Coffee Bar",
    "Roastery Coffee",
    "Glen's Bakehouse",
    "Toit Brewpub",
    "Ants Cafe",
    "Communiti",
    "The Permit Room",
    "Sante Spa Cuisine",
    "Koshy's Annexe",
    "Flechazo",
    "Social Koramangala",
    "Truffles Ice and Spice",
    "Cafe Noir",
]
_RESTAURANT_NAMES = [
    "Ichiran Shinjuku",
    "Ippudo Ramen",
    "Afuri Ebisu",
    "Menya Saimi",
    "Tsuta Soba",
    "Nakiryu",
    "Fuunji",
    "Rokurinsha",
    "Kikanbo",
    "Mutekiya",
]
_GENERIC_PLACES = [
    "Central Park Deli",
    "Market Square Bistro",
    "Harbour Lights",
    "Station Road Kitchen",
    "The Old Mill",
    "Riverside Grill",
    "Corner House",
    "Garden Terrace",
]
_REVIEWER_NAMES = [
    "A. Menon",
    "R. Iyer",
    "S. Fernandes",
    "P. Rao",
    "K. Nair",
    "D. Sharma",
    "M. Joshi",
    "T. Varghese",
    "N. Banerjee",
    "V. Kulkarni",
    "H. Shetty",
    "L. Dsouza",
    "G. Pillai",
    "J. Mathew",
    "B. Reddy",
    "C. Gupta",
    "F. Khan",
    "I. Bhat",
    "O. Dutta",
    "U. Prasad",
]
_DOMAINS = [
    "example.com",
    "docs.example.org",
    "blog.example.net",
    "news.example.co",
    "research.example.edu",
    "shop.example.io",
]


def _seed(engine: str, params: dict[str, Any]) -> int:
    material = (
        engine
        + "|"
        + "&".join(
            k + "=" + str(params[k])
            for k in sorted(params)
            if k not in {"api_key", "output", "no_cache"}
        )
    )
    return int(hashlib.blake2b(material.encode("utf-8"), digest_size=8).hexdigest(), 16)


def _rng(engine: str, params: dict[str, Any]) -> random.Random:
    return random.Random(_seed(engine, params))


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.blake2b("|".join(parts).encode("utf-8"), digest_size=8).hexdigest()
    return prefix + digest


def _data_id(name: str) -> str:
    """Google Maps style ``0x...:0x...`` identifier, stable per place name."""
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=16).hexdigest()
    return "0x" + digest[:16] + ":0x" + digest[16:32]


def _place_id(name: str) -> str:
    return "ChIJ" + hashlib.blake2b(name.encode("utf-8"), digest_size=12).hexdigest()[:22]


def _place_pool(params: dict[str, Any]) -> list[str]:
    haystack = normalize(str(params.get("q", "")) + " " + str(params.get("location", "")))
    if "koramangala" in haystack or "bangalore" in haystack or "bengaluru" in haystack:
        return _CAFE_NAMES
    if "ramen" in haystack or "tokyo" in haystack or "seoul" in haystack or "shinjuku" in haystack:
        return _RESTAURANT_NAMES
    if "cafe" in haystack or "coffee" in haystack:
        return _CAFE_NAMES
    return _GENERIC_PLACES


# --------------------------------------------------------------------------
# The contributor ring. This is what the reference demo is looking for.
# --------------------------------------------------------------------------
RING_CONTRIBUTORS = [
    "ring_alpha",
    "ring_bravo",
    "ring_charlie",
    "ring_delta",
    "ring_echo",
]


def _contributors_for_place(place: str, count: int) -> list[tuple[str, str]]:
    """Reviewers on one place.

    Two of every place's reviewers are drawn from a shared ring pool, so the
    same contributor identities recur across venues. That overlap is only
    visible after the contributor-history hop, which is exactly the finding the
    demo is meant to surface.
    """
    rng = random.Random(_stable_id("c", place))
    out: list[tuple[str, str]] = []
    ring_members = rng.sample(RING_CONTRIBUTORS, k=min(2, len(RING_CONTRIBUTORS)))
    for member in ring_members:
        out.append((_stable_id("1", member), "Reviewer " + member.split("_")[1].title()))
    while len(out) < count:
        idx = rng.randrange(len(_REVIEWER_NAMES))
        name = _REVIEWER_NAMES[idx]
        cid = _stable_id("1", place + name)
        if all(cid != existing for existing, _ in out):
            out.append((cid, name))
    return out[:count]


def _ring_places() -> list[str]:
    return _CAFE_NAMES[:6]


def _iso(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# per-engine generators
# --------------------------------------------------------------------------
def _maps(params: dict[str, Any]) -> dict[str, Any]:
    rng = _rng("google_maps", params)
    pool = _place_pool(params)
    count = min(int(params.get("_limit", 20) or 20), len(pool))
    results = []
    for i, name in enumerate(pool[:count]):
        results.append(
            {
                "position": i + 1,
                "title": name,
                "data_id": _data_id(name),
                "place_id": _place_id(name),
                "rating": round(3.6 + rng.random() * 1.3, 1),
                "reviews": rng.randint(80, 2400),
                "type": "Cafe" if pool is _CAFE_NAMES else "Restaurant",
                "address": str(rng.randint(1, 120))
                + " "
                + str(params.get("location") or "Main Road")
                + ", "
                + ("Bengaluru" if pool is _CAFE_NAMES else "City Centre"),
                "gps_coordinates": {
                    "latitude": round(12.93 + rng.random() * 0.02, 6),
                    "longitude": round(77.62 + rng.random() * 0.02, 6),
                },
            }
        )
    return {"local_results": results}


def _maps_reviews(params: dict[str, Any]) -> dict[str, Any]:
    data_id = str(params.get("data_id") or params.get("place_id") or "unknown")
    place = next(
        (
            n
            for n in _CAFE_NAMES + _RESTAURANT_NAMES + _GENERIC_PLACES
            if _data_id(n) == data_id or _place_id(n) == data_id
        ),
        "Unknown Place",
    )
    rng = random.Random(_stable_id("r", place))
    contributors = _contributors_for_place(place, 8)
    reviews = []
    for i, (cid, name) in enumerate(contributors):
        is_ring = cid in {_stable_id("1", m) for m in RING_CONTRIBUTORS}
        reviews.append(
            {
                "user": {
                    "name": name,
                    "contributor_id": cid,
                    "link": "https://www.google.com/maps/contrib/" + cid,
                    "reviews": rng.randint(12, 180),
                    "local_guide": bool(rng.getrandbits(1)),
                },
                "rating": 5 if is_ring else rng.randint(3, 5),
                "date": _iso(rng.randint(2, 180)),
                "snippet": (
                    "Outstanding experience, highly recommend to everyone."
                    if is_ring
                    else "Good coffee and a decent spot to work from for a couple of hours."
                ),
                "likes": rng.randint(0, 12),
                "position": i + 1,
            }
        )
    return {
        "place_info": {"title": place, "data_id": data_id, "rating": round(3.8 + rng.random(), 1)},
        "reviews": reviews,
    }


def _contributor_reviews(params: dict[str, Any]) -> dict[str, Any]:
    contributor_id = str(params.get("contributor_id") or "unknown")
    ring_ids = {_stable_id("1", m): m for m in RING_CONTRIBUTORS}
    rng = random.Random(_stable_id("cr", contributor_id))
    is_ring = contributor_id in ring_ids

    if is_ring:
        # A ring account reviews the same small set of venues, always 5 stars,
        # inside a narrow window. That pattern is the finding.
        places = _ring_places()
        base_day = rng.randint(30, 60)
        reviews = [
            {
                "place_info": {
                    "title": place,
                    "data_id": _data_id(place),
                    "address": "Koramangala, Bengaluru",
                    "type": "Cafe",
                },
                "rating": 5,
                "date": _iso(base_day - i),
                "snippet": "Absolutely the best in the area, cannot fault it.",
            }
            for i, place in enumerate(places)
        ]
    else:
        pool = _CAFE_NAMES + _GENERIC_PLACES
        picks = rng.sample(pool, k=min(rng.randint(3, 9), len(pool)))
        reviews = [
            {
                "place_info": {
                    "title": place,
                    "data_id": _data_id(place),
                    "address": "Bengaluru",
                    "type": "Cafe",
                },
                "rating": rng.randint(2, 5),
                "date": _iso(rng.randint(10, 900)),
                "snippet": "Visited a while back, it was fine.",
            }
            for place in picks
        ]

    return {
        "contributor": {
            "contributor_id": contributor_id,
            "name": "Reviewer "
            + (ring_ids[contributor_id].split("_")[1].title() if is_ring else "Anon"),
            "reviews_count": len(reviews),
            "local_guide_level": rng.randint(0, 8),
        },
        "reviews": reviews,
    }


def _organic(engine: str, params: dict[str, Any], key: str = "organic_results") -> dict[str, Any]:
    rng = _rng(engine, params)
    query = str(
        params.get("q")
        or params.get("query")
        or params.get("text")
        or params.get("search_query")
        or params.get("term")
        or params.get("p")
        or ""
    )
    results = []
    for i in range(10):
        domain = _DOMAINS[i % len(_DOMAINS)]
        results.append(
            {
                "position": i + 1,
                "title": query.title()[:70] + " - Result " + str(i + 1),
                "link": "https://" + domain + "/" + _stable_id("", query + str(i))[:10],
                "displayed_link": domain,
                "snippet": "Reference material covering " + query + ".",
                "source": domain,
            }
        )
    payload: dict[str, Any] = {key: results}
    if engine in {"google", "google_light"}:
        payload["related_questions"] = [
            {"question": "What is " + query + "?", "next_page_token": _stable_id("tok", query)},
            {
                "question": "How does " + query + " work?",
                "next_page_token": _stable_id("tok2", query),
            },
        ]
        payload["search_information"] = {"total_results": rng.randint(10_000, 9_000_000)}
    return payload


def _shopping(params: dict[str, Any]) -> dict[str, Any]:
    rng = _rng("google_shopping", params)
    query = str(params.get("q", "product"))
    return {
        "shopping_results": [
            {
                "position": i + 1,
                "title": query.title() + " variant " + str(i + 1),
                "product_id": _stable_id("", query + str(i))[:14],
                "price": "$" + str(rng.randint(29, 1999)) + ".99",
                "source": _DOMAINS[i % len(_DOMAINS)],
                "rating": round(3.5 + rng.random() * 1.4, 1),
                "reviews": rng.randint(5, 9000),
            }
            for i in range(12)
        ]
    }


def _flights(params: dict[str, Any]) -> dict[str, Any]:
    rng = _rng("google_flights", params)
    dep = str(params.get("departure_id", "HYD"))
    arr = str(params.get("arrival_id", "DAD"))
    return {
        "best_flights": [
            {
                "price": rng.randint(180, 980),
                "total_duration": rng.randint(240, 960),
                "departure_token": _stable_id("dt", dep + arr + str(i)),
                "flights": [
                    {
                        "departure_airport": {
                            "id": dep,
                            "time": "2026-11-25 06:" + str(10 + i * 5),
                        },
                        "arrival_airport": {"id": arr, "time": "2026-11-25 14:" + str(20 + i * 5)},
                        "airline": ["IndiGo", "Vietnam Airlines", "Singapore Airlines"][i % 3],
                        "flight_number": "XX " + str(100 + i),
                    }
                ],
            }
            for i in range(4)
        ]
    }


def _reviews_generic(engine: str, params: dict[str, Any]) -> dict[str, Any]:
    rng = _rng(engine, params)
    return {
        "reviews": [
            {
                "rating": rng.randint(1, 5),
                "title": "Review " + str(i + 1),
                "text": "Detailed impression number " + str(i + 1) + ".",
                "date": _iso(rng.randint(1, 400)),
                "user": {"name": _REVIEWER_NAMES[i % len(_REVIEWER_NAMES)]},
            }
            for i in range(10)
        ]
    }


_GENERATORS = {
    "google_maps": _maps,
    "google_local": lambda p: {
        "local_results": [
            {**r, "data_id": r["data_id"], "place_id": r["place_id"]}
            for r in _maps(p)["local_results"][:10]
        ]
    },
    "google_maps_reviews": _maps_reviews,
    "google_maps_contributor_reviews": _contributor_reviews,
    "google_shopping": _shopping,
    "google_flights": _flights,
    "yelp_reviews": lambda p: _reviews_generic("yelp_reviews", p),
    "walmart_product_reviews": lambda p: _reviews_generic("walmart_product_reviews", p),
    "apple_reviews": lambda p: _reviews_generic("apple_reviews", p),
}

_RESULT_KEYS = {
    "google_news": "news_results",
    "bing_news": "organic_results",
    "google_images": "images_results",
    "yandex_images": "image_results",
    "google_videos": "video_results",
    "youtube": "video_results",
    "google_jobs": "jobs_results",
    "google_events": "events_results",
    "google_scholar": "organic_results",
    "google_patents": "organic_results",
    "google_hotels": "properties",
    "yelp": "organic_results",
    "amazon": "organic_results",
    "walmart": "organic_results",
    "ebay": "organic_results",
    "home_depot": "products",
    "google_play": "organic_results",
    "apple_app_store": "organic_results",
}


def generate(engine: str, params: dict[str, Any]) -> dict[str, Any]:
    """Deterministic payload for one engine call."""
    clean = {k: v for k, v in params.items() if k not in {"api_key", "output", "no_cache"}}
    generator = _GENERATORS.get(engine)
    if generator is not None:
        body = generator(clean)
    else:
        body = _organic(engine, clean, _RESULT_KEYS.get(engine, "organic_results"))
        body = _decorate_identifiers(engine, clean, body)

    search_id = _stable_id("mock_", engine + "|" + str(sorted(clean.items())))
    body["search_metadata"] = {
        "id": search_id,
        "status": "Success",
        "created_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "engine": engine,
        MOCK_MARKER: True,
        "source": "serpflow-deterministic-mock",
    }
    body["search_parameters"] = {"engine": engine, **clean}
    return body


def _decorate_identifiers(
    engine: str, params: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    """Attach the chainable identifiers each engine is documented to produce,
    so multi-hop plans actually execute against the mock."""
    key = _RESULT_KEYS.get(engine, "organic_results")
    rows = body.get(key) or []
    query = str(
        params.get("q")
        or params.get("query")
        or params.get("term")
        or params.get("_nkw")
        or params.get("k")
        or ""
    )
    for i, row in enumerate(rows):
        token = _stable_id("", engine + query + str(i))
        if engine == "yelp":
            row["place_ids"] = [token[:16]]
        elif engine == "walmart":
            row["us_item_id"] = token[:12]
        elif engine == "home_depot":
            row["product_id"] = token[:12]
        elif engine == "google_scholar":
            row["result_id"] = token[:14]
            row["publication_info"] = {
                "authors": [{"name": "Author " + str(i), "author_id": token[:12]}]
            }
        elif engine == "google_patents":
            row["patent_id"] = "patent/US" + token[:8].upper() + "A1/en"
        elif engine == "google_play":
            row["items"] = [{"product_id": "com.example.app" + str(i), "title": "App " + str(i)}]
        elif engine == "apple_app_store":
            row["id"] = token[:10]
        elif engine == "google_images":
            row["original"] = "https://cdn.example.com/" + token[:12] + ".jpg"
        elif engine == "google_autocomplete":
            row["value"] = query + " " + ["near me", "reviews", "price", "open now"][i % 4]
    if engine == "google_autocomplete":
        body["suggestions"] = rows
        body.pop("organic_results", None)
    return body


def is_mock_payload(payload: dict[str, Any]) -> bool:
    return bool((payload.get("search_metadata") or {}).get(MOCK_MARKER))


def mock_account() -> dict[str, Any]:
    """Account endpoint shape for quota reconciliation in mock mode."""
    return {
        "account_id": "mock_account",
        "plan_name": "SerpFlow deterministic mock",
        "searches_per_month": 250,
        "this_month_usage": 0,
        "total_searches_left": 250,
        "plan_searches_left": 250,
        MOCK_MARKER: True,
    }


__all__ = [
    "MOCK_MARKER",
    "RING_CONTRIBUTORS",
    "generate",
    "is_mock_payload",
    "mock_account",
]
