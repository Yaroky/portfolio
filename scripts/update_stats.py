"""Собирает число подписчиков из соцсетей и пишет stats.json для страницы /links.

Запускается раз в день из GitHub Actions. Если соцсеть не ответила или поменяла
разметку, остаётся прошлое число: страница никогда не покажет ноль.
Файл перезаписывается, только когда меняется округлённая подпись (5к+, 80+),
чтобы не плодить коммиты каждый день.
"""
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "stats.json"
# Ролики на /links: их просмотры собираются вместе с подписчиками.
# Просмотры рилсов Instagram без входа недоступны, они вписаны в links.html вручную
SHORTS = ["v6yxLOy_-Cs", "zNzwDKlmW8c", "Yr-RgcI3F-4"]
TIKTOK_VIDEOS = ["7698254210139294990", "7698613052366687501", "7698602476861263118"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def get(url, headers=None, data=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def num(text):
    """'2,602' / '1 234' / '2.6K' / '1.2M' -> int"""
    t = text.strip().replace(" ", "").replace(" ", "").replace(",", "")
    m = re.match(r"([\d.]+)([KkMm]?)", t)
    if not m:
        raise ValueError(text)
    v = float(m.group(1))
    v *= {"k": 1e3, "m": 1e6}.get(m.group(2).lower(), 1)
    return int(v)


def telegram():
    s = get("https://t.me/YarokyChannel")
    return {"followers": num(re.search(r'tgme_page_extra">([\d\s,]+) subscribers', s).group(1))}


def youtube():
    s = get("https://www.youtube.com/@yaroslav.alekhno", {"Cookie": "SOCS=CAI"})
    m = re.search(r'([\d.,]+[KM]?) subscribers', s)
    out = {"followers": num(m.group(1))}
    # Просмотры шортсов, которые показаны на /links
    s = get("https://www.youtube.com/@yaroslav.alekhno/shorts", {"Cookie": "SOCS=CAI"})
    for vid in SHORTS:
        i = s.find('"videoId":"%s"' % vid)
        v = re.search(r'"secondaryText":\{"content":"([\d.,]+[KM]?) views', s[i:i + 8000]) if i >= 0 else None
        if v:
            out[vid] = num(v.group(1))
    return out


def tiktok():
    s = get("https://www.tiktok.com/@yaroslav.alekhno")
    pick = lambda k: int(re.search(r'"%s":(\d+)' % k, s).group(1))
    out = {"followers": pick("followerCount"), "likes": pick("heartCount"), "videos": pick("videoCount")}
    # Просмотры роликов, показанных на /links
    for vid in TIKTOK_VIDEOS:
        try:
            v = get("https://www.tiktok.com/@yaroslav.alekhno/video/" + vid)
            out[vid] = int(re.search(r'"playCount":(\d+)', v).group(1))
        except Exception:
            pass
    return out


def twitch():
    q = '{"query":"{user(login:\\"yar0ky\\"){followers{totalCount}}}"}'
    s = get("https://gql.twitch.tv/gql",
            {"Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko", "Content-Type": "application/json"},
            q.encode())
    return {"followers": json.loads(s)["data"]["user"]["followers"]["totalCount"]}


def instagram():
    # С полным браузерным User-Agent Instagram отдаёт страницу без счётчика
    s = get("https://www.instagram.com/yaroslav.alekhno/", {"User-Agent": "Mozilla/5.0"})
    m = re.search(r'content="([\d.,]+[KM]?) Followers, [\d.,]+[KM]? Following, ([\d.,]+[KM]?) Posts', s)
    return {"followers": num(m.group(1)), "posts": num(m.group(2))}


def label(n):
    """Та же логика, что в links.html: 87 -> 80+, 640 -> 600+, 5924 -> 5к+"""
    if n < 10:
        return str(n)
    if n < 1000:
        step = 10 if n < 100 else 100
        return f"{n // step * step}+"
    if n < 1_000_000:
        return f"{n // 1000}к+"
    return f"{n // 1_000_000}м+"


def labels(d):
    return {f"{k}.{f}": label(v) for k, fs in d.items() if isinstance(fs, dict) for f, v in fs.items()}


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    new = {k: dict(v) for k, v in old.items() if isinstance(v, dict)}
    for name, fn in [("telegram", telegram), ("youtube", youtube), ("tiktok", tiktok),
                     ("twitch", twitch), ("instagram", instagram)]:
        try:
            got = fn()
            # Ноль почти всегда значит, что страница отдала заглушку: не верим
            if any(v <= 0 for v in got.values()):
                raise ValueError(got)
            new.setdefault(name, {}).update(got)
            print(f"{name}: {got}")
        except Exception as e:  # соцсеть не ответила — оставляем прошлое значение
            print(f"{name}: пропуск ({type(e).__name__}: {e})", file=sys.stderr)
    if labels(new) == labels(old):
        print("Подписи не изменились, файл не трогаю")
        return
    new["updated"] = date.today().isoformat()
    OUT.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("stats.json обновлён")


if __name__ == "__main__":
    main()
