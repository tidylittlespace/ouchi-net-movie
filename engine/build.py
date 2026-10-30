"""content/posts/*.md から静的サイトを public/ に生成する。

  python -m engine.build
"""
import datetime as dt
import html
import re
import shutil
import sys
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader

from engine.lint import lint_all
from engine.common import (
    POSTS_DIR, ROOT, SHORTCODE_RE, load_config, load_offers, parse_post, unknown_shortcodes,
)

OUT = ROOT / "public"
MERMAID_RE = re.compile(r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.S)


def offer_link(offer, label):
    return (f'<a class="cta" href="{html.escape(offer["url"])}" rel="sponsored noopener" '
            f'target="_blank" data-offer="{offer["slug"]}">{label}</a>')


def render_offer_box(offer):
    # banner_html は ASP の広告コードをそのまま使う（改変すると規約違反・計測漏れになるため）
    banner = f'<div class="offer-banner">{offer["banner_html"]}</div>' if offer.get("banner_html") else ""
    points = "".join(f"<li>{html.escape(p)}</li>" for p in offer["points"])
    return (f'<div class="offer">{banner}<div class="offer-name">{html.escape(offer["name"])}</div>'
            f'<div class="offer-catch">{html.escape(offer["catch"])}</div><ul>{points}</ul>'
            f'{offer_link(offer, "公式サイトを見る")}<div class="pr">PR</div></div>')


def render_offer_table(offers, category):
    rows = "".join(
        f'<tr><td>{html.escape(o["name"])}</td><td>{html.escape(o["catch"])}</td>'
        f'<td>{offer_link(o, "詳細")}</td></tr>'
        for o in offers.values() if o["category"] == category)
    return ('<div class="table-wrap"><table class="offer-table"><thead><tr><th>サービス</th>'
            f'<th>特徴</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>')


EMPTY_SECTION_RE = re.compile(r"^##+ [^\n]*\n+(?=^##+ |\Z)", re.M)


def expand_shortcodes(body, offers, titles, base, show_offers=True):
    def repl(m):
        kind, key = m.groups()
        if kind == "post":
            return f'<a class="internal" href="{base}/posts/{key}/">{html.escape(titles[key])}</a>'
        if not show_offers:
            return ""
        block = render_offer_box(offers[key]) if kind == "offer" else render_offer_table(offers, key)
        return f"\n\n{block}\n\n"
    expanded = SHORTCODE_RE.sub(repl, body)
    return expanded if show_offers else EMPTY_SECTION_RE.sub("", expanded.rstrip() + "\n")


def load_posts(offers, base, show_offers=True):
    sources, errors = [], []
    for path in sorted(POSTS_DIR.glob("*.md")):
        parsed = parse_post(path.read_text(encoding="utf-8"))
        if not parsed:
            errors.append(f"{path.name}: frontmatter がありません")
        elif not parsed[0].get("draft"):
            sources.append((path.name, *parsed))
    titles = {meta["slug"]: meta["title"] for _, meta, _ in sources}

    posts = []
    for name, meta, body in sources:
        if bad := unknown_shortcodes(body, offers, titles.keys()):
            errors.append(f"{name}: 存在しない案件・記事 {', '.join(bad)}")
            continue
        md = markdown.Markdown(extensions=["tables", "toc", "fenced_code"],
                               extension_configs={"toc": {"toc_depth": "2-3"}})
        content = md.convert(expand_shortcodes(body, offers, titles, base, show_offers))
        content, n_diagrams = MERMAID_RE.subn(r'<pre class="mermaid">\1</pre>', content)
        posts.append({**meta, "date": str(meta.get("date", "")), "content": content,
                      "toc": md.toc, "has_mermaid": n_diagrams > 0,
                      "url": f"/posts/{meta['slug']}/"})
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts, errors


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    cfg = load_config()
    site = cfg["site"]
    base = ("/" + site["url"].split("://", 1)[-1].partition("/")[2].strip("/")).rstrip("/")
    show_offers = site.get("show_offers", True)
    lint_errors, lint_warnings = lint_all()
    for w in lint_warnings:
        print(f"警告（下書き） {w}")
    if lint_errors:
        print("文章ルール違反:" + chr(10) + "  " + (chr(10) + "  ").join(lint_errors), file=sys.stderr)
        return 1
    posts, errors = load_posts(load_offers(), base, show_offers)
    if errors:
        print("ビルドエラー:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    cats = cfg.get("categories", {})
    ctx = {"site": site, "author": cfg["author"], "disclosure": cfg["disclosure"],
           "post_disclosure": cfg["disclosure"] if show_offers else "",
           "base": base, "cats": cats, "year": dt.date.today().year}

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)

    write(OUT / "index.html", env.get_template("list.html").render(
        **ctx, posts=posts, heading="新着記事"))
    for cat in sorted({p["category"] for p in posts}):
        write(OUT / "category" / cat / "index.html", env.get_template("list.html").render(
            **ctx, posts=[p for p in posts if p["category"] == cat], heading=cats.get(cat, cat)))
    for p in posts:
        related = [q for q in posts if q["category"] == p["category"] and q is not p][:5]
        write(OUT / "posts" / p["slug"] / "index.html",
              env.get_template("post.html").render(**ctx, post=p, related=related))
    write(OUT / "about" / "index.html", env.get_template("about.html").render(**ctx))

    urls = ["/", "/about/"] + [p["url"] for p in posts]
    write(OUT / "sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"  <url><loc>{escape(site['url'] + u)}</loc></url>\n" for u in urls) +
          "</urlset>\n")
    write(OUT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n")
    write(OUT / "feed.xml", env.get_template("feed.xml").render(**ctx, posts=posts[:20]))

    print(f"ビルド完了: {len(posts)} 記事 → public/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
