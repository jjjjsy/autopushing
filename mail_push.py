#!/usr/bin/env python3
"""
邮件推送工具 - 通过 163 邮箱 SMTP 发送观点到微信
=================================================
微信收到邮件 → 微信「QQ邮箱提醒」会直接弹出通知
等效于推送到微信，无需手机运行任何程序。

用法：
  python3 mail_push.py text "今日观点：买入信号触发"
  python3 mail_push.py markdown --title "每日观点" --file report.md
  echo "## 报告" | python3 mail_push.py pipe
"""

import argparse
import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional


# ============================================================
# 163 邮箱 SMTP 配置
# ============================================================
SMTP_CONFIG = {
    "host": "smtp.163.com",
    "port": 465,           # SSL
    "user": "sjy2251942815@163.com",
    "password": os.environ.get("SMTP_PASSWORD", ""),
    "from_name": "量化观点推送",
}

# 收件人（推送到微信的关键：发到 QQ 邮箱，微信绑定 QQ 邮箱提醒即可收到通知）
TO_EMAIL = "sjy2251942815@163.com"


def send_email(subject: str, body: str, body_type: str = "html") -> dict:
    """发送邮件"""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SMTP_CONFIG['from_name']} <{SMTP_CONFIG['user']}>"
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    if body_type == "html":
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL(SMTP_CONFIG["host"], SMTP_CONFIG["port"], timeout=15) as server:
            server.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])
            server.sendmail(SMTP_CONFIG["user"], [TO_EMAIL], msg.as_string())
        return {"success": True, "message": "邮件发送成功"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "SMTP 认证失败，请检查邮箱账号和授权码"}
    except smtplib.SMTPException as e:
        return {"success": False, "message": f"SMTP 错误: {e}"}
    except Exception as e:
        return {"success": False, "message": f"发送失败: {e}"}


def _convert_tables(md_text: str) -> str:
    """将 Markdown 表格转换为 HTML 表格（在标题转换前调用）"""
    import re

    lines = md_text.split('\n')
    result = []
    in_table = False
    table_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            table_lines.append(stripped)
            in_table = True
            continue

        if in_table:
            result.append(_build_html_table(table_lines))
            table_lines = []
            in_table = False

        result.append(line)

    # 处理文末的表格
    if table_lines:
        result.append(_build_html_table(table_lines))

    return '\n'.join(result)


def _build_html_table(lines: list) -> str:
    """将表格行列表转为 HTML <table>"""
    if len(lines) < 2:
        return '\n'.join(lines)

    header_cells = [c.strip() for c in lines[0].split('|')[1:-1]]

    # 跳过分隔行 (|---|---|)
    data_start = 1
    sep_line = lines[1].replace('|', '').replace('-', '').replace(':', '').strip()
    if sep_line == '':
        data_start = 2

    # 解析数据行
    data_rows = []
    for line in lines[data_start:]:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        # 确保列数对齐
        while len(cells) < len(header_cells):
            cells.append('')
        data_rows.append(cells[:len(header_cells)])

    # 构建 HTML
    thead = '<tr>' + ''.join(
        f'<th style="padding:8px 10px;text-align:left;border-bottom:2px solid #e0e0e0;font-weight:600;font-size:13px">{h}</th>'
        for h in header_cells
    ) + '</tr>'

    tbody = ''
    for i, row in enumerate(data_rows):
        bg = '#fafafa' if i % 2 == 0 else '#fff'
        tbody += '<tr style="background:' + bg + '">' + ''.join(
            f'<td style="padding:8px 10px;border-bottom:1px solid #f0f0f0;font-size:13px">{c}</td>'
            for c in row
        ) + '</tr>'

    return f'<table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:13px"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'


