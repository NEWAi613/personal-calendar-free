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

CN_HOLIDAYS_FIXED = {
    "01-01": "元旦",
    "03-08": "妇女节",
    "03-12": "植树节",
    "05-01": "劳动节",
    "05-04": "青年节",
    "06-01": "儿童节",
    "07-01": "建党节",
    "08-01": "建军节",
    "09-03": "中国人民抗日战争胜利纪念日",
    "09-10": "教师节",
    "09-30": "烈士纪念日",
    "10-01": "国庆节",
    "11-08": "记者节",
    "12-04": "国家宪法日",
    "12-13": "南京大屠杀死难者国家公祭日",
    "12-20": "澳门回归纪念日",
}
CN_HOLIDAYS_2026 = {
    "2026-01-26": "腊八节",
    "2026-02-10": "北方小年",
    "2026-02-11": "南方小年",
    "2026-02-16": "除夕",
    "2026-02-17": "春节",
    "2026-03-03": "元宵节",
    "2026-04-05": "清明节",
    "2026-06-19": "端午节",
    "2026-08-19": "七夕节",
    "2026-08-27": "中元节",
    "2026-09-25": "中秋节",
    "2026-10-18": "重阳节",
}

# 需要连续休假的节日合并成一个全天跨日期事件，避免每天重复标记。
HOLIDAY_RANGES_2026 = [
    ("2026-05-01", "2026-05-05", "劳动节假期"),
    ("2026-06-19", "2026-06-21", "端午节假期"),
    ("2026-09-25", "2026-09-27", "中秋节假期"),
    ("2026-10-01", "2026-10-07", "国庆节假期"),
    ("2027-01-01", "2027-01-03", "元旦假期"),
]

SOLAR_TERMS_2026 = {
    "2026-01-05": "小寒", "2026-01-20": "大寒",
    "2026-02-04": "立春", "2026-02-18": "雨水",
    "2026-03-05": "惊蛰", "2026-03-20": "春分",
    "2026-04-04": "清明", "2026-04-20": "谷雨",
    "2026-05-05": "立夏", "2026-05-21": "小满",
    "2026-06-05": "芒种", "2026-06-21": "夏至",
    "2026-07-07": "小暑", "2026-07-23": "大暑",
    "2026-08-07": "立秋", "2026-08-23": "处暑",
    "2026-09-07": "白露", "2026-09-23": "秋分",
    "2026-10-08": "寒露", "2026-10-23": "霜降",
    "2026-11-07": "立冬", "2026-11-22": "小雪",
    "2026-12-07": "大雪", "2026-12-22": "冬至",
}

