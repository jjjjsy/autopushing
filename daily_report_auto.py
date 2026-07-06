#!/usr/bin/env python3
"""
每日全球市场与光电半导体情报 - 全自动版
===========================================
自动采集数据 → 生成HTML → 发送邮件

数据源：
- 美股三大指数：westock-data-clawhub npm 包
- 日韩指数：WebSearch（运行时由 AI agent 填入）
- 全球新闻：WebSearch（运行时由 AI agent 填入）
- 光电半导体情报：WebSearch（运行时由 AI agent 填入）
- 郑希点评：zhengxi-views skill

用法：
  python3 daily_report_auto.py              # 采集数据 → 生成HTML → 发送邮件
  python3 daily_report_auto.py --dry-run     # 仅生成HTML，不发送
  python3 daily_report_auto.py --dry-run -o preview.html  # 输出HTML到文件
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timedelta
from typing import Optional

# 导入邮件模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_push import (
    send_email,
    build_daily_report_html,
    build_importance_badge,
    build_source_badge,
    markdown_to_html,
)


# ============================================================
# 数据采集模块
# ============================================================

def _parse_westock_table(output: str) -> list:
    """
    解析 westock CLI 的表格输出（Markdown table 格式）
    返回: [{"date":"...", "open":..., "last":..., "high":..., "low":..., ...}, ...]
    """
    lines = output.strip().split('\n')
    rows = []
    header = []
    sep_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        cells = [c.strip() for c in stripped.split('|')[1:-1]]

        if not sep_found:
            # 检查是否是分隔行
            if all(c.replace('-', '').replace(':', '').strip() == '' for c in cells):
                sep_found = True
                continue
            header = cells
        else:
            if len(cells) == len(header):
                row = {}
                for i, h in enumerate(header):
                    val = cells[i]
                    if h in ('open', 'last', 'high', 'low', 'volume', 'amount', 'exchange'):
                        try:
                            row[h] = float(val.replace(',', ''))
                        except ValueError:
                            row[h] = val
                    else:
                        row[h] = val
                rows.append(row)

    return rows


def _collect_us_indices() -> dict:
    """
    采集美股三大指数数据
    使用 westock-data-clawhub npm 包获取最近2日K线
    """
    result = {
        "table_html": "",
        "note": "",
        "success": False,
    }

    indices = {
        "道琼斯工业": "us.DJI",
        "纳斯达克": "us.IXIC",
        "标普500": "us.INX",
    }

    rows = []
    for name, code in indices.items():
        try:
            proc = subprocess.run(
                ["npx", "westock-data-clawhub@1.0.4", "kline", code, "--limit", "2"],
                capture_output=True, text=True, timeout=30,
            )
            output = proc.stdout.strip()
            if proc.returncode != 0 or not output or output == "数据为空":
                rows.append([name, "—", "—", "—", "数据为空"])
                continue

            klines = _parse_westock_table(output)

            if len(klines) >= 2:
                today = klines[-1]
                yesterday = klines[-2]
                close = today.get("last", 0)
                prev_close = yesterday.get("last", close)
                if prev_close and prev_close != 0:
                    change_pct = (close - prev_close) / prev_close * 100
                else:
                    change_pct = 0

                arrow = "↓" if change_pct < -0.5 else ("↑" if change_pct > 0.5 else "→")
                change_amt = close - prev_close
                rows.append([
                    name,
                    f"{close:,.2f}",
                    f"{arrow} {change_pct:+.2f}%",
                    f"{change_amt:+.2f}",
                    "✓",
                ])
            elif len(klines) == 1:
                today = klines[0]
                close = today.get("last", 0)
                rows.append([
                    name,
                    f"{close:,.2f}",
                    "—",
                    "—",
                    "仅1日数据",
                ])
            else:
                rows.append([name, "—", "—", "—", "解析失败"])
        except Exception as e:
            rows.append([name, "—", "—", "—", f"错误: {str(e)[:20]}"])

    # 构建表格
    headers = ["指数", "收盘价", "涨跌幅", "涨跌额", "状态"]
    thead = '<tr>' + ''.join(
        f'<th style="padding:8px 10px;text-align:left;border-bottom:2px solid #e0e0e0;font-weight:600;font-size:13px">{h}</th>'
        for h in headers
    ) + '</tr>'

    tbody = ''
    for i, row in enumerate(rows):
        bg = '#fafafa' if i % 2 == 0 else '#fff'
        tbody += '<tr style="background:' + bg + '">' + ''.join(
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f0f0;font-size:13px">{c}</td>'
            for c in row
        ) + '</tr>'

    result["table_html"] = f'<table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:13px"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'
    result["success"] = any(row[-1] == "✓" for row in rows)

    # 生成解读
    if result["success"]:
        up_count = sum(1 for r in rows if "↑" in r[2])
        down_count = sum(1 for r in rows if "↓" in r[2])
        if down_count >= 2:
            result["note"] = "⚠️ 美股三大指数多数下跌，市场风险偏好下降，建议关注后续走势。"
        elif up_count >= 2:
            result["note"] = "✅ 美股三大指数多数上涨，市场情绪偏积极。"
        else:
            result["note"] = "📊 美股三大指数涨跌互现，市场方向待明确。"

    return result


def _build_index_table_html(rows: list, headers: list) -> str:
    """构建指数数据表格 HTML"""
    thead = '<tr>' + ''.join(
        f'<th style="padding:8px 10px;text-align:left;border-bottom:2px solid #e0e0e0;font-weight:600;font-size:13px">{h}</th>'
        for h in headers
    ) + '</tr>'

    tbody = ''
    for i, row in enumerate(rows):
        bg = '#fafafa' if i % 2 == 0 else '#fff'
        tbody += '<tr style="background:' + bg + '">' + ''.join(
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f0f0;font-size:13px">{c}</td>'
            for c in row
        ) + '</tr>'

    return f'<table style="width:100%;border-collapse:collapse;margin:8px 0;font-size:13px"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'


def _build_news_html(news_items: list) -> str:
    """
    构建新闻列表 HTML
    每条新闻格式: {"title": "...", "summary": "...", "importance": 1-5, "source_type": "official"|"rumor"|"analysis"}
    """
    if not news_items:
        return '<p style="color:#999;text-align:center;padding:20px">暂无数据，请稍后更新</p>'

    items_html = ""
    for item in news_items:
        badge = build_importance_badge(item.get("importance", 2))
        src_badge = build_source_badge(item.get("source_type", "analysis"))

        items_html += f'''<div style="border-bottom:1px solid #f0f0f0;padding:10px 0">
    <div style="font-size:14px;font-weight:600;color:#212121;margin-bottom:4px;line-height:1.5">
        {item.get("title", "")}{badge}{src_badge}
    </div>
    <div style="font-size:12px;color:#757575;line-height:1.6">
        {item.get("summary", "")}
    </div>
</div>'''

    return items_html


def _get_weekday_cn(dt: date) -> str:
    """获取中文星期"""
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return weekdays[dt.weekday()]


# ============================================================
# 日报构建器（接受外部数据，由 AI agent 填充）
# ============================================================

def build_and_send_report(
    report_date_str: str,
    global_news: list,
    us_indices_data: dict,
    jk_indices_rows: list,
    jk_note: str,
    semi_news: list,
    zhengxi_content: str,
    focus_items: list,
    dry_run: bool = False,
    output_file: str = None,
) -> dict:
    """
    构建并发送日报

    Args:
        report_date_str: 报告日期，如 "2026年7月3日（周五）"
        global_news: 全球新闻列表 [{"title":"...", "summary":"...", "importance":1-5, "source_type":"..."}]
        us_indices_data: 美股指数数据 {"table_html":"...", "note":"..."}
        jk_indices_rows: 日韩指数行数据 [["日经225", "收盘价", "涨跌幅", "涨跌额"], ...]
        jk_note: 日韩市场解读
        semi_news: 光电半导体新闻列表
        zhengxi_content: 郑希点评HTML内容
        focus_items: 关注要点 [{"num":1, "color":"#d32f2f", "text":"..."}]
        dry_run: 仅生成HTML不发送
        output_file: 输出HTML到文件
    """
    # 构建 sections
    sections = {
        "global_news": {
            "title": "一、全球新闻大事",
            "content": _build_news_html(global_news),
        },
        "us_market": {
            "title": "二、美股三大指数",
            "table_html": us_indices_data.get("table_html", ""),
            "note": us_indices_data.get("note", ""),
        },
        "japan_korea": {
            "title": "三、日韩市场",
            "table_html": _build_index_table_html(
                jk_indices_rows,
                ["指数", "收盘价", "涨跌幅", "涨跌额"]
            ),
            "note": jk_note,
        },
        "semiconductor": {
            "title": "四、光电半导体情报追踪",
            "content": _build_news_html(semi_news),
        },
        "zhengxi_views": {
            "title": "五、郑希视角点评",
            "content": zhengxi_content,
        },
        "focus_points": {
            "title": "六、今日关注要点",
            "items": focus_items,
        },
    }

    # 生成 HTML
    html = build_daily_report_html(
        report_date=report_date_str,
        sections=sections,
    )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

    if dry_run:
        return {"success": True, "message": "HTML已生成（dry-run）", "html": html}

    # 发送邮件
    subject = f"每日全球市场与光电半导体情报 - {report_date_str}"
    result = send_email(subject, html, "html")
    return result


# ============================================================
# Python 原生 HTTP 数据采集（不依赖 AI agent）
# ============================================================

import requests as _requests
import time as _time

_EASTMONEY_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _fetch_with_retry(url, params=None, headers=None, max_retries=3, timeout=10):
    """带重试的 HTTP 请求"""
    hdrs = headers or _EASTMONEY_HEADERS
    for attempt in range(max_retries):
        try:
            resp = _requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            _time.sleep(1)
    return None


def _collect_all_indices() -> dict:
    """
    通过东方财富 API 获取全部指数数据（美股+日韩）
    返回: {"us": table_html/note, "jk": rows/note}
    """
    # 东方财富 secid 映射
    em_indices = {
        "道琼斯": "100.DJIA",
        "纳斯达克": "100.NDX",
        "标普500": "100.SPX",
        "日经225": "100.N225",
        "韩国KOSPI": "100.KS11",
    }

    secids = ",".join(em_indices.values())
    data = _fetch_with_retry(
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        params={"fltt": "2", "fields": "f2,f3,f4,f12,f14", "secids": secids},
    )

    result_map = {}
    if data and data.get("data") and data["data"].get("diff"):
        for item in data["data"]["diff"]:
            code = item.get("f12", "")
            for name, secid in em_indices.items():
                if code == secid.split(".")[1]:
                    result_map[name] = {
                        "price": item.get("f2", 0),
                        "pct": item.get("f3", 0),
                        "chg": item.get("f4", 0),
                    }
                    break

    # 构建美股表格
    us_names = ["道琼斯", "纳斯达克", "标普500"]
    us_rows = []
    for name in us_names:
        d = result_map.get(name)
        if d and d["price"]:
            arrow = "↓" if d["pct"] < -0.5 else ("↑" if d["pct"] > 0.5 else "→")
            us_rows.append([
                name,
                f"{d['price']:,.2f}",
                f"{arrow} {d['pct']:+.2f}%",
                f"{d['chg']:+.2f}",
                "✓",
            ])
        else:
            us_rows.append([name, "—", "—", "—", "数据获取失败"])

    us_table = _build_index_table_html(us_rows, ["指数", "收盘价", "涨跌幅", "涨跌额", "状态"])

    us_up = sum(1 for r in us_rows if "↑" in r[2])
    us_down = sum(1 for r in us_rows if "↓" in r[2])
    if us_down >= 2:
        us_note = "⚠️ 美股三大指数多数下跌，市场风险偏好下降。"
    elif us_up >= 2:
        us_note = "✅ 美股三大指数多数上涨，市场情绪偏积极。"
    else:
        us_note = "📊 美股三大指数涨跌互现，市场方向待明确。"

    # 构建��韩表格
    jk_names = ["日经225", "韩国KOSPI"]
    jk_rows = []
    for name in jk_names:
        d = result_map.get(name)
        if d and d["price"]:
            arrow = "↓" if d["pct"] < -0.5 else ("↑" if d["pct"] > 0.5 else "→")
            jk_rows.append([
                name,
                f"{d['price']:,.2f}",
                f"{arrow} {d['pct']:+.2f}%",
                f"{d['chg']:+.2f}",
            ])
        else:
            jk_rows.append([name, "—", "—", "—"])

    jk_up = sum(1 for r in jk_rows if "↑" in r[2])
    jk_down = sum(1 for r in jk_rows if "↓" in r[2])
    if jk_down >= 2:
        jk_note = "⚠️ 日韩市场多数下跌，亚太市场风险偏好下降。"
    elif jk_up >= 2:
        jk_note = "✅ 日韩市场多数上涨，亚太市场情绪积极。"
    else:
        jk_note = "📊 日韩市场涨跌互现，整体表现平稳。"

    return {
        "us": {"table_html": us_table, "note": us_note, "success": any(r[-1] == "✓" for r in us_rows)},
        "jk": {"rows": jk_rows, "note": jk_note},
    }


def _collect_news() -> list:
    """
    采集财经新闻（多源容错）
    依次尝试：东方财富快讯API → 东方财富新闻页面抓取 → 生成基础新闻
    """
    news_items = []

    # 方法1: 东方财富 7x24 快讯 API（尝试多个端点）
    em_endpoints = [
        {
            "url": "https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
            "params": {
                "client": "web", "biz": "web_724", "fastColumn": "102",
                "sortEnd": "", "pageSize": "20",
                "req_trace": str(int(_time.time() * 1000)),
            },
        },
        {
            "url": "https://np-listapi.eastmoney.com/comm/web/getListByDirection",
            "params": {
                "client": "web", "biz": "web_724",
                "direction": "down", "pageSize": "20",
                "req_trace": str(int(_time.time() * 1000)),
            },
        },
    ]

    for ep in em_endpoints:
        if news_items:
            break
        try:
            resp = _requests.get(ep["url"], params=ep["params"], headers=_EASTMONEY_HEADERS, timeout=10)
            data = resp.json()
            if data.get("data"):
                items = data["data"].get("list", data["data"].get("roll_data", []))
                for item in items[:10]:
                    title = item.get("title", "") or item.get("content", "")[:80]
                    summary = item.get("content", "")[:150] if item.get("content") else title
                    if title:
                        news_items.append({
                            "title": title[:80],
                            "summary": summary,
                            "importance": 3,
                            "source_type": "official",
                        })
        except Exception:
            pass

    # 方法2: 抓取东方财富新闻页面
    if not news_items:
        try:
            resp = _requests.get(
                "https://finance.eastmoney.com/a/czqyw.html",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=10,
            )
            resp.encoding = "utf-8"
            # 提取新闻标题（东方财富新闻页面格式）
            titles = re.findall(r'<a[^>]*title="([^"]{10,80})"[^>]*href="https://finance\.eastmoney\.com/a/[^"]*"', resp.text)
            for title in titles[:8]:
                news_items.append({
                    "title": title,
                    "summary": title,
                    "importance": 3,
                    "source_type": "official",
                })
        except Exception:
            pass

    # 方法3: 新浪财经 RSS
    if not news_items:
        try:
            resp = _requests.get(
                "https://finance.sina.com.cn/roll/index.d.html",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            resp.encoding = "utf-8"
            titles = re.findall(r'<a[^>]*>([^<]{10,80})</a>', resp.text)
            seen = set()
            for title in titles:
                title = title.strip()
                if title not in seen and len(title) > 10 and not title.startswith("http"):
                    seen.add(title)
                    news_items.append({
                        "title": title[:80],
                        "summary": title,
                        "importance": 3,
                        "source_type": "official",
                    })
                    if len(news_items) >= 8:
                        break
        except Exception:
            pass

    return news_items


def _filter_semi_news(news_items: list) -> list:
    """从新闻列表中筛选光电半导体相关新闻"""
    keywords = [
        "光模块", "光通信", "半导体", "芯片", "存储", "光纤",
        "HBM", "DRAM", "NAND", "光刻", "刻蚀", "封装",
        "磷化铟", "砷化镓", "硅片", "SOI", "VCSEL",
        "800G", "1.6T", "GPU", "算力", "AI芯片",
    ]
    semi_news = []
    for item in news_items:
        text = item.get("title", "") + item.get("summary", "")
        if any(kw in text for kw in keywords):
            item["importance"] = 4
            semi_news.append(item)
    return semi_news


def _generate_zhengxi_content(market_data: dict, news_items: list) -> str:
    """
    基于郑希投资框架生成模板化点评（不依赖 AI agent）
    根据市场数据和新闻关键词动态生成分析
    """
    # 分析市场趋势
    us_data = market_data.get("us", {})
    jk_data = market_data.get("jk", {})
    us_note = us_data.get("note", "")
    jk_note = jk_data.get("note", "")

    # 检测新闻关键词
    all_news_text = " ".join(n.get("title", "") + n.get("summary", "") for n in news_items)
    has_semi = any(kw in all_news_text for kw in ["半导体", "芯片", "光模块", "存储"])
    has_monetary = any(kw in all_news_text for kw in ["央行", "降息", "加息", "流动性", "逆回购"])
    has_trade = any(kw in all_news_text for kw in ["关税", "贸易", "制裁", "出口管制"])

    # 构建点评
    parts = []
    parts.append('<div style="background:#e8f5e9;border-left:4px solid #2e7d32;padding:12px 16px;margin-bottom:16px;border-radius:0 4px 4px 0;font-size:13px;color:#555;line-height:1.8">')
    parts.append('<strong>📌 郑希框架分析</strong><br><br>')

    # 一、景气方向
    parts.append('<strong>一、景气方向判断</strong><br>')
    if has_semi:
        parts.append('从郑希的景气方向框架看，AI算力产业链（光模块/光通信/半导体/存储）当前仍处于景气周期。需关注短期拥挤度调整与景气拐点的区别——交易拥挤导致的回调不代表基本面恶化。<br><br>')
    else:
        parts.append('从郑希的景气方向框架看，需持续跟踪AI算力、新能源等高景气方向的供给端变化。关注产业链"通胀环节"——即供给端创造的需求，这是郑希选股的核心观测点。<br><br>')

    # 二、ROE弹性
    parts.append('<strong>二、ROE低位弹性</strong><br>')
    parts.append('半导体设备/材料板块中，部分国产替代标的处于ROE周期底部。在国产替代加速和全球晶圆厂扩产双重驱动下，盈利修复空间可观。郑希在多份季报中强调"ROE弹性最大的方向"值得重点关注。<br><br>')

    # 三、全球比较优势
    parts.append('<strong>三、全球比较优势</strong><br>')
    parts.append('中国在光模块领域已具备明确的全球比较优势——全球市占率第一的光模块厂商在中国，产业链配套完整。但在上游化合物半导体衬底领域仍有差距，需持续跟踪。<br><br>')

    # 四、流动性
    parts.append('<strong>四、流动性考量</strong><br>')
    if has_monetary:
        parts.append('央行流动性操作及美联储政策预期是当前市场的关键变量。郑希框架中流动性维度提示：宽松环境利好科技成长股估值，但需警惕高拥挤度赛道的波动风险。<br><br>')
    else:
        parts.append(f'{us_note} 流动性环境对科技成长股估值有直接影响，需关注美联储政策节奏及国内央行操作。<br><br>')

    parts.append('</div>')

    # 声明
    parts.append('<div style="background:#fff3e0;border-left:4px solid #f57c00;padding:12px 16px;border-radius:0 4px 4px 0;font-size:13px;color:#555;line-height:1.8">')
    parts.append('<strong>⚠️ 声明：以上分析基于郑希公开投资框架的推演，并非郑希本人对当前市场的直接评论。</strong>')
    parts.append('郑希核心方法论：景气方向→ROE低位弹性→全球比较优势→流动性→集中度→业绩验证。本点评据此框架结合当日市场动态进行前瞻推演。')
    parts.append('</div>')

    return "".join(parts)


def _generate_focus_items(market_data: dict, news_items: list) -> list:
    """基于采集数据规则生成关注要点"""
    items = []
    num = 1

    # 美股相关
    us = market_data.get("us", {})
    us_note = us.get("note", "")
    if "下跌" in us_note:
        items.append({"num": num, "color": "#d32f2f", "text": "美股多数下跌，关注美联储政策信号及全球风险偏好变化"})
    elif "上涨" in us_note:
        items.append({"num": num, "color": "#2e7d32", "text": "美股多数上涨，关注科技股走势及市场情绪延续性"})
    else:
        items.append({"num": num, "color": "#1976d2", "text": "美股涨跌互现，关注美联储政策动态及经济数据"})
    num += 1

    # 日韩相关
    jk = market_data.get("jk", {})
    jk_note = jk.get("note", "")
    items.append({"num": num, "color": "#f57c00", "text": f"日韩市场动态：{jk_note}"})
    num += 1

    # 半导体相关
    items.append({"num": num, "color": "#f57c00", "text": "关注光模块/光通信产业链订单与需求变化，800G/1.6T升级迭代进展"})
    num += 1

    items.append({"num": num, "color": "#f57c00", "text": "关注存储芯片（HBM/DRAM/NAND）价格走势及产能扩张动态"})
    num += 1

    items.append({"num": num, "color": "#1976d2", "text": "关注半导体设备与材料国产替代进展及政策支持"})
    num += 1

    return items
def main():
    parser = argparse.ArgumentParser(description="每日全球市场与光电半导体情报 - 全自动版")
    parser.add_argument("--dry-run", action="store_true", help="仅生成HTML，不发送邮件")
    parser.add_argument("--output", "-o", help="将HTML输出到文件")
    parser.add_argument("--data-file", "-d", help="从JSON数据文件读取（跳过自动采集）")
    args = parser.parse_args()

    if args.data_file:
        # 从 JSON 文件读取数据
        with open(args.data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = build_and_send_report(
            report_date_str=data.get("report_date", datetime.now().strftime("%Y年%m月%d日")),
            global_news=data.get("global_news", []),
            us_indices_data=data.get("us_indices", {}),
            jk_indices_rows=data.get("jk_indices", []),
            jk_note=data.get("jk_note", ""),
            semi_news=data.get("semi_news", []),
            zhengxi_content=data.get("zhengxi_content", ""),
            focus_items=data.get("focus_items", []),
            dry_run=args.dry_run,
            output_file=args.output,
        )

        if args.dry_run:
            print(f"Dry run - HTML长度: {len(result.get('html', ''))} 字符")
            if args.output:
                print(f"HTML已输出到 {args.output}")
        elif result.get("success"):
            print(f"✅ {result['message']}")
        else:
            print(f"❌ {result['message']}")
            sys.exit(1)
        return

    # 自动采集���式
    print("=" * 60)
    print("每日全球市场与光电半导体情报 - 自动采集模式")
    print("=" * 60)

    today = date.today()
    report_date_str = f"{today.year}年{today.month}月{today.day}日（{_get_weekday_cn(today)}）"
    print(f"报告日期: {report_date_str}")

    # 1. 采集全部指数数据（东方财富 API）
    print("\n[1/4] 采集全球指数数据（东方财富 API）...")
    all_indices = _collect_all_indices()
    us_data = all_indices["us"]
    jk_data = all_indices["jk"]
    print(f"  美股: {'✓' if us_data['success'] else '✗ 部分失败'}")
    print(f"  日韩: {'✓' if any(r[1] != '—' for r in jk_data['rows']) else '✗ 失败'}")

    # 如果东方财富失败，回退到 westock CLI 获取美股
    if not us_data["success"]:
        print("  回退到 westock CLI 采集美股...")
        us_data = _collect_us_indices()

    # 2. 采集财经新闻
    print("\n[2/4] 采集财经新闻...")
    global_news = _collect_news()
    print(f"  新闻数: {len(global_news)}")

    # 3. 筛选半导体相关新闻
    print("\n[3/4] 筛选光电半导体情报...")
    semi_news = _filter_semi_news(global_news)
    print(f"  半导体相关: {len(semi_news)} 条")

    # 4. 生成郑希点评和关注要点
    print("\n[4/4] 生成郑希点评和关注要点...")
    market_data = {"us": us_data, "jk": jk_data}
    zhengxi_html = _generate_zhengxi_content(market_data, global_news + semi_news)
    focus_items = _generate_focus_items(market_data, global_news)
    print(f"  点评和关注要点已生成")

    # 构建并发送
    result = build_and_send_report(
        report_date_str=report_date_str,
        global_news=global_news,
        us_indices_data=us_data,
        jk_indices_rows=jk_data["rows"],
        jk_note=jk_data["note"],
        semi_news=semi_news if semi_news else global_news[:3],
        zhengxi_content=zhengxi_html,
        focus_items=focus_items,
        dry_run=args.dry_run,
        output_file=args.output,
    )

    if args.dry_run:
        print(f"\nDry run - HTML长度: {len(result.get('html', ''))} 字符")
        if args.output:
            print(f"HTML已输出到 {args.output}")
    elif result.get("success"):
        print(f"\n✅ {result['message']}")
    else:
        print(f"\n❌ {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
