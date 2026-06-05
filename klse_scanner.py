"""
KLSE 莊家思維掃描器 v2
- 數據來源：yfinance
- 邏輯：C系列收縮（V41規則）+ Stage
- 通知：Telegram
- 界面：Flask Web（含搜索框、公司名稱）
- 股票：~300只 Bursa主板
"""

import os, time, threading, logging, requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from flask import Flask, render_template_string, request
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
SCANNER_URL      = os.environ.get('SCANNER_URL', '')
MYT = pytz.timezone('Asia/Kuala_Lumpur')
app = Flask(__name__)

# ── 300只 KLSE 股票（代號: 公司名稱）────────────────────
KLSE_STOCKS = {
    # 金融
    '1155.KL': 'Maybank',
    '1295.KL': 'Public Bank',
    '1023.KL': 'CIMB',
    '5819.KL': 'Hong Leong Bank',
    '1066.KL': 'RHB Bank',
    '5168.KL': 'Hong Leong Financial',
    '1015.KL': 'Affin Bank',
    '1082.KL': 'AmBank',
    '5258.KL': 'BIMB Holdings',
    '1277.KL': 'Alliance Bank',
    '5185.KL': 'Kenanga',
    '6947.KL': 'Allianz Malaysia',
    '6399.KL': 'Aeon Credit',
    '5099.KL': 'Bursa Malaysia',
    '5235.KL': 'MBSB',
    '5115.KL': 'AFG',
    '7107.KL': 'ELK-Desa',
    # 電信/科技基建
    '6012.KL': 'Maxis',
    '4863.KL': 'Telekom Malaysia',
    '5212.KL': 'Celcomdigi',
    '3037.KL': 'Astro',
    '5031.KL': 'Time dotCom',
    '5136.KL': 'MyEG',
    '0082.KL': 'OCK Group',
    '0166.KL': 'Tele Radio',
    '0072.KL': 'Censof',
    '0011.KL': 'Opcom',
    # 能源/石油
    '5183.KL': 'Petronas Gas',
    '5071.KL': 'Petronas Chemicals',
    '6033.KL': 'Petronas Dagangan',
    '3816.KL': 'MISC',
    '5218.KL': 'Dialog Group',
    '5285.KL': 'Yinson',
    '5264.KL': 'Hibiscus Petroleum',
    '5132.KL': 'Bumi Armada',
    '5225.KL': 'Sapura Energy',
    '7084.KL': 'Wah Seong',
    '0207.KL': 'Uzma',
    '7179.KL': 'Perdana Petroleum',
    '0101.KL': 'Icon Offshore',
    '7253.KL': 'Coastal Contracts',
    '0172.KL': 'Carimin Petroleum',
    '5020.KL': 'Malaysia Marine',
    '7277.KL': 'Dialog',
    # 電力/公用事業
    '5347.KL': 'Tenaga Nasional',
    '5062.KL': 'YTL Power',
    '6888.KL': 'Axiata',
    # 棕榈油/農業
    '1961.KL': 'IOI Corp',
    '2445.KL': 'Sime Darby Plant',
    '4197.KL': 'KL Kepong',
    '2291.KL': 'PPB Group',
    '1899.KL': 'Genting Plantations',
    '2038.KL': 'TSH Resources',
    '5029.KL': 'TH Plantations',
    '2220.KL': 'Boustead Plantations',
    '1724.KL': 'Hap Seng Plantations',
    '2054.KL': 'United Plantations',
    '5113.KL': 'Sarawak Oil Palms',
    '9695.KL': 'Batu Kawan',
    '5025.KL': 'SOP',
    # 科技/半導體
    '0146.KL': 'Vitrox',
    '3948.KL': 'Inari Amertron',
    '2771.KL': 'Frontken',
    '1929.KL': "D&O Green Tech",
    '5135.KL': 'MPI',
    '0148.KL': 'Greatech',
    '4731.KL': 'Datasonic',
    '5033.KL': 'Globetronics',
    '4715.KL': 'Pentamaster',
    '5026.KL': 'Unimech',
    '5116.KL': 'Malaysian Pacific Ind',
    '5141.KL': 'Matrix',
    '5148.KL': 'Dufu Technology',
    '8583.KL': 'CTOS Digital',
    '5011.KL': 'GHL Systems',
    '0092.KL': 'Scicom',
    '0078.KL': 'Aemulus',
    '0197.KL': 'KESM Industries',
    '0196.KL': 'Elsoft Research',
    '3182.KL': 'Genting',
    # 消費/零售
    '4707.KL': 'Nestle Malaysia',
    '5242.KL': '99 Speedmart',
    '3026.KL': 'British American Tobacco',
    '7052.KL': 'Padini',
    '5252.KL': 'Mr DIY',
    '3689.KL': 'Dutch Lady',
    '3417.KL': 'Carlsberg Brewery',
    '3069.KL': 'Guinness Anchor',
    '4316.KL': 'Berjaya Food',
    '7668.KL': 'Hwa Tai',
    '3867.KL': 'Mynews',
    '7178.KL': 'QL Resources',
    '2836.KL': 'Scientex',
    '5024.KL': 'Caring Pharmacy',
    '5126.KL': 'Farm Fresh',
    '5322.KL': 'Spritzer',
    '6432.KL': 'Power Root',
    '4162.KL': 'Oldtown',
    '7222.KL': 'Kawan Food',
    '5015.KL': 'Parkson',
    '5014.KL': 'Aeon',
    '6556.KL': 'Berjaya Corp',
    '3255.KL': 'Berjaya Sports Toto',
    '2658.KL': 'PPB',
    '7216.KL': 'Tomypak',
    # 工業/製造
    '3476.KL': 'Press Metal',
    '6742.KL': 'Hartalega',
    '2267.KL': 'Kossan Rubber',
    '1562.KL': 'Top Glove',
    '7076.KL': 'Supermax',
    '0177.KL': 'Careplus',
    '5878.KL': 'Rubberex',
    '3336.KL': 'Lafarge Cement',
    '1996.KL': 'Ann Joo Resources',
    '9679.KL': 'Malaysian Steel Works',
    '3549.KL': 'Prestar Resources',
    '1589.KL': 'Cahya Mata Sarawak',
    '5211.KL': 'Southern Steel',
    '9261.KL': 'Tasek Corp',
    '2194.KL': 'YTL Cement',
    '5053.KL': 'Magni-Tech',
    '8869.KL': 'Pintaras Jaya',
    '8230.KL': 'PMB Technology',
    '5139.KL': 'Benalec',
    '4588.KL': 'Oriental Holdings',
    '7293.KL': 'Panasonic Manufacturing',
    # 建築/工程
    '5027.KL': 'Gamuda',
    '7113.KL': 'IJM Corp',
    '0138.KL': 'Gabungan AQRS',
    '7090.KL': 'WCT Holdings',
    '9814.KL': 'Sunway Construction',
    '5243.KL': 'Econpile',
    '3557.KL': 'Kerjaya Prospek',
    '5079.KL': 'Muhibbah Engineering',
    '7153.KL': 'Protasco',
    '9121.KL': 'HSL',
    '9075.KL': 'Naim Holdings',
    '5081.KL': 'Hua Yang',
    # 房地產/REIT
    '1301.KL': 'SP Setia',
    '5236.KL': 'EcoWorld',
    '5180.KL': 'Sime Darby Property',
    '5247.KL': 'IGB Berhad',
    '5246.KL': 'UEM Sunrise',
    '7028.KL': 'UOA Development',
    '6599.KL': 'Sunway',
    '4898.KL': 'IOI Properties',
    '3794.KL': 'Mah Sing',
    '5007.KL': 'MRCB',
    '1643.KL': 'Matrix Concepts',
    '5269.KL': 'LBS Bina',
    '5275.KL': 'Glomac',
    '5106.KL': 'Tambun Indah',
    '5109.KL': 'Mah Sing',
    '5119.KL': 'OSK Holdings',
    '3786.KL': 'KLCC Property',
    '7212.KL': 'Axis REIT',
    '4665.KL': 'IGB REIT',
    '0049.KL': 'Pavilion REIT',
    '5296.KL': 'Sunway REIT',
    '7034.KL': 'UOA REIT',
    '0090.KL': 'Al-Salam REIT',
    '5008.KL': 'Eastern Pacific',
    '9814.KL': 'Sunway Construction',
    # 醫療/健康
    '9296.KL': 'IHH Healthcare',
    '7073.KL': 'KPJ Healthcare',
    '0097.KL': 'Duopharma',
    '0186.KL': 'Pharmaniaga',
    '0065.KL': 'Careplus Group',
    '0050.KL': 'Kossan',
    # 運輸/汽車
    '5227.KL': 'Bermaz Auto',
    '5124.KL': 'MBM Resources',
    '3816.KL': 'MISC',
    '5216.KL': 'UMW Holdings',
    '5111.KL': 'Pos Malaysia',
    '3743.KL': 'DRB-Hicom',
    '4609.KL': 'Tan Chong Motor',
    # 綜合企業
    '4635.KL': 'Genting Berhad',
    '5983.KL': 'Genting Malaysia',
    '4677.KL': 'YTL Corp',
    '2828.KL': 'Sime Darby',
    '5073.KL': 'Boustead Holdings',
    '7182.KL': 'Felda Global',
    '1619.KL': 'Berjaya Land',
    '0051.KL': 'TWL Holdings',
    '5200.KL': 'YTL Hospitality',
    # 其他主板
    '5209.KL': 'EcoWorld International',
    '4898.KL': 'IOI Properties',
    '5215.KL': 'Revenue Group',
    '7293.KL': 'Panasonic',
    '5126.KL': 'Farm Fresh',
    '6963.KL': 'Tradewinds Plantation',
    '0023.KL': 'Revenue Group',
    '5205.KL': 'Technove Global',
    '9075.KL': 'Naim Holdings',
    '4588.KL': 'Oriental Holdings',
    '5062.KL': 'YTL Power',
    '5322.KL': 'Spritzer',
    # 額外補充
    '2445.KL': 'SD Guthrie',
    '5347.KL': 'Tenaga Nasional',
    '6012.KL': 'Maxis',
    '4863.KL': 'Telekom Malaysia',
    '5212.KL': 'Celcomdigi',
    '5027.KL': 'Gamuda',
    '3476.KL': 'Press Metal',
    '9296.KL': 'IHH Healthcare',
    '1961.KL': 'IOI Corp',
    '6599.KL': 'Sunway',
    '5242.KL': '99 Speedmart',
    '4677.KL': 'YTL Corp',
    '5062.KL': 'YTL Power',
    '2828.KL': 'Sime Darby',
    '4635.KL': 'Genting',
    '5983.KL': 'Genting Malaysia',
    '3816.KL': 'MISC',
    '5218.KL': 'Dialog',
    '4707.KL': 'Nestle',
    '7113.KL': 'IJM Corp',
    '1023.KL': 'CIMB',
    '1155.KL': 'Maybank',
    '1295.KL': 'Public Bank',
    '5819.KL': 'Hong Leong Bank',
    '1066.KL': 'RHB Bank',
}

