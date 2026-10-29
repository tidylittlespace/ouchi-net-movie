"""keywords.csv の未処理キーワードから記事を生成し content/posts/ に保存する。

  python -m engine.generate            # config の articles_per_run 件を生成
  python -m engine.generate -n 1       # 件数指定
  python -m engine.generate --dry-run  # API を呼ばずにダミー記事で動作確認
"""
import argparse
import datetime as dt
import hashlib
import re
import sys
from string import Template

import anthropic

from engine.common import (
    POSTS_DIR, ROOT, dump_post, list_posts, load_config, load_offers, parse_post,
    read_experience, read_keywords, unknown_shortcodes, write_keywords,
)

MAX_LINK_CANDIDATES = 40

REVIEW_SUMMARY = ROOT / ".review_summary.md"


def pick_keywords(rows, n):
    pending = [r for r in rows if r["status"] == "pending"]
    pending.sort(key=lambda r: int(r["priority"] or 0), reverse=True)
    return pending[:n]


def build_system_prompt(cfg, offers):
    offer_list = "\n".join(
        f"- {o['slug']}（カテゴリ: {o['category']}）{o['name']} … {o['catch']} / 特徴: {'、'.join(o['points'])}"
        for o in offers.values()
    )
    tpl = Template((ROOT / "prompts" / "system.md").read_text(encoding="utf-8"))
    return tpl.substitute(
        site_name=cfg["site"]["name"],
        site_description=cfg["site"]["description"],
        author_name=cfg["author"]["name"],
        author_profile=cfg["author"]["profile"],
        offer_list=offer_list,
    )


def build_user_prompt(kw, min_chars, posts):
    # 同じカテゴリの記事を優先して内部リンク候補にする
    posts = sorted(posts, key=lambda p: p.get("category") != kw["category"])[:MAX_LINK_CANDIDATES]
    link_list = "\n".join(f"- {{{{post:{p['slug']}}}}} {p['title']}" for p in posts) or "（まだなし）"
    return (
        f"検索キーワード: {kw['keyword']}\n"
        f"検索意図: {kw['intent']}\n"
        f"主に紹介するカテゴリ: {kw['category']}\n"
        f"本文の目安: {min_chars} 文字以上\n\n"
        f"内部リンクに使える既存記事:\n{link_list}\n\n"
        f"運営者の体験メモ:\n{read_experience(kw['category']) or '（なし）'}"
    )


def call_claude(client, cfg, system, user):
    gen = cfg["generation"]
    with client.beta.messages.stream(
        model=gen["model"],
        max_tokens=gen["max_tokens"],
        output_config={"effort": gen["effort"]},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("モデルが生成を辞退しました")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("max_tokens に達して途中で切れました")
    return "".join(b.text for b in msg.content if b.type == "text")


def dummy_article(kw, posts):
    link = f"関連: {{{{post:{posts[0]['slug']}}}}}\n\n" if posts else ""
    body = (
        f"## 結論\n\n{kw['keyword']} の結論を最初に書きます。\n\n{link}"
        f"{{{{offer-table:{kw['category']}}}}}\n\n## 手順\n\n"
        "```mermaid\nflowchart LR\n  A[\"申し込み\"] --> B[\"工事日の調整\"] --> C[\"開通\"]\n```\n\n"
        "## 選び方\n\n" + "ダミー本文。" * 700
    )
    first_offer = next(o for o in load_offers().values() if o["category"] == kw["category"])
    body += f"\n\n{{{{offer:{first_offer['slug']}}}}}\n"
    return dump_post(
        {"title": f"【ダミー】{kw['keyword']}", "description": "ダミー記事です。",
         "slug": "", "review_notes": ["要確認: ダミー"]},
        body,
    )


def make_slug(meta_slug, keyword):
    slug = (meta_slug or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        slug = "post-" + hashlib.sha1(keyword.encode()).hexdigest()[:8]
    base, n = slug, 2
    while (POSTS_DIR / f"{slug}.md").exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    offers = load_offers()
    rows = read_keywords()
    targets = pick_keywords(rows, args.n or cfg["generation"]["articles_per_run"])
    if not targets:
        print("未処理キーワードがありません。data/keywords.csv に追加してください。")
        return 0

    client = None if args.dry_run else anthropic.Anthropic()
    system = build_system_prompt(cfg, offers)
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    summary, failures = [], 0

    for kw in targets:
        print(f"生成中: {kw['keyword']}")
        posts = list_posts()
        try:
            raw = dummy_article(kw, posts) if args.dry_run else call_claude(
                client, cfg, system, build_user_prompt(kw, cfg["generation"]["min_chars"], posts))
        except (anthropic.APIError, RuntimeError) as e:
            print(f"  失敗: {e}", file=sys.stderr)
            failures += 1
            continue

        parsed = parse_post(raw)
        if not parsed:
            print("  失敗: frontmatter を解析できません", file=sys.stderr)
            failures += 1
            continue
        meta, body = parsed

        problems = []
        if len(body) < cfg["generation"]["min_chars"]:
            problems.append(f"本文が短すぎます（{len(body)} 文字）")
        if bad := unknown_shortcodes(body, offers, {p["slug"] for p in posts}):
            problems.append(f"存在しない案件・記事を参照: {', '.join(bad)}")
        if problems:
            print("  不合格: " + " / ".join(problems), file=sys.stderr)
            failures += 1
            continue

        slug = make_slug(meta.get("slug"), kw["keyword"])
        meta.update(slug=slug, date=dt.date.today().isoformat(),
                    category=kw["category"], keyword=kw["keyword"])
        (POSTS_DIR / f"{slug}.md").write_text(dump_post(meta, body), encoding="utf-8")
        kw.update(status="generated", slug=slug, generated_at=meta["date"])
        print(f"  保存: content/posts/{slug}.md（{len(body)} 文字）")

        notes = meta.get("review_notes") or ["（なし）"]
        summary.append(f"### {meta['title']}\n`content/posts/{slug}.md`\n" +
                       "\n".join(f"- [ ] {n}" for n in notes))

    write_keywords(rows)
    if summary:
        REVIEW_SUMMARY.write_text(
            "公開前に以下の要確認事項をチェックしてください。\n\n" + "\n\n".join(summary) + "\n",
            encoding="utf-8")
    print(f"完了: 成功 {len(summary)} / 失敗 {failures}")
    return 1 if failures and not summary else 0


if __name__ == "__main__":
    sys.exit(main())
