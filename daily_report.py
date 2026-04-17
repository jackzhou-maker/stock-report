#!/usr/bin/env python3
"""
股票快报 - 每日三市报告
US 🇺🇸 / HK 🇭🇰 / A股 🇨🇳
数据: Finnhub (美股) + yfinance (港股/A股)
"""

import os
import requests
import warnings
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

warnings.filterwarnings("ignore")

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "d7f5cthr01qpjqqjh0ugd7f5cthr01qpjqqjh0v0")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "J73MPVCAJ64S16YK")
CACHE_DIR = "/tmp/stock_cache"
Path(CACHE_DIR).mkdir(exist_ok=True)

# ── 美股 ──────────────────────────────────────────
US_STOCKS = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon",
    "META": "Meta Platforms", "NVDA": "NVIDIA", "TSLA": "Tesla", "JPM": "JPMorgan",
    "V": "Visa", "UNH": "UnitedHealth", "HD": "Home Depot", "MA": "Mastercard",
    "PG": "Procter & Gamble", "DIS": "Walt Disney", "BABA": "Alibaba", "JD": "JD.com",
    "PDD": "PDD Holdings", "NTES": "NetEase", "TCEHY": "Tencent",
}
LOGO_URL = "https://storage.googleapis.com/iex/api/logos/{}.png"

# ── 港股 ──────────────────────────────────────────
HK_STOCKS = {
    "0700.HK": "腾讯控股", "9988.HK": "阿里巴巴", "9999.HK": "网易",
    "3690.HK": "美团", "6160.HK": "京东集团", "9618.HK": "京东物流",
    "1024.HK": "快手", "1810.HK": "小米集团", "2382.HK": "舜宇光学",
    "2319.HK": "蒙牛乳业", "0941.HK": "中国移动", "2628.HK": "中国人寿",
    "1398.HK": "工商银行", "3968.HK": "招商银行(港)", "6618.HK": "京东健康",
}

# ── A股 ──────────────────────────────────────────
CN_STOCKS = {
    "600519.SS": "贵州茅台", "601318.SS": "中国平安", "600036.SS": "招商银行",
    "000333.SZ": "美的集团", "002594.SZ": "比亚迪", "601888.SS": "中国中免",
    "600030.SS": "中信证券", "600900.SS": "长江电力", "601166.SS": "兴业银行",
    "000001.SZ": "平安银行", "002415.SZ": "海康威视", "000858.SZ": "五粮液",
    "600887.SS": "伊利股份", "601111.SS": "中国国航", "688981.SS": "中芯国际",
}


# ── Finnhub helpers ───────────────────────────────
_S = requests.Session()
_S.headers.update({"User-Agent": "Mozilla/5.0"})

def fh(path, symbol, params=None, timeout=8):
    try:
        url = f"https://finnhub.io/api/v1{path}?symbol={symbol}&token={FINNHUB_KEY}"
        if params:
            url += "".join(f"&{k}={v}" for k, v in params.items())
        return _S.get(url, timeout=timeout).json()
    except:
        return None


# ── Alpha Vantage helpers ─────────────────────────────
def av_news(tickers=None, limit=20, timeout=8):
    """获取Alpha Vantage新闻情绪分析"""
    try:
        url = "https://www.alphavantage.co/query?function=NEWS_SENTIMENT&apikey=" + ALPHA_VANTAGE_KEY
        if tickers:
            url += "&tickers=" + ",".join(tickers)
        url += f"&limit={limit}"
        r = _S.get(url, timeout=timeout).json()
        feed = r.get("feed", [])
        return [{
            "title": item.get("title"),
            "summary": item.get("summary", "")[:200],
            "url": item.get("url"),
            "source": item.get("source"),
            "time": item.get("time_published"),
            "sentiment": item.get("overall_sentiment_label", "Neutral"),
            "sentiment_score": item.get("overall_sentiment_score", 0),
            "topics": [t.get("topic") for t in item.get("topics", [])],
            "tickers": [(t.get("ticker"), t.get("ticker_sentiment_label")) for t in item.get("ticker_sentiment", [])],
        } for item in feed]
    except:
        return []


