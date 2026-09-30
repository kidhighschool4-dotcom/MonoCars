"""Configured public websites: dealership sites, blogs with public comment sections, community boards. No login.

Access: public_web over PoliteHttp — only the configured sites' hosts, robots.txt honoured, pacing, challenge / 403 /
429 stop the cycle. Sites live under "web_sites" in `config/sites_v1.json` (or inline in platforms.web_sites.sites):
    name, enabled, kind (dealer | blog | board), base_url, search_url ("{query}"/"{page}") or listing_urls,
    result_link (CSS), page_url_regex (which URLs are pages to collect; group 1 = id),
    page {title, body, date, author}, comments {item, body, author, date, id_attr, parent_attr} (optional),
    organization {name, kind} (a dealership / media site is stored as an Organization).
Collected: page title + body text (phones/emails/links redacted), displayed date, and — where the site shows a public
comment section — comments with reply threading (DOM nesting, e.g. WordPress `ul.children`, or parent attribute).
Privacy: commenter / blog-author names are keyer input only (never stored); a dealer site is an Organization.
Listing pages of a site (not a search) are filtered locally so only links whose text matches the query are kept.
Screenshots: none (HTTP-only) — capture_evidence returns None.
Blocker: ships with no site configured (health → misconfigured) until a site's selectors are verified by hand.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ...social.model import SocialPost
from ..base import HttpAdapterBase
from ..contract import AdapterContext, CommentBatch, Health, Organization, SearchItem
from ..leads import prep
from ..registry import register
from .kh_classifieds import (PLACEHOLDER_HOSTS, ConfigSitesMixin, base_post, clean_text, extract_threaded_comments,
                             parse_date, sel_attr, sel_text, site_for_url, site_host)

VERSION = "web-sites-config-v1"
_ORG_KINDS = {"dealer", "shop", "page", "channel", "marketplace_seller", "forum", "media", "other"}


@register
class WebSitesAdapter(ConfigSitesMixin, HttpAdapterBase):
    name = "web_sites"
    platform = "web"
    display_name = "Dealer sites, blogs & community boards (configured)"
    tier = 3
    access = "public_web"
    adapter_version = VERSION
    supports_comments = True
    content_type = "web_page"
    allowed_hosts = PLACEHOLDER_HOSTS
    section = "web_sites"
    url_regex_key = "page_url_regex"

    def __init__(self, ctx: AdapterContext):
        self._init_sites(ctx)
        super().__init__(ctx)
        self._pages: dict[str, dict] = {}

    def health_check(self) -> Health:
        if not self.sites:
            return Health("misconfigured", "no web sites configured (add a dealer site / blog / community board under "
                                           "\"web_sites\" in config/sites_v1.json, or list it in platforms.web_sites.sites)")
        return Health("ok")

    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        site = site_for_url(self.sites, url) if canon else None
        if not canon or not site:
            self.last_skip_reason = "not_a_configured_page_url"
            return None
        r = self.http.get(canon)
        soup = BeautifulSoup(r.text, "html.parser")
        spec = site.get("page", {})
        title = sel_text(soup, spec.get("title"))
        body_el = soup.select_one(spec["body"]) if spec.get("body") else None
        if not title and body_el is None:
            self.last_skip_reason = "page_not_found"
            return None
        if body_el is not None and (site.get("comments") or {}).get("item"):
            body_el = BeautifulSoup(str(body_el), "html.parser")
            for c in body_el.select(site["comments"]["item"]):      # comments are collected separately
                c.decompose()
        m = self._url_matches(site, canon)
        post = self.normalize_result({
            "site": site, "url": canon, "id": m.group(1) if m and m.groups() else None, "title": title,
            "text": body_el.get_text(" ") if body_el is not None else None,
            "date": sel_attr(soup, spec.get("date"), "datetime") or sel_text(soup, spec.get("date")),
            "author": sel_attr(soup, spec.get("author_link"), "href") or sel_text(soup, spec.get("author")),
            "search_query": item.query if item else "", "search_url": item.search_url if item else None})
        self._pages[canon] = {"site": site, "soup": soup, "op_key": post.author_key}
        return post

    def normalize_result(self, d: dict) -> SocialPost:
        site = d["site"]
        disp = d.get("date")
        has_comments = bool((site.get("comments") or {}).get("item"))
        post = base_post(self, url=d["url"], source_id=f"{site['name']}:{d['id']}" if d.get("id") else None,
                         title=clean_text(d.get("title"), 500), text=clean_text(d.get("text")), published_text=disp,
                         published_at=parse_date(disp, site.get("date_format")),
                         evidence=f"Public page on {site_host(site)} (no login)", query=d.get("search_query", ""),
                         search_url=d.get("search_url"), engagement={"site": site["name"], "site_kind": site.get("kind", "other")},
                         comments_supported=has_comments)
        org = site.get("organization")
        if site.get("kind") == "dealer" or org:
            org = org or {}
            kind = org.get("kind") or ("dealer" if site.get("kind") == "dealer" else "other")
            post.organization = Organization(platform="web", name=org.get("name") or site["name"], url=site["base_url"],
                                             kind=kind if kind in _ORG_KINDS else "other",
                                             evidence=org.get("evidence") or f"configured as a {site.get('kind', 'organizational')} website")
        elif d.get("author"):
            post.author_key = self.keyer.key_for(f"web:{site_host(site)}", prep(d["author"]))
            post.author_key_version = self.keyer.version
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        pg = self._pages.get(post.canonical_post_url)
        if pg is None or not (pg["site"].get("comments") or {}).get("item"):
            return CommentBatch([], "comments_unavailable")
        site = pg["site"]
        comments = extract_threaded_comments(self, pg["soup"], site["comments"], post, key_ns=f"web:{site_host(site)}",
                                             op_key=pg["op_key"])
        return CommentBatch(comments, "complete")

    def capture_evidence(self, item) -> None:
        return None   # HTTP-only adapter; the public page URL is the evidence
