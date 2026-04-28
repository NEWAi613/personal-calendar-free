#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CITY = "北京海淀"
LAT = 39.9593
LON = 116.2985
TZ = "Asia/Shanghai"
OUT = Path(__file__).resolve().parent / "calendar.ics"
TODAY = date.today()
WEATHER_DAYS = 7

CN_HOLIDAYS_FIXED = {"01-01": "元旦", "05-01": "劳动节", "10-01": "国庆节"}
CN_HOLIDAYS_2026 = {
    "2026-02-17": "春节",
    "2026-04-05": "清明节",
    "2026-06-19": "端午节",
    "2026-09-25": "中秋节",
}

FALLBACK_AI = [
    {"title": "AI 热点暂未拉取到实时新闻，建议关注 OpenAI、Claude、Gemini、DeepSeek、国内大模型更新", "url": ""},
]
FALLBACK_ENTERTAINMENT = [
    {"title": "影视热点暂未拉取到实时新闻，建议关注院线新片、平台新剧、国漫/日漫更新和热榜口碑变化", "url": ""},
]


def fetch_json(url: str, timeout: int = 15, retries: int = 3) -> dict:
    last_error = None
    for _ in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "personal-calendar-free/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_error = e
    raise last_error


def clean_text(text: str, max_len: int = 90) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].rstrip() + ("…" if len(text) > max_len else "")


def fetch_page_summary(url: str, title: str = "", max_len: int = 150) -> str:
    if not url:
        return ""
    # Google News 中转页经常不直接给正文，RSS snippet 会作为兜底。
    if "news.google.com/rss/articles" in url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 personal-calendar-free/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            ctype = str(resp.headers.get("content-type") or "").lower()
            if "text/html" not in ctype and "application/xhtml" not in ctype:
                return ""
            raw = resp.read(350_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    meta_patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ]
    for pat in meta_patterns:
        m = re.search(pat, raw, flags=re.I)
        if m:
            summary = clean_text(m.group(1), max_len)
            if summary and summary not in title:
                return summary

    paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", raw, flags=re.I)
    cleaned = [clean_text(p, 220) for p in paragraphs]
    cleaned = [p for p in cleaned if len(p) >= 35 and p not in title]
    if cleaned:
        return clean_text(" ".join(cleaned[:2]), max_len)
    return ""


def google_news_articles(query: str, max_records: int = 8) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "zh-CN",
        "gl": "CN",
        "ceid": "CN:zh-Hans",
    })
    url = f"https://news.google.com/rss/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 personal-calendar-free/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_text = resp.read().decode("utf-8", errors="ignore")
        root = ET.fromstring(xml_text)
    except Exception:
        return []
    rows = []
    seen = set()
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"), 90)
        link = str(item.findtext("link") or "")
        source = clean_text(item.findtext("source") or "Google News", 24)
        snippet = clean_text(item.findtext("description"), 150)
        if not title or title in seen:
            continue
        seen.add(title)
        rows.append({"title": title, "url": link, "source": source, "summary": snippet})
        if len(rows) >= max_records:
            break
    return rows


def gdelt_articles(query: str, max_records: int = 8) -> list[dict]:
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "sort": "HybridRel",
        "timespan": "24h",
    })
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?{params}"
    try:
        data = fetch_json(url, timeout=20, retries=4)
    except Exception:
        return []
    rows = []
    seen = set()
    for item in data.get("articles", []) or []:
        title = clean_text(item.get("title"), 80)
        link = str(item.get("url") or "")
        if not title or title in seen:
            continue
        seen.add(title)
        source = clean_text(item.get("sourceCommonName") or item.get("domain") or "", 24)
        snippet = clean_text(item.get("seendate") or item.get("language") or "", 80)
        rows.append({"title": title, "url": link, "source": source, "summary": snippet})
    return rows


def hn_ai_articles(max_records: int = 6) -> list[dict]:
    cutoff = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    rows = []
    seen = set()
    for keyword in ["AI", "OpenAI", "ChatGPT", "Claude", "Gemini", "DeepSeek"]:
        params = urllib.parse.urlencode({
            "query": keyword,
            "tags": "story",
            "numericFilters": f"created_at_i>{cutoff}",
            "hitsPerPage": 4,
        })
        try:
            data = fetch_json(f"https://hn.algolia.com/api/v1/search_by_date?{params}", timeout=15, retries=2)
        except Exception:
            continue
        for hit in data.get("hits", []) or []:
            title = clean_text(hit.get("title") or hit.get("story_title"), 80)
            if not title or title in seen:
                continue
            seen.add(title)
            points = hit.get("points")
            comments = hit.get("num_comments")
            snippet = f"Hacker News 讨论热度：{points or 0} points，{comments or 0} comments"
            rows.append({"title": title, "url": hit.get("url") or hit.get("story_url") or "", "source": "Hacker News", "summary": snippet})
            if len(rows) >= max_records:
                return rows
    return rows