def markdown_to_html(md_text: str) -> str:
    """增强版 Markdown → HTML 转换（支持表格、链接、有序列表）"""
    import re

    html = md_text

    # 1. 先处理表格（必须在其他规则之前）
    html = _convert_tables(html)

    # 2. 标题
    html = re.sub(r'^### (.+)$', r'<h3 style="color:#333;margin:16px 0 8px">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2 style="color:#1a73e8;margin:20px 0 10px;border-bottom:2px solid #1a73e8;padding-bottom:6px">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1 style="color:#0d47a1;margin:24px 0 12px">\1</h1>', html, flags=re.MULTILINE)

    # 3. 引用
    html = re.sub(r'^> (.+)$', r'<blockquote style="border-left:4px solid #1a73e8;margin:8px 0;padding:8px 16px;background:#f5f7fa;color:#555">\1</blockquote>', html, flags=re.MULTILINE)

    # 4. 链接
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" style="color:#1a73e8">\1</a>', html)

    # 5. 加粗
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

    # 6. 水平线
    html = re.sub(r'^---$', r'<hr style="border:none;border-top:1px solid #ddd;margin:20px 0">', html, flags=re.MULTILINE)

    # 7. 有序列表（先处理，避免和无序列表混淆）
    html = re.sub(r'^(\d+)\.\s+(.+)$', r'<li>\2</li>', html, flags=re.MULTILINE)

    # 8. 无序列表
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)

    # 9. font color 标签（企微风格 → HTML）
    html = re.sub(r'<font color="info">(.+?)</font>', r'<span style="color:#07c160">\1</span>', html)
    html = re.sub(r'<font color="comment">(.+?)</font>', r'<span style="color:#999">\1</span>', html)
    html = re.sub(r'<font color="warning">(.+?)</font>', r'<span style="color:#fa5151">\1</span>', html)

    # 10. 段落处理
    html = html.replace('\n\n', '</p><p style="margin:8px 0;line-height:1.8">')
    html = '<p style="margin:8px 0;line-height:1.8">' + html + '</p>'

    # 11. 包裹列表（将连续的 <li> 包裹在 <ul> 或 <ol> 中）
    html = re.sub(r'((?:<li>.*?</li>\s*)+)', r'<ul style="padding-left:20px;margin:8px 0">\1</ul>', html, flags=re.DOTALL)

    # 12. 清理空段落
    html = re.sub(r'<p[^>]*>\s*</p>', '', html)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:640px;margin:0 auto;padding:16px;color:#333;background:#fff">
{html}
<hr style="border:none;border-top:1px solid #eee;margin:24px 0 8px">
<p style="color:#aaa;font-size:12px;text-align:center">⚠️ 以上观点仅供参考，不构成投资建议。投资有风险，决策需谨慎。</p>
</body>
</html>"""


def build_viewpoint_html(title: str, date: str, viewpoints: list,
                          signals: Optional[list] = None, summary: str = "") -> str:
    """构建观点推送 HTML"""
    parts = []
    parts.append(f'<h1 style="color:#0d47a1">📊 {title}</h1>')
    parts.append(f'<p style="color:#999">推送时间：{date}</p>')

    if summary:
        parts.append(f'<p style="background:#f0f7ff;padding:12px 16px;border-radius:8px;margin:16px 0">{summary}</p>')

    if signals:
        parts.append('<h2 style="color:#1a73e8">🔔 触发信号</h2>')
        for s in signals:
            parts.append(f'<li><strong>{s["name"]}</strong>：{s["detail"]}</li>')

    if viewpoints:
        parts.append('<h2 style="color:#1a73e8">📈 今日观点</h2>')
        for vp in viewpoints:
            signal = vp.get("signal", "")
            emoji = {"买入": "🟢", "卖出": "🔴", "持有": "🟡", "观望": "⚪"}.get(signal, "➡️")
            color = {"买入": "#07c160", "卖出": "#fa5151", "持有": "#f0ad4e", "观望": "#999"}.get(signal, "#333")

            parts.append(f'<div style="border:1px solid #e8e8e8;border-radius:8px;padding:12px 16px;margin:12px 0">')
            parts.append(f'<h3 style="margin:0 0 8px">{emoji} {vp["stock"]}（{vp.get("code", "")}）'
                         f' - <span style="color:{color}">{signal}</span></h3>')
            if vp.get("price"):
                parts.append(f'<p style="margin:4px 0">💰 参考价格：<strong>{vp["price"]}</strong></p>')
            if vp.get("reason"):
                parts.append(f'<p style="margin:4px 0">📝 理由：{vp["reason"]}</p>')
            if vp.get("target"):
                parts.append(f'<p style="margin:4px 0">🎯 目标：{vp["target"]} | 🛑 止损：{vp.get("stop", "—")}</p>')
            parts.append('</div>')

    return "\n".join(parts)


def build_importance_badge(level: int) -> str:
    """
    构建重要性星级标记
    Args:
        level: 1-5 的重要性级别
    Returns:
        带颜色的 HTML span
    """
    colors_map = {
        5: "#d32f2f",  # 红色 - 极其重要
        4: "#f57c00",  # 橙色 - 很重要
        3: "#f9a825",  # 黄色 - 重要
        2: "#1976d2",  # 蓝色 - 关注
        1: "#9e9e9e",  # 灰色 - 参考
    }
    labels = {
        5: "极其重要",
        4: "很重要",
        3: "重要",
        2: "关注",
        1: "参考",
    }
    color = colors_map.get(level, "#9e9e9e")
    label = labels.get(level, "参考")
    stars = "★" * level + "☆" * (5 - level)

    return f'<span style="display:inline-block;background:{color};color:#fff;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap;margin-left:6px">{stars} {label}</span>'


def build_source_badge(source_type: str) -> str:
    """
    构建消息来源标记
    Args:
        source_type: "official" | "rumor" | "analysis"
    """
    badges = {
        "official": {"text": "官方", "bg": "#2e7d32", "color": "#fff"},
        "rumor": {"text": "传闻", "bg": "#fff3e0", "color": "#e65100"},
        "analysis": {"text": "分析", "bg": "#e3f2fd", "color": "#1565c0"},
    }
    b = badges.get(source_type, badges["official"])
    return f'<span style="display:inline-block;background:{b["bg"]};color:{b["color"]};padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;border:1px solid {b["color"]}20;margin-left:4px">{b["text"]}</span>'


def build_daily_report_html(
    report_date: str,
    sections: dict,
    disclaimer: str = ""
) -> str:
    """
    构建完整的日报 HTML 邮件

    Args:
        report_date: 报告日期，如 "2026年7月3日（周五）"
        sections: {
            "global_news": {"title": "...", "content": "预格式化的HTML"},
            "us_market": {"title": "...", "table_html": "...", "note": "..."},
            "japan_korea": {"title": "...", "table_html": "...", "note": "..."},
            "semiconductor": {"title": "...", "content": "..."},
            "zhengxi_views": {"title": "...", "content": "..."},
            "focus_points": {"title": "...", "items": [{"num":1, "color":"#d32f2f", "text":"..."}]},
        }
        disclaimer: 免责声明文本
    """
    # 颜色方案
    colors = {
        "header_bg": "#1a1a2e",
        "header_text": "#ffffff",
        "header_accent": "#e94560",
        "section_global": "#1565c0",
        "section_us": "#0d47a1",
        "section_jp_kr": "#c62828",
        "section_semi": "#6a1b9a",
        "section_zhengxi": "#2e7d32",
        "section_focus": "#e65100",
        "bg_body": "#f5f6fa",
        "bg_card": "#ffffff",
        "text_primary": "#212121",
        "border": "#e0e0e0",
    }

    # Section 构建器
    def build_section(title, content, color, icon=""):
        return f'''<div style="background:{colors['bg_card']};border-radius:8px;margin:16px 0;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08)">
    <div style="background:{color};padding:12px 20px;color:#fff;font-size:16px;font-weight:700;letter-spacing:0.5px">
        {icon} {title}
    </div>
    <div style="padding:16px 20px">
        {content}
    </div>
</div>'''

    # 头部 Banner
    header_html = f'''<div style="background:linear-gradient(135deg, {colors['header_bg']} 0%, #16213e 100%);padding:28px 24px;text-align:center;border-radius:8px 8px 0 0">
    <div style="font-size:12px;color:{colors['header_accent']};letter-spacing:4px;text-transform:uppercase;margin-bottom:8px">DAILY MARKET INTELLIGENCE</div>
    <h1 style="color:{colors['header_text']};font-size:22px;margin:8px 0;font-weight:700;line-height:1.4">
        每日全球市场与光电半导体情报
    </h1>
    <div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:8px">
        {report_date} | 自动生成 · 仅供参考
    </div>
</div>'''

    # 构建各 section
    sections_html = ""

    # 1. 全球新闻大事
    if "global_news" in sections:
        sections_html += build_section(
            sections["global_news"].get("title", "一、全球新闻大事"),
            sections["global_news"].get("content", ""),
            colors["section_global"],
            "🌍"
        )

    # 2. 美股三大指数
    if "us_market" in sections:
        us = sections["us_market"]
        us_content = us.get("table_html", "")
        if us.get("note"):
            us_content += f'''<div style="background:#e3f2fd;border-left:4px solid {colors['section_us']};padding:10px 14px;margin-top:12px;border-radius:0 4px 4px 0;font-size:13px;color:#555;line-height:1.6">
            {us["note"]}
        </div>'''
        sections_html += build_section(
            us.get("title", "二、美股三大指数"),
            us_content,
            colors["section_us"],
            "🇺🇸"
        )

    # 3. 日韩市场
    if "japan_korea" in sections:
        jk = sections["japan_korea"]
        jk_content = jk.get("table_html", "")
        if jk.get("note"):
            jk_content += f'''<div style="background:#ffebee;border-left:4px solid {colors['section_jp_kr']};padding:10px 14px;margin-top:12px;border-radius:0 4px 4px 0;font-size:13px;color:#555;line-height:1.6">
            {jk["note"]}
        </div>'''
        sections_html += build_section(
            jk.get("title", "三、日韩市场"),
            jk_content,
            colors["section_jp_kr"],
            "🇯🇵🇰🇷"
        )

    # 4. 光电半导体情报
    if "semiconductor" in sections:
        sections_html += build_section(
            sections["semiconductor"].get("title", "四、光电半导体情报追踪"),
            sections["semiconductor"].get("content", ""),
            colors["section_semi"],
            "🔬"
        )

    # 5. 郑希视角点评
    if "zhengxi_views" in sections:
        sections_html += build_section(
            sections["zhengxi_views"].get("title", "五、郑希视角点评"),
            sections["zhengxi_views"].get("content", ""),
            colors["section_zhengxi"],
            "💡"
        )

    # 6. 今日关注要点
    if "focus_points" in sections:
        fp = sections["focus_points"]
        items = fp.get("items", [])
        focus_items = ''.join(
            f'<div style="display:flex;align-items:flex-start;padding:10px 0;border-bottom:1px solid {colors["border"]}">'
            f'<span style="flex-shrink:0;width:28px;height:28px;border-radius:50%;background:{item["color"]};color:#fff;text-align:center;line-height:28px;font-size:14px;font-weight:700;margin-right:12px">{item["num"]}</span>'
            f'<span style="line-height:1.7;color:{colors["text_primary"]};font-size:14px">{item["text"]}</span>'
            f'</div>'
            for item in items
        )
        sections_html += build_section(
            fp.get("title", "六、今日关注要点"),
            f'<div style="padding:4px 0">{focus_items}</div>',
            colors["section_focus"],
            "🎯"
        )

    # 免责声明
    disclaimer_html = f'''<div style="background:#fafafa;border-radius:8px;padding:16px 20px;margin:16px 0;font-size:11px;color:#999;line-height:1.6;text-align:center">
    {disclaimer or "⚠️ 以上内容仅供参考，不构成投资建议。投资有风险，决策需谨慎。"}
</div>'''

    # 底部
    footer_html = f'''<div style="text-align:center;padding:16px 0;color:#bbb;font-size:11px">
    每日全球市场与光电半导体情报 · 自动生成于 {report_date}
</div>'''

    # 组装完整 HTML
    full_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="format-detection" content="telephone=no">
<title>每日全球市场与光电半导体情报 - {report_date}</title>
</head>
<body style="margin:0;padding:0;background:{colors['bg_body']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;color:{colors['text_primary']};line-height:1.6;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">
<div style="max-width:680px;margin:0 auto;padding:12px">
    {header_html}
    <div style="background:{colors['bg_body']};padding:4px 0 0 0">
        {sections_html}
        {disclaimer_html}
        {footer_html}
    </div>
</div>
</body>
</html>'''

    return full_html


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="邮件推送工具 - 观点推送到邮箱（微信可收通知）")
    subparsers = parser.add_subparsers(dest="command", help="操作类型")

    # text
    tp = subparsers.add_parser("text", help="发送纯文本")
    tp.add_argument("content", help="文本内容")
    tp.add_argument("--title", "-t", default="观点推送", help="邮件标题")

    # markdown
    mp = subparsers.add_parser("markdown", help="发送 Markdown（自动转 HTML）")
    mp.add_argument("--title", "-t", default="量化观点推送", help="邮件标题")
    mp.add_argument("--content", "-c", help="Markdown 内容")
    mp.add_argument("--file", "-f", help="从文件读取")

    # pipe
    pp = subparsers.add_parser("pipe", help="从管道/stdin 读取")
    pp.add_argument("--title", "-t", default="量化观点推送", help="邮件标题")

    # viewpoint
    vp = subparsers.add_parser("viewpoint", help="观点模板推送")
    vp.add_argument("--data", "-d", help="JSON 格式观点数据")
    vp.add_argument("--file", "-f", help="JSON 文件")

    # test
    subparsers.add_parser("test", help="发送测试邮件")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "test":
        subject = "✅ 邮件推送测试"
        body_html = markdown_to_html(f"""# 🎉 推送通道已就绪

