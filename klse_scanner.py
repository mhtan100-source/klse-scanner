"""
KLSE 莊家思維掃描器
- 數據來源：yfinance（Bursa Malaysia 股票）
- 邏輯：C系列收縮（V41規則）
- 通知：Telegram + SendGrid Email
- 界面：Flask Web
- 股票：174只 Bursa主板
"""

import os
import time
import threading
import logging
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from flask import Flask, render_template_string
import pytz

# ── 日誌設置 ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ── 環境變量 ──────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
ALERT_EMAIL      = os.environ.get('ALERT_EMAIL', 'mhtan100@gmail.com')
SCANNER_URL      = os.environ.get('SCANNER_URL', '')   # Railway 部署後填入

# ── KLSE 174只股票 ────────────────────────────────────────
KLSE_SYMBOLS = [
    # 金融
    '1155.KL','1023.KL','1295.KL','5819.KL','1066.KL',
    '1015.KL','5258.KL','5185.KL','1277.KL','1082.KL',
    '6947.KL','6888.KL','5099.KL','5235.KL','6399.KL',
    '5115.KL','7107.KL','1597.KL','5168.KL','6012.KL',
    # 能源/石油
    '5183.KL','6033.KL','5071.KL','5347.KL','5218.KL',
    '7277.KL','3816.KL','5285.KL','7084.KL','5132.KL',
    '0207.KL','5225.KL','7179.KL','0101.KL','0216.KL',
    '7253.KL','0172.KL','5264.KL','5020.KL',
    # 電信
    '4863.KL','0082.KL','5031.KL','0023.KL','3037.KL',
    '0166.KL','5136.KL','0072.KL','0011.KL','5212.KL',
    # 消費/零售
    '4707.KL','3026.KL','7052.KL','5252.KL','3689.KL',
    '5015.KL','5014.KL','3417.KL','3069.KL','4316.KL',
    '7668.KL','3867.KL','5242.KL','7178.KL','2836.KL',
    '6556.KL','3255.KL','2658.KL','4162.KL',
    # 棕榈油/農業
    '1961.KL','2445.KL','4197.KL','2291.KL','1899.KL',
    '2038.KL','5029.KL','2220.KL','1724.KL',
    # 科技
    '0146.KL','2771.KL','5026.KL','3948.KL','5116.KL',
    '1929.KL','5135.KL','0148.KL','5033.KL','4731.KL',
    '3182.KL','4715.KL','5141.KL','5148.KL','8583.KL',
    # 工業
    '3336.KL','1996.KL','9679.KL','3549.KL','1589.KL',
    '5211.KL','9261.KL','2194.KL','3476.KL','5053.KL',
    '6742.KL','2267.KL','1562.KL','7076.KL','0177.KL',
    '5878.KL','7153.KL','5027.KL','7113.KL','0138.KL',
    '7090.KL','9814.KL','5243.KL','3557.KL','5079.KL',
    '3794.KL','5007.KL','9121.KL','8869.KL','9075.KL',
    '5139.KL','8230.KL',
    # 房地產/REIT
    '0197.KL','7212.KL','4665.KL','0049.KL','5296.KL',
    '0078.KL','0090.KL','7034.KL','1301.KL','5236.KL',
    '5180.KL','5247.KL','5246.KL','7028.KL','6599.KL',
    '4898.KL','5008.KL',
    # 醫療
    '0097.KL','0196.KL','0065.KL','9296.KL','7073.KL',
    '0050.KL','0186.KL',
    # 運輸/物流
    '5216.KL','5111.KL','5227.KL','5124.KL','5269.KL',
    '5275.KL','5106.KL','5109.KL','5119.KL','3786.KL',
    # 其他/補充主板大型股
    '4635.KL','5983.KL','1619.KL','7293.KL','4588.KL',
    '5081.KL','7222.KL','4609.KL','0051.KL',
    '4677.KL','5062.KL','5200.KL','2828.KL',
    '5073.KL','7182.KL','3743.KL',
]