SOLAR_TERM_TIPS = {
    "立春": "典故：立春为二十四节气之首，古代有迎春、鞭春牛的礼俗，寓意劝农开耕。",
    "雨水": "典故：雨水取“东风解冻，散而为雨”之意，民间常说春雨贵如油。",
    "惊蛰": "典故：惊蛰意为春雷惊醒蛰伏虫兽，古人认为这是万物复苏的节点。",
    "春分": "典故：春分昼夜平分，古代有竖蛋、祭日等习俗。",
    "清明": "典故：清明兼具节气与节日属性，既是踏青时节，也是慎终追远的扫墓日。",
    "谷雨": "典故：谷雨有“雨生百谷”之意，相传也与仓颉造字、谷子如雨相关。",
    "立夏": "典故：立夏表示夏季开始，民间有称人、吃立夏蛋等习俗。",
    "小满": "典故：小满指麦类等夏熟作物籽粒渐满但未全满，讲究“满而不盈”。",
    "芒种": "典故：芒种意为有芒作物可收、有芒作物可种，是农忙节气。",
    "夏至": "典故：夏至白昼最长，古代既祭地，也有吃面、消夏的习俗。",
    "小暑": "典故：小暑意为暑气初盛，民间常有食新、晒伏等习俗。",
    "大暑": "典故：大暑是一年暑热最盛之时，民间讲究饮伏茶、晒伏姜。",
    "立秋": "典故：立秋标志秋季开启，民间有贴秋膘、啃秋等习俗。",
    "处暑": "典故：处暑意为暑气到此而止，民间有出游迎秋、放河灯等传统。",
    "白露": "典故：白露因夜间水汽凝成露珠而得名，古语说“白露身不露”。",
    "秋分": "典故：秋分昼夜再度平分，也是中国农民丰收节所在节气。",
    "寒露": "典故：寒露比白露更冷，露水将凝成霜，民间有登高、赏菊习俗。",
    "霜降": "典故：霜降是秋季最后一个节气，古人重视补冬前的进补。",
    "立冬": "典故：立冬为冬季开始，民间有补冬、吃饺子的习俗。",
    "小雪": "典故：小雪表示降雪渐起但未盛，北方常有腌菜、腌肉习俗。",
    "大雪": "典故：大雪表示雪量增多、仲冬开始，民间讲究进补御寒。",
    "冬至": "典故：冬至阳气始生，古人称“冬至大如年”，北方吃饺子，南方吃汤圆。",
    "小寒": "典故：小寒进入一年最冷阶段，民间有画九九消寒图的雅俗。",
    "大寒": "典故：大寒为岁末最后节气，常与除旧布新、准备年节相连。",
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
    # AI 新闻按用户要求只从 Google News 中文搜索，优先当天/过去 24 小时。
    rows = google_news_articles('AI OR 人工智能 OR 大模型 OR OpenAI OR ChatGPT OR Claude OR Gemini OR DeepSeek when:1d', max_records=8)
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


def douban_subjects(subject_type: str, tag: str, max_records: int = 5) -> list[dict]:
    """Fetch Douban public subject lists.

    Douban does not offer a stable official free API for every ranking page, but
    this public endpoint is enough for lightweight daily calendar recommendations.
    """
    params = urllib.parse.urlencode({
        "type": subject_type,
        "tag": tag,
        "sort": "recommend",
        "page_limit": max_records,
        "page_start": 0,
    })
    url = f"https://movie.douban.com/j/search_subjects?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 personal-calendar-free/1.0",
            "Referer": "https://movie.douban.com/explore",
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    rows = []
    label = "电视剧" if subject_type == "tv" else "电影"
    for item in data.get("subjects", []) or []:
        title = clean_text(item.get("title"), 80)
        if not title:
            continue
        rate = clean_text(item.get("rate") or "暂无评分", 20)
        url = str(item.get("url") or "")
        summary = f"豆瓣{tag}{label}推荐；评分：{rate}。适合快速判断今天值得关注的{label}。"
        rows.append({"title": f"{title}｜豆瓣{tag}{label}", "url": url, "source": "豆瓣", "summary": summary})
    return rows


def douban_subject_detail(url: str) -> dict:
    if not url:
        return {}
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 personal-calendar-free/1.0",
            "Referer": "https://movie.douban.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(400_000).decode("utf-8", errors="ignore")
    except Exception:
        return {}
    intro = ""
    m = re.search(r'<span property="v:summary"[^>]*>([\s\S]*?)</span>', raw, flags=re.I)
    if m:
        intro = clean_text(m.group(1), 120)
    directors = "、".join(clean_text(x, 20) for x in re.findall(r'rel="v:directedBy">([^<]+)</a>', raw)[:2])
    actors = "、".join(clean_text(x, 20) for x in re.findall(r'rel="v:starring">([^<]+)</a>', raw)[:4])
    release_dates = re.findall(r'property="v:initialReleaseDate"[^>]*content="([^"]+)"', raw)
    return {"intro": intro, "directors": directors, "actors": actors, "date": clean_text(" / ".join(release_dates[:2]), 60)}


def douban_coming_movies(max_records: int = 5) -> list[dict]:
    url = "https://movie.douban.com/coming"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 personal-calendar-free/1.0",
            "Referer": "https://movie.douban.com/",
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read(600_000).decode("utf-8", errors="ignore")
    except Exception:
        return []

    rows = []
    for tr in re.findall(r"<tr>([\s\S]*?)</tr>", raw, flags=re.I):
        date_m = re.search(r"<td>\s*([0-9]{2}月[0-9]{2}日)", tr)
        link_m = re.search(r'<a href="([^"]+)" title="([^"]+)">([^<]+)</a>', tr)
        tds = re.findall(r"<td>\s*([\s\S]*?)\s*</td>", tr, flags=re.I)
        if not date_m or not link_m or len(tds) < 5:
            continue
        title = clean_text(link_m.group(3), 80)
        href = link_m.group(1)
        kind = clean_text(tds[2], 50)
        area = clean_text(tds[3], 40)
        wish = clean_text(tds[4], 30)
        detail = douban_subject_detail(href)
        desc_parts = [f"日期：{date_m.group(1)}", f"类型：{kind}", f"地区：{area}", f"热度：{wish}"]
        if detail.get("actors"):
            desc_parts.append(f"演员：{detail['actors']}")
        if detail.get("intro"):
            desc_parts.append(f"简介：{detail['intro']}")
        rows.append({"title": f"{title}｜即将上映电影", "url": href, "source": "豆瓣", "summary": "；".join(desc_parts)})
        if len(rows) >= max_records:
            break
    return rows


def upcoming_news_items(label: str, query: str, max_records: int = 2) -> list[dict]:
    rows = []
    for item in google_news_articles(query, max_records=max_records * 2):
        title = strip_source_from_title(item.get("title", ""), item.get("source", ""))
        if not has_cjk(title):
            continue
        date_m = re.search(r"([0-9]{1,2}月[0-9]{1,2}日|今日|明日|本周|五一|暑期|暑假|即将)", title)
        date_text = date_m.group(1) if date_m else "见新闻/平台官宣"
        summary = title_takeaway(title, item.get("source", ""), 140)
        rows.append({
            "title": f"{title}｜近期{label}",
            "url": item.get("url", ""),
            "source": item.get("source") or "Google News",
            "summary": f"日期：{date_text}；演员/主创：见原文；简介：{summary}",
        })
        if len(rows) >= max_records:
            break
    return rows


def douban_nowplaying(max_records: int = 5) -> list[dict]:
    url = "https://movie.douban.com/cinema/nowplaying/beijing/"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 personal-calendar-free/1.0",
            "Referer": "https://movie.douban.com/cinema/nowplaying/beijing/",
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read(500_000).decode("utf-8", errors="ignore")
    except Exception:
        return []

    rows = []
    seen = set()
    for block in re.findall(r"<li[^>]+data-title=\"([^\"]+)\"[\s\S]*?</li>", raw, flags=re.I):
        title = clean_text(block, 80)
        if not title or title in seen:
            continue
        seen.add(title)
        rows.append({
            "title": f"{title}｜豆瓣北京正在上映",
            "url": url,
            "source": "豆瓣",
            "summary": f"豆瓣北京正在上映影片；可优先判断近期新片和院线热度。",
        })
        if len(rows) >= max_records:
            break
    return rows


def entertainment_hotspots() -> list[dict]:
    # 每日热度推荐：按豆瓣热门电影、热门电视剧优先排序。
    rows = []
    rows.extend(douban_subjects("movie", "热门", max_records=3))
    rows.extend(douban_subjects("tv", "热门", max_records=3))
    if len(rows) < 5:
        for q in ['豆瓣 热门 电影 when:7d', '豆瓣 热门 电视剧 when:7d']:
            rows.extend([
                r for r in google_news_articles(q, max_records=8)
                if has_cjk(r.get("title")) and has_cjk(r.get("source"))
            ][:3])
    unique = []
    seen = set()
    for row in rows:
        title = row.get("title")
        if title and title not in seen:
            unique.append(row)
            seen.add(title)
    return unique[:8] or FALLBACK_ENTERTAINMENT


def upcoming_entertainment() -> list[dict]:
    rows = []
    rows.extend(douban_coming_movies(max_records=3))
    rows.extend(upcoming_news_items("电视剧", '电视剧 新剧 定档 开播 演员 简介 when:14d', max_records=2))
    rows.extend(upcoming_news_items("短剧", '短剧 定档 开播 演员 简介 when:14d', max_records=2))
    rows.extend(upcoming_news_items("动漫", '动漫 动画 定档 开播 简介 when:14d', max_records=2))
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


def vevent(day: date, summary: str, description: str, hour: int = 9, all_day: bool = False, end_day=None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid(day.isoformat() + summary)}",
        f"DTSTAMP:{stamp}",
    ]
    if all_day:
        end_day = end_day or (day + timedelta(days=1))
        lines.extend([
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_day.strftime('%Y%m%d')}",
        ])
    else:
        start = datetime(day.year, day.month, day.day, hour, 0, 0)
        end = start + timedelta(minutes=30)
        lines.extend([
            f"DTSTART;TZID={TZ}:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;TZID={TZ}:{end.strftime('%Y%m%dT%H%M%S')}",
        ])
    lines.extend([
        f"SUMMARY:{esc(summary)}",
        f"DESCRIPTION:{esc(description)}",
        "END:VEVENT",
    ])
    return "\r\n".join(fold(x) for x in lines)