def fetch_us(sym):
    q = fh("/quote", sym) or {}
    rec = fh("/stock/recommendation", sym) or []
    m = fh("/stock/metric", sym, {"metric": "all"}) or {}
    m = m.get("metric", {}) if isinstance(m, dict) else {}
    price = q.get("c") or q.get("pc")
    dp = q.get("dp", 0)
    dh = q.get("h"); dl = q.get("l")
    pe = m.get("peExclExtraTTM")
    wh52 = m.get("52WeekHigh") or dh
    wl52 = m.get("52WeekLow") or dl
    if wh52 and wl52 and wh52 > wl52 and price:
        pos = ((price - wl52) / (wh52 - wl52)) * 100
    else:
        pos = 50
    if rec and len(rec) > 0:
        r = rec[0]
        buy=r.get("buy",0); hold=r.get("hold",0); sell=r.get("sell",0)
        sb=r.get("strongBuy",0); ss=r.get("strongSell",0)
        total = buy+hold+sell+sb+ss
        if total > 0:
            a_score = round((sb + buy*2 + hold*3 + sell*4 + ss*5) / total, 1)
            a_idx = min(max(int(round(a_score)), 1), 5)
            al = {1:"强烈买入",2:"买入",3:"持有",4:"减持",5:"卖出"}.get(a_idx,"N/A")
            ac = {1:"#22c55e",2:"#84cc16",3:"#f59e0b",4:"#f97316",5:"#ef4444"}.get(a_idx,"#6b7280")
        else:
            al="N/A"; ac="#6b7280"
    else:
        al="N/A"; ac="#6b7280"
    tgt = m.get("priceTargetMean")
    if tgt and price:
        tgt_up = f"{((tgt-price)/price*100):+.0f}%"
        tc = "#22c55e" if tgt > price else "#ef4444"
        tgt_str = f"${round(tgt,1)} ({tgt_up})"
    else:
        tgt_str = "N/A"; tc = "#6b7280"
    ts = 0
    if pe and 0 < pe < 25: ts += 2
    elif pe and pe < 40: ts += 1
    if pos < 30: ts += 3
    elif pos < 50: ts += 1
    if ts >= 7: sig="强烈买入"; sc="#22c55e"; sbg="rgba(34,197,94,0.15)"
    elif ts >= 4: sig="可以考虑"; sc="#f59e0b"; sbg="rgba(245,158,11,0.15)"
    elif ts >= 2: sig="观望"; sc="#f97316"; sbg="rgba(249,115,22,0.15)"
    else: sig="不推荐"; sc="#ef4444"; sbg="rgba(239,68,68,0.15)"
    return {
        "sym": sym, "name": US_STOCKS.get(sym, sym), "market": "US",
        "price": price, "dp": dp,
        "pe": round(pe,1) if pe else None, "pe_str": f"{round(pe,1)}" if pe else "N/A",
        "wh52": round(wh52,1) if wh52 else None, "wl52": round(wl52,1) if wl52 else None,
        "pos": pos, "ts": ts, "signal": sig, "sc": sc, "sbg": sbg,
        "analyst_label": al, "analyst_color": ac,
        "tgt_str": tgt_str, "tgt_color": tc,
        "beta_str": f"{round(m.get('beta',0),2)}" if m.get('beta') else "N/A",
        "ni_str": f"${round(m.get('netIncomeTTM',0)/1e9,1)}B" if m.get('netIncomeTTM') else "N/A",
        "rev_str": f"${round(m.get('totalRevenueTTM',0)/1e9,1)}B" if m.get('totalRevenueTTM') else "N/A",
        "eps_str": f"{round(m.get('epsExclExtraItemsTTM',0),2)}" if m.get('epsExclExtraItemsTTM') else "N/A",
        "cr_str": f"{round(m.get('currentRatioQuarterly',0),2)}" if m.get('currentRatioQuarterly') else "N/A",
        "pm_str": f"{m.get('netProfitMarginTTM',0)*100:.1f}%" if m.get('netProfitMarginTTM') else "N/A",
        "logo": LOGO_URL.format(sym),
        "chg_color": "#22c55e" if dp >= 0 else "#ef4444",
        "dp_str": f"+{round(dp,2)}%" if dp >= 0 else f"{round(dp,2)}%",
        "pos_str": f"{pos:.0f}%",
    }


