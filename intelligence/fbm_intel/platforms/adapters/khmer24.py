"""Khmer24 (khmer24.com) public car listings — public web pages, no login, no private/internal API.

Access (verified live 2026-10-01 with the project's PoliteHttp UA; robots.txt + 2 pages):
- robots.txt (User-agent: *) disallows /search (the site's internal search), /login, /register, /chats/, /me/, …,
  and tracking params (?utm_ / fbclid / gclid). The internal search is therefore NOT used.
- The car category page `/c-cars-for-sale` with the site's own filter params (`?ad_field=<brand>&ad_model=<model>`)
  is allowed and server-rendered (Nuxt SSR): a schema.org JSON-LD `ItemList` of `Product`s plus `a.post[href*=adid-]`
  cards. Queries are mapped to these filters via `model_filters` in the platform config; a query without a mapping
  browses the unfiltered category and keeps only cards whose title matches the query.
- Listing pages `/<slug>-adid-<id>` (canonical `https://www.khmer24.com/post-adid-<id>`) are server-rendered with a
  JSON-LD `Product` (name, description, price, year, brand/model, seller address) and a `__NUXT_DATA__` payload
  (posted_date, district-level location, seller user object). No JS rendering or challenge was needed.
Collected: listing id, title, description (phones/emails/links redacted), price, year, district-level location,
posted date, listing kind (offer | wanted).
Seller privacy: JSON-LD `offers.seller` carries the seller's name, profile URL and telephone numbers — telephone fields
are never read into any stored field; the seller is stored as an `Organization` only when the account has a
company/shop profile or its name clearly reads as a business (dealer); otherwise only
`PersonKeyer.key_for("khmer24", <seller user id>)`. (Every seller is typed "Organization" in Khmer24's JSON-LD, so
that flag is NOT used as evidence. The Nuxt `user_type` field (1/2) has undocumented meaning and is not used either.)
Wanted/buying ads: Khmer24 shows no separate public "wanted" section in the car category; ads whose title/description
say "ត្រូវការទិញ" / "want to buy" / "wanted" … are marked listing_kind "wanted" (budget kept out of the text) so the
lead classifier can type them as buyers. `wanted_category_paths` can add a section if one is verified later.
Comments: listings have no public comments → comments_unavailable.
Screenshots: none (HTTP-only) — capture_evidence returns None.
Pagination: `page_param` ("page") is an assumption not verified live; the cursor walks at most `max_pages_per_query`
pages then restarts at page 1 (the worker's `seen` / revisit window dedupes).
"""
from __future__ import annotations

import json
import re
from datetime import timezone
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from ...normalize import normalize_text
from ...social.model import SocialPost
from ..base import HttpAdapterBase
from ..contract import Checkpoint, CommentBatch, Organization, SearchItem, SearchPage
from ..http import safe_url
from ..leads import looks_organizational
from ..registry import register
from .kh_classifieds import WANTED_MARKERS, base_post, clean_text, is_wanted, parse_date, query_matches

VERSION = "khmer24-public-web-v1"
BASE = "https://www.khmer24.com"
_AD_PATH = re.compile(r"^/(?:(?:en|km|zh)/)?[^/?#]*?-?adid-(\d{5,12})(?:\.html)?/?$")
_DEVALUE_WRAP = ("Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef", "EmptyShallowRef")
DEFAULT_FILTERS = [
    {"pattern": r"rx\s*-?\s*300|rx៣០០", "params": {"ad_field": "lexus", "ad_model": "rx300"}},
    {"pattern": r"lexus|ឡិចស៊ីស", "params": {"ad_field": "lexus"}},
]


# ─── parsing ────────────────────────────────────────────────────────────────

def jsonld(soup) -> list[dict]:
    out: list[dict] = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.get_text())
        except ValueError:
            continue
        for x in d if isinstance(d, list) else [d]:
            if isinstance(x, dict):
                out.extend(x["@graph"] if isinstance(x.get("@graph"), list) else [x])
    return out


