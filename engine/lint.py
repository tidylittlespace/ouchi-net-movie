"""記事の文章ルールを自動検査する（prompts/system.md と CLAUDE.md のルールのうち、機械で判定できるもの）。

公開記事のエラーはビルドを止める。下書き（draft: true）は警告にとどめる。
単独実行: python -m engine.lint
"""
from __future__ import annotations

import re
import sys

from engine.common import POSTS_DIR, ROOT, parse_post

DRAFTS_DIR = ROOT / "drafts"  # 公開しない下書き置き場（.gitignore 済み）

BANNED_PHRASES = [
    "確実に効いてきます", "身をもって", "ぐっと上がります", "欠かせません",
    "間違いなく", "しっかり", "が大切です", "といえるでしょう",
]
PLACEHOLDERS = ["○", "運営者名", "example.com", "TODO", "（例）"]

CODE_BLOCK_RE = re.compile(r"```.*?```", re.S)
SHORTCODE_LINE_RE = re.compile(r"^\{\{[^}]*\}\}\s*$", re.M)
KANJI_NUM = "一二三四五六七八九十"
KANJI_ORDINAL_RE = re.compile(rf"[{KANJI_NUM}](?:作目|作とも|作の違い)|前の[{KANJI_NUM}]作")
# 「!」の直後に文が続くなら、半角スペースを1つ空ける。「」」「?」などが続く場合は不要。
BANG_NO_SPACE_RE = re.compile(r"!(?![\s!?」』）)*|]|$)")


def _plain(body: str) -> str:
    return SHORTCODE_LINE_RE.sub("", CODE_BLOCK_RE.sub("", body))


def lint_post(meta: dict, body: str) -> list[str]:
    problems: list[str] = []
    text = _plain(body)

    for phrase in BANNED_PHRASES:
        if phrase in text:
            problems.append(f"禁止表現「{phrase}」")
    if "筆者" in text:
        problems.append("「筆者」は使わない（一人称は「私」）")
    for ph in PLACEHOLDERS:
        if ph in text:
            problems.append(f"仮の値「{ph}」が残っている")
    for m in KANJI_ORDINAL_RE.finditer(text):
        problems.append(f"算用数字にする: 「{m.group(0)}」")
    for line in text.splitlines():
        if BANG_NO_SPACE_RE.search(line):
            problems.append(f"「!」の直後に半角スペースがない: {line.strip()[:30]}…")
    if not meta.get("review_notes"):
        problems.append("review_notes が空（要確認事項か、確認済みの記録を書く）")
    for key in ("title", "description", "slug"):
        if not meta.get(key):
            problems.append(f"frontmatter に {key} がない")
    return problems


def lint_all() -> tuple[list[str], list[str]]:
    """(errors, warnings) を返す。公開記事の問題は errors、下書きの問題は warnings。"""
    errors, warnings = [], []
    paths = [(p, False) for p in sorted(POSTS_DIR.glob("*.md"))]
    paths += [(p, True) for p in sorted(DRAFTS_DIR.glob("*.md"))] if DRAFTS_DIR.exists() else []
    for path, in_drafts in paths:
        parsed = parse_post(path.read_text(encoding="utf-8"))
        if not parsed:
            continue
        meta, body = parsed
        target = warnings if (in_drafts or meta.get("draft")) else errors
        target.extend(f"{path.name}: {p}" for p in lint_post(meta, body))
    return errors, warnings


def main() -> int:
    errors, warnings = lint_all()
    for w in warnings:
        print(f"警告（下書き） {w}")
    for e in errors:
        print(f"エラー {e}", file=sys.stderr)
    print(f"lint: エラー {len(errors)} 件、警告 {len(warnings)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