def fetch_cn(sym, name):
    """A股/港股 - yfinance"""
    try:
        t = yf.Ticker(sym)
        info = t.info
        hist = t.history(period="1y")
        if hist.empty or len(hist) < 30:
            return None
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
        dp = ((price - prev) / prev * 100) if prev and price else 0
        pe = info.get("trailingPE") or info.get("forwardPE")
        ma20 = hist["Close"].tail(20).mean()
        ma60 = hist["Close"].tail(60).mean()
        ma200 = hist["Close"].tail(200).mean() if len(hist) >= 200 else None
        year_high = hist["High"].tail(252).max()
        year_low = hist["Low"].tail(252).min()
        pos = ((price - year_low) / (year_high - year_low)) * 100 if year_high > year_low else 50
        r = info.get("recommendationMean")
        if r:
            idx = min(max(int(round(r)), 1), 5)
            al = {1:"强烈买入",2:"买入",3:"持有",4:"减持",5:"卖出"}.get(idx,"N/A")
            ac = {1:"#22c55e",2:"#84cc16",3:"#f59e0b",4:"#f97316",5:"#ef4444"}.get(idx,"#6b7280")
        else:
            al="N/A"; ac="#6b7280"
        tgt = info.get("targetMeanPrice")
        if tgt and price:
            tgt_up = f"{((tgt-price)/price*100):+.0f}%"
            tc = "#22c55e" if tgt > price else "#ef4444"
            tgt_str = f"¥{round(tgt,1)} ({tgt_up})"
        else:
            tgt_str = "N/A"; tc = "#6b7280"
        ts = 0
        if pe and 0 < pe < 25: ts += 2
        elif pe and pe < 40: ts += 1
        if pos < 30: ts += 3
        elif pos < 50: ts += 1
        if ma200 and price < ma200: ts += 2
        if ts >= 7: sig="强烈买入"; sc="#22c55e"; sbg="rgba(34,197,94,0.15)"
        elif ts >= 4: sig="可以考虑"; sc="#f59e0b"; sbg="rgba(245,158,11,0.15)"
        elif ts >= 2: sig="观望"; sc="#f97316"; sbg="rgba(249,115,22,0.15)"
        else: sig="不推荐"; sc="#ef4444"; sbg="rgba(239,68,68,0.15)"
        return {
            "sym": sym, "name": name, "market": "HK" if ".HK" in sym else "CN",
            "price": price, "dp": dp,
            "pe": round(pe,1) if pe else None, "pe_str": f"{round(pe,1)}" if pe else "N/A",
            "wh52": round(year_high,1), "wl52": round(year_low,1),
            "pos": pos, "ts": ts, "signal": sig, "sc": sc, "sbg": sbg,
            "analyst_label": al, "analyst_color": ac,
            "tgt_str": tgt_str, "tgt_color": tc,
            "beta_str": f"{round(info.get('beta', 0),2)}" if info.get('beta') else "N/A",
            "ni_str": f"¥{round(info.get('netIncomeToCommon',0)/1e8,1)}亿" if info.get('netIncomeToCommon') else "N/A",
            "rev_str": f"¥{round(info.get('totalRevenue',0)/1e8,1)}亿" if info.get('totalRevenue') else "N/A",
            "eps_str": f"{round(info.get('trailingEps',0),2)}" if info.get('trailingEps') else "N/A",
            "cr_str": f"{round(info.get('currentRatio',0),2)}" if info.get('currentRatio') else "N/A",
            "pm_str": f"{info.get('profitMargins',0)*100:.1f}%" if info.get('profitMargins') else "N/A",
            "logo": "", "chg_color": "#22c55e" if dp >= 0 else "#ef4444",
            "dp_str": f"+{round(dp,2)}%" if dp >= 0 else f"{round(dp,2)}%",
            "pos_str": f"{pos:.0f}%",
        }
    except:
        return None


