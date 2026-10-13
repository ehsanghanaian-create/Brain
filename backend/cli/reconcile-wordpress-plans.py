"""Read-only preview by default; --apply imports live WordPress posts into Content Brain.

This command never writes to WordPress. It creates an online SQLite backup before
any SEO Brain write, and refuses unexpected plan counts.
"""
from __future__ import annotations

import argparse

from seo_brain.brain.planner.wordpress_reconcile import action_counts, apply_with_backup, live_actions
from seo_brain.brain.content import ContentService
from seo_brain.db.engine import get_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-published", type=int)
    parser.add_argument("--expect-brief", type=int)
    parser.add_argument("--expect-linked-published", type=int)
    args = parser.parse_args()
    engine = get_engine()
    actions, post_count = live_actions(engine, args.site)
    counts = action_counts(actions)
    print({"site": args.site, "wordpress_posts": post_count, "actions": counts, "mode": "apply" if args.apply else "preview"})
    if not args.apply:
        return
    if any(value is None for value in (args.expect_published, args.expect_brief, args.expect_linked_published)):
        raise SystemExit("--apply requires all three expected counts")
    expected = {"published": args.expect_published, "brief": args.expect_brief,
                "linked_published": args.expect_linked_published}
    if any(counts.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"Preview counts changed: expected {expected}; found {counts}")
    print(apply_with_backup(engine, args.site, actions))
    # Imported articles must appear in the operational graph immediately. This
    # is idempotent, so rerunning --apply also repairs an interrupted graph sync.
    print({"content_graph": ContentService(engine).sync_graph(args.site)})


if __name__ == "__main__":
    main()