# 去重
KLSE_SYMBOLS = list(dict.fromkeys(KLSE_SYMBOLS))

TIMEFRAMES = {
    '1D': {'period': '1y',  'interval': '1d'},
    '4H': {'period': '60d', 'interval': '1h'},
    '1H': {'period': '30d', 'interval': '1h'},
}

MYT = pytz.timezone('Asia/Kuala_Lumpur')

app = Flask(__name__)

scan_results   = []
last_scan_time = None
notified_set   = set()

# ══════════════════════════════════════════════════════════
# 數據獲取
# ══════════════════════════════════════════════════════════

def fetch_ohlcv(symbol, tf_cfg, tf_label):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=tf_cfg['period'], interval=tf_cfg['interval'])
        if df is None or df.empty:
            return None
        df = df[['Open','High','Low','Close','Volume']].copy()
        df.columns = ['open','high','low','close','volume']
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        if tf_label == '4H':
            df = df.resample('4h').agg({
                'open':'first','high':'max','low':'min','close':'last','volume':'sum'
            }).dropna()
        return df if len(df) >= 20 else None
    except Exception as e:
        logger.debug(f"{symbol} {tf_label}: {e}")
        return None

# ══════════════════════════════════════════════════════════
# Stage（僅1D用）
# ══════════════════════════════════════════════════════════

def get_stage(df):
    if len(df) < 200:
        return '-'
    c = df['close']
    ma50  = c.rolling(50).mean()
    ma150 = c.rolling(150).mean()
    ma200 = c.rolling(200).mean()
    cur50,prev50   = ma50.iloc[-1], ma50.iloc[-10]
    cur150,prev150 = ma150.iloc[-1], ma150.iloc[-10]
    cur200,prev200 = ma200.iloc[-1], ma200.iloc[-10]
    price = c.iloc[-1]
    up50  = cur50  > prev50
    up150 = cur150 > prev150
    up200 = cur200 > prev200
    ab50  = price > cur50
    ab150 = price > cur150
    ab200 = price > cur200
    if up50 and up150 and up200 and ab50 and ab150 and ab200:
        return 'S2'
    if not up50 and not up150 and not up200 and not ab50 and not ab150 and not ab200:
        return 'S4'
    if up150 and up200 and ab150 and ab200:
        return 'S1'
    if not up150 and not up200 and not ab150 and not ab200:
        return 'S3'
    return 'S0'

# ══════════════════════════════════════════════════════════
# C系列邏輯（V41）
# ══════════════════════════════════════════════════════════

def is_pivot_low(df, i, length=5):
    lows = df['low'].values
    if i < length or i >= len(lows) - length:
        return False
    pivot = lows[i]
    return (all(pivot <= lows[i-j] for j in range(1, length+1)) and
            all(pivot <= lows[i+j] for j in range(1, length+1)))

def has_three_combo(df, start_i, end_i):
    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows_  = df['low'].values
    if end_i - start_i < 2:
        return False
    for i in range(start_i, end_i - 1):
        count = 0
        for j in range(i, min(i+3, end_i+1)):
            body = abs(closes[j] - opens[j])
            rng  = highs[j] - lows_[j]
            is_bear = closes[j] < opens[j]
            is_doji = rng > 0 and body/rng < 0.3
            if is_bear or is_doji:
                count += 1
            else:
                break
        if count >= 3:
            return True
    return False

def find_next_c(df, search_from, prev_low, length=5):
    n = len(df)
    lows  = df['low'].values
    highs = df['high'].values

    pivot_idx = None
    for i in range(search_from + length, n - length):
        if is_pivot_low(df, i, length) and lows[i] > prev_low:
            pivot_idx = i
            break
    if pivot_idx is None:
        return None

    seg_high_val, seg_high_idx = -1, search_from
    for i in range(search_from, pivot_idx):
        if highs[i] > seg_high_val:
            seg_high_val = highs[i]
            seg_high_idx = i

    if seg_high_val <= 0:
        return None
    if not has_three_combo(df, seg_high_idx, pivot_idx):
        return None
    if pivot_idx - seg_high_idx < 3:
        return None

    return seg_high_val, seg_high_idx, lows[pivot_idx], pivot_idx