def nuxt_payload(soup) -> list | None:
    el = soup.find("script", id="__NUXT_DATA__")
    if not el:
        return None
    try:
        nd = json.loads(el.get_text())
    except ValueError:
        return None
    return nd if isinstance(nd, list) else None


def devalue(nd: list, idx, depth: int = 0, max_depth: int = 6):
    """Resolve one value of Nuxt's devalue-serialized payload (index references into a flat array)."""
    if depth > max_depth or not isinstance(idx, int) or idx < 0 or idx >= len(nd):
        return None
    v = nd[idx]
    if isinstance(v, dict):
        return {k: devalue(nd, i, depth + 1, max_depth) for k, i in v.items()}
    if isinstance(v, list):
        if v and isinstance(v[0], str) and v[0] in _DEVALUE_WRAP:
            return devalue(nd, v[1], depth, max_depth) if len(v) > 1 else None
        if v and v[0] == "Date" and len(v) > 1:
            return v[1]
        return [devalue(nd, i, depth + 1, max_depth) for i in v]
    return v


def nuxt_ad(nd: list | None, ad_id: str) -> dict | None:
    """The listing record ({id,title,description,posted_date,location,user,…}) for `ad_id` in the Nuxt payload."""
    if not nd:
        return None
    for o in nd:
        if isinstance(o, dict) and {"id", "title", "user"} <= set(o) and ("posted_date" in o or "renew_date" in o):
            if str(devalue(nd, o["id"])) == str(ad_id):
                return {k: devalue(nd, i, 1) for k, i in o.items()}
    return None


