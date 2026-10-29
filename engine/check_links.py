"""案件リンクの死活と終了日をチェックする。問題があれば終了コード 1。

  python -m engine.check_links
"""
import datetime as dt
import sys
import urllib.error
import urllib.request

from engine.common import load_offers

UA = "Mozilla/5.0 (compatible; affiliate-link-checker/1.0)"


def check(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, res.url
    except urllib.error.HTTPError as e:
        return e.code, url
    except (urllib.error.URLError, TimeoutError) as e:
        return None, str(e)


def main():
    today = dt.date.today().isoformat()
    problems = []
    for o in load_offers().values():
        if o.get("end_date") and o["end_date"] < today:
            problems.append(f"{o['slug']}: 案件終了日 {o['end_date']} を過ぎています")
        status, final = check(o["url"])
        if status is None or status >= 400:
            problems.append(f"{o['slug']}: リンク異常 status={status} ({final})")
        else:
            print(f"OK  {o['slug']}  {status}")
    for p in problems:
        print(f"NG  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