def holiday_events(start: date, days: int) -> list[str]:
    events = []
    end = start + timedelta(days=days)
    covered = set()
    for raw_start, raw_end, name in HOLIDAY_RANGES_2026:
        d1 = date.fromisoformat(raw_start)
        d2_inclusive = date.fromisoformat(raw_end)
        d2_exclusive = d2_inclusive + timedelta(days=1)
        if d2_exclusive <= start or d1 >= end:
            continue
        for n in range((d2_exclusive - d1).days):
            covered.add(d1 + timedelta(days=n))
        desc = f"中国大陆节假日：{name}\n日期：{d1.strftime('%Y-%m-%d')} 至 {d2_inclusive.strftime('%Y-%m-%d')}"
        events.append(vevent(d1, name, desc, all_day=True, end_day=d2_exclusive))
    for i in range(days):
        d = start + timedelta(days=i)
        if d in covered:
            continue
        name = CN_HOLIDAYS_FIXED.get(d.strftime("%m-%d")) or CN_HOLIDAYS_2026.get(d.isoformat())
        if name:
            events.append(vevent(d, name, f"中国大陆常见节日：{name}", all_day=True))
    return events


def solar_term_events(start: date, days: int) -> list[str]:
    events = []
    end = start + timedelta(days=days)
    for raw_day, name in SOLAR_TERMS_2026.items():
        d = date.fromisoformat(raw_day)
        if start <= d < end:
            tip = SOLAR_TERM_TIPS.get(name, "中国传统二十四节气。")
            events.append(vevent(d, name, f"二十四节气：{name}\n{tip}", all_day=True))
    return events