> 测试时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 通道信息

- **发件邮箱**：{SMTP_CONFIG['user']}
- **收件邮箱**：{TO_EMAIL}
- **推送方式**：163 SMTP → 邮箱 → 微信 QQ邮箱提醒

---

<font color="info">如果你收到这封邮件，说明推送通道配置成功！</font>
""")
        result = send_email(subject, body_html)
        print(f"{'✅' if result['success'] else '❌'} {result['message']}")
        return

    if args.command == "text":
        subject = args.title
        body = args.content
        result = send_email(subject, body, "plain")

    elif args.command == "markdown":
        subject = args.title
        content = args.content or ""
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                content = f.read()
        body_html = markdown_to_html(content)
        result = send_email(subject, body_html)

    elif args.command == "pipe":
        subject = args.title
        content = sys.stdin.read().strip()
        if not content:
            print("❌ 没有接收到任何内容")
            return
        body_html = markdown_to_html(content)
        result = send_email(subject, body_html)

    elif args.command == "viewpoint":
        if args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                vp_data = json.load(f)
        elif args.data:
            vp_data = json.loads(args.data)
        else:
            vp_data = json.load(sys.stdin)

        subject = vp_data.get("title", "量化观点推送")
        date = vp_data.get("date", datetime.now().strftime("%Y-%m-%d %H:%M"))
        body_html = markdown_to_html(build_viewpoint_html(
            title=vp_data.get("title", "观点推送"),
            date=date,
            viewpoints=vp_data.get("viewpoints", []),
            signals=vp_data.get("signals", []),
            summary=vp_data.get("summary", ""),
        ))
        result = send_email(subject, body_html)

    else:
        parser.print_help()
        return

    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"   收件人：{TO_EMAIL}")
        print(f"   💡 微信绑定 QQ邮箱提醒即可在微信收到通知")
    else:
        print(f"❌ {result['message']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