def find_c_series(df):
    n = len(df)
    c_list = []

    for start in range(0, n - 20):
        result = find_next_c(df, start, 0.0)
        if result:
            hv, hi, lv, li = result
            pct = (hv - lv) / hv * 100
            if pct >= 3.0:
                c_list.append({'hv':hv,'hi':hi,'lv':lv,'li':li,'pct':pct})
                break

    if not c_list:
        return []

    for _ in range(5):
        prev = c_list[-1]
        result = find_next_c(df, prev['li'], prev['lv'])
        if not result:
            break
        hv, hi, lv, li = result
        pct = (hv - lv) / hv * 100
        min_pct = prev['pct'] / 2 + 0.5
        max_pct = prev['pct']
        if not (min_pct < pct < max_pct):
            break
        c_list.append({'hv':hv,'hi':hi,'lv':lv,'li':li,'pct':pct})

    return c_list

# ══════════════════════════════════════════════════════════
# 掃描單一股票
# ══════════════════════════════════════════════════════════

def scan_symbol(symbol):
    row = {'symbol': symbol}
    for tf_label, tf_cfg in TIMEFRAMES.items():
        df = fetch_ohlcv(symbol, tf_cfg, tf_label)
        if df is None:
            row[tf_label] = '-'
            continue
        c_list = find_c_series(df)
        c_count = len(c_list)
        if tf_label == '1D':
            stage = get_stage(df)
            if c_count == 0:
                row[tf_label] = stage
            else:
                entry = '🎯' if 3.0 <= c_list[-1]['pct'] <= 10.0 else ''
                row[tf_label] = f"{stage} C{c_count}{entry}"
        else:
            if c_count == 0:
                row[tf_label] = '-'
            else:
                entry = '🎯' if 3.0 <= c_list[-1]['pct'] <= 10.0 else ''
                row[tf_label] = f"C{c_count}{entry}"
        time.sleep(0.2)
    return row

# ══════════════════════════════════════════════════════════
# 通知
# ══════════════════════════════════════════════════════════

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram 錯誤: {e}")

def send_email(subject, html_body):
    if not SENDGRID_API_KEY:
        return
    try:
        requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={
                'Authorization': f'Bearer {SENDGRID_API_KEY}',
                'Content-Type': 'application/json'
            },
            json={
                'personalizations': [{'to': [{'email': ALERT_EMAIL}]}],
                'from': {'email': 'scanner@mhtan.trade', 'name': 'KLSE Scanner'},
                'subject': subject,
                'content': [{'type': 'text/html', 'value': html_body}]
            },
            timeout=15
        )
    except Exception as e:
        logger.error(f"Email 錯誤: {e}")

def check_and_notify(results):
    global notified_set
    entry_signals = []
    for row in results:
        for tf in ['1D','4H','1H']:
            cell = row.get(tf, '')
            if '🎯' in cell:
                key = f"{row['symbol']}_{tf}_{cell}"
                if key not in notified_set:
                    notified_set.add(key)
                    entry_signals.append({'symbol': row['symbol'], 'tf': tf, 'signal': cell})
    if not entry_signals:
        return

    now_str = datetime.now(MYT).strftime('%Y-%m-%d %H:%M')
    url_line = f'\n🔗 <a href="{SCANNER_URL}">{SCANNER_URL}</a>' if SCANNER_URL else ''
    msg_lines = [f"🇲🇾 <b>KLSE 莊家思維信號</b> {now_str}{url_line}\n"]
    for s in entry_signals:
        msg_lines.append(f"🎯 <b>{s['symbol']}</b> [{s['tf']}] {s['signal']}")
    send_telegram('\n'.join(msg_lines))

    rows_html = ''.join(
        f"<tr><td>{s['symbol']}</td><td>{s['tf']}</td><td>{s['signal']}</td></tr>"
        for s in entry_signals
    )
    url_html = f'<p>🔗 掃描器：<a href="{SCANNER_URL}">{SCANNER_URL}</a></p>' if SCANNER_URL else ''
    html = f"""
    <h2>🇲🇾 KLSE 莊家思維入場信號</h2>
    <p>掃描時間：{now_str} MYT</p>
    {url_html}
    <table border="1" cellpadding="6" style="border-collapse:collapse">
      <tr><th>股票</th><th>時框</th><th>信號</th></tr>
      {rows_html}
    </table>
    """
    send_email(f"KLSE 信號 {now_str}", html)