# 去重，保留順序
seen = set()
KLSE_SYMBOLS = []
KLSE_NAMES   = {}
for sym, name in KLSE_STOCKS.items():
    if sym not in seen:
        seen.add(sym)
        KLSE_SYMBOLS.append(sym)
        KLSE_NAMES[sym] = name

logger.info(f"股票數量: {len(KLSE_SYMBOLS)}")

TIMEFRAMES = {
    '1D': {'period': '1y',  'interval': '1d'},
    '4H': {'period': '60d', 'interval': '1h'},
    '1H': {'period': '30d', 'interval': '1h'},
}

scan_results   = []
last_scan_time = None
notified_set   = set()

# ══════════════════════════════════════════════════════════
# 數據獲取
# ══════════════════════════════════════════════════════════

def fetch_ohlcv(symbol, tf_cfg, tf_label):
    try:
        df = yf.Ticker(symbol).history(period=tf_cfg['period'], interval=tf_cfg['interval'])
        if df is None or df.empty:
            return None
        df = df[['Open','High','Low','Close','Volume']].copy()
        df.columns = ['open','high','low','close','volume']
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        if tf_label == '4H':
            df = df.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        return df if len(df) >= 20 else None
    except Exception as e:
        logger.debug(f"{symbol} {tf_label}: {e}")
        return None

