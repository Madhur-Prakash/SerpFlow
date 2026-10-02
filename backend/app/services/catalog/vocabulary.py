"""Capability vocabulary: the words that mean a capability tag.

Catalog domain data, not model behaviour. Both stage A (retrieval) and the
deterministic selector read it, so an intent that says "trading at right now"
puts ``finance_quote`` engines in the shortlist rather than hoping an embedding
happens to land near ``google_finance``'s purpose line.

Embedding similarity alone is a poor retriever here. Engine documentation is
short and uses the vendor's vocabulary, not the user's: nothing in
``google_finance``'s description contains the word "trading", and nothing in
``google_shopping``'s contains "65-inch". Scoring a declared capability against
the words people actually use is what makes the shortlist usable.
"""

from __future__ import annotations

from app.core.text import normalize

# Capability tag -> the phrases that indicate it. Multi-word phrases are
# stronger evidence than single words and score higher.
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "place_search": (
        "cafe",
        "cafes",
        "coffee shop",
        "restaurant",
        "restaurants",
        "bar",
        "bars",
        "shop",
        "place",
        "places",
        "business",
        "businesses",
        "near me",
        "nearby",
        "venue",
        "clinic",
        "salon",
        "bakery",
        "gym",
        "office",
        "walk-ins",
        "omakase",
        "delivery chain",
        "pizzeria",
        "dentist",
        "notary",
        # Cuisine and venue words: a local intent usually names the food, not
        # the word "restaurant".
        "ramen",
        "sushi",
        "pizza",
        "barbecue",
        "bbq",
        "noodles",
        "brunch",
        "dim sum",
        "taco",
        "tacos",
        "burger",
        "burgers",
        "steakhouse",
        "izakaya",
        "food court",
        "bistro",
        "diner",
        "pub",
        "brewery",
        "roasters",
        "worth the line",
        "open past",
        "open late",
        "takes walk-ins",
    ),
    "local_business": (
        "local",
        "neighbourhood",
        "neighborhood",
        "listing",
        "listings",
        "opening hours",
        "open now",
        "address",
        "phone number",
    ),
    "place_reviews": (
        "review",
        "reviews",
        "rating",
        "ratings",
        "star reviews",
        "five-star",
        "complaining",
        "complaints",
        "testimonial",
        "what people say",
        "are people still",
    ),
    "contributor_history": (
        "reviewer",
        "reviewers",
        "contributor",
        "contributors",
        "review ring",
        "review rings",
        "coordinated",
        "same accounts",
        "same handful",
        "same people",
        "astroturf",
        "fake reviews",
        "suspiciously uniform",
        "posting history",
        "account history",
        "across venues",
        "glowing reviews",
        "come from the same",
        "read the same",
        "all read",
        "same set of accounts",
        "handful of accounts",
        "same reviewers",
        "uniform five-star",
        "picked up twelve",
        "burst of reviews",
        "who left them",
    ),
    "place_photos": (
        "photo",
        "photos",
        "picture",
        "pictures",
        "interior photos",
        "what it looks like",
    ),
    "directions": (
        "directions",
        "walking directions",
        "driving directions",
        "route",
        "how do i get",
        "travel time",
        "how long does it take to get",
    ),
    "web_search": (
        "web page",
        "website",
        "article",
        "articles",
        "guide",
        "explain",
        "background on",
        "information about",
        "what is",
        "who is",
        "saying about",
        "buyers actually saying",
        "most popular",
        "comparison",
    ),
    "answer_synthesis": (
        "summarize",
        "summarise",
        "overview of",
        "brief answer",
        "ai overview",
        "ai mode",
        "synthesised answer",
        "what does the ai",
    ),
    "related_questions": ("people also ask", "follow-up questions", "related questions"),
    "query_expansion": (
        "suggest",
        "suggestions",
        "autocomplete",
        "related queries",
        "what else do people search",
    ),
    "news_search": (
        "news",
        "headline",
        "headlines",
        "coverage",
        "breaking",
        "reported",
        "announcement",
        "press",
        "latest on",
        "developing story",
    ),
    "product_search": (
        "buy",
        "price",
        "prices",
        "cheapest",
        "deal",
        "deals",
        "discount",
        "shopping",
        "product",
        "under",
        "dollars",
        "in stock",
        "specs for",
        "inch",
        "oled",
        "model",
        "best-selling",
        "listing for",
    ),
    "product_detail": (
        "specs",
        "specification",
        "specifications",
        "offers",
        "sellers",
        "product details",
        "price and specs",
    ),
    "product_reviews": (
        "product review",
        "product reviews",
        "buyer reviews",
        "customer reviews",
        "buyers said",
        "buyers say",
        "what buyers",
        "customer feedback",
        "buyer feedback",
        "owner reviews",
        "verified purchase",
    ),
    "image_search": ("image", "images", "photo of", "picture of", "wallpaper", "logo"),
    "image_lookup": (
        "reverse image",
        "what is this image",
        "identify this",
        "visual match",
        "where did this image",
        "which page hosts",
        "i have a photo",
        "photo of it",
        "what is this plant",
        "what is this building",
        "identify from a photo",
        "lens",
    ),
    "video_search": ("video", "videos", "clip", "footage", "watch", "youtube", "tutorial"),
    "academic_search": (
        "paper",
        "papers",
        "study",
        "studies",
        "research",
        "publication",
        "journal",
        "preprint",
        "citations",
        "cited",
        "doi",
        "arxiv",
    ),
    "academic_author": (
        "author",
        "researcher",
        "professor",
        "h-index",
        "publications by",
        "who is",
        "most cited papers",
    ),
    "job_search": (
        "job",
        "jobs",
        "hiring",
        "vacancy",
        "vacancies",
        "openings",
        "open roles",
        "salary",
        "career",
        "recruiting",
        "engineers in",
    ),
    "flight_search": (
        "flight",
        "flights",
        "fly",
        "airfare",
        "fare",
        "layover",
        "one way",
        "round trip",
        "nonstop",
        "non-stop",
        "flight options",
        "cheapest nonstop",
    ),
    "hotel_search": (
        "hotel",
        "hotels",
        "stay",
        "accommodation",
        "resort",
        "rooms",
        "check in",
        "airbnb",
        "availability in",
        "charging for",
        "per night",
    ),
    "event_search": (
        "event",
        "events",
        "concert",
        "concerts",
        "gig",
        "gigs",
        "festival",
        "meetup",
        "meetups",
        "conference",
        "conferences",
        "happening this",
        "happening in",
        "tickets for",
        "what is on in",
    ),
    "trend_analysis": (
        "trend",
        "trends",
        "interest over time",
        "popularity",
        "search volume",
        "rising",
        "spiking",
        "search interest",
        "interest curve",
        "over the last",
        "chart the",
        "how often people search",
    ),
    "finance_quote": (
        "stock",
        "share price",
        "ticker",
        "nasdaq",
        "nyse",
        "market cap",
        "earnings",
        "quote",
        "trading at",
        "stock price",
        "shares",
        "exchange rate",
        "usd to",
        "conversion rate",
        "currency",
        "yen rate",
        "euro rate",
        "price per share",
        "market close",
    ),
    "patent_search": (
        "patent",
        "patents",
        "prior art",
        "uspto",
        "filing",
        "claim set",
        "claims",
    ),
    "app_search": (
        "app",
        "apps",
        "application",
        "play store",
        "app store",
        "download",
        "ios app",
        "android app",
        "google play",
        "listing on the",
        "install",
    ),
    "app_reviews": ("app review", "app reviews", "app ratings", "app store reviews"),
}


def tag_scores(text: str) -> dict[str, float]:
    """How strongly an intent indicates each capability tag.

    Multi-word phrases score double: "trading at" is far stronger evidence of a
    finance intent than "price" is of a shopping one.
    """
    haystack = " " + normalize(text) + " "
    scores: dict[str, float] = {}
    for tag, phrases in TAG_KEYWORDS.items():
        total = 0.0
        for phrase in phrases:
            if phrase not in haystack:
                continue
            words = phrase.count(" ") + 1
            if words > 1:
                total += 2.0
            elif " " + phrase + " " in haystack:
                total += 1.0
            else:
                total += 0.5
        if total:
            scores[tag] = total
    return scores


def normalized_tag_affinity(text: str, tags: list[str]) -> float:
    """0..1 affinity between an intent and one engine's capability tags."""
    scores = tag_scores(text)
    if not scores or not tags:
        return 0.0
    best = max(scores.values())
    matched = sum(scores.get(tag, 0.0) for tag in tags)
    return min(1.0, matched / (best * 1.5)) if best else 0.0


__all__ = ["TAG_KEYWORDS", "normalized_tag_affinity", "tag_scores"]