def parse_search(html: str, base_url: str) -> list[dict]:
    """Results of a category page: JSON-LD ItemList products first (the filtered list); cards as a fallback."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for node in jsonld(soup):
        if node.get("@type") != "ItemList":
            continue
        for p in node.get("itemListElement") or []:
            p = p.get("item", p) if isinstance(p, dict) else {}
            m = _AD_PATH.match(urlsplit(p.get("url") or "").path)
            ad_id = str(p.get("sku") or (m.group(1) if m else "") or "")
            if not ad_id.isdigit():
                continue
            offer = p.get("offers") or {}
            out.setdefault(ad_id, {"id": ad_id, "title": normalize_text(p.get("name")), "price": offer.get("price"),
                                   "currency": offer.get("priceCurrency"), "year": p.get("releaseDate"), "source": "jsonld"})
    if not out:
        for a in soup.select("a[href*='adid-']"):
            m = _AD_PATH.match(urlsplit(urljoin(base_url, a.get("href") or "")).path)
            if not m:
                continue
            t = a.select_one(".title")
            price = a.select_one("strong")
            loc = a.select(".date-location p span")
            out.setdefault(m.group(1), {"id": m.group(1), "title": normalize_text(t.get_text(" ")) if t else None,
                                        "price": normalize_text(price.get_text()) if price else None,
                                        "location": normalize_text(loc[1].get_text()) if len(loc) > 1 else None,
                                        "source": "card"})
    return list(out.values())


def parse_listing(html: str, ad_id: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    prod = next((n for n in jsonld(soup) if n.get("@type") == "Product" and str(n.get("sku")) == str(ad_id)), None)
    ad = nuxt_ad(nuxt_payload(soup), ad_id)
    if prod is None and ad is None:
        return None
    prod = prod or {}
    ad = ad or {}
    offer = prod.get("offers") or {}
    seller = offer.get("seller") or {}                       # name / sameAs / telephone: never copied as-is
    user = ad.get("user") if isinstance(ad.get("user"), dict) else {}
    loc = ad.get("location") if isinstance(ad.get("location"), dict) else {}
    addr = seller.get("address") if isinstance(seller.get("address"), dict) else {}
    company = user.get("company")
    company_name = (company.get("name") if isinstance(company, dict) else company if isinstance(company, str) else None)
    cat = ad.get("category") if isinstance(ad.get("category"), dict) else {}
    brand = prod.get("brand")
    specs = ad.get("object_specs") if isinstance(ad.get("object_specs"), dict) else {}
    year = prod.get("releaseDate") or ((specs.get("car-year") or {}).get("value") if isinstance(specs.get("car-year"), dict) else None)
    return {
        "id": str(ad_id),
        "title": prod.get("name") or ad.get("title"),
        "description": ad.get("description") or prod.get("description"),
        "price": offer.get("price") or ad.get("price"),
        "currency": offer.get("priceCurrency") or "USD",
        "year": year,
        "brand": brand.get("name") if isinstance(brand, dict) else brand,
        "model": prod.get("model"),
        # district-level only (no street address)
        "location": loc.get("en_name2") or loc.get("en_name") or addr.get("addressLocality"),
        "posted_date": ad.get("posted_date") or ad.get("renew_date"),
        "category_slug": cat.get("slug"),
        "ad_type": ad.get("type"),
        # used only for org detection / keying, never stored for private individuals
        "seller_name": user.get("name") or seller.get("name"),
        "seller_username": user.get("username"),
        "seller_id": str(user.get("id") or "") or (urlsplit(seller.get("sameAs") or "").path.strip("/").split("/")[-1] or None),
        "seller_profile": seller.get("sameAs"),
        "company_name": company_name,
        "has_company": bool(company),
    }


# ─── adapter ────────────────────────────────────────────────────────────────

@register
class Khmer24Adapter(HttpAdapterBase):
    name = "khmer24"
    platform = "classifieds"
    display_name = "Khmer24 (public car listings)"
    tier = 2
    access = "public_web"
    adapter_version = VERSION
    supports_comments = False
    content_type = "classified_listing"
    allowed_hosts = frozenset({"khmer24.com"})

    @property
    def base_url(self) -> str:
        return (self.cfg.get("base_url") or BASE).rstrip("/")

    def canonicalize_url(self, url: str) -> str | None:
        if not url:
            return None
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or p.netloc.lower() not in ("khmer24.com", "www.khmer24.com", "m.khmer24.com"):
            return None
        m = _AD_PATH.match(p.path)
        return f"{BASE}/post-adid-{m.group(1)}" if m else None

    def _category_urls(self, query: str, page: int) -> tuple[list[str], bool]:
        """(urls, filtered) — filtered=True when the query maps to the site's own brand/model filter."""
        params: dict = {}
        for f in self.cfg.get("model_filters") or DEFAULT_FILTERS:
            if re.search(f["pattern"], query, re.I):
                params = dict(f["params"])
                break
        pp = self.cfg.get("page_param", "page")
        if page > 1:
            params[pp] = page
        paths = [self.cfg.get("category_path", "/c-cars-for-sale")] + list(self.cfg.get("wanted_category_paths", []))
        urls = [f"{self.base_url}{p}" + (f"?{urlencode(params)}" if params else "") for p in paths]
        return urls, bool({k for k in params if k != pp})

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        page = int(cursor.get("page", 1))
        urls, filtered = self._category_urls(query, page)
        self._cache: dict[str, dict] = getattr(self, "_cache", {})
        items: list[SearchItem] = []
        seen = set(checkpoint.seen)
        max_id = int(cursor.get("max_id", 0))
        pages: dict[str, str] = getattr(self, "_pages", {})     # one fetch per category URL per cycle
        self._pages = pages
        for url in urls:
            if url not in pages:
                pages[url] = self.http.get(url).text
            for res in parse_search(pages[url], url):
                canon = f"{BASE}/post-adid-{res['id']}"
                if canon in seen or (not filtered and not query_matches(query, res.get("title"))):
                    continue
                seen.add(canon)
                self._cache[canon] = res
                items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=safe_url(url),
                                        source_id=res["id"], preview={k: res.get(k) for k in ("id", "title", "price", "year")}))
                max_id = max(max_id, int(res["id"]))
        max_pages = int(self.cfg.get("max_pages_per_query", 3))
        nxt_page = page + 1 if items and page < max_pages else 1
        nxt = Checkpoint(query=query, cursor=json.dumps({"page": nxt_page, "max_id": max_id}), page=checkpoint.page + 1,
                         seen=list(checkpoint.seen))
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        if not canon:
            self.last_skip_reason = "not_a_khmer24_listing_url"
            return None
        ad_id = canon.rsplit("-", 1)[-1]
        r = self.http.get(canon)
        d = parse_listing(r.text, ad_id)
        if d is None or not d.get("title"):
            self.last_skip_reason = "listing_not_found_or_removed"
            return None
        d.update(url=canon, search_query=item.query if item else "", search_url=item.search_url if item else None)
        return self.normalize_result(d)

    def normalize_result(self, d: dict) -> SocialPost:
        title = clean_text(d.get("title"), 500, drop_contacts=True)
        desc = clean_text(d.get("description"), drop_contacts=True)   # listing text: contact placeholders dropped
        markers = self.cfg.get("wanted_markers") or WANTED_MARKERS
        wanted = (is_wanted(title, desc, markers=markers) or str(d.get("ad_type") or "").lower() in ("buy", "wanted")
                  or (d.get("category_slug") or "") in self.cfg.get("wanted_category_slugs", []))
        price = None
        if d.get("price"):
            try:
                price = f"${float(str(d['price']).replace('$', '').replace(',', '')):,.0f}" if (d.get("currency") or "USD") == "USD" else str(d["price"])
            except ValueError:
                price = str(d["price"])
        listing = {k: v for k, v in {"price": price, "year": d.get("year"), "brand": d.get("brand"), "model": d.get("model"),
                                      "location": d.get("location"), "listing_kind": "wanted" if wanted else "offer"}.items() if v}
        text = desc
        if not wanted:
            # offers: structured facts in the text help seller typing ("$9,800 … 2001"); a wanted ad's budget stays out
            facts = " · ".join(x for x in (f"Price: {price}" if price else None, f"Year: {d['year']}" if d.get("year") else None,
                                           f"Location: {d['location']}" if d.get("location") else None) if x)
            text = " · ".join(x for x in (desc, facts) if x) or None
        dt = parse_date(d.get("posted_date"))
        if dt is not None and d.get("posted_date") and "T" not in str(d["posted_date"]):
            dt = dt.replace(tzinfo=timezone.utc)   # site time is shown without zone; stored as observed
        post = base_post(self, url=d.get("url") or f"{BASE}/post-adid-{d['id']}", source_id=str(d["id"]), title=title, text=text,
                         published_text=d.get("posted_date"), published_at=dt,
                         evidence="Public Khmer24 listing page (server-rendered, no login)",
                         query=d.get("search_query", ""), search_url=d.get("search_url"), engagement={"listing": listing},
                         hashtags=[])
        org = self._organization(d)
        if org:
            post.organization = org
        elif d.get("seller_id"):
            post.author_key = self.keyer.key_for("khmer24", str(d["seller_id"]).casefold())
            post.author_key_version = self.keyer.version
        return post

    def _organization(self, d: dict) -> Organization | None:
        if d.get("has_company"):
            return Organization(platform="khmer24", name=d.get("company_name") or d.get("seller_name") or "Khmer24 shop",
                                url=d.get("seller_profile"), kind="dealer",
                                evidence="Khmer24 account has a company/shop profile")
        for nm in (d.get("seller_name"), d.get("seller_username")):
            if looks_organizational(nm):
                return Organization(platform="khmer24", name=d.get("seller_name") or nm, url=d.get("seller_profile"),
                                    kind="dealer", evidence="seller account name reads as a business (dealer/shop)")
        return None

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch([], "comments_unavailable")

    def capture_evidence(self, item) -> None:
        return None   # HTTP-only adapter; the public listing URL is the evidence