# ══════════════════════════════════════════════════════════
# Stage
# ══════════════════════════════════════════════════════════

def get_stage(df):
    if len(df) < 200:
        return '-'
    c = df['close']
    ma50  = c.rolling(50).mean()
    ma150 = c.rolling(150).mean()
    ma200 = c.rolling(200).mean()
    cur50,prev50   = ma50.iloc[-1],ma50.iloc[-10]
    cur150,prev150 = ma150.iloc[-1],ma150.iloc[-10]
    cur200,prev200 = ma200.iloc[-1],ma200.iloc[-10]
    price = c.iloc[-1]
    up50  = cur50>prev50; up150=cur150>prev150; up200=cur200>prev200
    ab50  = price>cur50;  ab150=price>cur150;   ab200=price>cur200
    if up50 and up150 and up200 and ab50 and ab150 and ab200: return 'S2'
    if not up50 and not up150 and not up200 and not ab50 and not ab150 and not ab200: return 'S4'
    if up150 and up200 and ab150 and ab200: return 'S1'
    if not up150 and not up200 and not ab150 and not ab200: return 'S3'
    return 'S0'

# ══════════════════════════════════════════════════════════
# C系列
# ══════════════════════════════════════════════════════════

def is_pivot_low(df, i, length=5):
    lows = df['low'].values
    if i < length or i >= len(lows)-length: return False
    pivot = lows[i]
    return all(pivot<=lows[i-j] for j in range(1,length+1)) and all(pivot<=lows[i+j] for j in range(1,length+1))