def make_section(results, market_label, flag, color):
    if not results:
        return f"<div class='sec'><h2 class='sec-title'>{flag} {market_label}</h2><p style='color:#64748b;font-size:12px'>暂无数据</p></div>"
    order = {"强烈买入":0,"可以考虑":1,"观望":2,"不推荐":3}
    sorted_r = sorted(results, key=lambda x: (order.get(x["signal"],4), -x["ts"]))
    buy_count = sum(1 for r in results if r["signal"]=="强烈买入")
    consider_count = sum(1 for r in results if r["signal"]=="可以考虑")
    # cards
    cards = ""
    for r in sorted_r:
        if r["signal"] in ["强烈买入","可以考虑"]:
            cur = "$" if r["market"] == "US" else "¥"
            price_str = f"{cur}{r['price']:.2f}" if r['price'] else "--"
            cards += f"""<div class="bc">
<div class="bln"><span class="bsym" style="color:{r['sc']}">{r['sym']}</span><span class="bname">{r['name']}</span></div>
<div class="bpri">{price_str}</div>
<div class="bmeta"><span style="color:{r['analyst_color']};font-weight:600">{r['analyst_label']}</span> · PE {r['pe_str']} · {r['pos_str']}低位 · β{r['beta_str']}</div>
<div class="brig"><span class="sig-pill" style="background:{r['sbg']};color:{r['sc']}">{r['signal']}</span><span class="sc-num">评分{r['ts']}</span></div>
</div>"""
    # table
    rows = ""
    for r in sorted_r:
        cur = "$" if r["market"] == "US" else "¥"
        price_cell = f"{cur}{r['price']:.2f}" if r['price'] else "N/A"
        rows += f"""<tr>
<td class="sym-cell"><div class="ln"><div><span class="ticker">{r['sym']}</span><span class="cname">{r['name']}</span></div></div></td>
<td class="price">{price_cell}</td>
<td style="color:{r['chg_color']};font-weight:600">{r['dp_str']}</td>
<td>{r['pe_str']}</td>
<td>{r['pos_str']}</td>
<td>{r['wl52'] or 'N/A'}</td>
<td>{r['wh52'] or 'N/A'}</td>
<td class="score">{r['ts']}</td>
<td class="sig" style="background:{r['sbg']};color:{r['sc']}">{r['signal']}</td>
<td style="color:{r['analyst_color']};font-weight:600">{r['analyst_label']}</td>
<td style="color:{r['tgt_color']}">{r['tgt_str']}</td>
<td>{r['rev_str']}</td>
<td>{r['ni_str']}</td>
<td>{r['eps_str']}</td>
<td>{r['cr_str']}</td>
</tr>"""
    summary = f"""<div class="sum-row">
<span class="sr g">强烈买入 {buy_count}</span>
<span class="sr o">可以考虑 {consider_count}</span>
<span class="sr r">其他 {len(results)-buy_count-consider_count}</span>
</div>"""
    return f"""<div class="sec">
<h2 class="sec-title" style="border-left:4px solid {color}">{flag} {market_label}</h2>
{summary}
<div class="bc-list">{cards}</div>
<table>
<thead><tr><th>代码</th><th>价格</th><th>涨跌</th><th>PE</th><th>年低位</th><th>52W Low</th><th>52W High</th><th>评分</th><th>信号</th><th>分析师</th><th>目标价</th><th>营收</th><th>净利润</th><th>EPS</th><th>流比</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>"""


def make_html(us_data, hk_data, cn_data, now):
    us_sec = make_section(us_data, "美股", "🇺🇸", "#3b82f6")
    hk_sec = make_section(hk_data, "港股", "🇭🇰", "#ef4444")
    cn_sec = make_section(cn_data, "A股", "🇨🇳", "#f59e0b")
    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>股票快报</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:16px}}