def tvmaze_updates(max_records: int = 6) -> list[dict]:
    rows = []
    seen = set()
    for d in [TODAY, TODAY - timedelta(days=1)]:
        try:
            data = fetch_json(f"https://api.tvmaze.com/schedule/web?date={d.isoformat()}", timeout=15, retries=2)
        except Exception:
            continue
        for item in data or []:
            show = item.get("_embedded", {}).get("show", {}) if isinstance(item, dict) else {}
            name = clean_text(show.get("name") or item.get("name"), 60)
            if not name or name in seen:
                continue
            seen.add(name)
            season = item.get("season")
            number = item.get("number")
            episode = clean_text(item.get("name"), 40)
            label = f"{name} 更新"
            if season and number:
                label += f" S{season}E{number}"
            if episode and episode != name:
                label += f"：{episode}"
            genres = "、".join(show.get("genres") or [])
            network = (show.get("webChannel") or show.get("network") or {}).get("name") if isinstance(show, dict) else ""
            snippet_parts = []
            if genres:
                snippet_parts.append(f"类型：{genres}")
            if network:
                snippet_parts.append(f"平台：{network}")
            if item.get("airdate"):
                snippet_parts.append(f"更新日期：{item.get('airdate')}")
            rows.append({"title": label, "url": show.get("url") or item.get("url") or "", "source": "TVMaze", "summary": "；".join(snippet_parts)})
            if len(rows) >= max_records:
                return rows
    return rows


def ai_hotspots() -> list[dict]:
    # Google News 中文热点 + GDELT + Hacker News，多源兜底，优先当天/过去 24 小时。
    rows = google_news_articles('AI OR 人工智能 OR 大模型 OR OpenAI OR ChatGPT OR Claude OR Gemini OR DeepSeek when:1d', max_records=8)
    query = '(AI OR OpenAI OR ChatGPT OR Claude OR Gemini OR DeepSeek)'
    if len(rows) < 4:
        rows.extend(gdelt_articles(query, max_records=8 - len(rows)))
    if len(rows) < 6:
        rows.extend(hn_ai_articles(max_records=8 - len(rows)))
    unique = []
    seen = set()
    for row in rows:
        title = row.get("title")
        if title and title not in seen:
            unique.append(row)
            seen.add(title)
    return unique[:8] or FALLBACK_AI


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def entertainment_hotspots() -> list[dict]:
    # 影视优先走中文热点，分别抓电影、电视剧、动漫，避免泛娱乐新闻混进来。
    rows = []
    for q in ['电影 新片 上映 when:1d', '电视剧 新剧 热播 when:1d', '动漫 国漫 日漫 更新 when:1d']:
        rows.extend([
            r for r in google_news_articles(q, max_records=8)
            if has_cjk(r.get("title")) and has_cjk(r.get("source"))
        ][:3])
    query = '(movie OR film OR anime OR Netflix OR Disney OR HBO)'
    if len(rows) < 4:
        rows.extend(gdelt_articles(query, max_records=8 - len(rows)))
    if len(rows) < 6:
        rows.extend(tvmaze_updates(max_records=8 - len(rows)))
    unique = []
    seen = set()
    for row in rows:
        title = row.get("title")
        if title and title not in seen:
            unique.append(row)
            seen.add(title)
    return unique[:8] or FALLBACK_ENTERTAINMENT


def weather_code_text(code: int) -> str:
    table = {
        0: "晴", 1: "大部晴朗", 2: "局部多云", 3: "阴",
        45: "有雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨", 55: "较强毛毛雨",
        61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 81: "较强阵雨", 82: "强阵雨", 95: "雷暴",
    }
    return table.get(int(code), f"天气代码{code}")


def clothing_tip(tmax: float, tmin: float, code: int) -> str:
    rain_codes = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95}
    if tmax >= 28:
        base = "短袖/轻薄透气，注意防晒"
    elif tmax >= 22:
        base = "长袖或薄外套，早晚看体感"
    elif tmax >= 15:
        base = "卫衣/薄外套，早晚偏凉"
    elif tmax >= 8:
        base = "厚外套/毛衣，注意保暖"
    else:
        base = "羽绒服/厚外套，重点保暖"
    if int(code) in rain_codes:
        base += "，带伞"
    if (tmax - tmin) >= 10:
        base += "，昼夜温差大"
    return base