def strip_source_from_title(title: str, source: str = "") -> str:
    text = clean_text(title, 160)
    if source:
        text = re.sub(rf"\s*-\s*{re.escape(source)}\s*$", "", text).strip()
    text = re.sub(r"\s*-\s*(手机新浪网|新浪财经|搜狐网|腾讯网|网易|央视网|观察者网|澎湃新闻|证券时报|thepaper\.cn|guancha\.cn)\s*$", "", text).strip()
    return text


def split_title_parts(title: str) -> list[str]:
    title = strip_source_from_title(title)
    parts = re.split(r"[，,；;：:。！？!？——]|\s+-\s+", title)
    return [clean_text(p, 80) for p in parts if len(clean_text(p, 80)) >= 3]


def infer_content_type(title: str) -> str:
    t = str(title)
    if any(k in t for k in ["电影", "新片", "票房", "上映", "五一档", "院线"]):
        return "电影"
    if any(k in t for k in ["电视剧", "新剧", "热播剧", "追剧", "开播", "收官", "剧集"]):
        return "电视剧"
    if any(k in t for k in ["动漫", "动画", "国漫", "日漫", "番剧", "漫画"]):
        return "动漫"
    if any(k in t for k in ["AI", "人工智能", "大模型", "DeepSeek", "OpenAI", "Claude", "Gemini", "ChatGPT"]):
        return "AI"
    return "热点"


