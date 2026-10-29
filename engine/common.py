"""設定・データ読み込みと記事ファイルの共通処理。"""
import csv
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "content" / "posts"
EXPERIENCE_DIR = ROOT / "data" / "experience"
KEYWORDS_CSV = ROOT / "data" / "keywords.csv"

# {{offer:slug}} 紹介ボックス / {{offer-table:category}} 比較表 / {{post:slug}} 内部リンク
SHORTCODE_RE = re.compile(r"\{\{(offer|offer-table|post):([a-z0-9-]+)\}\}")
FRONTMATTER_RE = re.compile(r"\A\s*---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)


def load_config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_offers():
    offers = yaml.safe_load((ROOT / "data" / "offers.yaml").read_text(encoding="utf-8")) or []
    return {o["slug"]: o for o in offers}


def read_keywords():
    with KEYWORDS_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_keywords(rows):
    with KEYWORDS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_post(text):
    """frontmatter 付き Markdown を (meta, body) に分ける。frontmatter がなければ None。"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, m.group(2).strip()


def dump_post(meta, body):
    fm = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{fm}\n---\n\n{body}\n"


def list_posts():
    """公開対象（draft でない）記事の meta 一覧。"""
    metas = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        parsed = parse_post(path.read_text(encoding="utf-8"))
        if parsed and not parsed[0].get("draft"):
            metas.append(parsed[0])
    return metas


def read_experience(category):
    """共通メモ＋カテゴリ別メモを、コメントと未記入の（例）行を除いて返す。"""
    texts = []
    for name in ("common", category):
        path = EXPERIENCE_DIR / f"{name}.md"
        if path.exists():
            text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
            lines = [ln for ln in text.splitlines() if "（例）" not in ln]
            texts.append("\n".join(lines))
    # 見出ししか残っていない＝体験が未記入
    body = "\n".join(texts)
    if not re.sub(r"^#.*$", "", body, flags=re.M).strip():
        return ""
    return body.strip()


def unknown_shortcodes(body, offers, post_slugs):
    """記事中のショートコードのうち、参照先が存在しないものを返す。"""
    categories = {o["category"] for o in offers.values()}
    valid = {"offer": offers.keys(), "offer-table": categories, "post": post_slugs}
    return [f"{{{{{kind}:{key}}}}}" for kind, key in SHORTCODE_RE.findall(body)
            if key not in valid[kind]]