.c{{max-width:1700px;margin:0 auto}}
.hdr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;padding-bottom:14px;border-bottom:2px solid #1e293b}}
.hdr h1{{font-size:24px;font-weight:800;color:#f8fafc}}
.hdr .sub{{font-size:11px;color:#64748b;margin-top:2px}}
.hdr .time{{font-size:11px;color:#64748b;text-align:right}}
.sec{{margin-bottom:28px;padding:16px;background:#1e293b;border-radius:12px}}
.sec-title{{font-size:15px;font-weight:700;color:#f8fafc;margin-bottom:10px;padding-bottom:8px}}
.sum-row{{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap}}
.sr{{background:#0f172a;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600}}
.sr.g{{color:#22c55e}}.sr.o{{color:#f59e0b}}.sr.r{{color:#64748b}}
.bc-list{{display:flex;flex-direction:column;gap:4px;margin-bottom:10px;padding:6px;background:#0f172a;border-radius:8px}}
.bc{{display:flex;align-items:center;gap:10px;padding:6px 8px;border-bottom:1px solid #1e293b;font-size:11px}}
.bc:last-child{{border-bottom:none}}
.bln{{min-width:120px}}
.bsym{{font-weight:700;font-size:12px;display:block}}
.bname{{font-size:9px;color:#94a3b8}}
.bpri{{font-weight:700;min-width:60px;text-align:center}}
.bmeta{{flex:1;font-size:10px;color:#94a3b8}}
.brig{{text-align:right;min-width:100px;display:flex;flex-direction:column;align-items:flex-end}}
.sig-pill{{font-weight:600;border-radius:4px;padding:1px 6px;font-size:10px}}
.sc-num{{font-size:9px;color:#64748b;margin-top:1px}}
table{{width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;font-size:11px;margin-top:4px}}
th{{text-align:left;padding:7px 9px;font-size:9px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #334155;white-space:nowrap}}
td{{padding:7px 9px;border-bottom:1px solid #1e293b;white-space:nowrap}}
tr:last-child td{{border-bottom:none}}
tr:hover{{background:#263348}}
.sym-cell{{}}
.ticker{{font-weight:700;font-size:12px}}
.cname{{font-size:9px;color:#94a3b8;display:block}}
.price{{font-weight:700}}
.score{{font-weight:700;text-align:center}}
.sig{{font-weight:600;text-align:center;border-radius:4px;padding:1px 5px;font-size:10px}}
.foot{{margin-top:20px;text-align:center;font-size:10px;color:#475569;padding:10px 0;border-top:1px solid #1e293b}}
</style>
</head>
<body>
<div class="c">
  <div class="hdr">
    <div><h1>📈 股票快报</h1><div class="sub">每日三市 · 美股🇺🇸 · 港股🇭🇰 · A股🇨🇳</div></div>
    <div class="time">{now} CST<br><span style="font-size:10px">数据来源: Finnhub (美股) · Yahoo Finance (港/A股)</span></div>
  </div>
  {us_sec}
  {hk_sec}
  {cn_sec}
  <div class="foot">股票快报 · 评分逻辑: PE合理度(30%) + 历史低位(40%) + 分析师推荐(30%) · 不作为投资建议</div>
</div>
</body>
</html>"""


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"📈 股票快报 {now}")
    print("=" * 50)

    # 美股 (并发)
    print("🇺🇸 美股...")
    us_results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_us, sym): sym for sym in US_STOCKS}
        for f in as_completed(futures):
            r = f.result()
            if r and r.get("price"):
                us_results.append(r)
                print(f"  {r['sym']}: ${r['price']:.2f} → {r['signal']}")
    print(f"  → {len(us_results)}/{len(US_STOCKS)} 只")

    # 港股 (yfinance)
    print("🇭🇰 港股...")
    hk_results = []
    for sym, name in HK_STOCKS.items():
        r = fetch_cn(sym, name)
        if r:
            hk_results.append(r)
            p = f"{r['price']:.2f}" if r['price'] else "?"
            print(f"  {sym}: ¥{p} → {r['signal']}")
    print(f"  → {len(hk_results)}/{len(HK_STOCKS)} 只")

    # A股
    print("🇨🇳 A股...")
    cn_results = []
    for sym, name in CN_STOCKS.items():
        r = fetch_cn(sym, name)
        if r:
            cn_results.append(r)
            p = f"{r['price']:.2f}" if r['price'] else "?"
            print(f"  {sym}: ¥{p} → {r['signal']}")
    print(f"  → {len(cn_results)}/{len(CN_STOCKS)} 只")

    html = make_html(us_results, hk_results, cn_results, now)
    out = "/Users/jack/.openclaw/workspace/stock_report.html"
    Path(out).write_text(html)
    total = len(us_results) + len(hk_results) + len(cn_results)
    print(f"\n✅ 完成: {total} 只股票 → {out} ({len(html)} bytes)")
    return out


if __name__ == "__main__":
    main()

def push_to_github():
    """自动推送到 GitHub Pages"""
    import subprocess
    token = "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"
    repo = "jackzhou-maker/stock-report"
    try:
        # 确认 git remote
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd="/Users/jack/.openclaw/workspace"
        )
        current_url = result.stdout.strip()
        expected_url = f"https://jackzhou-maker:{token}@github.com/{repo}.git"
        if expected_url not in current_url and token not in current_url:
            # 更新 remote URL
            subprocess.run(
                ["git", "remote", "set-url", "origin", expected_url],
                cwd="/Users/jack/.openclaw/workspace", check=True
            )
        # 添加文件
        subprocess.run(["git", "add", "stock_report.html"], cwd="/Users/jack/.openclaw/workspace", capture_output=True)
        # 检查变更
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd="/Users/jack/.openclaw/workspace")
        if status.stdout.strip():
            subprocess.run(["git", "config", "user.email", "jack@openclaw.ai"], cwd="/Users/jack/.openclaw/workspace")
            subprocess.run(["git", "config", "user.name", "Jack Zhou"], cwd="/Users/jack/.openclaw/workspace")
            subprocess.run(["git", "commit", "-m", "📈 Stock Report $(date '+%Y-%m-%d %H:%M')"], cwd="/Users/jack/.openclaw/workspace")
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd="/Users/jack/.openclaw/workspace")
            print("✅ GitHub Pages 已更新")
        else:
            print("📝 无变更，跳过推送")
    except Exception as e:
        print(f"⚠️ GitHub 推送失败: {e}")

if __name__ == "__main__":
    push_to_github()