# ══════════════════════════════════════════════════════════
# 掃描循環
# ══════════════════════════════════════════════════════════

def run_scan():
    global scan_results, last_scan_time
    logger.info(f"開始掃描 {len(KLSE_SYMBOLS)} 只股票...")
    results = []
    for sym in KLSE_SYMBOLS:
        try:
            row = scan_symbol(sym)
            results.append(row)
            logger.info(f"✅ {sym}: {row}")
        except Exception as e:
            logger.error(f"❌ {sym}: {e}")
            results.append({'symbol': sym, '1D': 'ERR', '4H': 'ERR', '1H': 'ERR'})
    scan_results   = results
    last_scan_time = datetime.now(MYT)
    check_and_notify(results)
    logger.info(f"掃描完成！共 {len(results)} 只")

def scan_loop():
    while True:
        run_scan()
        time.sleep(30 * 60)

# ══════════════════════════════════════════════════════════
# Flask Web
# ══════════════════════════════════════════════════════════

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>KLSE 莊家思維掃描器</title>
  <style>
    body{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:16px}
    h1{color:#58a6ff;text-align:center;margin-bottom:4px}
    .url{text-align:center;font-size:12px;color:#8b949e;margin-bottom:4px}
    .url a{color:#58a6ff}
    .info{text-align:center;color:#8b949e;margin-bottom:16px;font-size:13px}
    .info a{color:#58a6ff}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th{background:#161b22;color:#8b949e;padding:8px;border:1px solid #30363d}
    td{padding:7px 10px;border:1px solid #21262d;text-align:center}
    tr:hover td{background:#161b22}
    .entry{color:#f0883e;font-weight:bold}
    .sym{text-align:left;font-weight:bold;color:#79c0ff}
  </style>
</head>
<body>
  <h1>🇲🇾 KLSE 莊家思維掃描器</h1>
  {% if scanner_url %}
  <div class="url">🔗 <a href="{{ scanner_url }}">{{ scanner_url }}</a></div>
  {% endif %}
  <div class="info">
    最後掃描：{{ last_scan }} MYT｜股票：{{ count }} 只
    ｜<a href="/scan">立即掃描</a>
  </div>
  <table>
    <thead>
      <tr><th>股票</th><th>1D (Stage+C)</th><th>4H C系列</th><th>1H C系列</th></tr>
    </thead>
    <tbody>
      {% for row in results %}
      <tr>
        <td class="sym">{{ row.symbol }}</td>
        {% for tf in ['1D','4H','1H'] %}
        <td class="{{ 'entry' if '🎯' in row.get(tf,'') else '' }}">{{ row.get(tf,'-') }}</td>
        {% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""

@app.route('/')
def index():
    last = last_scan_time.strftime('%Y-%m-%d %H:%M') if last_scan_time else '未掃描'
    return render_template_string(HTML_TEMPLATE,
        results=scan_results,
        last_scan=last,
        count=len(scan_results),
        scanner_url=SCANNER_URL
    )

@app.route('/scan')
def trigger_scan():
    threading.Thread(target=run_scan, daemon=True).start()
    return '掃描已觸發，請稍後刷新頁面！', 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8082))
    threading.Thread(target=scan_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=port)
