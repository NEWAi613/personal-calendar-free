#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CITY = "北京海淀"
LAT = 39.9593
LON = 116.2985
TZ = "Asia/Shanghai"
OUT = Path(__file__).resolve().parent / "calendar.ics"
TODAY = date.today()
DAYS = 14

AI_TOPICS = [
    "检查 AI 热点：OpenAI / Claude / Gemini / 国内大模型",
    "整理一个适合小白的 AI 实操选题",
    "复盘本周 AI 工具更新，筛出能做成短视频的点",
]
MOVIE_TOPICS = [
    "检查影视更新：新剧、新片、平台热榜",
    "整理可做内容的影视热点，保留 1-2 个选题",
]

CN_HOLIDAYS_FIXED = {"01-01": "元旦", "05-01": "劳动节", "10-01": "国庆节"}
CN_HOLIDAYS_2026 = {
    "2026-02-17": "春节",
    "2026-04-05": "清明节",
    "2026-06-19": "端午节",
    "2026-09-25": "中秋节",
}


def fetch_json(url: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        "forecast_days": DAYS,
    })
    data = fetch_json(f"https://api.open-meteo.com/v1/forecast?{params}")
    daily = data.get("daily", {})
    rows = []
    for i, day in enumerate(daily.get("time", [])):
        code = int(daily.get("weather_code", [0])[i])
        tmax = float(daily.get("temperature_2m_max", [0])[i])
        tmin = float(daily.get("temperature_2m_min", [0])[i])
        rain = daily.get("precipitation_probability_max", [None])[i]
        rows.append({
            "date": date.fromisoformat(day),
            "summary": f"{CITY}天气：{weather_code_text(code)} {tmin:.0f}-{tmax:.0f}℃",
            "description": f"穿衣推荐：{clothing_tip(tmax, tmin, code)}\n降水概率：{rain if rain is not None else '-'}%\n数据源：Open-Meteo",
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


def recurring_content_events(start: date, days: int) -> list[str]:
    events = []
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() in {0, 2, 4}:
            topic = AI_TOPICS[(i // 2) % len(AI_TOPICS)]
            events.append(vevent(d, f"AI热点提醒：{topic}", "适合整理成小红书/抖音选题，优先保留新手可实操内容。", 10))
        if d.weekday() in {1, 5}:
            topic = MOVIE_TOPICS[(i // 3) % len(MOVIE_TOPICS)]
            events.append(vevent(d, f"影视更新提醒：{topic}", "检查平台热榜和新上线内容，只记录值得做内容的更新。", 20))
    return events


def build() -> str:
    events = []
    try:
        for row in load_weather():
            events.append(vevent(row["date"], row["summary"], row["description"], 7))
    except Exception as e:
        events.append(vevent(TODAY, "天气更新失败", f"Open-Meteo 拉取失败：{e}", 7))
    events.extend(holiday_events(TODAY, 120))
    events.extend(recurring_content_events(TODAY, DAYS))
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