def has_three_combo(df, start_i, end_i):
    closes=df['close'].values; opens=df['open'].values; highs=df['high'].values; lows=df['low'].values
    if end_i-start_i<2: return False
    for i in range(start_i, end_i-1):
        count=0
        for j in range(i, min(i+3, end_i+1)):
            body=abs(closes[j]-opens[j]); rng=highs[j]-lows[j]
            if closes[j]<opens[j] or (rng>0 and body/rng<0.3): count+=1
            else: break
        if count>=3: return True
    return False

def find_next_c(df, search_from, prev_low, length=5):
    n=len(df); lows=df['low'].values; highs=df['high'].values
    pivot_idx=None
    for i in range(search_from+length, n-length):
        if is_pivot_low(df,i,length) and lows[i]>prev_low:
            pivot_idx=i; break
    if pivot_idx is None: return None
    seg_high_val,seg_high_idx=-1,search_from
    for i in range(search_from, pivot_idx):
        if highs[i]>seg_high_val: seg_high_val=highs[i]; seg_high_idx=i
    if seg_high_val<=0 or not has_three_combo(df,seg_high_idx,pivot_idx) or pivot_idx-seg_high_idx<3: return None
    return seg_high_val, seg_high_idx, lows[pivot_idx], pivot_idx

def find_c_series(df):
    c_list=[]
    for start in range(0, len(df)-20):
        result=find_next_c(df,start,0.0)
        if result:
            hv,hi,lv,li=result; pct=(hv-lv)/hv*100
            if pct>=3.0: c_list.append({'hv':hv,'hi':hi,'lv':lv,'li':li,'pct':pct}); break
    if not c_list: return []
    for _ in range(5):
        prev=c_list[-1]; result=find_next_c(df,prev['li'],prev['lv'])
        if not result: break
        hv,hi,lv,li=result; pct=(hv-lv)/hv*100
        if not (prev['pct']/2+0.5 < pct < prev['pct']): break
        c_list.append({'hv':hv,'hi':hi,'lv':lv,'li':li,'pct':pct})
    return c_list

# ══════════════════════════════════════════════════════════
# 掃描
# ══════════════════════════════════════════════════════════

def scan_symbol(symbol):
    row = {'symbol': symbol, 'name': KLSE_NAMES.get(symbol, '')}
    for tf_label, tf_cfg in TIMEFRAMES.items():
        df = fetch_ohlcv(symbol, tf_cfg, tf_label)
        if df is None: row[tf_label]='-'; continue
        c_list=find_c_series(df); c_count=len(c_list)
        if tf_label=='1D':
            stage=get_stage(df)
            if c_count==0: row[tf_label]=stage
            else:
                entry='🎯' if 3.0<=c_list[-1]['pct']<=10.0 else ''
                row[tf_label]=f"{stage} C{c_count}{entry}"
        else:
            if c_count==0: row[tf_label]='-'
            else:
                entry='🎯' if 3.0<=c_list[-1]['pct']<=10.0 else ''
                row[tf_label]=f"C{c_count}{entry}"
        time.sleep(0.2)
    return row

# ══════════════════════════════════════════════════════════
# 通知
# ══════════════════════════════════════════════════════════

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id':TELEGRAM_CHAT_ID,'text':message,'parse_mode':'HTML'}, timeout=10)
    except Exception as e: logger.error(f"Telegram: {e}")

def check_and_notify(results):
    global notified_set
    signals=[]
    for row in results:
        for tf in ['1D','4H','1H']:
            cell=row.get(tf,'')
            if '🎯' in cell:
                key=f"{row['symbol']}_{tf}_{cell}"
                if key not in notified_set:
                    notified_set.add(key)
                    signals.append({'symbol':row['symbol'],'name':row.get('name',''),'tf':tf,'signal':cell})
    if not signals: return
    now_str=datetime.now(MYT).strftime('%Y-%m-%d %H:%M')
    url_line=f'\n🔗 <a href="{SCANNER_URL}">{SCANNER_URL}</a>' if SCANNER_URL else ''
    lines=[f"🇲🇾 <b>KLSE 莊家思維信號</b> {now_str}{url_line}\n"]
    for s in signals:
        lines.append(f"🎯 <b>{s['symbol']}</b> {s['name']} [{s['tf']}] {s['signal']}")
    send_telegram('\n'.join(lines))