def title_takeaway(title: str, source: str = "", max_len: int = 180) -> str:
    core = strip_source_from_title(title, source)
    parts = split_title_parts(core)
    ctype = infer_content_type(core)
    if ctype == "电影":
        prefix = "电影信息："
        advice = "适合快速判断近期院线/平台新片和档期热度。"
    elif ctype == "电视剧":
        prefix = "剧集信息："
        advice = "适合快速判断今天有哪些剧在更新、开播或收官。"
    elif ctype == "动漫":
        prefix = "动漫信息："
        advice = "适合快速判断国漫/日漫更新和热度变化。"
    elif ctype == "AI":
        prefix = "AI动向："
        advice = "适合关注模型能力、产品变化和内容选题机会。"
    else:
        prefix = "热点信息："
        advice = "适合先判断是否值得继续点开。"
    if len(parts) >= 2:
        text = f"{prefix}{parts[0]}；关键信息：{'；'.join(parts[1:3])}。{advice}"
    else:
        text = f"{prefix}{core}。{advice}"
    return clean_text(text, max_len)


def enrich_article_summaries(items: list[dict], max_items: int = 5) -> list[dict]:
    enriched = []
    for item in items[:max_items]:
        row = dict(item)
        title = row.get("title", "")
        source = row.get("source", "")
        summary = clean_text(row.get("summary"), 180)
        # RSS 自带摘要不够可读时，再尝试读取原网页 meta description / 正文段落。
        if source != "豆瓣" and (not summary or len(summary) < 35 or summary.lower() in {"english", "chinese"}) and row.get("url"):
            summary = fetch_page_summary(row.get("url"), title, 150)
        title_core = strip_source_from_title(title, source)
        # 如果摘要只是把标题重复一遍，就改成结构化信息提炼。
        if not summary or summary == title or summary in title or title_core in summary or summary in title_core:
            summary = title_takeaway(title, source, 180)
        row["summary"] = summary
        row["type"] = infer_content_type(title)
        enriched.append(row)
    return enriched


def article_lines(items: list[dict], limit: int = 5) -> str:
    lines = []
    for idx, item in enumerate(enrich_article_summaries(items, limit), 1):
        source = f"｜来源：{item.get('source')}" if item.get("source") else ""
        ctype = item.get("type") or infer_content_type(item.get("title", ""))
        title = strip_source_from_title(item.get("title", ""), item.get("source", ""))
        # Apple Calendar 里长链接很影响阅读，默认不堆 URL，只展示可读摘要。
        lines.append(f"{idx}. [{ctype}] {title}\n   提炼：{item.get('summary')}{source}")
    return "\n\n".join(lines)


def today_hotspot_events() -> list[str]:
    hot_items = entertainment_hotspots()
    upcoming_items = upcoming_entertainment()
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        vevent(
            TODAY,
            f"影视每日热度：{clean_text(hot_items[0].get('title'), 34)}",
            f"每日热点电影/电视剧推荐，按豆瓣热度优先，生成时间：{generated}\n\n{article_lines(hot_items)}",
            20,
        ),
        vevent(
            TODAY,
            f"近期即将上映/开播：{clean_text(upcoming_items[0].get('title'), 30)}",
            f"近期即将上映/开播内容，覆盖电影、电视剧、短剧、动漫，生成时间：{generated}\n\n{article_lines(upcoming_items, 8)}",
            21,
        ),
    ]


def build() -> str:
    events = []
    try:
        for row in load_weather():
            events.append(vevent(row["date"], row["summary"], row["description"], 7))
    except Exception as e:
        events.append(vevent(TODAY, "天气更新失败", f"Open-Meteo 拉取失败：{e}", 7))
    events.extend(holiday_events(TODAY, 365))
    events.extend(solar_term_events(TODAY, 365))
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
