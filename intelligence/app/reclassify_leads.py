"""Re-type stored comments with the current lead rules (after a rule change).  python -m app.reclassify_leads [--dry-run]"""
from __future__ import annotations

import argparse
import collections
import sys

import httpx

from fbm_intel.platforms.leads import PostContext, classify_comment
from fbm_intel.settings import Settings
from fbm_intel.social.intent_score import score_comment


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    st = Settings.load()
    h = {"apikey": st.service_role_key, "Authorization": f"Bearer {st.service_role_key}", "Content-Type": "application/json"}
    base = f"{st.supabase_url}/rest/v1"
    posts = {p["id"]: p for p in httpx.get(f"{base}/public_social_posts", headers=h, params={
        "select": "id,post_title,document_title,post_text,hashtags,search_query", "limit": "5000"}, timeout=60).json()}
    comments = httpx.get(f"{base}/public_social_comments", headers=h, params={
        "select": "id,post_id,comment_text,lead_type,is_post_author,account_type", "limit": "10000"}, timeout=60).json()
    changes = collections.Counter()
    for c in comments:
        p = posts.get(c["post_id"]) or {}
        ctx = PostContext(" ".join(filter(None, [p.get("post_title"), p.get("document_title"), p.get("post_text"),
                                                 " ".join(p.get("hashtags") or [])])), search_query=p.get("search_query") or "")
        L = classify_comment(c["comment_text"], ctx, intent=score_comment(c["comment_text"]),
                             is_post_author=bool(c.get("is_post_author")), is_business=c.get("account_type") == "business")
        # only correct over-confident buyers; never revive comments demoted for other reasons (e.g. too old)
        if c["lead_type"] == "confirmed_rx300_buyer" and L.lead_type != c["lead_type"]:
            changes[(c["lead_type"], L.lead_type)] += 1
            if not a.dry_run:
                httpx.patch(f"{base}/public_social_comments", headers=h, params={"id": f"eq.{c['id']}"}, json={
                    "lead_type": L.lead_type, "lead_reasons": L.reasons + ["reclassified"], "lead_confidence": L.confidence,
                    "lead_needs_review": L.needs_review, "lead_version": L.version, "rx300_context": L.rx300_context,
                    "rx300_mentioned": L.rx300_mentioned}, timeout=30)
    for (old, new), n in sorted(changes.items(), key=lambda x: -x[1]):
        print(f"{n:4d}  {old} → {new}")
    print(("would change" if a.dry_run else "changed"), sum(changes.values()), "of", len(comments))
    return 0


if __name__ == "__main__":
    sys.exit(main())
