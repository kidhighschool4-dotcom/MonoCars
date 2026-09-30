"""Public forums: Discourse (documented public JSON) and generic HTML forums (config selectors). No login.

Access: public_web over PoliteHttp — only the configured forums' hosts, robots.txt honoured, pacing, challenge / 403 /
429 stop the cycle. Sites are listed under "forums" in `config/sites_v1.json` (or inline in platforms.forums.sites).

(a) Discourse (`"type": "discourse"`): Discourse's documented public JSON views of public pages —
    `/search.json?q=` (the JSON twin of /search) and `/t/<id>.json` (topic + first chunk of posts), plus
    `/t/<id>/posts.json?post_ids[]=` for the rest of the stream (capped by `max_posts_per_thread`).
    Default Discourse robots.txt disallows `/search` for all crawlers; when robots.txt forbids the search JSON the
    adapter falls back to the site's public listing JSON (`listing_paths`, default `/latest.json`) and keeps topics
    whose title matches the query. Nothing private (PMs, restricted categories need login and are not returned).
    Thread = first post (post_text); the other posts are comments, threaded with `reply_to_post_number`.
(b) Generic HTML (`"type": "html"`): search_url template or listing_urls, `result_link`, `thread_url_regex`,
    `thread` {title, first_post, date}, `comments` {item, body, author, date, id_attr, parent_attr} — threading from
    DOM nesting / parent attribute.
Privacy: usernames / display names are never stored — they are keyer input only (key namespace `forum:<host>`);
the thread author's replies are marked is_post_author. Forum accounts are not treated as organizations.
Screenshots: none (HTTP-only) — capture_evidence returns None.
Blocker: ships with no forum configured (health → misconfigured) — no Cambodian car forum with a verified public
Discourse/HTML structure is known yet.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urljoin, urlsplit

from bs4 import BeautifulSoup

from ...social.model import SocialComment, SocialPost, make_comment
from ..base import HttpAdapterBase
from ..contract import AdapterContext, Checkpoint, CommentBatch, Health, SearchItem, SearchPage
from ..http import safe_url
from ..leads import prep
from ..registry import register
from .kh_classifieds import (ConfigSitesMixin, base_post, clean_text, extract_threaded_comments, hosts_of, load_sites,
                             parse_date, query_matches, sel_attr, sel_text, site_for_url, site_host)

VERSION = "forums-discourse-html-v1"
_DISCOURSE_TOPIC = re.compile(r"^/t/(?:([^/]+)/)?(\d+)(?:/\d+)?/?$")


def _html_text(cooked: str | None) -> str:
    if not cooked:
        return ""
    soup = BeautifulSoup(cooked, "html.parser")
    for q in soup.select("aside.quote, .quote"):        # quoted text belongs to the quoted post
        q.decompose()
    return soup.get_text(" ")


@register
class ForumsAdapter(ConfigSitesMixin, HttpAdapterBase):
    name = "forums"
    platform = "forum"
    display_name = "Public forums (Discourse / HTML)"
    tier = 2
    access = "public_web"
    adapter_version = VERSION
    supports_comments = True
    content_type = "forum_thread"
    allowed_hosts = frozenset({"configured-sites.invalid"})
    section = "forums"
    url_regex_key = "thread_url_regex"

    def __init__(self, ctx: AdapterContext):
        self.sites = load_sites(self.section, ctx.config)
        self.allowed_hosts = hosts_of(self.sites)
        super().__init__(ctx)
        self._threads: dict[str, dict] = {}

    def health_check(self) -> Health:
        if not self.sites:
            return Health("misconfigured", "no forums configured (add a public Discourse or HTML forum under \"forums\" in "
                                           "config/sites_v1.json, or list it in platforms.forums.sites)")
        return Health("ok")

    # ── URLs ──
    def _url_matches(self, site: dict, url: str):
        if site.get("type") == "discourse":
            return _DISCOURSE_TOPIC.match(urlsplit(url).path)
        return super()._url_matches(site, url)

    def canonicalize_url(self, url: str) -> str | None:
        if not url or not url.startswith(("http://", "https://")):
            return None
        site = site_for_url(self.sites, url)
        if site and site.get("type") == "discourse":
            m = _DISCOURSE_TOPIC.match(urlsplit(url).path)
            if not m:
                return None
            slug = m.group(1) or "topic"
            return f"https://{site_host(site)}/t/{slug}/{m.group(2)}"
        return super().canonicalize_url(url)

    # ── search ──
    def search(self, query: str, checkpoint: Checkpoint) -> SearchPage:
        html_sites = [s for s in self.sites if s.get("type") != "discourse"]
        disc_sites = [s for s in self.sites if s.get("type") == "discourse"]
        cursor = json.loads(checkpoint.cursor) if checkpoint.cursor else {}
        items: list[SearchItem] = []
        if html_sites:
            all_sites, self.sites = self.sites, html_sites
            try:
                sub = ConfigSitesMixin.search(self, query, Checkpoint(query=query, cursor=json.dumps(
                    {k: v for k, v in cursor.items() if k in {s["name"] for s in html_sites}}), seen=list(checkpoint.seen)))
            finally:
                self.sites = all_sites
            items += sub.items
            cursor.update(json.loads(sub.next_checkpoint.cursor or "{}"))
        seen = set(checkpoint.seen) | {i.canonical_url for i in items}
        max_pages = int(self.cfg.get("max_pages_per_query", 3))
        for site in disc_sites:
            base = site["base_url"].rstrip("/")
            page = int(cursor.get(site["name"], {}).get("page", 1))
            url = f"{base}/search.json?q={quote_plus(query)}" + (f"&page={page}" if page > 1 else "")
            topics: list[dict]
            if self.http.robots_allows(url):
                data = self.http.get(url, headers={"Accept": "application/json"}).json()
                topics = data.get("topics") or []
                src, filtered = url, True
            else:
                topics, src, filtered = [], None, False
                for path in site.get("listing_paths") or ["/latest.json"]:
                    src = urljoin(base + "/", path.lstrip("/"))
                    data = self.http.get(src, headers={"Accept": "application/json"}).json()
                    topics += (data.get("topic_list") or {}).get("topics") or []
            found = 0
            for t in topics:
                if not t.get("id") or (not filtered and not query_matches(query, t.get("title"), t.get("excerpt"))):
                    continue
                canon = f"https://{site_host(site)}/t/{t.get('slug') or 'topic'}/{t['id']}"
                if canon in seen:
                    continue
                seen.add(canon)
                found += 1
                items.append(SearchItem(url=canon, canonical_url=canon, query=query, search_url=safe_url(src),
                                        source_id=f"{site_host(site)}:{t['id']}", preview={"title": t.get("title")}))
            cursor[site["name"]] = {"page": page + 1 if (filtered and found and page < max_pages) else 1}
        nxt = Checkpoint(query=query, cursor=json.dumps(cursor, sort_keys=True), page=checkpoint.page + 1,
                         seen=list(checkpoint.seen))
        self._next_checkpoint = nxt
        return SearchPage(items=items, next_checkpoint=nxt, exhausted=not items)

    # ── threads ──
    def collect_post(self, url: str, item: SearchItem | None = None) -> SocialPost | None:
        canon = self.canonicalize_url(url)
        site = site_for_url(self.sites, url) if canon else None
        if not canon or not site:
            self.last_skip_reason = "not_a_configured_forum_thread"
            return None
        q = (item.query if item else "", item.search_url if item else None)
        post = self._discourse_thread(site, canon, *q) if site.get("type") == "discourse" else self._html_thread(site, canon, *q)
        return post

    def _discourse_thread(self, site: dict, canon: str, query: str, search_url: str | None) -> SocialPost | None:
        base = site["base_url"].rstrip("/")
        tid = canon.rsplit("/", 1)[-1]
        data = self.http.get(f"{base}/t/{tid}.json", headers={"Accept": "application/json"}).json()
        stream = (data.get("post_stream") or {})
        posts = list(stream.get("posts") or [])
        have = {p.get("id") for p in posts}
        missing = [i for i in (stream.get("stream") or []) if i not in have][: max(0, int(self.cfg.get("max_posts_per_thread", 200)) - len(posts))]
        for i in range(0, len(missing), 20):
            chunk = missing[i:i + 20]
            qs = "&".join(f"post_ids[]={x}" for x in chunk)
            more = self.http.get(f"{base}/t/{tid}/posts.json?{qs}", headers={"Accept": "application/json"}).json()
            posts += (more.get("post_stream") or {}).get("posts") or []
        posts.sort(key=lambda p: p.get("post_number") or 0)
        if not posts or data.get("archetype", "regular") == "private_message":
            self.last_skip_reason = "thread_not_public"
            return None
        slug = data.get("slug") or "topic"
        canon = f"https://{site_host(site)}/t/{slug}/{tid}"
        op = posts[0]
        post = self.normalize_result({"kind": "discourse", "site": site, "url": canon, "id": tid, "title": data.get("title"),
                                      "text": _html_text(op.get("cooked")), "date": op.get("created_at") or data.get("created_at"),
                                      "search_query": query, "search_url": search_url,
                                      "engagement": {k: data[k] for k in ("posts_count", "views", "like_count") if k in data},
                                      "author": str(op.get("user_id") or op.get("username") or "")})
        self._threads[canon] = {"kind": "discourse", "site": site, "posts": posts[1:], "op_key": post.author_key}
        return post

    def _html_thread(self, site: dict, canon: str, query: str, search_url: str | None) -> SocialPost | None:
        r = self.http.get(canon)
        soup = BeautifulSoup(r.text, "html.parser")
        t = site.get("thread", {})
        title = sel_text(soup, t.get("title"))
        if not title:
            self.last_skip_reason = "thread_not_found"
            return None
        m = self._url_matches(site, canon)
        first = soup.select_one(t["first_post"]) if t.get("first_post") else None
        author = sel_attr(soup, t.get("author_link"), "href") or sel_text(soup, t.get("author"))
        date = sel_attr(soup, t.get("date"), "datetime") or sel_text(soup, t.get("date"))
        post = self.normalize_result({"kind": "html", "site": site, "url": canon, "id": m.group(1) if m and m.groups() else None,
                                      "title": title, "text": first.get_text(" ") if first else "", "date": date,
                                      "search_query": query, "search_url": search_url, "author": author})
        self._threads[canon] = {"kind": "html", "site": site, "soup": soup, "op_key": post.author_key}
        return post

    def normalize_result(self, d: dict) -> SocialPost:
        site = d["site"]
        title = clean_text(d.get("title"), 500)
        text = clean_text(d.get("text"))
        disp = d.get("date")
        post = base_post(self, url=d["url"], source_id=f"{site_host(site)}:{d['id']}" if d.get("id") else None, title=title,
                         text=text, published_text=disp, published_at=parse_date(disp, site.get("date_format")),
                         evidence=f"Public forum thread on {site_host(site)} (readable without login)",
                         query=d.get("search_query", ""), search_url=d.get("search_url"), engagement=d.get("engagement") or {},
                         comments_supported=True)
        if d.get("author"):
            post.author_key = self.keyer.key_for(f"forum:{site_host(site)}", prep(d["author"]))
            post.author_key_version = self.keyer.version
        return post

    def collect_comments(self, post: SocialPost) -> CommentBatch:
        th = self._threads.get(post.canonical_post_url)
        if th is None:
            return CommentBatch([], "comments_unavailable")
        site = th["site"]
        if th["kind"] == "html":
            spec = site.get("comments") or {}
            comments = extract_threaded_comments(self, th["soup"], spec, post, key_ns=f"forum:{site_host(site)}",
                                                 op_key=th["op_key"])
            return CommentBatch(comments, "complete" if spec.get("item") else "comments_unavailable")
        host = site_host(site)
        by_num: dict[int, SocialComment] = {}
        counter: dict = {}
        out: list[SocialComment] = []
        for p in th["posts"]:
            if p.get("hidden") or p.get("deleted_at") or p.get("post_type", 1) != 1:
                continue
            who = str(p.get("user_id") or p.get("username") or "")
            ckey = self.keyer.key_for(f"forum:{host}", prep(who)) if who else None
            parent = by_num.get(p.get("reply_to_post_number") or -1)
            num = p.get("post_number")
            curl = f"{post.canonical_post_url}/{num}" if num else None
            created = p.get("created_at")
            c = make_comment(platform=self.platform, post_url=post.canonical_post_url, raw_text=_html_text(p.get("cooked")),
                             is_reply=parent is not None, parent=parent, commenter_key=ckey,
                             key_version=self.keyer.version if ckey else None, displayed_timestamp=created,
                             commented_at=parse_date(created) if created else None,
                             source_comment_id=f"{host}:{p['id']}" if p.get("id") else None, source_comment_url=curl,
                             occurrence_counter=counter)
            if c is None:
                continue
            c.is_post_author = bool(th["op_key"] and ckey == th["op_key"])
            if num:
                by_num[num] = c
            out.append(c)
        return CommentBatch(out, "complete")

    def capture_evidence(self, item) -> None:
        return None   # HTTP-only adapter; the public thread URL is the evidence