def load_weather() -> list[dict]:
    params = urllib.parse.urlencode({
        "latitude": LAT,
        "longitude": LON,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": TZ,
        "forecast_days": WEATHER_DAYS,
    })
    data = fetch_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    daily = data.get("daily", {})
    rows = []
    for i, day in enumerate(daily.get("time", [])):
        code = int(daily.get("weather_code", [0])[i])
        tmax = float(daily.get("temperature_2m_max", [0])[i])
        tmin = float(daily.get("temperature_2m_min", [0])[i])
        rain = daily.get("precipitation_probability_max", [None])[i]
        tip = clothing_tip(tmax, tmin, code)
        rows.append({
            "date": date.fromisoformat(day),
            "summary": f"{CITY}天气：{weather_code_text(code)} {tmin:.0f}-{tmax:.0f}℃｜穿衣：{tip}",
            "description": f"天气：{weather_code_text(code)}\n温度：{tmin:.0f}-{tmax:.0f}℃\n穿衣推荐：{tip}\n降水概率：{rain if rain is not None else '-'}%\n数据源：Open-Meteo",
        })
    return rows


def esc(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    if len(line.encode("utf-8")) <= 73:
        return line
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 73:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def uid(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest() + "@personal-calendar-free"


def vevent(day: date, summary: str, description: str, hour: int = 9) -> str:
    start = datetime(day.year, day.month, day.day, hour, 0, 0)
    end = start + timedelta(minutes=30)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid(day.isoformat() + summary)}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID={TZ}:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={TZ}:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(description)}",
        "END:VEVENT",
    ]
    return "\r\n".join(fold(x) for x in lines)


def holiday_events(start: date, days: int) -> list[str]:
    events = []
    for i in range(days):
        d = start + timedelta(days=i)
        name = CN_HOLIDAYS_FIXED.get(d.strftime("%m-%d")) or CN_HOLIDAYS_2026.get(d.isoformat())
        if name:
            events.append(vevent(d, f"节假日：{name}", "中国节假日提醒", 8))
    return events


def title_takeaway(title: str, source: str = "", max_len: int = 150) -> str:
    text = clean_text(title, max_len)
    if source:
        text = re.sub(rf"\s*-\s*{re.escape(source)}\s*$", "", text).strip()
    if not text.endswith(("。", "！", "？", ".", "!", "?")):
        text += "。"
    return text


def enrich_article_summaries(items: list[dict], max_items: int = 5) -> list[dict]:
    enriched = []
    for item in items[:max_items]:
        row = dict(item)
        title = row.get("title", "")
        source = row.get("source", "")
        summary = clean_text(row.get("summary"), 150)
        # RSS 自带摘要不够可读时，再尝试读取原网页 meta description / 正文段落。
        if (not summary or len(summary) < 35 or summary.lower() in {"english", "chinese"}) and row.get("url"):
            summary = fetch_page_summary(row.get("url"), title, 150)
        # 仍然拿不到正文时，不展示“失败”，直接把标题改写成可读看点，避免日历里堆网址。
        if not summary or summary == title or summary in title:
            summary = title_takeaway(title, source, 150)
        row["summary"] = summary
        enriched.append(row)
    return enriched


def article_lines(items: list[dict], limit: int = 5) -> str:
    lines = []
    for idx, item in enumerate(enrich_article_summaries(items, limit), 1):
        source = f"｜来源：{item.get('source')}" if item.get("source") else ""
        # Apple Calendar 里长链接很影响阅读，默认不堆 URL，只展示可读摘要。
        lines.append(f"{idx}. {item.get('title')}\n   看点：{item.get('summary')}{source}")
    return "\n\n".join(lines)


def today_hotspot_events() -> list[str]:
    ai_items = ai_hotspots()
    video_items = entertainment_hotspots()
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        vevent(
            TODAY,
            f"AI 24小时热点：{clean_text(ai_items[0].get('title'), 34)}",
            f"过去24小时 AI 热点推荐，生成时间：{generated}\n\n{article_lines(ai_items)}",
            9,
        ),
        vevent(
            TODAY,
            f"影视24小时推荐：{clean_text(video_items[0].get('title'), 34)}",
            f"过去24小时影视/电视剧/电影/动漫热点推荐，生成时间：{generated}\n\n{article_lines(video_items)}",
            20,
        ),
    ]


def build() -> str:
    events = []
    try:
        for row in load_weather():
            events.append(vevent(row["date"], row["summary"], row["description"], 7))
    except Exception as e:
        events.append(vevent(TODAY, "天气更新失败", f"Open-Meteo 拉取失败：{e}", 7))
    events.extend(holiday_events(TODAY, 120))
    events.extend(today_hotspot_events())
    body = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//NEWAi613//Personal Calendar Feed//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:北京海淀生活提醒",
        f"X-WR-TIMEZONE:{TZ}",
        *events,
        "END:VCALENDAR",
    ]
    return "\r\n".join(body) + "\r\n"


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"Wrote {OUT}")
