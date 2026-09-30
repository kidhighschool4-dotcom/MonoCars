"""Generic config-driven Cambodian classifieds adapter (public web pages, no login, robots.txt respected).

Access: public_web over PoliteHttp (allowlisted hosts = the configured sites' hosts, pacing, robots.txt honoured,
challenge / 403 / 429 pages stop the cycle — never bypassed).

Each site is a block under "classifieds" in `config/sites_v1.json` (or inline in platforms.kh_classifieds.sites):
    name, enabled, base_url, search_url  ("{query}" / "{page}" placeholders; must be a robots-allowed page),
    result_link (CSS for listing links on the result page), listing_url_regex (which URLs are listings; group 1 = id),
    fields {title, price, location, date, description, seller, seller_link}  (CSS selectors),
    seller_id_attr / seller_id_regex (how to derive a stable seller id, used ONLY as keyer input),
    org_markers (CSS selectors or text markers that mark a shop / dealer account), wanted_markers, date_format.
Collected: listing id, title, description (phones / emails / links redacted), price, location, posted date.
Seller: an `Organization` only when an org marker matches or the name clearly reads as a business; otherwise only a
pseudonymous key from the seller id — names, usernames, profile URLs and phone fields are never stored.
Comments: classified listings have no public comments → `comments_unavailable`.
Screenshots: none (HTTP-only adapter) — capture_evidence returns None; the public listing URL is the evidence.
Blocker: ships with NO site enabled (health → misconfigured) until a site's selectors have been verified by hand.

This module also holds the small selector engine shared by `forums` (HTML forums) and `web_sites`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from ...comments import redact
from ...normalize import normalize_text, sha256_hex
from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import AdapterContext, Checkpoint, CommentBatch, Health, Organization, SearchItem, SearchPage
from ..http import safe_url
from ..leads import looks_organizational, prep
from ..registry import register

VERSION = "kh-classifieds-config-v1"
SITES_PATH = Path(__file__).resolve().parents[3] / "config" / "sites_v1.json"
PLACEHOLDER_HOSTS = frozenset({"configured-sites.invalid"})   # real hosts come from the configured sites
_KHMER_DIGITS = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")
WANTED_MARKERS = ("ត្រូវការទិញ", "រកទិញ", "ចង់ទិញ", "want to buy", "wanted", "wtb", "looking for", "buying")


# ─── shared helpers (also used by forums / web_sites / khmer24) ─────────────

def clean_text(text: str | None, limit: int = 20000, *, drop_contacts: bool = False) -> str | None:
    """Normalize + redact phones / emails / links. Khmer digits are folded to ASCII first so Khmer-digit phone
    numbers are redacted too (the shared redact regex only knows ASCII digits).
    drop_contacts: remove the [phone]/[email]/[link] placeholders entirely — used for classified-listing text, where
    contact details are never content and where the placeholder would otherwise make intent scoring flag the listing
    as spam (leads.classify_post treats any negative signal, including spam:contains_phone, as negation)."""
    t = normalize_text((text or "").translate(_KHMER_DIGITS))
    t = redact(t)
    if drop_contacts:
        t = normalize_text(re.sub(r"\[(?:phone|email|link)\]", " ", t))
        t = re.sub(r"\s+([,.;:·។])", r"\1", t)
    t = t[:limit]
    return t or None


def is_wanted(*texts: str | None, markers: tuple[str, ...] | list[str] = WANTED_MARKERS) -> bool:
    t = prep(" ".join(x for x in texts if x))
    for m in markers:
        m = prep(m)
        if m.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(m)}(?![a-z0-9])", t):
                return True
        elif m in t:
            return True
    return False


def load_sites(section: str, cfg: dict) -> list[dict]:
    """Enabled sites of one section of sites_v1.json plus the platform block's inline `sites`.
    A string in platforms.<name>.sites enables that named site from the file even if it is not enabled there."""
    path = Path(cfg.get("sites_file") or SITES_PATH)
    try:
        file_sites = json.loads(path.read_text(encoding="utf-8")).get(section, [])
    except (OSError, ValueError):
        file_sites = []
    by_name = {s.get("name"): s for s in file_sites if isinstance(s, dict)}
    out = [s for s in file_sites if isinstance(s, dict) and s.get("enabled") is True]
    for s in cfg.get("sites", []) or []:
        if isinstance(s, str) and s in by_name:
            out.append({**by_name[s], "enabled": True})
        elif isinstance(s, dict) and s.get("enabled", True):
            out.append(s)
    seen, uniq = set(), []
    for s in out:
        base = s.get("base_url", "")
        if s.get("name") in seen or not base.startswith("https://"):
            continue
        seen.add(s.get("name"))
        uniq.append(s)
    return uniq


def site_host(site: dict) -> str:
    return urlsplit(site["base_url"]).netloc.lower()


def hosts_of(sites: list[dict]) -> frozenset[str]:
    return frozenset(site_host(s) for s in sites) or PLACEHOLDER_HOSTS


def site_for_url(sites: list[dict], url: str) -> dict | None:
    host = urlsplit(url).netloc.lower()
    for s in sites:
        h = site_host(s)
        if host == h or host == "www." + h or "www." + host == h:
            return s
    return None


def strip_url(url: str) -> str:
    """https URL without fragment / tracking params (utm_*, fbclid, gclid)."""
    p = urlsplit(url)
    q = "&".join(kv for kv in p.query.split("&") if kv and not re.match(r"(utm_\w+|fbclid|gclid)=", kv))
    return urlunsplit(("https", p.netloc.lower(), p.path, q, ""))


def sel_text(root, css: str | None) -> str | None:
    if not css or root is None:
        return None
    el = root.select_one(css)
    return normalize_text(el.get_text(" ")) if el else None


def sel_attr(root, css: str | None, attr: str) -> str | None:
    if not css or root is None:
        return None
    el = root.select_one(css)
    return el.get(attr) if el else None


def parse_date(text: str | None, fmt: str | None = None) -> datetime | None:
    if not text:
        return None
    t = text.strip()
    fmts = [fmt] if fmt else []
    fmts += ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"]
    for f in fmts:
        try:
            d = datetime.strptime(t.replace("Z", "+0000") if "%z" in f else t, f)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def query_matches(query: str, *texts: str | None) -> bool:
    """Local relevance filter for listing pages that are not a site search: every query token appears."""
    t = prep(" ".join(x for x in texts if x))
    compact = t.replace(" ", "")
    toks = [x for x in prep(query).split() if len(x) >= 2]
    return bool(toks) and all(x in t or x in compact for x in toks)


def org_marked(root, markers: list[str] | None) -> str | None:
    """First org marker that matches: a CSS selector present in the page, or 'text:<phrase>' in the page text."""
    for m in markers or []:
        if m.startswith("text:"):
            if prep(m[5:]) in prep(root.get_text(" ")):
                return m
        else:
            try:
                if root.select_one(m) is not None:
                    return m
            except Exception:  # noqa: BLE001 - invalid selector in config
                continue
    return None


def base_post(adapter, *, url: str, source_id: str | None, title: str | None, text: str | None, published_text: str | None,
              published_at: datetime | None, evidence: str, query: str = "", search_url: str | None = None,
              engagement: dict | None = None, hashtags: list[str] | None = None, comments_supported: bool = False) -> SocialPost:
    body = " ".join(x for x in (title, text) if x)
    return SocialPost(
        platform=adapter.platform, source_content_type=adapter.content_type, source_post_id=source_id, source_post_url=url,
        canonical_post_url=url, document_title=None, post_title=title, post_text=text,
        hashtags=hashtags if hashtags is not None else re.findall(r"#\w+", text or ""),
        published_text_displayed=published_text, published_at_observed=published_at, engagement=engagement or {},
        visibility_status="public_verified", visibility_evidence=evidence, search_query=query, search_url=search_url,
        captured_at=datetime.now(timezone.utc), adapter_version=adapter.adapter_version,
        content_hash=sha256_hex(body.casefold()), completeness_status="comments_unavailable",
        comments_supported=comments_supported)


def extract_threaded_comments(adapter, soup, spec: dict, post: SocialPost, *, key_ns: str, op_key: str | None,
                              limit: int = 500) -> list[SocialComment]:
    """Comments from a rendered page via config selectors. Threading from DOM nesting (an item inside another item is
    a reply to it — WordPress `ul.children`, nested forum quotes) or `parent_attr` (id of the parent item).
    Author text / links are used only as keyer input and never stored."""
    item_css = spec.get("item")
    if not item_css:
        return []
    items = soup.select(item_css)[:limit]
    by_node: dict[int, SocialComment] = {}
    by_id: dict[str, SocialComment] = {}
    counter: dict = {}
    out: list[SocialComment] = []
    id_attr = spec.get("id_attr", "id")
    # items marked as written by the page's own author (e.g. WordPress `.bypostauthor`) → is_post_author
    own_nodes = {id(x) for x in soup.select(spec["post_author_marker"])} if spec.get("post_author_marker") else set()
    for el in items:
        body_el = el.select_one(spec["body"]) if spec.get("body") else el
        if body_el is None:
            continue
        # text of this item only (drop nested child items so a parent's text does not include its replies)
        body = BeautifulSoup(str(body_el), "html.parser")
        for nested in body.select(item_css):
            nested.decompose()
        author = sel_attr(el, spec.get("author_link"), "href") or sel_text(el, spec.get("author"))
        ckey = adapter.keyer.key_for(key_ns, prep(author)) if author else None
        parent = None
        if spec.get("parent_attr") and el.get(spec["parent_attr"]):
            parent = by_id.get(str(el.get(spec["parent_attr"])))
        if parent is None:
            anc = el.find_parent(lambda t: t is not None and id(t) in by_node)
            parent = by_node.get(id(anc)) if anc is not None else None
        cid = el.get(id_attr)
        disp = sel_attr(el, spec.get("date"), "datetime") or sel_text(el, spec.get("date"))
        c = make_comment(platform=adapter.platform, post_url=post.canonical_post_url, raw_text=body.get_text(" "),
                         is_reply=parent is not None, parent=parent, commenter_key=ckey,
                         key_version=adapter.keyer.version if ckey else None, displayed_timestamp=disp,
                         commented_at=parse_date(disp, spec.get("date_format")),
                         source_comment_id=f"{key_ns}:{cid}" if cid else None,
                         source_comment_url=f"{post.canonical_post_url}#{cid}" if cid else None, occurrence_counter=counter)
        if c is None:
            continue
        c.is_post_author = bool(op_key and ckey == op_key) or id(el) in own_nodes
        by_node[id(el)] = c
        if cid:
            by_id[str(cid)] = c
        out.append(c)
    return out


class ConfigSitesMixin:
    """Search over configured sites (search_url template or listing_urls) with a per-site page cursor."""
    section = ""
    link_css_key = "result_link"
    url_regex_key = "listing_url_regex"

    def _init_sites(self, ctx: AdapterContext) -> None:
        self.sites = load_sites(self.section, ctx.config)
        self.allowed_hosts = hosts_of(self.sites)

    def _url_matches(self, site: dict, url: str) -> re.Match | None:
        rx = site.get(self.url_regex_key)
        path = urlsplit(url).path + (("?" + urlsplit(url).query) if urlsplit(url).query else "")
        return re.search(rx, path) if rx else None

    def canonicalize_url(self, url: str) -> str | None:
        if not url or not url.startswith(("http://", "https://")):
            return None
        site = site_for_url(self.sites, url)
        if not site or not self._url_matches(site, url):
            return None
        p = urlsplit(strip_url(url))
        return urlunsplit(("https", site_host(site), p.path, p.query, ""))

    def _pages_for(self, site: dict, query: str, page: int) -> list[str]:
        if site.get("search_url"):
            return [site["search_url"].replace("{query}", quote_plus(query)).replace("{page}", str(page))]
        urls = site.get("listing_urls") or []
        return [urljoin(site["base_url"], u) for u in urls] if page == 1 else []

    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        items: list[SearchItem] = []
        seen = set(checkpoint.seen)
        max_pages = int(self.cfg.get("max_pages_per_query", 3))
        for site in self.sites:
            page = int(cursor.get(site["name"], {}).get("page", 1))
            found = 0
            for url in self._pages_for(site, query, page):
                r = self.http.get(url)
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.select(site.get(self.link_css_key) or "a[href]"):
                    href = urljoin(url, a.get("href") or "")
                    canon = self.canonicalize_url(href)
                    if not canon or canon in seen:
                        continue
                    label = normalize_text(a.get_text(" "))
                    if not site.get("search_url") and not query_matches(query, label):
                        continue          # listing pages are not a search: keep only titles matching the query
                    seen.add(canon)
                    m = self._url_matches(site, canon)
                    sid = m.group(1) if m and m.groups() else None
                    items.append(SearchItem(url=href, canonical_url=canon, query=query, search_url=safe_url(url),
                                            source_id=f"{site['name']}:{sid}" if sid else None,
                                            preview={"site": site["name"], "title": label[:300]}))
                    found += 1
            nxt = page + 1 if (found and site.get("search_url") and page < max_pages) else 1
            cursor[site["name"]] = {"page": nxt}
        nxt_cp = Checkpoint(query=query, cursor=json.dumps(cursor, sort_keys=True), page=checkpoint.page + 1,
                            seen=list(checkpoint.seen))
        self._next_checkpoint = nxt_cp
        return SearchPage(items=items, next_checkpoint=nxt_cp, exhausted=not items)


@register
class KhClassifiedsAdapter(ConfigSitesMixin, HttpAdapterBase):
    name = "kh_classifieds"
    platform = "classifieds"
    display_name = "Cambodian classifieds (config-driven)"
    tier = 2
    access = "public_web"
    adapter_version = VERSION
    supports_comments = False
    content_type = "classified_listing"
    allowed_hosts = PLACEHOLDER_HOSTS
    section = "classifieds"

    def __init__(self, ctx: AdapterContext):
        self._init_sites(ctx)
        super().__init__(ctx)

    def health_check(self) -> Health:
        if not self.sites:
            return Health("misconfigured", "no classifieds sites configured (enable a verified site under \"classifieds\" "
                                           "in config/sites_v1.json or list it in platforms.kh_classifieds.sites)")
        return Health("ok")

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        site = site_for_url(self.sites, url) if canon else None
        if not canon or not site:
            self.last_skip_reason = "not_a_configured_listing_url"
            return None
        r = self.http.get(canon)
        soup = BeautifulSoup(r.text, "html.parser")
        f = site.get("fields", {})
        title = sel_text(soup, f.get("title"))
        if not title:
            self.last_skip_reason = "listing_not_found_or_removed"
            return None
        m = self._url_matches(site, canon)
        raw = {
            "site": site, "url": canon, "id": m.group(1) if m and m.groups() else None, "title": title,
            "description": sel_text(soup, f.get("description")), "price": sel_text(soup, f.get("price")),
            "location": sel_text(soup, f.get("location")), "date_text": sel_text(soup, f.get("date")),
            "seller_name": sel_text(soup, f.get("seller")), "seller_id": self._seller_id(site, soup),
            "org_marker": org_marked(soup, site.get("org_markers")),
            "search_query": item.query if item else "", "search_url": item.search_url if item else None,
        }
        return self.normalize_result(raw)

    @staticmethod
    def _seller_id(site: dict, soup) -> str | None:
        f = site.get("fields", {})
        link = sel_attr(soup, f.get("seller_link"), site.get("seller_id_attr", "href"))
        if not link:
            return None
        rx = site.get("seller_id_regex")
        m = re.search(rx, link) if rx else None
        return m.group(1) if m else urlsplit(link).path.strip("/") or link

    def normalize_result(self, d: dict) -> SocialPost:
        site = d["site"]
        title = clean_text(d.get("title"), 500, drop_contacts=True)
        desc = clean_text(d.get("description"), drop_contacts=True)
        wanted = is_wanted(title, desc, markers=site.get("wanted_markers") or WANTED_MARKERS)
        listing = {k: v for k, v in {"price": d.get("price"), "location": d.get("location"), "site": site["name"],
                                      "listing_kind": "wanted" if wanted else "offer"}.items() if v}
        text = desc
        if not wanted and d.get("price"):
            # offers: price in the text helps the seller typing; wanted ads keep the budget out of the text
            text = " · ".join(x for x in (desc, f"Price: {d['price']}") if x)
        post = base_post(self, url=d["url"], source_id=f"{site['name']}:{d['id']}" if d.get("id") else None, title=title,
                         text=text, published_text=d.get("date_text"),
                         published_at=parse_date(d.get("date_text"), site.get("date_format")),
                         evidence=f"Public listing page on {site_host(site)} (no login)", query=d.get("search_query", ""),
                         search_url=d.get("search_url"), engagement={"listing": listing})
        seller = d.get("seller_name")
        if d.get("org_marker") or looks_organizational(seller):
            post.organization = Organization(platform=self.platform, name=seller or site["name"], url=None, kind="dealer",
                                             evidence=f"shop/dealer marker {d['org_marker']!r}" if d.get("org_marker")
                                             else "seller name reads as a business")
        elif d.get("seller_id"):
            post.author_key = self.keyer.key_for(f"classifieds:{site_host(site)}", str(d["seller_id"]))
            post.author_key_version = self.keyer.version
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        return CommentBatch([], "comments_unavailable")

    def capture_evidence(self, item) -> None:
        return None   # HTTP-only adapter: no rendered screenshot; the public listing URL is the evidence