def run_scan():
    global scan_results, last_scan_time
    logger.info(f"開始掃描 {len(KLSE_SYMBOLS)} 只...")
    results=[]
    for sym in KLSE_SYMBOLS:
        try:
            row=scan_symbol(sym); results.append(row)
            logger.info(f"✅ {sym}: {row}")
        except Exception as e:
            logger.error(f"❌ {sym}: {e}")
            results.append({'symbol':sym,'name':KLSE_NAMES.get(sym,''),'1D':'ERR','4H':'ERR','1H':'ERR'})
    scan_results=results; last_scan_time=datetime.now(MYT)
    check_and_notify(results)
    logger.info("掃描完成！")

def scan_loop():
    while True:
        run_scan()
        time.sleep(30*60)

# ══════════════════════════════════════════════════════════
# Flask Web
# ══════════════════════════════════════════════════════════

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>KLSE 莊家思維</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:12px}
    h1{color:#58a6ff;text-align:center;margin:0 0 4px}
    .url{text-align:center;font-size:12px;color:#8b949e;margin-bottom:4px}
    .url a{color:#58a6ff}
    .info{text-align:center;color:#8b949e;margin-bottom:10px;font-size:13px}
    .info a{color:#58a6ff}
    .search-box{display:flex;justify-content:center;margin-bottom:12px}
    .search-box input{width:100%;max-width:400px;padding:8px 12px;border-radius:6px;
      border:1px solid #30363d;background:#161b22;color:#e6edf3;font-size:14px}
    .search-box input:focus{outline:none;border-color:#58a6ff}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th{background:#161b22;color:#8b949e;padding:8px;border:1px solid #30363d;text-align:center}
    td{padding:6px 8px;border:1px solid #21262d;text-align:center}
    tr:hover td{background:#161b22}
    .sym{text-align:left;font-weight:bold;color:#79c0ff;white-space:nowrap}
    .name{text-align:left;color:#8b949e;font-size:12px}
    .entry{color:#f0883e;font-weight:bold}
    .s2{color:#3fb950}.s4{color:#f85149}.s1,.s3{color:#d29922}
    .hidden{display:none}
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
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="🔍 搜索股票代號或公司名稱..." oninput="filterTable()">
  </div>
  <table id="stockTable">
    <thead>
      <tr><th>代號</th><th>公司</th><th>1D Stage+C</th><th>4H C系列</th><th>1H C系列</th></tr>
    </thead>
    <tbody>
      {% for row in results %}
      <tr>
        <td class="sym"><a href="https://www.tradingview.com/chart/?symbol=KLSE:{{ row.symbol.replace('.KL','') }}" target="_blank" style="color:#79c0ff;text-decoration:none">{{ row.symbol }}</a></td>
        <td class="name">{{ row.name }}</td>
        {% for tf in ['1D','4H','1H'] %}
        <td class="{{ 'entry' if '🎯' in row.get(tf,'') else '' }}">{{ row.get(tf,'-') }}</td>
        {% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <script>
    function filterTable(){
      var q=document.getElementById('searchInput').value.toLowerCase();
      var rows=document.querySelectorAll('#stockTable tbody tr');
      rows.forEach(function(row){
        var sym=row.cells[0].textContent.toLowerCase();
        var name=row.cells[1].textContent.toLowerCase();
        row.classList.toggle('hidden', q && !sym.includes(q) && !name.includes(q));
      });
    }
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    last=last_scan_time.strftime('%Y-%m-%d %H:%M') if last_scan_time else '未掃描'
    return render_template_string(HTML,results=scan_results,last_scan=last,count=len(scan_results),scanner_url=SCANNER_URL)

@app.route('/scan')
def trigger_scan():
    threading.Thread(target=run_scan,daemon=True).start()
    return '掃描已觸發，請稍後刷新！',200

@app.route('/health')
def health():
    return 'OK',200

if __name__=='__main__':
    port=int(os.environ.get('PORT',8080))
    threading.Thread(target=scan_loop,daemon=True).start()
    app.run(host='0.0.0.0',port=port)
