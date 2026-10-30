"""
莊家思維 股票掃描器（多市場：🇲🇾 KLSE ＋ 🇺🇸 美股 ＋ 🇸🇬 新加坡 ＋ 🇭🇰 港股 ＋ 🇨🇳 A股）
- 2026-10-28：加入 🇨🇳 A股（/cn）。只掃日線1D，只放滬深主板（滬深港通北向，Moomoo馬來西亞可買；
  創業板300/301、科創板688北向只限機構投資者，所以不放）。漲跌停±10%，跳動單位0.01，
  TradingView用 SSE:/SZSE:代號，Telegram前面加🇨🇳。A股專用設定加前綴 CN_。
- 2026-10-28：加入 🇭🇰 港股（/hk）。只掃日線1D，C1門檻7%、日線BO/SL緩衝±1%，跳動單位用港交所價位表，
  TradingView用 HKEX:代號（去掉前面的0），Telegram前面加🇭🇰。港股專用設定加前綴 HK_。
- 2026-10-28：加入 🇸🇬 新加坡（/sg）。只掃日線1D（MH決定：新加入的亞洲市場只看日線），C1門檻7%、日線BO/SL緩衝±1%，
  TradingView用 SGX:代號，Telegram跟KLSE一樣推（前面加🇸🇬）。新加坡專用設定加前綴 SG_。
- 2026-10-27：美股併進這個服務。同一份程式在同一個Railway服務裡載入兩次（KLSE一份、美股一份），
  兩個市場的狀態、資料檔、排程完全分開；美股網頁在 /us 底下。之後新加坡／港股／A股照同樣方式加。
- 環境變數 MARKETS 決定開哪些市場（預設 KLSE,US）。美股專用的設定加前綴 US_（例：US_TG_MIN_TURNOVER）。
- 數據來源：yfinance (.KL / 美股代碼)
- 邏輯：C系列收縮（對齊 莊家思維 Contraction V53 / scannerrailway.py 核心演算法）
- 通知：Telegram
- 界面：Flask Web（視覺風格對齊 crypto 版 scannerrailway.py）
"""

import os
import time
import threading
import logging
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, jsonify, Response, request, redirect
import pytz
import re
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
MY_TZ = pytz.timezone('Asia/Kuala_Lumpur')

# ============================================================
# 🌏 市場設定：每個市場一份。SCANNER_MARKET 決定這一份程式是哪個市場（由啟動程式設定）
# ============================================================
MKT_CFG = {
    'KLSE': {
        'flag': '🇲🇾', 'flag_html': '&#x1F1F2;&#x1F1FE;', 'name': '大馬', 'short': 'KLSE', 'tab': '🇲🇾 馬股',
        'base': '', 'env_prefix': '', 'tz': 'Asia/Kuala_Lumpur',
        'open': (9, 0), 'close': (17, 0), 'daily_close': (17, 5), 'post_close': (17, 40), 'post_close_end': (19, 0),
        'scan_every_min': 60, 'currency': 'RM', 'suffix': '.KL', 'tv_prefix': 'MYX:',
        'auto_adjust': True, 'rs_benchmark': '', 'turnover_env': 'TG_MIN_TURNOVER_MYR', 'default_sym': '1155.KL',
        'data_sub': '', 'tg_tfs': '1D', 'html_replace': [], 'tfs': ['1D', '4H', '1H'],
    },
    'US': {
        'flag': '🇺🇸', 'flag_html': '&#x1F1FA;&#x1F1F8;', 'name': '美股', 'short': 'US', 'tab': '🇺🇸 美股',
        'base': '/us', 'env_prefix': 'US_', 'tz': 'America/New_York',
        'open': (9, 30), 'close': (16, 0), 'daily_close': (16, 5), 'post_close': (16, 20), 'post_close_end': (18, 0),
        'scan_every_min': 30, 'currency': 'US$', 'suffix': '', 'tv_prefix': '',
        # 美股沿用舊us_scanner.py的資料設定：只做拆股調整、不做股息調整（跟TradingView預設一致）、4H對齊美東開盤
        'auto_adjust': False, 'rs_benchmark': 'SPY', 'turnover_env': 'US_TG_MIN_TURNOVER', 'default_sym': 'AAPL',
        'data_sub': 'us', 'tg_tfs': '1D,4H,1H',   # MH 2026-10-27：美股可開單／突破卡片推 1D、4H、1H
        'html_replace': [('&#x1F1F2;&#x1F1FE;', '&#x1F1FA;&#x1F1F8;'), ('🇲🇾', '🇺🇸'), ('大馬', '美股'),
                         ('KLSE股票', '美股'), ('板塊', '行業'),
                         ('開市時間每小時一次＋17:40收盤後一次', '開盤時間每30分鐘一次＋收盤後一次（美東16:20，大馬時間清晨）'),
                         ('每小時盯盤', '每30分鐘盯盤'), ('17:05後', '美東16:05後')],
        'tfs': ['1D', '4H', '1H'],
    },
    'SG': {
        'flag': '🇸🇬', 'flag_html': '&#x1F1F8;&#x1F1EC;', 'name': '新加坡', 'short': 'SGX', 'tab': '🇸🇬 新加坡',
        'base': '/sg', 'env_prefix': 'SG_', 'tz': 'Asia/Singapore',
        # SGX 09:00–17:00 連續交易（中午不休市），17:06前收盤競價結束
        'open': (9, 0), 'close': (17, 0), 'daily_close': (17, 10), 'post_close': (17, 40), 'post_close_end': (19, 0),
        'scan_every_min': 60, 'currency': 'S$', 'suffix': '.SI', 'tv_prefix': 'SGX:',
        'auto_adjust': True, 'rs_benchmark': 'ES3.SI', 'turnover_env': 'SG_TG_MIN_TURNOVER', 'default_sym': 'D05.SI',
        'data_sub': 'sg', 'tg_tfs': '1D',
        'html_replace': [('&#x1F1F2;&#x1F1FE;', '&#x1F1F8;&#x1F1EC;'), ('🇲🇾', '🇸🇬'), ('大馬', '新加坡'),
                         ('KLSE股票', '新加坡股票')],
        'tfs': ['1D'],   # MH 2026-10-28：新加坡只掃日線
        'min_turnover_default': '500000',   # Telegram流動性門檻：20日平均成交額 S$50萬
    },
    'HK': {
        'flag': '🇭🇰', 'flag_html': '&#x1F1ED;&#x1F1F0;', 'name': '港股', 'short': 'HKEX', 'tab': '🇭🇰 港股',
        'base': '/hk', 'env_prefix': 'HK_', 'tz': 'Asia/Hong_Kong',
        # 港交所 09:30–12:00、13:00–16:00（午休照樣掃沒關係）；收市競價到約16:10
        'open': (9, 30), 'close': (16, 0), 'daily_close': (16, 15), 'post_close': (16, 40), 'post_close_end': (18, 0),
        'scan_every_min': 60, 'currency': 'HK$', 'suffix': '.HK', 'tv_prefix': 'HKEX:',
        'auto_adjust': True, 'rs_benchmark': '2800.HK', 'turnover_env': 'HK_TG_MIN_TURNOVER', 'default_sym': '0700.HK',
        'data_sub': 'hk', 'tg_tfs': '1D',
        'html_replace': [('&#x1F1F2;&#x1F1FE;', '&#x1F1ED;&#x1F1F0;'), ('🇲🇾', '🇭🇰'), ('大馬', '港股'),
                         ('KLSE股票', '港股'), ('17:40', '16:40'), ('17:05後', '16:15後')],
        'tfs': ['1D'],   # MH 2026-10-28：新加入的亞洲市場只掃日線
        'min_turnover_default': '10000000',   # Telegram流動性門檻：20日平均成交額 HK$1,000萬
    },
    'CN': {
        'flag': '🇨🇳', 'flag_html': '&#x1F1E8;&#x1F1F3;', 'name': 'A股', 'short': 'A股', 'tab': '🇨🇳 A股',
        'base': '/cn', 'env_prefix': 'CN_', 'tz': 'Asia/Shanghai',
        # 滬深 09:30–11:30、13:00–15:00（午休照樣掃沒關係）
        'open': (9, 30), 'close': (15, 0), 'daily_close': (15, 5), 'post_close': (15, 40), 'post_close_end': (17, 0),
        'scan_every_min': 60, 'currency': '¥', 'suffix': '', 'tv_prefix': '',
        'auto_adjust': True, 'rs_benchmark': '510300.SS', 'turnover_env': 'CN_TG_MIN_TURNOVER', 'default_sym': '600519.SS',
        'data_sub': 'cn', 'tg_tfs': '1D',
        'html_replace': [('&#x1F1F2;&#x1F1FE;', '&#x1F1E8;&#x1F1F3;'), ('🇲🇾', '🇨🇳'), ('大馬', 'A股'),
                         ('KLSE股票', 'A股'), ('17:40', '15:40'), ('17:05後', '15:05後')],
        'tfs': ['1D'],   # MH 2026-10-28：新加入的亞洲市場只掃日線
        'min_turnover_default': '100000000',   # Telegram流動性門檻：20日平均成交額 ¥1億
    },
}
MARKET     = os.environ.get('SCANNER_MARKET', 'KLSE').upper()
if MARKET not in MKT_CFG:
    MARKET = 'KLSE'
M          = MKT_CFG[MARKET]
MKT_TZ     = pytz.timezone(M['tz'])
BASE       = M['base']                     # 網址前綴：KLSE是 ''，美股是 '/us'
SUFFIX     = M['suffix']
ACTIVE_MARKETS = [MARKET]                  # 啟動程式會改成實際開的全部市場（網頁上方切換按鈕用）
GLOBAL_SCAN_LOCK = threading.Lock()        # 啟動程式會換成全部市場共用的同一把鎖：一次只掃一個市場，避免Yahoo限流

def menv(name, default):
    """市場專用環境變數：KLSE讀原本的名字（舊設定不用改），美股讀 US_ 前綴"""
    return os.environ.get(M['env_prefix'] + name, default)

def sym_code(sym):
    if MARKET == 'CN':
        return sym.split('.')[0]   # 600519.SS → 600519
    return sym[:-len(SUFFIX)] if SUFFIX and sym.endswith(SUFFIX) else sym

def tv_sym(sym):
    code = sym_code(sym)
    if MARKET == 'HK':
        code = code.lstrip('0') or '0'   # TradingView港股代號不補0：0700.HK → HKEX:700
    if MARKET == 'CN':
        return ('SSE:' if sym.endswith('.SS') else 'SZSE:') + code   # 600519.SS → SSE:600519、000001.SZ → SZSE:000001
    return f"{M['tv_prefix']}{code}"

def norm_sym(raw):
    """使用者輸入的代碼 → 程式內部代碼（KLSE補.KL；美股去掉 NASDAQ: 這類前綴、BRK.B→BRK-B）"""
    s = (raw or '').strip().upper()
    if ':' in s:
        s = s.split(':')[-1]
    if MARKET == 'CN':
        code = s.split('.')[0]
        return code + ('.SS' if code.startswith('6') else '.SZ')   # 600519 → 600519.SS、000001 → 000001.SZ
    if MARKET == 'HK':
        code = s[:-3] if s.endswith('.HK') else s
        return (code.zfill(4) if code.isdigit() else code) + '.HK'   # 700 → 0700.HK
    if SUFFIX:
        return s if s.endswith(SUFFIX) else s + SUFFIX
    return s.replace('.', '-')

def label_of(name, sym):
    code = sym_code(sym)
    return code if (not name or name == code) else f'{name}({code})'

# 2026-10-28 移除Yahoo連續抓不到日線的36檔（重抓後仍沒有資料，多半已下市/私有化/代號變更）：
# 1597、1532、2771、2220、5033、4588、4609、5822、3549、2194、7090、1301、5124、4898、8230、5294、5119、3786、4635、4665、2267、7182、5879、5014、5074、1503、1236、5175、5179、5222、6025、7068、7112、7164、7213、8826
SYMBOLS = [
    '1155.KL',
    '1295.KL',
    '1023.KL',
    '5819.KL',
    '1066.KL',
    '1015.KL',
    '5185.KL',
    '1082.KL',
    '5258.KL',
    '5099.KL',
    '5115.KL',
    '7107.KL',
    '2488.KL',
    '6399.KL',
    '5347.KL',
    '5183.KL',
    '6033.KL',
    '5026.KL',
    '5116.KL',
    '3816.KL',
    '5071.KL',
    '3948.KL',
    '1929.KL',
    '5209.KL',
    '6742.KL',
    '6888.KL',
    '4863.KL',
    '6012.KL',
    '6947.KL',
    '5168.KL',
    '2445.KL',
    '1961.KL',
    '2291.KL',
    '1899.KL',
    '2038.KL',
    '5029.KL',
    '5135.KL',
    '4731.KL',
    '0146.KL',
    '1589.KL',
    '5211.KL',
    '0148.KL',
    '3867.KL',
    '2658.KL',
    '3026.KL',
    '5285.KL',
    '5081.KL',
    '7222.KL',
    '5878.KL',
    '6556.KL',
    '7293.KL',
    '7178.KL',
    '5242.KL',
    '4162.KL',
    '3255.KL',
    '5264.KL',
    '3182.KL',
    '4715.KL',
    '3336.KL',
    '1996.KL',
    '9679.KL',
    '5148.KL',
    '5141.KL',
    '1724.KL',
    '9261.KL',
    '3476.KL',
    '4197.KL',
    '8583.KL',
    '5983.KL',
    '1619.KL',
    '9814.KL',
    '5243.KL',
    '0051.KL',
    '0049.KL',
    '5296.KL',
    '0078.KL',
    '0090.KL',
    '7034.KL',
    '0097.KL',
    '0196.KL',
    '0065.KL',
    '9296.KL',
    '7073.KL',
    '0050.KL',
    '0186.KL',
    '0138.KL',
    '5053.KL',
    '7153.KL',
    '5027.KL',
    '7113.KL',
    '0177.KL',
    '7212.KL',
    '0197.KL',
    '5250.KL',
    '5216.KL',
    '3557.KL',
    '5079.KL',
    '3794.KL',
    '5007.KL',
    '9121.KL',
    '5136.KL',
    '5236.KL',
    '5180.KL',
    '5111.KL',
    '5227.KL',
    '5269.KL',
    '5020.KL',
    '5275.KL',
    '5008.KL',
    '5246.KL',
    '7028.KL',
    '8869.KL',
    '9075.KL',
    '5139.KL',
    '6599.KL',
    '5247.KL',
    '5106.KL',
    '5109.KL',
    '1562.KL',
    '7076.KL',
    '0023.KL',
    '5205.KL',
    '6076.KL',
    '5299.KL',
    '5143.KL',
    '3689.KL',
    '5134.KL',
    '3042.KL',
    '0163.KL',
    '3417.KL',
    '4502.KL',
    '5225.KL',
    '5326.KL',
    '4677.KL',
    '4707.KL',
    '5555.KL',
    '5249.KL',
    '2089.KL',
    '5681.KL',
    '5235SS.KL',
    '4065.KL',
    '5031.KL',
    '7277.KL',
    '5263.KL',
    '0128.KL',
    '5288.KL',
    '0166.KL',
    '5337.KL',
    '0151.KL',
    '5273.KL',
    '5176.KL',
    '5292.KL',
    '5005.KL',
    '1818.KL',
    '5340.KL',
    '3034.KL',
    '8206.KL',
    '5212.KL',
    '0208.KL',
    '8621.KL',
    '3301.KL',
    '5357.KL',
    '5323.KL',
    '1171.KL',
    '5286.KL',
    '5309.KL',
    '5606.KL',
    '5126.KL',
    '8664.KL',
    '2836.KL',
    '5200.KL',
    '4006.KL',
    '5306.KL',
    '1163.KL',
    '7160.KL',
    '5356.KL',
    '5102.KL',
    '7161.KL',
    '0270.KL',
    '7172.KL',
    '5038.KL',
    '0225.KL',
    '5151.KL',
    '0215.KL',
    '5272.KL',
    '5401.KL',
    '9822.KL',
    '3069.KL',
    '6139.KL',
    '5352.KL',
    '5330.KL',
    '6633.KL',
    '5012.KL',
    '5032.KL',
    '7195.KL',
    '6459.KL',
    '3565.KL',
    '5000.KL',
    '0338.KL',
    '0245.KL',
    '5138.KL',
    '5210.KL',
    '7103.KL',
    '5313.KL',
    '9687.KL',
    '5162.KL',
    '3859.KL',
    '5916.KL',
    '5255.KL',
    '0375.KL',
    '0318.KL',
    '8907.KL',
    '4456.KL',
    '5327.KL',
    '5301.KL',
    '7081.KL',
    '1651.KL',
    '7233.KL',
    '2429.KL',
    '3395.KL',
    '9059.KL',
    '5338.KL',
    '7187.KL',
    '5199.KL',
    '7052.KL',
    '5069.KL',
    '7105.KL',
    '0339.KL',
    '0303.KL',
    '0351.KL',
    '7100.KL',
    '0045.KL',
    '0233.KL',
    '2593.KL',
    '0168.KL',
    '4219.KL',
    '0056.KL',
    '7148.KL',
    '7179.KL',
    '5321.KL',
    '6114.KL',
    '5351.KL',
    '5248.KL',
    '2852.KL',
    '5161.KL',
    '6262.KL',
    '6718.KL',
    '5335.KL',
    '4383.KL',
    '5320.KL',
    '5271.KL',
    '1287.KL',
    '0295.KL',
    '5908.KL',
    '0259.KL',
    '0265.KL',
    '6963.KL',
    '4324.KL',
    '5302.KL',
    '7180.KL',
    '4758.KL',
    '0193.KL',
    '3905.KL',
    '5348.KL',
    '5123.KL',
    '7246.KL',
    '5173.KL',
    '0223.KL',
    '5293.KL',
    '0251.KL',
    '0101.KL',
    '8052.KL',
    '5307.KL',
    '0325.KL',
    '5280.KL',
    '7241.KL',
    '7106.KL',
    '5827.KL',
    '6971.KL',
    '3662.KL',
    '9792.KL',
    '5218.KL',
    '5317.KL',
    '5024.KL',
    '5274.KL',
    '7087.KL',
    '5328.KL',
    '6351.KL',
    '6491.KL',
    '0099.KL',
    '0376.KL',
    '5517.KL',
    '0161.KL',
    '0293.KL',
    '0291.KL',
    '0112.KL',
    '0392.KL',
    '0242.KL',
    '5284.KL',
    '7010.KL',
    '5041.KL',
    '0360.KL',
    '7035.KL',
    '5319.KL',
    '0273.KL',
    '0098.KL',
    '7048.KL',
    '5789.KL',
    '5325.KL',
    '5001.KL',
    '0390.KL',
    '3379.KL',
    '0239.KL',
    '0230.KL',
    '7095.KL',
    '5665.KL',
    '5075.KL',
    '7204.KL',
    '5084.KL',
    '8877.KL',
    '2569.KL',
    '5336.KL',
    '0240.KL',
    '7231.KL',
    '5015.KL',
    '8524.KL',
    '6939.KL',
    '2305.KL',
    '3611.KL',
    '6017.KL',
    '0002.KL',
    '5110.KL',
    '7197.KL',
    '5186.KL',
    '5184.KL',
    '0217.KL',
    '0326.KL',
    '7609.KL',
    '5125.KL',
    '1058.KL',
    '6874.KL',
    '0310.KL',
    '7084.KL',
    '5238.KL',
    '5318.KL',
    '0391.KL',
    '5142.KL',
    '2062.KL',
    '5112.KL',
    '0453.KL',
    '7252.KL',
    '5308.KL',
    '7167.KL',
    '7155.KL',
    '0372.KL',
    '0198.KL',
    '4243.KL',
    '5132.KL',
    '6432.KL',
    '9571.KL',
    '5072.KL',
    '6378.KL',
    '5080.KL',
    '0308.KL',
    '5331.KL',
    '0292.KL',
    '0286.KL',
    '5259.KL',
    '5073.KL',
    '5703.KL',
    '2097.KL',
    '0398.KL',
    '5332.KL',
    '2054.KL',
    '5171.KL',
    '7174.KL',
    '5010.KL',
    '0395.KL',
    '0263.KL',
    '0012.KL',
    '8117.KL',
    '0366.KL',
    '0298.KL',
    '7501.KL',
    '0368.KL',
    '5341.KL',
    '8311.KL',
    '0246.KL',
    '7210.KL',
    '0382.KL',
    '0296.KL',
    '0276.KL',
    '5303.KL',
    '9172.KL',
    '7108.KL',
    '5310.KL',
    '0037.KL',
    '5196.KL',
    '0157.KL',
    '5049.KL',
    '0236.KL',
    '5077.KL',
    '7192.KL',
    '0006.KL',
    '0011.KL',
    '0025.KL',
    '0028.KL',
    '0034.KL',
    '0039.KL',
    '0040.KL',
    '0058.KL',
    '0066.KL',
    '0074.KL',
    '0080.KL',
    '0089.KL',
    '0106.KL',
    '0109.KL',
    '0116.KL',
    '0117.KL',
    '0131.KL',
    '0136.KL',
    '0143.KL',
    '0149.KL',
    '0158.KL',
    '0167.KL',
    '0174.KL',
    '0175.KL',
    '0188.KL',
    '0192.KL',
    '0195.KL',
    '0200.KL',
    '0202.KL',
    '0206.KL',
    '0212.KL',
    '0222.KL',
    '0237.KL',
    '0238.KL',
    '0249.KL',
    '0250.KL',
    '0252.KL',
    '0256.KL',
    '0257.KL',
    '0258.KL',
    '0277.KL',
    '0278.KL',
    '0281.KL',
    '0284.KL',
    '0289.KL',
    '0290.KL',
    '0299.KL',
    '0302.KL',
    '0304.KL',
    '0307.KL',
    '0313.KL',
    '0317.KL',
    '0319.KL',
    '0320.KL',
    '0323.KL',
    '0327.KL',
    '0328.KL',
    '0331.KL',
    '0333.KL',
    '0336.KL',
    '0340.KL',
    '0341.KL',
    '0342.KL',
    '0343.KL',
    '0345.KL',
    '0346.KL',
    '0347.KL',
    '0348.KL',
    '0350.KL',
    '0353.KL',
    '0355.KL',
    '0357.KL',
    '0358.KL',
    '0363.KL',
    '0365.KL',
    '0367.KL',
    '0370.KL',
    '0379.KL',
    '0380.KL',
    '0383.KL',
    '0386.KL',
    '0393.KL',
    '0396.KL',
    '0399.KL',
    '0455.KL',
    '0457.KL',
    '0458.KL',
    '0459.KL',
    '0460.KL',
    '0463.KL',
    '0465.KL',
    '0466.KL',
    '2127.KL',
    '3247.KL',
    '3778.KL',
    '3891.KL',
    '3913.KL',
    '4057.KL',
    '4235.KL',
    '4316.KL',
    '5036.KL',
    '5070.KL',
    '5078.KL',
    '5098.KL',
    '5127.KL',
    '5147.KL',
    '5149.KL',
    '5157.KL',
    '5163.KL',
    '5166.KL',
    '5219.KL',
    '5300.KL',
    '5305.KL',
    '5322.KL',
    '5345.KL',
    '5533.KL',
    '5576.KL',
    '5738.KL',
    '5797.KL',
    '6203.KL',
    '6297.KL',
    '6637.KL',
    '6912.KL',
    '7004.KL',
    '7005.KL',
    '7020.KL',
    '7055.KL',
    '7071.KL',
    '7078.KL',
    '7080.KL',
    '7085.KL',
    '7115.KL',
    '7120.KL',
    '7123.KL',
    '7131.KL',
    '7133.KL',
    '7134.KL',
    '7140.KL',
    '7145.KL',
    '7170.KL',
    '7173.KL',
    '7176.KL',
    '7211.KL',
    '7215.KL',
    '7219.KL',
    '7230.KL',
    '7315.KL',
    '7382.KL',
    '7439.KL',
    '7579.KL',
    '7854.KL',
    '7935.KL',
    '8192.KL',
    '8273.KL',
    '8435.KL',
    '8613.KL',
    '8648.KL',
    '8893.KL',
    '9148.KL',
    '9237.KL',
    '9288.KL',
    '9326.KL',
    '9334.KL',
    '9369.KL',
    '9776.KL',
    '9881.KL',
]


# 股票名稱對照表
NAMES = {
    '1155.KL': 'Malayan Banking', '1023.KL': 'CIMB', '1295.KL': 'Public Bank',
    '5819.KL': 'Hong Leong Bank', '1066.KL': 'RHB Bank', '1015.KL': 'AMMB',
    '5185.KL': 'Affin Bank', '1082.KL': 'Hong Leong Financial Group', '6947.KL': 'Celcomdigi',
    '6888.KL': 'Axiata Group', '5168.KL': 'Hartalega Holdings', '6012.KL': 'Maxis',
    '1597.KL': 'BIMB', '5258.KL': 'Bank Islam Malaysia', '6399.KL': 'Astro',
    '5183.KL': 'Petronas Chemicals Group', '3816.KL': 'MISC',
    '5071.KL': 'Coastal Contracts', '1532.KL': 'Hibiscus', '6033.KL': 'PETRONAS Gas',
    '3948.KL': 'DutaLand', '5026.KL': 'MHC Plantations', '2771.KL': 'Boustead Holdings',
    '5116.KL': 'Al-\'Aqar Healthcare REIT', '1929.KL': 'Chin Teck Plantations',
    '4863.KL': 'Telekom', '6742.KL': 'YTL Power International', '5053.KL': 'OSK Holdings',
    '2445.KL': 'Kuala Lumpur Kepong', '1961.KL': 'IOI Corporation', '2291.KL': 'Genting Plantations',
    '1899.KL': 'Batu Kawan', '2038.KL': 'Negri Sembilan Oil Palms',
    '5029.KL': 'Far East Holdings', '2220.KL': 'Berjaya Land',
    '5135.KL': 'Sarawak Plant', '5033.KL': 'Kulim',
    '4731.KL': 'Scientex', '3182.KL': 'Genting', '4715.KL': 'Genting Malaysia',
    '3336.KL': 'IJM Corp', '1996.KL': 'Kretam Holdings', '9679.KL': 'WCT Holdings',
    '3549.KL': 'YTL Corp', '5148.KL': 'UEM Sunrise', '8583.KL': 'Mah Sing Group',
    '5141.KL': 'Dayang Enterprise Holdings', '1724.KL': 'Paramount Corporation',
    '9261.KL': 'Gadang Holdings', '2194.KL': 'MMC Corporation',
    '3476.KL': 'Keck Seng (Malaysia)', '5053.KL': 'OSK Holdings', '6742.KL': 'YTL Power International',
    '2267.KL': 'Lafarge', '1562.KL': 'Sports Toto', '7076.KL': 'CB Industrial Product Holding',
    '0177.KL': 'Midtown Group', '5878.KL': 'KPJ Healthcare', '7153.KL': 'Kossan Rubber Industries',
    '5027.KL': 'Kim Loong Resources', '7113.KL': 'Top Glove Corporation', '0138.KL': 'Zetrix AI',
    '7090.KL': 'Apex Healthcare', '0197.KL': 'Wegmans Holdings', '7212.KL': 'Destini',
    '4665.KL': 'Pos Malaysia', '0049.KL': 'Oceancash Pacific', '5296.KL': 'Revenue Group',
    '0078.KL': 'GDEX', '0090.KL': 'Elsoft Research', '7034.KL': 'Thong Guan Industries',
    '9814.KL': 'Bertam Alliance', '5243.KL': 'Velesto Energy', '0097.KL': 'ViTrox Corporation',
    '0196.KL': 'QES Group', '0065.KL': 'Excel Force MSC', '9296.KL': 'RCE Capital',
    '7073.KL': 'Seacera Group', '0050.KL': 'Systech', '0186.KL': 'Perak Transit',
    '5216.KL': 'NEXG', '1301.KL': 'KPJ Healthcare',
    '5236.KL': 'Matrix Concepts Holdings', '5180.KL': 'CapitaLand Malaysia Trust', '5111.KL': 'Tower Real Estate Investment Trust',
    '5227.KL': 'IGB Real Estate Investment Trust', '5124.KL': 'Amanahraya REIT',
    '5269.KL': 'Al-Salam Real Estate Investment Trust', '5020.KL': 'Glomac', '5275.KL': 'Mynews Holdings',
    '6599.KL': 'Aeon Co. (M)', '5247.KL': 'Karex',
    '5106.KL': 'Axis Real Estate Investment Trust', '5109.KL': 'YTL Hospitality REIT',
    '5119.KL': 'Lingkaran Trans', '3786.KL': 'PLUS (Litrak)',
    '4898.KL': 'TA Enterprise', '5008.KL': 'Harrisons Holdings (Malaysia)',
    '5246.KL': 'Westports Holdings', '7028.KL': 'Zecon',
    '3557.KL': 'EcoFirst Consolidated', '5079.KL': 'One Glove Group',
    '3794.KL': 'Malayan Cement', '5007.KL': 'Chin Well Holdings',
    '9121.KL': 'KPS Consortium', '5136.KL': 'Hextar Technologies Solutions',
    '8869.KL': 'Press Metal Aluminium Holdings', '9075.KL': 'Theta Edge',
    '5139.KL': 'AEON Credit Service (M)', '8230.KL': 'Tambun Indah',
    '4635.KL': 'Misc', '5983.KL': 'MBM Resources',
    '1619.KL': 'DRB-HICOM', '7293.KL': 'Yinson Holdings',
    '4588.KL': 'UMW Holdings', '5285.KL': 'SD Guthrie',
    '5081.KL': 'Esthetics International Group', '7222.KL': 'Imaspro Corporation',
    '4609.KL': 'Heineken', '0051.KL': 'Cuscapi',
    '3026.KL': 'Dutch Lady Milk Industries', '3867.KL': 'Malaysian Pacific',
    '2658.KL': 'Ajinomoto (Malaysia)', '4162.KL': 'British American Tobacco (Malaysia)',
    '7178.KL': 'Y.S.P. Southeast Asia Holding', '5242.KL': 'Solid Automotive',
    '6556.KL': 'Ann Joo Resources', '3255.KL': 'Heineken Malaysia',
    '4197.KL': 'Sime Darby', '5347.KL': 'Tenaga Nasional',
    '2488.KL': 'Alliance Bank Malaysia', '5099.KL': 'Capital A',
    '5250.KL': '7-Eleven Malaysia Holdings', '5822.KL': '99 Speed Mart',
    '5264.KL': 'Malakoff Corporation', '5294.KL': 'IOI Properties',
    '5879.KL': 'AirAsia X', '6076.KL': 'Encorp',
    '7182.KL': 'Eka Noodles', '0023.KL': 'IFCA MSC',
    '5209.KL': 'Gas Malaysia', '5205.KL': 'Eversendai Corporation',
    '5299.KL': 'IGB Commercial Real Estate Investment Trust', '5143.KL': 'Luxchem Corporation',
    '3689.KL': 'Fraser & Neave Holdings', '5134.KL': 'Southern Acids (M)',
    '3042.KL': 'Petron Malaysia Refining & Marketing', '0163.KL': 'Careplus Group',
    '3417.KL': 'Eastern & Oriental', '5014.KL': 'Malaysia Airports Holdings',
    '4502.KL': 'Media Prima', '0249.KL': 'LGMS',
    '3239.KL': 'TSM Global', '7084.KL': 'QL Resources',
    '5398.KL': 'Gamuda', '8532.KL': 'Aeon Credit',
    '0820EA.KL': 'Eco-Arc',
    '0146.KL': 'JF Technology', '0148.KL': 'Sunzen Group', '1589.KL': 'Iskandar Waterfront City',
    '5115.KL': 'Alam Maritim Resources', '7107.KL': 'Oriental Food Industries Holdings', '5211.KL': 'Sunway',
    '5225.KL': 'IHH Healthcare',
    '5326.KL': '99 Speed Mart Retail Holdings',
    '4677.KL': 'YTL Corporation',
    '4707.KL': 'Nestle (Malaysia)',
    '5555.KL': 'Sunway Healthcare Holdings',
    '5249.KL': 'IOI Properties Group',
    '2089.KL': 'United Plantations',
    '5681.KL': 'PETRONAS Dagangan',
    '5235SS.KL': 'KLCC Property Holdings',
    '4065.KL': 'PPB Group',
    '5031.KL': 'TIME dotCom',
    '7277.KL': 'Dialog Group',
    '5263.KL': 'Sunway Construction Group',
    '0128.KL': 'Frontken Corporation',
    '5288.KL': 'Sime Darby Property',
    '0166.KL': 'Inari Amertron',
    '5337.KL': 'Eco-Shop Marketing',
    '0151.KL': 'Kelington Group',
    '5273.KL': 'Chin Hin Group',
    '5176.KL': 'Sunway Real Estate Investment Trust',
    '5292.KL': 'UWC',
    '5005.KL': 'Unisem (M)',
    '1818.KL': 'Bursa Malaysia',
    '5340.KL': 'UMS Integration Limited',
    '3034.KL': 'Hap Seng Consolidated',
    '8206.KL': 'Eco World Development Group',
    '5212.KL': 'Pavilion Real Estate Investment Trust',
    '0208.KL': 'Greatech Technology',
    '8621.KL': 'LPI Capital',
    '3301.KL': 'Hong Leong Industries',
    '5357.KL': 'SkyeChip',
    '5323.KL': 'Johor Plantations Group',
    '1171.KL': 'MBSB',
    '5286.KL': 'Mi Technovation',
    '5309.KL': 'ITMAX System',
    '5606.KL': 'IGB',
    '5126.KL': 'Sarawak Oil Palms',
    '8664.KL': 'S P Setia',
    '2836.KL': 'Carlsberg Brewery Malaysia',
    '5200.KL': 'UOA Development',
    '4006.KL': 'Oriental Holdings',
    '5306.KL': 'Farm Fresh',
    '1163.KL': 'Allianz Malaysia',
    '7160.KL': 'Pentamaster Corporation',
    '5356.KL': 'Stratus Global Holdings',
    '5102.KL': 'Guan Chong',
    '7161.KL': 'Kerjaya Prospek Group',
    '0270.KL': 'NationGate Holdings',
    '7172.KL': 'PMB Technology',
    '5038.KL': 'KSL Holdings',
    '0225.KL': 'Southern Cable Group',
    '5151.KL': 'Hextar Global',
    '0215.KL': 'Solarvest Holdings',
    '5272.KL': 'Ranhill Utilities',
    '5401.KL': 'Tropicana Corporation',
    '9822.KL': 'SAM Engineering & Equipment (M)',
    '3069.KL': 'Mega First Corporation',
    '6139.KL': 'Syarikat Takaful Malaysia Keluarga',
    '5352.KL': 'MTT Shipping and Logistics',
    '5330.KL': 'TMK Chemical',
    '6633.KL': 'Leong Hup International',
    '5012.KL': 'Ta Ann Holdings',
    '5032.KL': 'Bintulu Port Holdings',
    '7195.KL': 'Binastra Corporation',
    '5074.KL': 'DXN Holdings',
    '6459.KL': 'MNRB Holdings',
    '3565.KL': 'WCE Holdings',
    '5000.KL': 'Hume Cement Industries',
    '0338.KL': 'Oriental Kopi Holdings',
    '0245.KL': 'MN Holdings',
    '5138.KL': 'Hap Seng Plantations Holdings',
    '5210.KL': 'Bumi Armada',
    '7103.KL': 'Spritzer',
    '5313.KL': 'Radium Development',
    '9687.KL': 'Ideal Capital',
    '5162.KL': 'VSTECS',
    '3859.KL': 'Magnum',
    '5916.KL': 'Malaysia Smelting Corporation',
    '5255.KL': 'Lianson Fleet Group',
    '0375.KL': 'THMY Holdings',
    '0318.KL': 'Elridge Energy Holdings',
    '8907.KL': 'EG Industries',
    '4456.KL': 'Dagang NeXchange',
    '5327.KL': 'Mega Fortris',
    '5301.KL': 'CTOS Digital',
    '7081.KL': 'Pharmaniaga',
    '1651.KL': 'Malaysian Resources Corporation',
    '7233.KL': 'Dufu Technology Corp.',
    '2429.KL': 'Tanco Holdings',
    '3395.KL': 'Berjaya Corporation',
    '9059.KL': 'TSH Resources',
    '5338.KL': 'Paradigm Real Estate Investment Trust',
    '7187.KL': 'Chin Hin Group Property',
    '5199.KL': 'Hibiscus Petroleum',
    '7052.KL': 'Padini Holdings',
    '5069.KL': 'BLD Plantation',
    '7105.KL': 'HCK Capital Group',
    '0339.KL': 'CBH Engineering Holding',
    '0303.KL': 'Alpha IVF Group',
    '0351.KL': 'Lim Seong Hai Capital',
    '7100.KL': 'Uchi Technologies',
    '0045.KL': 'Southern Score Builders',
    '0233.KL': 'Pekat Group',
    '2593.KL': 'United Malacca',
    '0168.KL': 'BM GreenTech',
    '4219.KL': 'Berjaya Property',
    '0056.KL': 'NCT Alliance',
    '7148.KL': 'Duopharma Biotech',
    '7179.KL': 'Lagenda Properties',
    '5321.KL': 'Keyfield International',
    '6114.KL': 'MKH',
    '5351.KL': 'Empire Premium Food',
    '5248.KL': 'Bermaz Auto',
    '2852.KL': 'Cahya Mata Sarawak',
    '5161.KL': 'JCY International',
    '6262.KL': 'Innoprise Plantations',
    '6718.KL': 'Crescendo Corporation',
    '5335.KL': 'HI Mobility',
    '4383.KL': 'Jaya Tiasa Holdings',
    '5320.KL': 'Prolintas Infra Business Trust',
    '5271.KL': 'Pecca Group',
    '1287.KL': 'Exsim Hospitality',
    '0295.KL': 'Master Tec Group',
    '5908.KL': 'DKSH Holdings (Malaysia)',
    '0259.KL': 'SNS Network Technology',
    '0265.KL': 'Infomina',
    '6963.KL': 'V.S. Industry',
    '4324.KL': 'Hengyuan Refining Company',
    '5302.KL': 'Aurelius Technologies',
    '7180.KL': 'Sern Kou Resources',
    '4758.KL': 'Ancom Nylex',
    '0193.KL': 'Kinergy Advancement',
    '3905.KL': 'Mulpha International',
    '5348.KL': 'Orkim',
    '5123.KL': 'Sentral REIT',
    '7246.KL': 'Signature International',
    '5173.KL': 'Shin Yang Group',
    '0223.KL': 'Samaiden Group',
    '5293.KL': 'AME Elite Consortium',
    '0251.KL': 'SFP Tech Holdings',
    '0101.KL': 'TMC Life Sciences',
    '8052.KL': 'Central Global',
    '5307.KL': 'AME Real Estate Investment Trust',
    '0325.KL': 'Northeast Group',
    '5280.KL': 'KIP Real Estate Investment Trust',
    '7241.KL': 'Nextgreen Global',
    '7106.KL': 'Supermax Corporation',
    '5827.KL': 'Oriental Interest',
    '6971.KL': 'Kobay Technology',
    '3662.KL': 'Malayan Flour Mills',
    '9792.KL': 'SEG International',
    '5218.KL': 'Vantris Energy',
    '5317.KL': 'CPE Technology',
    '5024.KL': 'Hup Seng Industries',
    '5274.KL': 'Hong Leong Capital',
    '7087.KL': 'Magni-Tech Industries',
    '5328.KL': 'Life Water',
    '6351.KL': 'Amway (Malaysia) Holdings',
    '6491.KL': 'Kumpulan Fima',
    '0099.KL': 'Scicom (MSC)',
    '0376.KL': 'Insights Analytics',
    '5517.KL': 'Shangri-La Hotels (Malaysia)',
    '0161.KL': 'Hextar Industries',
    '0293.KL': 'KJTS Group',
    '1503.KL': 'GuocoLand (Malaysia)',
    '0291.KL': 'Critical Holdings',
    '0112.KL': 'Mikro MSC',
    '0392.KL': 'Kee Ming Group',
    '0242.KL': 'Pappajack',
    '5284.KL': 'Lotte Chemical Titan Holding',
    '7010.KL': 'PTT Synergy Group',
    '5041.KL': 'PBA Holdings',
    '0360.KL': 'Signature Alliance Group',
    '7035.KL': 'CCK Consolidated Holdings',
    '5319.KL': 'MKH Oil Palm (East Kalimantan)',
    '0273.KL': 'Vestland',
    '0098.KL': 'AuMas Resources',
    '7048.KL': 'Atlan Holdings',
    '5789.KL': 'LBS Bina Group',
    '5325.KL': 'Well Chip Group',
    '5001.KL': 'Mieco',
    '0390.KL': 'ISF Group',
    '3379.KL': 'Insas',
    '0239.KL': 'Ecomate Holdings',
    '0230.KL': 'Teladan Group',
    '7095.KL': 'P.I.E. Industrial',
    '5665.KL': 'Southern Steel',
    '5075.KL': 'Plenitude',
    '7204.KL': 'D & O Green Technologies',
    '5084.KL': 'Ibraco',
    '8877.KL': 'Ekovest',
    '2569.KL': 'Sungei Bagan Rubber Company (Malaya)',
    '5336.KL': 'CUCKOO International (MAL)',
    '0240.KL': 'Coraza Integrated Technology',
    '7231.KL': 'Wellcall Holdings',
    '5015.KL': 'APM Automotive Holdings',
    '8524.KL': 'Taliworks Corporation',
    '6939.KL': 'Fiamma Holdings',
    '2305.KL': 'AYER Holdings',
    '3611.KL': 'Paragon Globe',
    '6017.KL': 'SHL Consolidated',
    '0002.KL': 'Kotra Industries',
    '5110.KL': 'Uoa Real Estate Investment',
    '7197.KL': 'GE-Shen Corporation',
    '5186.KL': 'Malaysia Marine and Heavy Engineering Holdings',
    '5184.KL': 'Cypark Resources',
    '0217.KL': 'Powerwell Holdings',
    '0326.KL': 'Sorento Capital',
    '7609.KL': 'Ajiya',
    '5125.KL': 'Pantech Group Holdings',
    '1058.KL': 'Manulife Holdings',
    '6874.KL': 'JAG Capital',
    '0310.KL': 'UUE Holdings',
    '5238.KL': 'AirAsia Group',
    '5318.KL': 'DXN Holdings',
    '0391.KL': 'Ambest Group',
    '5142.KL': 'Wasco',
    '2062.KL': 'Harbour-Link Group',
    '5112.KL': 'Th Plantations',
    '0453.KL': 'EI Power',
    '7252.KL': 'Teo Seng Capital',
    '5308.KL': 'Seng Fong Holdings',
    '7167.KL': 'Able Global',
    '7155.KL': 'Skp Resources',
    '0372.KL': 'Cheeding Holdings',
    '0198.KL': 'GDB Holdings',
    '4243.KL': 'W T K Holdings',
    '5132.KL': 'Deleum',
    '6432.KL': 'Apollo Food Holdings',
    '9571.KL': 'Mitrajaya Holdings',
    '5072.KL': 'Hiap Teck Venture',
    '6378.KL': 'Bedi',
    '5080.KL': 'Poh Kong Holdings',
    '0308.KL': 'KTI Landmark',
    '5331.KL': 'Pantech Global',
    '0292.KL': 'Jati Tinggi Group',
    '0286.KL': 'Evergreen Max Cash Capital',
    '5259.KL': 'Avangaad',
    '5073.KL': 'Naim Holdings',
    '5703.KL': 'Muhibbah Engineering (M)',
    '2097.KL': 'Meta Bright Group',
    '0398.KL': 'Golden Destinations Group',
    '5332.KL': 'Reach Ten Holdings',
    '2054.KL': 'Tdm',
    '5171.KL': 'Kimlun Corporation',
    '7174.KL': 'CAB Cakaran Corporation',
    '5010.KL': 'Tong Herr Resources',
    '0395.KL': 'OGX Group',
    '0263.KL': 'Betamek',
    '0012.KL': 'Three-A Resources',
    '8117.KL': 'PGF Capital',
    '0366.KL': 'Icents Group Holdings',
    '0298.KL': 'Wentel Engineering Holdings',
    '7501.KL': 'Harn Len Corporation',
    '0368.KL': 'Oxford Innotech',
    '5341.KL': 'LAC Med',
    '8311.KL': 'Pesona Metro Holdings',
    '0246.KL': 'Cnergenz',
    '7210.KL': 'Fm Global Logistics Holdings',
    '0382.KL': 'Foodie Media',
    '0296.KL': 'HE Group',
    '0276.KL': 'Autocount Dotcom',
    '5303.KL': 'Swift Haulage',
    '9172.KL': 'Formosa Prosonic Industries',
    '7108.KL': 'Perdana Petroleum',
    '5310.KL': 'Kumpulan Kitacon',
    '0037.KL': 'RGB International',
    '5196.KL': 'Berjaya Food',
    '0157.KL': 'Focus Point Holdings',
    '5049.KL': 'Country View',
    '0236.KL': 'Ramssol Group',
    '5077.KL': 'Maybulk',
    '7192.KL': 'Giib Holdings',
    '0006.KL': 'Pineapple Resources',
    '0011.KL': 'Brite-Tech',
    '0034.KL': 'Mmag Holdings',
    '0066.KL': 'Vsolar Group',
    '0074.KL': 'Green Ocean Corporation',
    '0080.KL': 'Straits Energy Resources',
    '0109.KL': 'Sc Estate Builder',
    '0116.KL': 'Focus Dynamics Group',
    '0117.KL': 'Smrt Holdings',
    '0136.KL': 'Greenyield',
    '0143.KL': 'Key Asic',
    '0174.KL': 'Evd',
    '0175.KL': 'Hhrg',
    '0188.KL': 'Hlt Global',
    '0195.KL': 'Binasat Communications',
    '0200.KL': 'Revenue Group',
    '0238.KL': 'Cekd',
    '0278.KL': 'Edelteq Holdings',
    '0281.KL': 'Daythree Digital',
    '0289.KL': 'Plytec Holding',
    '0304.KL': 'Farm Price Holdings',
    '0320.KL': 'Steel Hawk',
    '0328.KL': '3Ren',
    '0343.KL': 'Techstore',
    '0345.KL': 'Es Sunlogy',
    '0347.KL': 'Wawasan Dengkil Holdings',
    '0350.KL': 'Msb Global Group',
    '0358.KL': 'Ict Zone Asia',
    '0365.KL': 'A1 A.K. Koh Group',
    '0367.KL': 'Enproserve Group',
    '0379.KL': 'Pmw International',
    '0393.KL': 'Teamstar',
    '0399.KL': 'Ams Advanced Material',
    '0457.KL': 'Pentech Holdings',
    '0458.KL': 'Elsa',
    '0459.KL': 'Sum Technology',
    '0463.KL': 'Eckem Holdings',
    '0466.KL': 'Srkk Ai',
    '1236.KL': 'Mbf Holdings',
    '2127.KL': 'Comfort Gloves',
    '3778.KL': 'Melewar Industrial Group',
    '3891.KL': 'Malayan United Industries',
    '4057.KL': 'Asian Pac Holdings',
    '4235.KL': 'Lion Industries Corporation',
    '4316.KL': 'Sin Heng Chan (Malaya)',
    '5098.KL': 'Malaysia Steel Works (Kl)',
    '5127.KL': 'Amanahraya Reits',
    '5157.KL': 'Saudigold Group',
    '5163.KL': 'Seremban Engineering',
    '5166.KL': 'Cyberjaya Education Group',
    '5175.KL': 'Ivory Properties Group',
    '5179.KL': 'Berjaya Retail',
    '5222.KL': 'Fgv Holdings',
    '5305.KL': 'Senheng New Retail',
    '5322.KL': 'Feytech Holdings',
    '5345.KL': 'Geohan Corporation',
    '5533.KL': 'Ocb',
    '5576.KL': 'Minho (M)',
    '5738.KL': 'Country Heights Holdings',
    '5797.KL': 'Choo Bee Metal Industries',
    '6025.KL': 'Berjaya Media',
    '6637.KL': 'Pne Pcb',
    '7005.KL': 'B.I.G. Industries',
    '7020.KL': 'Asteel Group',
    '7068.KL': 'Akn Technology',
    '7071.KL': 'Ocr Group',
    '7078.KL': 'Ahmad Zaki Resources',
    '7080.KL': 'Permaju Industries',
    '7112.KL': 'Ingress Corporation',
    '7120.KL': 'Axteria Group',
    '7123.KL': 'Priceworth International',
    '7140.KL': 'Oka Corporation',
    '7164.KL': 'Knm Group',
    '7173.KL': 'Toyo Ink Group',
    '7213.KL': 'Hovid',
    '7215.KL': 'Ni Hsin Group',
    '7219.KL': 'Aizo Group',
    '7315.KL': 'Ahb Holdings',
    '7439.KL': 'Teck Guan Perdana',
    '7854.KL': 'Timberwell',
    '8648.KL': 'Jasa Kita',
    '8826.KL': 'Eng Teknologi Holdings',
    '8893.KL': 'Mk Land Holdings',
    '9148.KL': 'Greater Bay Holdings',
    '9237.KL': 'Sarawak Consolidated Industries',
    '9288.KL': 'Bonia Corporation',
    '9334.KL': 'Kesm Industries',
    '9881.KL': 'Leader Steel Holdings',

    # --- 606->606 補齊缺NAMES的87檔（audit_missing核對，2026-08-18）---
    '0025.KL': 'YBS International',
    '0028.KL': 'Scope Industries',
    '0039.KL': 'GFM Services',
    '0040.KL': 'OpenSys',
    '0058.KL': 'JcbNext',
    '0089.KL': 'Tex Cycle Technology',
    '0106.KL': 'OpenMove AI',
    '0131.KL': 'Divfex',
    '0149.KL': 'Fibon',
    '0158.KL': 'SCC Holdings',
    '0167.KL': 'MClean Technologies',
    '0192.KL': 'Inta Bina Group',
    '0202.KL': 'Radiant Globaltech',
    '0206.KL': 'Gagasan Nadi Cergas',
    '0212.KL': 'SDS Group',
    '0222.KL': 'Optimax Holdings',
    '0237.KL': 'Haily Group',
    '0250.KL': 'YX Precious Metals',
    '0252.KL': 'Orgabio Holdings',
    '0256.KL': 'UMediC Group',
    '0257.KL': 'Unique Fire Holdings',
    '0258.KL': 'Agmo Holdings',
    '0277.KL': 'Cloudpoint Technology',
    '0284.KL': 'Glostrext',
    '0290.KL': 'Panda Eco System',
    '0299.KL': 'AGX Group',
    '0302.KL': 'Topmix',
    '0307.KL': 'Kawan Renergy',
    '0313.KL': 'BWYS Group',
    '0317.KL': 'EPB Group',
    '0319.KL': 'VETECE Holdings',
    '0323.KL': 'Crest Group',
    '0327.KL': 'OB Holdings',
    '0331.KL': 'Cropmate',
    '0333.KL': 'Vanzo Holdings',
    '0336.KL': 'Winstar Capital',
    '0340.KL': 'Northern Solar Holdings',
    '0341.KL': 'Colform Group',
    '0342.KL': 'RichTech Digital',
    '0346.KL': 'Saliran Group',
    '0348.KL': 'Chemlite Innovation',
    '0353.KL': 'West River',
    '0355.KL': 'Fibromat',
    '0357.KL': 'Oasis Home Holding',
    '0363.KL': 'PMCK',
    '0370.KL': 'Express Powerr Solutions',
    '0380.KL': 'Aquawalk Group',
    '0383.KL': 'PSP Energy',
    '0386.KL': 'SBS Nexus',
    '0396.KL': 'Adnex Group',
    '0455.KL': 'Bus Cap',
    '0460.KL': 'HSS Holdings',
    '0465.KL': 'RNG Tech',
    '3247.KL': 'GUH Holdings',
    '3913.KL': 'MUI Properties',
    '5036.KL': 'Edaran',
    '5070.KL': 'Protasco',
    '5078.KL': 'Marine & General',
    '5147.KL': 'Samchem Holdings',
    '5149.KL': 'TAS Offshore',
    '5219.KL': 'Pestec International',
    '5300.KL': 'Yenher Holdings',
    '6203.KL': 'Khee San',
    '6297.KL': 'Box-Pak',
    '6912.KL': 'Pasdec Holdings',
    '7004.KL': 'MCE Holdings',
    '7055.KL': 'PLB Engineering',
    '7085.KL': 'LTKM',
    '7115.KL': 'SKB Shutters Corporation',
    '7131.KL': 'ACME Holdings',
    '7133.KL': 'United U-LI Corporation',
    '7134.KL': 'PWF Corporation',
    '7145.KL': 'Txcd',
    '7170.KL': 'LFE Corporation',
    '7176.KL': 'TPC Plus',
    '7211.KL': 'TAFI Industries',
    '7230.KL': 'Tomei Consolidated',
    '7382.KL': 'Golden Land',
    '7579.KL': 'AWC',
    '7935.KL': 'Milux Corporation',
    '8192.KL': 'Mercury Industries',
    '8273.KL': 'Public Packages Holdings',
    '8435.KL': 'Concrete Engineering Products',
    '8613.KL': 'ENRA Group',
    '9326.KL': 'LB Aluminium',
    '9369.KL': 'Teo Guan Lee Corporation',
    '9776.KL': 'Rivertree STF Synergies',
}

# 板塊分類
SECTORS = {
    # 金融
    '1155.KL':'金融','1023.KL':'金融','1295.KL':'金融','5819.KL':'金融',
    '1066.KL':'金融','1015.KL':'金融','5185.KL':'金融','1082.KL':'金融',
    '5258.KL':'金融','5099.KL':'工業','1597.KL':'金融','1277.KL':'金融',
    '5115.KL':'能源','7107.KL':'消費','2488.KL':'金融','6399.KL':'電信',
    '6076.KL':'房地產','8532.KL':'金融',
    # 公用/能源
    '5347.KL':'能源','5183.KL':'能源','6033.KL':'能源','5026.KL':'棕榈油',
    '5116.KL':'房地產','3816.KL':'工業','5071.KL':'能源','1532.KL':'能源',
    '3948.KL':'消費','2771.KL':'工業','1929.KL':'棕榈油',
    # 電信
    '6888.KL':'電信','4863.KL':'電信','6012.KL':'電信','6947.KL':'電信',
    '5168.KL':'手套','6742.KL':'能源','6399.KL':'電信',
    # 棕榈油
    '2445.KL':'工業','1961.KL':'消費','2291.KL':'棕榈油','1899.KL':'工業',
    '2038.KL':'棕榈油','5029.KL':'棕榈油','5135.KL':'棕榈油','5033.KL':'棕榈油',
    '4731.KL':'消費','0146.KL':'科技','1589.KL':'房地產','5211.KL':'工業',
    '0148.KL':'消費','3867.KL':'科技','2658.KL':'消費','3026.KL':'消費',
    '4502.KL':'電信','5398.KL':'工業',
    # 消費/零售
    '4588.KL':'工業','5285.KL':'消費','5081.KL':'消費','7222.KL':'工業',
    '4609.KL':'消費','5878.KL':'消費','6556.KL':'工業','7293.KL':'消費',
    '7178.KL':'醫療','5242.KL':'工業','4162.KL':'消費','3255.KL':'消費',
    '5822.KL':'消費','5264.KL':'能源','3042.KL':'能源','0163.KL':'手套',
    '5014.KL':'運輸','3417.KL':'房地產','5143.KL':'工業',
    # 工業/建築
    '3182.KL':'消費','4715.KL':'消費','3336.KL':'工業','1996.KL':'棕榈油',
    '9679.KL':'工業','3549.KL':'工業','5148.KL':'房地產','5141.KL':'能源',
    '1724.KL':'房地產','9261.KL':'工業','2194.KL':'工業','3476.KL':'棕榈油',
    '4197.KL':'工業','8583.KL':'房地產','5983.KL':'工業','1619.KL':'工業',
    '2220.KL':'工業','3689.KL':'消費','0249.KL':'科技','3239.KL':'工業',
    # 科技/半導體
    '0049.KL':'消費','5296.KL':'消費','0078.KL':'工業','0090.KL':'科技','0051.KL':'科技',
    '7034.KL':'消費','9814.KL':'房地產','5243.KL':'能源','0097.KL':'科技',
    '0196.KL':'科技','0065.KL':'科技','9296.KL':'金融','7073.KL':'工業',
    '0050.KL':'科技','0186.KL':'工業','0138.KL':'科技','5053.KL':'房地產',
    '0177.KL':'工業','7212.KL':'工業','0197.KL':'消費','5250.KL':'工業',
    '5134.KL':'工業','5205.KL':'工業','5299.KL':'房地產',
    # 手套
    '7153.KL':'手套','5027.KL':'棕榈油','7113.KL':'手套','7090.KL':'醫療',
    # 醫療
    '5216.KL':'科技','1301.KL':'醫療','3557.KL':'房地產','5079.KL':'醫療',
    '3794.KL':'醫療','5007.KL':'醫療','9121.KL':'醫療','5136.KL':'工業',
    # 房地產/REIT
    '5236.KL':'房地產','5180.KL':'房地產','5111.KL':'房地產','5227.KL':'房地產',
    '5124.KL':'房地產','5269.KL':'房地產','5020.KL':'房地產','5275.KL':'消費',
    '4898.KL':'房地產','5008.KL':'工業','5246.KL':'工業','7028.KL':'工業',
    '8869.KL':'工業','9075.KL':'科技','5139.KL':'金融','8230.KL':'房地產',
    '5294.KL':'房地產','5209.KL':'能源',
    # 運輸/基建
    '6599.KL':'消費','5247.KL':'消費','5106.KL':'房地產','5109.KL':'房地產',
    '5119.KL':'運輸','3786.KL':'運輸','4635.KL':'運輸','4665.KL':'運輸',
    '5879.KL':'運輸','0820EA.KL':'運輸',
    # 其他
    '1562.KL':'工業','7076.KL':'工業','2267.KL':'其他','7084.KL':'其他',
    '0023.KL':'其他','7182.KL':'其他','2488.KL':'金融',
    # 新增-醫療
    '5225.KL':'醫療','5555.KL':'醫療','7081.KL':'醫療','0303.KL':'醫療',
    '7148.KL':'醫療','1287.KL':'醫療','0101.KL':'醫療',
    # 新增-工業
    '5326.KL':'工業','4065.KL':'工業','7277.KL':'工業','5263.KL':'工業',
    '0151.KL':'工業','5273.KL':'工業','3301.KL':'工業','4006.KL':'工業',
    '5356.KL':'工業','7161.KL':'工業','0270.KL':'工業','5038.KL':'工業',
    '0225.KL':'工業','9822.KL':'工業','5012.KL':'工業','3565.KL':'工業',
    '5000.KL':'工業','0338.KL':'工業','0245.KL':'工業','5255.KL':'工業',
    '0375.KL':'工業','8907.KL':'工業','2429.KL':'工業','9059.KL':'工業',
    '7052.KL':'工業','7105.KL':'工業','0339.KL':'工業','0233.KL':'工業',
    '4383.KL':'工業','5271.KL':'工業','0295.KL':'工業','7180.KL':'工業',
    '0193.KL':'工業','5173.KL':'工業','0223.KL':'工業','0325.KL':'工業',
    '5024.KL':'工業','6351.KL':'工業','0161.KL':'工業','0293.KL':'工業',
    '0291.KL':'工業','0392.KL':'工業','7010.KL':'工業','0360.KL':'工業',
    '7035.KL':'工業','0098.KL':'工業','5789.KL':'工業','0390.KL':'工業',
    '0239.KL':'工業','0230.KL':'工業','7095.KL':'工業','5665.KL':'工業',
    '7231.KL':'工業','5015.KL':'工業','6939.KL':'工業','2305.KL':'工業',
    '0002.KL':'工業','5186.KL':'工業','5184.KL':'工業','0310.KL':'工業',
    # 新增-消費
    '4677.KL':'消費','4707.KL':'消費','5681.KL':'消費','5031.KL':'消費',
    '0128.KL':'消費','0166.KL':'消費','5337.KL':'消費','5292.KL':'消費',
    '5005.KL':'消費','1818.KL':'消費','5340.KL':'消費','3034.KL':'消費',
    '8621.KL':'消費','5286.KL':'消費','5606.KL':'消費','8664.KL':'消費',
    '2836.KL':'消費','5200.KL':'消費','5306.KL':'消費','7160.KL':'消費',
    '5102.KL':'消費','5151.KL':'消費','5401.KL':'消費','3069.KL':'消費',
    '5330.KL':'消費','6633.KL':'消費','7195.KL':'消費','5074.KL':'消費',
    '5210.KL':'消費','7103.KL':'消費','5313.KL':'消費','5162.KL':'消費',
    '3859.KL':'消費','5916.KL':'消費','4456.KL':'消費','5327.KL':'消費',
    '1651.KL':'消費','3395.KL':'消費','7100.KL':'消費','0045.KL':'消費',
    '2593.KL':'消費','0056.KL':'消費','5321.KL':'消費','6114.KL':'消費',
    '5351.KL':'消費','5248.KL':'消費','2852.KL':'消費','5161.KL':'消費',
    '6718.KL':'消費','5320.KL':'消費','5908.KL':'消費','0265.KL':'消費',
    '6963.KL':'消費','5302.KL':'消費','4758.KL':'消費','3905.KL':'消費',
    '5348.KL':'消費','7246.KL':'消費','5293.KL':'消費','8052.KL':'消費',
    '7241.KL':'消費','7106.KL':'消費','5827.KL':'消費','3662.KL':'消費',
    '9792.KL':'消費','5328.KL':'消費','6491.KL':'消費','0099.KL':'消費',
    '0376.KL':'消費','5517.KL':'消費','1503.KL':'消費','0112.KL':'消費',
    '0242.KL':'消費','5284.KL':'消費','5041.KL':'消費','7048.KL':'消費',
    '5001.KL':'消費','3379.KL':'消費','5075.KL':'消費','7204.KL':'消費',
    '5084.KL':'消費','8877.KL':'消費','2569.KL':'消費','5336.KL':'消費',
    '8524.KL':'消費','3611.KL':'消費','6017.KL':'消費','7197.KL':'消費',
    '7609.KL':'消費',
    # 新增-房地產
    '5249.KL':'房地產','5235SS.KL':'房地產','5288.KL':'房地產','5176.KL':'房地產',
    '8206.KL':'房地產','5212.KL':'房地產','5338.KL':'房地產','7187.KL':'房地產',
    '4219.KL':'房地產','7179.KL':'房地產','5123.KL':'房地產','5307.KL':'房地產',
    '5280.KL':'房地產','0273.KL':'房地產','5110.KL':'房地產',
    # 新增-棕榈油
    '2089.KL':'棕榈油','5323.KL':'棕榈油','5126.KL':'棕榈油','5138.KL':'棕榈油',
    '5069.KL':'棕榈油','6262.KL':'棕榈油','5319.KL':'棕榈油',
    # 新增-科技
    '0208.KL':'科技','5357.KL':'科技','5309.KL':'科技','7172.KL':'科技',
    '7233.KL':'科技','0168.KL':'科技','0259.KL':'科技','0251.KL':'科技',
    '6971.KL':'科技','5317.KL':'科技','7087.KL':'科技','5325.KL':'科技',
    '0240.KL':'科技','5125.KL':'科技',
    # 新增-金融
    '1171.KL':'金融','1163.KL':'金融','6139.KL':'金融','6459.KL':'金融',
    '9687.KL':'金融','0351.KL':'金融','5274.KL':'金融','0326.KL':'金融',
    '1058.KL':'金融','6874.KL':'金融',
    # 新增-能源
    '0215.KL':'能源','5272.KL':'能源','0318.KL':'能源','5199.KL':'能源',
    '4324.KL':'能源','5218.KL':'能源','0217.KL':'能源',
    # 新增-運輸
    '5352.KL':'運輸','5032.KL':'運輸','5335.KL':'運輸',
    # 新增-電信
    '5301.KL':'電信',
    '5318.KL': '消費',
    '5142.KL': '能源',
    '2062.KL': '運輸',
    '5112.KL': '棕榈油',
    '0453.KL': '工業',
    '7252.KL': '棕榈油',
    '7167.KL': '消費',
    '0372.KL': '工業',
    '0198.KL': '工業',
    '4243.KL': '工業',
    '5132.KL': '能源',
    '6432.KL': '消費',
    '9571.KL': '工業',
    '5072.KL': '工業',
    '5080.KL': '消費',
    '0308.KL': '房地產',
    '5331.KL': '工業',
    '0292.KL': '工業',
    '0286.KL': '金融',
    '5259.KL': '運輸',
    '0398.KL': '消費',
    '5332.KL': '電信',
    '5171.KL': '工業',
    '7174.KL': '棕榈油',
    '0395.KL': '科技',
    '0263.KL': '工業',
    '8117.KL': '工業',
    '0366.KL': '工業',
    '0298.KL': '工業',
    '5341.KL': '醫療',
    '8311.KL': '工業',
    '0382.KL': '消費',
    '0296.KL': '工業',
    '0276.KL': '科技',
    '9172.KL': '消費',
    '5310.KL': '工業',
    '0037.KL': '消費',
    '0157.KL': '消費',
    '5049.KL': '房地產',
    '0236.KL': '科技',
    '0011.KL': '能源',
    '0025.KL': '工業',
    '0028.KL': '工業',
    '0039.KL': '工業',
    '0040.KL': '科技',
    '0058.KL': '工業',
    '0089.KL': '工業',
    '0106.KL': '科技',
    '0117.KL': '科技',
    '0131.KL': '科技',
    '0149.KL': '工業',
    '0158.KL': '消費',
    '0167.KL': '工業',
    '0192.KL': '工業',
    '0202.KL': '科技',
    '0206.KL': '工業',
    '0212.KL': '消費',
    '0222.KL': '醫療',
    '0237.KL': '工業',
    '0238.KL': '工業',
    '0250.KL': '消費',
    '0252.KL': '消費',
    '0256.KL': '醫療',
    '0257.KL': '工業',
    '0258.KL': '科技',
    '0277.KL': '科技',
    '0278.KL': '科技',
    '0284.KL': '工業',
    '0290.KL': '科技',
    '0299.KL': '運輸',
    '0302.KL': '工業',
    '0304.KL': '消費',
    '0307.KL': '工業',
    '0313.KL': '工業',
    '0317.KL': '工業',
    '0319.KL': '科技',
    '0320.KL': '能源',
    '0323.KL': '工業',
    '0327.KL': '消費',
    '0328.KL': '科技',
    '0331.KL': '工業',
    '0333.KL': '消費',
    '0336.KL': '工業',
    '0340.KL': '能源',
    '0341.KL': '工業',
    '0342.KL': '消費',
    '0343.KL': '科技',
    '0345.KL': '工業',
    '0346.KL': '工業',
    '0348.KL': '工業',
    '0353.KL': '工業',
    '0355.KL': '工業',
    '0357.KL': '消費',
    '0358.KL': '科技',
    '0363.KL': '醫療',
    '0370.KL': '工業',
    '0380.KL': '消費',
    '0383.KL': '工業',
    '0386.KL': '消費',
    '0396.KL': '工業',
    '0399.KL': '工業',
    '0455.KL': '工業',
    '0460.KL': '消費',
    '0465.KL': '消費',
    '2127.KL': '手套',
    '3247.KL': '工業',
    '3913.KL': '房地產',
    '5036.KL': '科技',
    '5070.KL': '工業',
    '5078.KL': '運輸',
    '5147.KL': '工業',
    '5149.KL': '運輸',
    '5163.KL': '工業',
    '5166.KL': '消費',
    '5219.KL': '工業',
    '5300.KL': '棕榈油',
    '6203.KL': '消費',
    '6297.KL': '工業',
    '6912.KL': '房地產',
    '7004.KL': '工業',
    '7005.KL': '工業',
    '7055.KL': '房地產',
    '7085.KL': '棕榈油',
    '7115.KL': '工業',
    '7131.KL': '房地產',
    '7133.KL': '工業',
    '7134.KL': '棕榈油',
    '7145.KL': '工業',
    '7170.KL': '工業',
    '7176.KL': '棕榈油',
    '7211.KL': '消費',
    '7230.KL': '消費',
    '7382.KL': '棕榈油',
    '7579.KL': '工業',
    '7935.KL': '消費',
    '8192.KL': '工業',
    '8273.KL': '工業',
    '8435.KL': '工業',
    '8613.KL': '能源',
    '8648.KL': '工業',
    '9326.KL': '工業',
    '9369.KL': '消費',
    '9776.KL': '棕榈油',

    # --- 補齊缺SECTORS的92檔（audit_missing核對，2026-08-18）---
    '0006.KL': '科技',
    '0012.KL': '消費',
    '0034.KL': '科技',
    '0066.KL': '科技',
    '0074.KL': '消費',
    '0080.KL': '運輸',
    '0109.KL': '工業',
    '0116.KL': '消費',
    '0136.KL': '消費',
    '0143.KL': '科技',
    '0174.KL': '科技',
    '0175.KL': '消費',
    '0188.KL': '工業',
    '0195.KL': '電信',
    '0200.KL': '科技',
    '0246.KL': '工業',
    '0281.KL': '科技',
    '0289.KL': '工業',
    '0347.KL': '工業',
    '0350.KL': '消費',
    '0365.KL': '消費',
    '0367.KL': '工業',
    '0368.KL': '工業',
    '0379.KL': '工業',
    '0391.KL': '工業',
    '0393.KL': '消費',
    '0457.KL': '科技',
    '0458.KL': '能源',
    '0459.KL': '工業',
    '0463.KL': '工業',
    '0466.KL': '科技',
    '1236.KL': '金融',
    '2054.KL': '消費',
    '2097.KL': '消費',
    '3778.KL': '工業',
    '3891.KL': '消費',
    '4057.KL': '房地產',
    '4235.KL': '工業',
    '4316.KL': '消費',
    '5010.KL': '工業',
    '5073.KL': '工業',
    '5077.KL': '運輸',
    '5098.KL': '工業',
    '5127.KL': '房地產',
    '5157.KL': '消費',
    '5175.KL': '房地產',
    '5179.KL': '消費',
    '5196.KL': '消費',
    '5222.KL': '棕榈油',
    '5238.KL': '運輸',
    '5303.KL': '運輸',
    '5305.KL': '消費',
    '5308.KL': '工業',
    '5322.KL': '消費',
    '5345.KL': '工業',
    '5533.KL': '消費',
    '5576.KL': '工業',
    '5703.KL': '工業',
    '5738.KL': '消費',
    '5797.KL': '工業',
    '6025.KL': '消費',
    '6378.KL': '工業',
    '6637.KL': '科技',
    '7020.KL': '工業',
    '7068.KL': '工業',
    '7071.KL': '房地產',
    '7078.KL': '工業',
    '7080.KL': '消費',
    '7108.KL': '能源',
    '7112.KL': '工業',
    '7120.KL': '房地產',
    '7123.KL': '工業',
    '7140.KL': '工業',
    '7155.KL': '工業',
    '7164.KL': '能源',
    '7173.KL': '工業',
    '7192.KL': '工業',
    '7210.KL': '運輸',
    '7213.KL': '醫療',
    '7215.KL': '消費',
    '7219.KL': '工業',
    '7315.KL': '消費',
    '7439.KL': '消費',
    '7501.KL': '消費',
    '7854.KL': '工業',
    '8826.KL': '科技',
    '8893.KL': '房地產',
    '9148.KL': '消費',
    '9237.KL': '工業',
    '9288.KL': '消費',
    '9334.KL': '科技',
    '9881.KL': '工業',
}

# TradingView 代碼對照 (用於Watchlist匯入)
TV_SYMBOLS = {
    '1155.KL': 'MAYBANK', '1295.KL': 'PBBANK', '1023.KL': 'CIMB',
    '5819.KL': 'HLBANK', '1066.KL': 'RHBBANK', '1015.KL': 'AMBANK',
    '5185.KL': 'AFFIN', '1082.KL': 'ABMB', '5258.KL': 'MBSB',
    '5099.KL': 'BURSA', '1597.KL': 'BIMB', '1277.KL': 'HLFG',
    '5115.KL': 'ALAM', '7107.KL': 'OFI', '2488.KL': 'KLCC',
    '6399.KL': 'ASTRO', '6076.KL': 'AMBANK',
    '5347.KL': 'TENAGA', '5183.KL': 'PCHEM', '6033.KL': 'PETGAS',
    '5026.KL': 'VELESTO', '5116.KL': 'YINSON', '3816.KL': 'PETDAG',
    '5071.KL': 'DIALOG', '1532.KL': 'HIBISCS', '3948.KL': 'ARMADA',
    '2771.KL': 'BSTEAD', '5250.KL': 'PMETAL',
    '6888.KL': 'MAXIS', '4863.KL': 'TM', '6012.KL': 'CDB',
    '6947.KL': 'AXIATA', '5168.KL': 'TM', '6742.KL': 'TIMECOM',
    '2445.KL': 'IOICORP', '1961.KL': 'KLK', '2291.KL': 'GENP',
    '1899.KL': 'GENP', '2038.KL': 'BPLANT', '5029.KL': 'FGV',
    '5135.KL': 'SWKPLNT', '5033.KL': 'KULIM', '4731.KL': 'PPB',
    '0146.KL': 'JFTECH', '1589.KL': 'IWCITY', '5211.KL': 'SUNWAY',
    '0148.KL': 'SUNZEN', '3867.KL': 'MPI', '2658.KL': 'THP',
    '3026.KL': 'TWP', '4502.KL': 'IJMPLNT',
    '4588.KL': 'UMWH', '5285.KL': 'QL', '5081.KL': 'DLADY',
    '7222.KL': 'F&N', '4609.KL': 'HEIM', '5878.KL': 'AEON',
    '6556.KL': 'MRDIY', '7293.KL': 'AEONCR', '7178.KL': 'PADINI',
    '5242.KL': 'BONIA', '4162.KL': 'SCIENTX', '3255.KL': 'VS',
    '5822.KL': '99SMART', '5264.KL': 'FFB', '3042.KL': 'HAIO',
    '0163.KL': 'BJFOOD', '5014.KL': 'AIRPORT', '3417.KL': 'TCHONG',
    '5143.KL': 'MFM',
    '3182.KL': 'GENTING', '4715.KL': 'GENM', '3336.KL': 'IJM',
    '1996.KL': 'KRETAM', '9679.KL': 'WCT', '3549.KL': 'YTL',
    '5148.KL': 'YTLPOWR', '5141.KL': 'HAPSENG', '1724.KL': 'SIME',
    '9261.KL': 'BJCORP', '2194.KL': 'MMCCORP', '3476.KL': 'KSENG',
    '4197.KL': 'KERJAYA', '8583.KL': 'PARKSON', '5983.KL': 'KKBE',
    '1619.KL': 'BJLAND', '2220.KL': 'BJLAND', '3689.KL': 'BKAWAN',
    '0049.KL': 'VITROX', '5296.KL': 'REVENUE', '0078.KL': 'GHL',
    '0090.KL': 'GTRONIC', '7034.KL': 'UNISEM', '9814.KL': 'PENTA',
    '5243.KL': 'UWC', '0097.KL': 'CORAZA', '0196.KL': 'DNEX',
    '0065.KL': 'SCICOM', '9296.KL': 'RCECAP', '7073.KL': 'FRONTKN',
    '0050.KL': 'PRESBHD', '0186.KL': 'DKSH', '0138.KL': 'MYEG',
    '5053.KL': 'INARI', '0177.KL': 'DATASONIC', '7212.KL': 'KAREX',
    '0197.KL': 'GENETEC', '5134.KL': 'CAPITALA', '5205.KL': 'TECHNOVE',
    '5299.KL': 'TELADAN', '7153.KL': 'TOPGLOV', '5027.KL': 'KOSSAN',
    '7113.KL': 'SUPERMX', '7090.KL': 'APEX',
    '5216.KL': 'IHH', '1301.KL': 'KPJ', '3557.KL': 'PHARMA',
    '5079.KL': 'APEX', '3794.KL': 'DUOPHARMA', '5007.KL': 'HOVID',
    '9121.KL': 'CCK', '5136.KL': 'CARING',
    '5236.KL': 'SUNREIT', '5180.KL': 'KLCCSS', '5111.KL': 'PAVREIT',
    '5227.KL': 'AXREIT', '5124.KL': 'AMFIRST', '5269.KL': 'IGBREIT',
    '5020.KL': 'SURIA', '5275.KL': 'SENTRAL', '4898.KL': 'TAENT',
    '5008.KL': 'SPSETIA', '5246.KL': 'ECOWLD', '7028.KL': 'MAHSING',
    '8869.KL': 'MATRIX', '9075.KL': 'SIGN', '5139.KL': 'SWKCORP',
    '8230.KL': 'TAMBUN', '5294.KL': 'IOIPG', '5209.KL': 'ECOWLD',
    '6599.KL': 'AIRPORT', '5247.KL': 'MAB', '5106.KL': 'WPRTS',
    '5109.KL': 'BIPORT', '5119.KL': 'LITRAK', '3786.KL': 'LITRAK',
    '4635.KL': 'MISC', '4665.KL': 'POS', '5879.KL': 'AAX',
    '1562.KL': 'PANAMY', '7076.KL': 'POHKONG', '2267.KL': 'LAFMSIA',
    '7182.KL': 'EKA', '0023.KL': 'REVENUE', '7084.KL': 'QL',
    '3239.KL': 'TSM', '0249.KL': 'LGMS', '5398.KL': 'GAMUDA',
    '8532.KL': 'AEONCR', '0820EA.KL': 'ECOARC',
    '5225.KL': 'IHH',
    '5326.KL': '99SMART',
    '4677.KL': 'YTL',
    '4707.KL': 'NESTLE',
    '5555.KL': 'SUNMED',
    '5249.KL': 'IOIPG',
    '2089.KL': 'UTDPLT',
    '5681.KL': 'PETDAG',
    '5235SS.KL': 'KLCC',
    '4065.KL': 'PPB',
    '5031.KL': 'TIMECOM',
    '7277.KL': 'DIALOG',
    '5263.KL': 'SUNCON',
    '0128.KL': 'FRONTKN',
    '5288.KL': 'SIMEPROP',
    '0166.KL': 'INARI',
    '5337.KL': 'ECOSHOP',
    '0151.KL': 'KGB',
    '5273.KL': 'CHINHIN',
    '5176.KL': 'SUNREIT',
    '5292.KL': 'UWC',
    '5005.KL': 'UNISEM',
    '1818.KL': 'BURSA',
    '5340.KL': 'UMSINT',
    '3034.KL': 'HAPSENG',
    '8206.KL': 'ECOWLD',
    '5212.KL': 'PAVREIT',
    '0208.KL': 'GREATEC',
    '8621.KL': 'LPI',
    '3301.KL': 'HLIND',
    '5357.KL': 'SKYECHIP',
    '5323.KL': 'JPG',
    '1171.KL': 'MBSB',
    '5286.KL': 'MI',
    '5309.KL': 'ITMAX',
    '5606.KL': 'IGBB',
    '5126.KL': 'SOP',
    '8664.KL': 'SPSETIA',
    '2836.KL': 'CARLSBG',
    '5200.KL': 'UOADEV',
    '4006.KL': 'ORIENT',
    '5306.KL': 'FFB',
    '1163.KL': 'ALLIANZ',
    '7160.KL': 'PENTA',
    '5356.KL': 'STRATUS',
    '5102.KL': 'GCB',
    '7161.KL': 'KERJAYA',
    '0270.KL': 'NATGATE',
    '7172.KL': 'PMBTECH',
    '5038.KL': 'KSL',
    '0225.KL': 'SCGBHD',
    '5151.KL': 'HEXTAR',
    '0215.KL': 'SLVEST',
    '5272.KL': 'RANHILL',
    '5401.KL': 'TROP',
    '9822.KL': 'SAM',
    '3069.KL': 'MFCB',
    '6139.KL': 'TAKAFUL',
    '5352.KL': 'MTTSL',
    '5330.KL': 'TMK',
    '6633.KL': 'LHI',
    '5012.KL': 'TAANN',
    '5032.KL': 'BIPORT',
    '7195.KL': 'BNASTRA',
    '5074.KL': 'DXN',
    '6459.KL': 'MNRB',
    '3565.KL': 'WCEHB',
    '5000.KL': 'HUMEIND',
    '0338.KL': 'KOPI',
    '0245.KL': 'MNHLDG',
    '5138.KL': 'HSPLANT',
    '5210.KL': 'ARMADA',
    '7103.KL': 'SPRITZER',
    '5313.KL': 'RADIUM',
    '9687.KL': 'IDEAL',
    '5162.KL': 'VSTECS',
    '3859.KL': 'MAGNUM',
    '5916.KL': 'MSC',
    '5255.KL': 'LFG',
    '0375.KL': 'THMY',
    '0318.KL': 'ELRIDGE',
    '8907.KL': 'EG',
    '4456.KL': 'DNEX',
    '5327.KL': 'MEGAFB',
    '5301.KL': 'CTOS',
    '7081.KL': 'PHARMA',
    '1651.KL': 'MRCB',
    '7233.KL': 'DUFU',
    '2429.KL': 'TANCO',
    '3395.KL': 'BJCORP',
    '9059.KL': 'TSH',
    '5338.KL': 'PARADIGM',
    '7187.KL': 'CHGP',
    '5199.KL': 'HIBISCS',
    '7052.KL': 'PADINI',
    '5069.KL': 'BLDPLNT',
    '7105.KL': 'HCK',
    '0339.KL': 'CBHB',
    '0303.KL': 'ALPHA',
    '0351.KL': 'LSH',
    '7100.KL': 'UCHITEC',
    '0045.KL': 'SSB8',
    '0233.KL': 'PEKAT',
    '2593.KL': 'UMCCA',
    '0168.KL': 'BMGREEN',
    '4219.KL': 'BPROP',
    '0056.KL': 'NCT',
    '7148.KL': 'DPHARMA',
    '7179.KL': 'LAGENDA',
    '5321.KL': 'KEYFIELD',
    '6114.KL': 'MKH',
    '5351.KL': 'EMPIRE',
    '5248.KL': 'BAUTO',
    '2852.KL': 'CMSB',
    '5161.KL': 'JCY',
    '6262.KL': 'INNO',
    '6718.KL': 'CRESNDO',
    '5335.KL': 'HI',
    '4383.KL': 'JTIASA',
    '5320.KL': 'PLINTAS',
    '5271.KL': 'PECCA',
    '1287.KL': 'EXSIMHB',
    '0295.KL': 'MTEC',
    '5908.KL': 'DKSH',
    '0259.KL': 'SNS',
    '0265.KL': 'INFOM',
    '6963.KL': 'VS',
    '4324.KL': 'HENGYUAN',
    '5302.KL': 'ATECH',
    '7180.KL': 'SERNKOU',
    '4758.KL': 'ANCOMNY',
    '0193.KL': 'KINERGY',
    '3905.KL': 'MULPHA',
    '5348.KL': 'ORKIM',
    '5123.KL': 'SENTRAL',
    '7246.KL': 'SIGN',
    '5173.KL': 'SYGROUP',
    '0223.KL': 'SAMAIDEN',
    '5293.KL': 'AME',
    '0251.KL': 'SFPTECH',
    '0101.KL': 'TMCLIFE',
    '8052.KL': 'CGB',
    '5307.KL': 'AMEREIT',
    '0325.KL': 'NE',
    '5280.KL': 'KIPREIT',
    '7241.KL': 'NGGB',
    '7106.KL': 'SUPERMX',
    '5827.KL': 'OIB',
    '6971.KL': 'KOBAY',
    '3662.KL': 'MFLOUR',
    '9792.KL': 'SEG',
    '5218.KL': 'VANTNRG',
    '5317.KL': 'CPETECH',
    '5024.KL': 'HUPSENG',
    '5274.KL': 'HLCAP',
    '7087.KL': 'MAGNI',
    '5328.KL': 'LWSABAH',
    '6351.KL': 'AMWAY',
    '6491.KL': 'KFIMA',
    '0099.KL': 'SCICOM',
    '0376.KL': 'IAB',
    '5517.KL': 'SHANG',
    '0161.KL': 'HEXIND',
    '0293.KL': 'KJTS',
    '1503.KL': 'GUOCO',
    '0291.KL': 'CHB',
    '0112.KL': 'MIKROMB',
    '0392.KL': 'KEEMING',
    '0242.KL': 'PPJACK',
    '5284.KL': 'LCTITAN',
    '7010.KL': 'PTT',
    '5041.KL': 'PBA',
    '0360.KL': 'SAG',
    '7035.KL': 'CCK',
    '5319.KL': 'MKHOP',
    '0273.KL': 'VLB',
    '0098.KL': 'AUMAS',
    '7048.KL': 'ATLAN',
    '5789.KL': 'LBS',
    '5325.KL': 'WELLCHIP',
    '5001.KL': 'MIECO',
    '0390.KL': 'ISF',
    '3379.KL': 'INSAS',
    '0239.KL': 'ECOMATE',
    '0230.KL': 'TELADAN',
    '7095.KL': 'PIE',
    '5665.KL': 'SSTEEL',
    '5075.KL': 'PLENITU',
    '7204.KL': 'D_O',
    '5084.KL': 'IBRACO',
    '8877.KL': 'EKOVEST',
    '2569.KL': 'SBAGAN',
    '5336.KL': 'CKI',
    '0240.KL': 'CORAZA',
    '7231.KL': 'WELLCAL',
    '5015.KL': 'APM',
    '8524.KL': 'TALIWRK',
    '6939.KL': 'FIAMMA',
    '2305.KL': 'AYER',
    '3611.KL': 'PGLOBE',
    '6017.KL': 'SHL',
    '0002.KL': 'KOTRA',
    '5110.KL': 'UOAREIT',
    '7197.KL': 'GESHEN',
    '5186.KL': 'MHB',
    '5184.KL': 'CYPARK',
    '0217.KL': 'PWRWELL',
    '0326.KL': 'SORENTO',
    '7609.KL': 'AJIYA',
    '5125.KL': 'PANTECH',
    '1058.KL': 'MANULFE',
    '6874.KL': 'JAGCPTL',
    '0310.KL': 'UUE',
}

# ============================================================
# 🇺🇸 美股股票清單（從舊 us_scanner.py 搬過來，依行業分組；程式會自動去重）
# 2026-09 清理：SQ→XYZ、GOLD→B、PARA→PSKY、L3H(錯誤代碼)→LHX；移除已下市：DFS、PXD、HES、MRO、X
# 有代碼抓不到資料時，打開 /us/debug_missing 看是哪幾隻
# ============================================================
US_SECTOR_SYMBOLS = {
    '指數ETF': ['SPY','QQQ','DIA','IWM','SMH','ARKK','GLD',
               'XLK','XLF','XLE','XLV','XLI','XLC','XLY','XLP','XLB','XLRE','XLU'],
    '科技': ['AAPL','MSFT','GOOGL','META','AMZN','ORCL','CRM','ADBE','NOW','INTU',
            'WDAY','NFLX','PYPL','UBER','SNOW','PLTR','XYZ','SHOP','NET','DDOG',
            'ZS','CRWD','PANW','OKTA','TWLO','MDB','ABNB','DASH','RBLX','U',
            'LYFT','SNAP','PINS','RDDT','APP','TTD','SPOT','DUOL','TOST','DELL',
            'HPE','ANET','IONQ','CRWV','NBIS'],
    '半導體': ['NVDA','AMD','INTC','TSM','AVGO','QCOM','TXN','MU','AMAT','LRCX',
             'KLAC','MRVL','MCHP','ON','SWKS','MPWR','ENTG','WOLF','SMCI','ARM',
             'ASML','ALAB'],
    '金融': ['JPM','BAC','GS','MS','WFC','C','BLK','V','MA','AXP',
            'COF','SCHW','IBKR','MET','PRU','AFL','TRV','PGR','CB',
            'COIN','HOOD','AFRM','SOFI','NU','MSTR'],
    '醫療': ['JNJ','UNH','PFE','ABBV','MRK','LLY','TMO','ABT','DHR','AMGN',
            'GILD','BIIB','REGN','VRTX','ISRG','BSX','SYK','MDT','ZBH','EW',
            'NVO','HIMS'],
    '消費': ['WMT','HD','MCD','NKE','SBUX','TGT','COST','LOW','TJX','DG',
            'BKNG','MAR','HLT','CMG','YUM','DPZ','WYNN','MGM','LVS',
            'DECK','ONON','ELF','CELH','CAVA','CVNA','MELI','SE'],
    '能源': ['XOM','CVX','COP','SLB','EOG','MPC','PSX','VLO','HAL','BKR',
            'OXY','DVN','FANG','APA','NOG'],
    '工業': ['BA','CAT','GE','MMM','HON','LMT','RTX','DE','UPS','FDX',
            'NOC','GD','LHX','TDG','EMR','ETN','ROK','PH','AME','FAST',
            'GEV','VRT','PWR','AXON','RKLB'],
    '通訊媒體': ['T','VZ','TMUS','CMCSA','DIS','CHTR','WBD','PSKY','FOX'],
    '原材料': ['NEM','FCX','AA','CLF','NUE','B','RS','ATI'],
    '房地產': ['AMT','PLD','EQIX','CCI','SPG','O','WPC','VICI','IRM','WELL'],
    '公用事業': ['CEG','VST'],
    'EV/新能源': ['TSLA','RIVN','LCID','NIO','XPEV','LI','F','GM','STLA',
                'ENPH','SEDG','RUN','ARRY','BE','FCEL','PLUG'],
}

if MARKET == 'US':
    SYMBOLS, NAMES, SECTORS, TV_SYMBOLS = [], {}, {}, {}
    for _sec, _lst in US_SECTOR_SYMBOLS.items():
        for _s in _lst:
            if _s not in SECTORS:
                SECTORS[_s] = _sec
                SYMBOLS.append(_s)


# ============================================================
# 🇸🇬 新加坡股票清單（2026-10-28，依行業分組；SGX流動性集中在這約145檔，再往下日均成交額大多不到S$10萬）
# 有代碼抓不到資料時，打開 /sg/debug_missing 看是哪幾隻
# 2026-10-28 移除Yahoo抓不到的8檔（多半已私有化/下市）：JLB、5CP、NO4、UD2、A26、J91U、SK6U、CWBU
# ============================================================
SG_SECTOR_SYMBOLS = {
    '銀行': [('D05', 'DBS'), ('O39', 'OCBC'), ('U11', 'UOB')],
    '金融': [('S68', 'SGX'), ('AIY', 'iFAST'), ('U10', 'UOB Kay Hian'), ('S41', 'HL Finance'), ('G07', 'Great Eastern'), ('S20', 'Straits Trading')],
    '電信': [('Z74', 'Singtel'), ('CC3', 'StarHub'), ('CJLU', 'NetLink Trust'), ('S7OU', 'Asian Pay TV')],
    '工業': [('S63', 'ST Engineering'), ('BN4', 'Keppel'), ('U96', 'Sembcorp Ind'), ('5E2', 'Seatrium'), ('BS6', 'Yangzijiang'), ('YF8', 'YZJ Financial'), ('H22', 'HL Asia'), ('544', 'CSE Global'), ('F9D', 'Boustead'), ('P52', 'Pan-United'), ('E3B', 'Wee Hur'), ('OU8', 'Centurion'), ('CHZ', 'HRnetGroup'), ('ER0', 'KSH Holdings'), ('BQM', 'Tiong Woon')],
    '綜合企業': [('J36', 'Jardine Matheson(USD)'), ('C07', 'Jardine C&C'), ('9CI', 'CapitaLand Invest'), ('Z59', 'Yoma Strategic'), ('LJ3', 'OUE')],
    '運輸': [('C6L', 'SIA'), ('S59', 'SIA Engineering'), ('S58', 'SATS'), ('C52', 'ComfortDelGro'), ('S61', 'SBS Transit'), ('S08', 'SingPost'), ('G92', 'China Aviation Oil'), ('S56', 'Samudera'), ('NS8U', 'HPH Trust(USD)')],
    '科技/電子': [('V03', 'Venture'), ('558', 'UMS'), ('AWX', 'AEM'), ('E28', 'Frencken'), ('MZH', 'Nanofilm'), ('5DD', 'Micro-Mechanics'), ('BN2', 'Valuetronics'), ('8AZ', 'Aztech'), ('M14', 'InnoTek'), ('F13', 'Fu Yu'), ('I07', 'ISDN')],
    '能源/海工': [('5LY', 'Marco Polo Marine'), ('1MZ', 'Nam Cheong'), ('5WH', 'Rex Intl'), ('RE4', 'Geo Energy'), ('T13', 'RH PetroGas'), ('C9Q', 'Sinostar PEC'), ('U9E', 'China Everbright Water')],
    '原材料': [('5TP', 'CNMC Goldmine'), ('QES', 'China Sunsine')],
    '種植/農業': [('F34', 'Wilmar'), ('E5H', 'Golden Agri'), ('EB5', 'First Resources'), ('P8Z', 'Bumitama'), ('VC2', 'Olam'), ('MV4', 'Mewah'), ('5JS', 'Indofood Agri'), ('NC2', 'Sri Trang Agro')],
    '消費': [('Y92', 'Thai Beverage'), ('F99', 'Fraser & Neave'), ('D01', 'DFI Retail(USD)'), ('OV8', 'Sheng Siong'), ('P34', 'Delfi'), ('Q01', 'QAF'), ('F03', 'Food Empire'), ('1D0', 'Kimly'), ('42R', 'Jumbo'), ('AGS', 'Hour Glass'), ('D03', 'Del Monte Pac'), ('EMI', 'Emperador'), ('G13', 'Genting Sing'), ('H15', 'Hotel Properties'), ('H02', 'Haw Par')],
    '醫療': [('BSL', 'Raffles Medical'), ('AP4', 'Riverstone'), ('BVA', 'Top Glove'), ('A50', 'Thomson Medical'), ('QC7', 'Q&M Dental'), ('546', 'Medtecs')],
    '房地產': [('C09', 'City Developments'), ('U14', 'UOL'), ('TQ5', 'Frasers Property'), ('H78', 'HK Land(USD)'), ('F17', 'GuocoLand'), ('Z25', 'Yanlord'), ('ADN', 'First Sponsor'), ('H13', 'Ho Bee'), ('W05', 'Wing Tai'), ('B61', 'Bukit Sembawang'), ('5UX', 'Oxley'), ('T24', 'Tuan Sing'), ('OYY', 'PropNex'), ('CLN', 'APAC Realty')],
    'REIT/信託': [('C38U', 'CapitaLand Int Comm'), ('A17U', 'CapitaLand Ascendas'), ('M44U', 'Mapletree Logistics'), ('ME8U', 'Mapletree Industrial'), ('N2IU', 'Mapletree PanAsia'), ('J69U', 'Frasers Centrepoint'), ('BUOU', 'Frasers Logistics'), ('T82U', 'Suntec REIT'), ('K71U', 'Keppel REIT'), ('AJBU', 'Keppel DC REIT'), ('A7RU', 'Keppel Infra Trust'), ('JYEU', 'Lendlease REIT'), ('DCRU', 'Digital Core REIT(USD)'), ('J85', 'CDL Hosp Trust'), ('HMN', 'CapitaLand Ascott'), ('C2PU', 'Parkway Life'), ('P40U', 'Starhill Global'), ('TS0U', 'OUE REIT'), ('O5RU', 'AIMS APAC REIT'), ('AU8U', 'CapitaLand China'), ('CY6U', 'CapitaLand India'), ('Q5T', 'Far East Hosp'), ('CRPU', 'Sasseur REIT'), ('AW9U', 'First REIT'), ('OXMU', 'Prime US REIT(USD)'), ('BTOU', 'Manulife US REIT(USD)'), ('CMOU', 'KORE(USD)'), ('ODBU', 'United Hampshire(USD)'), ('DHLU', 'Daiwa House Log'), ('MXNU', 'Elite UK REIT(GBP)'), ('UD1U', 'IREIT Global(EUR)')],
}

if MARKET == 'SG':
    SYMBOLS, NAMES, SECTORS, TV_SYMBOLS = [], {}, {}, {}
    for _sec, _lst in SG_SECTOR_SYMBOLS.items():
        for _c, _n in _lst:
            _s = _c + '.SI'
            if _s not in SECTORS:
                SECTORS[_s] = _sec
                NAMES[_s] = _n
                SYMBOLS.append(_s)


# ============================================================
# 🇭🇰 港股清單（2026-10-28，依行業分組，約260檔高成交額股票；代號用Yahoo的4位數格式）
# 有代碼抓不到資料時，打開 /hk/debug_missing 看是哪幾隻
# 2026-10-28 移除Yahoo抓不到的2檔（已私有化/下市）：0011 恒生銀行、0489 東風集團
# ============================================================
HK_SECTOR_SYMBOLS = {
    '指數ETF': [('2828', '恒生中國企業ETF'), ('3033', '南方恒生科技ETF')],
    '銀行': [('0005', '滙豐控股'), ('0939', '建設銀行'), ('1398', '工商銀行'), ('3988', '中國銀行'), ('1288', '農業銀行'), ('3328', '交通銀行'), ('3968', '招商銀行'), ('0998', '中信銀行'), ('1658', '郵儲銀行'), ('2388', '中銀香港'), ('0023', '東亞銀行')],
    '保險': [('1299', '友邦保險'), ('2318', '中國平安'), ('2628', '中國人壽'), ('2601', '中國太保'), ('1339', '中國人保'), ('2328', '中國財險'), ('1336', '新華保險'), ('0966', '中國太平'), ('6060', '眾安在線')],
    '金融': [('0388', '香港交易所'), ('6030', '中信証券'), ('6886', '華泰證券'), ('3908', '中金公司'), ('2611', '國泰海通'), ('6099', '招商證券'), ('1776', '廣發證券'), ('1359', '中國信達'), ('2799', '中國中信金融資產'), ('0165', '中國光大控股'), ('2588', '中銀航空租賃')],
    '互聯網': [('0700', '騰訊控股'), ('9988', '阿里巴巴'), ('3690', '美團'), ('9618', '京東集團'), ('9999', '網易'), ('9888', '百度集團'), ('1024', '快手'), ('9961', '攜程集團'), ('9626', '嗶哩嗶哩'), ('0780', '同程旅行'), ('2423', '貝殼'), ('1698', '騰訊音樂'), ('9898', '微博'), ('0772', '閱文集團'), ('6618', '京東健康'), ('0241', '阿里健康'), ('1833', '平安好醫生'), ('2618', '京東物流'), ('0696', '中國民航信息'), ('1357', '美圖公司'), ('0777', '網龍'), ('2400', '心動公司')],
    '科技/半導體': [('1810', '小米集團'), ('0981', '中芯國際'), ('1347', '華虹半導體'), ('0992', '聯想集團'), ('0268', '金蝶國際'), ('3888', '金山軟件'), ('9698', '萬國數據'), ('2382', '舜宇光學'), ('2018', '瑞聲科技'), ('0285', '比亞迪電子'), ('1478', '丘鈦科技'), ('0522', 'ASMPT'), ('0020', '商湯'), ('9660', '地平線機器人'), ('2498', '速騰聚創'), ('9880', '優必選'), ('6869', '長飛光纖'), ('0148', '建滔集團'), ('1888', '建滔積層板'), ('6969', '思摩爾國際')],
    '汽車': [('1211', '比亞迪股份'), ('0175', '吉利汽車'), ('2015', '理想汽車'), ('9868', '小鵬汽車'), ('9866', '蔚來'), ('9863', '零跑汽車'), ('2333', '長城汽車'), ('2238', '廣汽集團'), ('3750', '寧德時代'), ('0425', '敏實集團'), ('1316', '耐世特'), ('1585', '雅迪控股'), ('3606', '福耀玻璃'), ('0881', '中升控股'), ('2338', '濰柴動力'), ('3808', '中國重汽')],
    '消費': [('9992', '泡泡瑪特'), ('2020', '安踏體育'), ('2331', '李寧'), ('1913', '普拉達'), ('1929', '周大福'), ('6181', '老鋪黃金'), ('2313', '申洲國際'), ('6110', '滔搏'), ('9896', '名創優品'), ('9633', '農夫山泉'), ('6862', '海底撈'), ('9987', '百勝中國'), ('2097', '蜜雪集團'), ('0291', '華潤啤酒'), ('0168', '青島啤酒'), ('1876', '百威亞太'), ('0322', '康師傅'), ('0151', '中國旺旺'), ('0220', '統一企業中國'), ('2319', '蒙牛乳業'), ('1044', '恒安國際'), ('1880', '中國中免'), ('6690', '海爾智家'), ('0300', '美的集團'), ('1999', '敏華控股'), ('9901', '新東方'), ('1797', '東方甄選'), ('2367', '巨子生物'), ('0669', '創科實業'), ('0179', '德昌電機')],
    '博彩': [('0027', '銀河娛樂'), ('1928', '金沙中國'), ('0880', '澳博控股'), ('1128', '永利澳門'), ('2282', '美高梅中國'), ('0200', '新濠國際')],
    '醫藥': [('2269', '藥明生物'), ('2359', '藥明康德'), ('3759', '康龍化成'), ('1177', '中國生物製藥'), ('1093', '石藥集團'), ('6160', '百濟神州'), ('1801', '信達生物'), ('3692', '翰森製藥'), ('2196', '復星醫藥'), ('1099', '國藥控股'), ('1066', '威高股份'), ('0867', '康哲藥業'), ('9926', '康方生物'), ('1530', '三生製藥'), ('2162', '康諾亞'), ('9995', '榮昌生物'), ('0013', '和黃醫藥'), ('6990', '科倫博泰'), ('9688', '再鼎醫藥'), ('1877', '君實生物'), ('0853', '微創醫療'), ('2252', '微創機器人'), ('2186', '綠葉製藥'), ('0570', '中國中藥'), ('3320', '華潤醫藥'), ('2607', '上海醫藥'), ('1548', '金斯瑞生物'), ('2228', '晶泰控股'), ('2096', '先聲藥業'), ('1952', '雲頂新耀'), ('6855', '亞盛醫藥'), ('9969', '諾誠健華')],
    '地產': [('0016', '新鴻基地產'), ('1109', '華潤置地'), ('0688', '中國海外發展'), ('1113', '長實集團'), ('0012', '恒基地產'), ('0017', '新世界發展'), ('0083', '信和置業'), ('0101', '恒隆地產'), ('0960', '龍湖集團'), ('3900', '綠城中國'), ('1997', '九龍倉置業'), ('0004', '九龍倉集團'), ('0123', '越秀地產'), ('0119', '保利置業'), ('1908', '建發國際'), ('2202', '萬科企業'), ('0754', '合生創展'), ('1030', '新城發展'), ('3383', '雅居樂'), ('1918', '融創中國'), ('1209', '華潤萬象生活'), ('6098', '碧桂園服務'), ('2869', '綠城服務'), ('0823', '領展房產基金'), ('0778', '置富產業信託')],
    '公用事業': [('0002', '中電控股'), ('0003', '香港中華煤氣'), ('0006', '電能實業'), ('1038', '長江基建'), ('0836', '華潤電力'), ('0902', '華能國際'), ('0991', '大唐發電'), ('0916', '龍源電力'), ('1816', '中廣核電力'), ('0384', '中國燃氣'), ('2688', '新奧能源'), ('1193', '華潤燃氣'), ('0135', '昆侖能源'), ('0270', '粵海投資'), ('0371', '北控水務'), ('0257', '光大環境')],
    '能源/資源': [('0857', '中國石油'), ('0386', '中國石化'), ('0883', '中國海洋石油'), ('1088', '中國神華'), ('1898', '中煤能源'), ('1171', '兗礦能源'), ('3993', '洛陽鉬業'), ('2899', '紫金礦業'), ('1818', '招金礦業'), ('2600', '中國鋁業'), ('0358', '江西銅業'), ('1208', '五礦資源'), ('0486', '俄鋁'), ('0914', '海螺水泥'), ('3323', '中國建材'), ('2689', '玖龍紙業'), ('0189', '東岳集團')],
    '新能源': [('2208', '金風科技'), ('0968', '信義光能'), ('0868', '信義玻璃'), ('3800', '協鑫科技'), ('1772', '贛鋒鋰業'), ('9696', '天齊鋰業'), ('6865', '福萊特玻璃')],
    '電信': [('0941', '中國移動'), ('0762', '中國聯通'), ('0728', '中國電信'), ('0788', '中國鐵塔'), ('6823', '香港電訊'), ('0008', '電訊盈科')],
    '工業/運輸': [('0001', '長和'), ('0267', '中信股份'), ('0019', '太古股份A'), ('0656', '復星國際'), ('0066', '港鐵公司'), ('0144', '招商局港口'), ('0316', '東方海外國際'), ('1919', '中遠海控'), ('1308', '海豐國際'), ('2343', '太平洋航運'), ('0598', '中國外運'), ('6936', '順豐控股'), ('0753', '中國國航'), ('0670', '東方航空'), ('1055', '南方航空'), ('0293', '國泰航空'), ('0694', '北京首都機場'), ('0576', '浙江滬杭甬'), ('0177', '江蘇寧滬'), ('1800', '中國交通建設'), ('0390', '中國中鐵'), ('1186', '中國鐵建'), ('1766', '中國中車'), ('3311', '中國建築國際'), ('1072', '東方電氣'), ('3898', '時代電氣'), ('1157', '中聯重科'), ('0631', '三一國際'), ('2357', '中航科工'), ('3899', '中集安瑞科'), ('2039', '中集集團'), ('1882', '海天國際')],
}

if MARKET == 'HK':
    SYMBOLS, NAMES, SECTORS, TV_SYMBOLS = [], {}, {}, {}
    for _sec, _lst in HK_SECTOR_SYMBOLS.items():
        for _c, _n in _lst:
            _s = _c + '.HK'
            if _s not in SECTORS:
                SECTORS[_s] = _sec
                NAMES[_s] = _n
                SYMBOLS.append(_s)


# ============================================================
# 🇨🇳 A股清單（2026-10-28，滬深主板高成交額約300檔；6開頭＝上海.SS，0開頭＝深圳.SZ）
# 只放北向可買的主板股票（創業板300/301、科創板688北向只限機構投資者）
# 有代碼抓不到資料時，打開 /cn/debug_missing 看是哪幾隻
# 2026-10-28 移除 601989 中國重工（已併入中國船舶 600150）
# ============================================================
CN_SECTOR_SYMBOLS = {
    '銀行': [('601398', '工商銀行'), ('601288', '農業銀行'), ('601988', '中國銀行'), ('601939', '建設銀行'), ('601328', '交通銀行'), ('600036', '招商銀行'), ('601166', '興業銀行'), ('600000', '浦發銀行'), ('600016', '民生銀行'), ('601998', '中信銀行'), ('601818', '光大銀行'), ('601658', '郵儲銀行'), ('600919', '江蘇銀行'), ('601009', '南京銀行'), ('601229', '上海銀行'), ('600926', '杭州銀行'), ('601169', '北京銀行'), ('000001', '平安銀行'), ('002142', '寧波銀行')],
    '保險': [('601318', '中國平安'), ('601628', '中國人壽'), ('601601', '中國太保'), ('601336', '新華保險'), ('601319', '中國人保')],
    '證券': [('600030', '中信證券'), ('601211', '國泰海通'), ('601688', '華泰證券'), ('600999', '招商證券'), ('601995', '中金公司'), ('600958', '東方證券'), ('601788', '光大證券'), ('601066', '中信建投'), ('601881', '中國銀河'), ('601901', '方正證券'), ('600918', '中泰證券'), ('601555', '東吳證券'), ('600109', '國金證券'), ('601108', '財通證券'), ('600061', '國投資本'), ('000166', '申萬宏源'), ('000776', '廣發證券'), ('002736', '國信證券'), ('000783', '長江證券'), ('000750', '國海證券'), ('000728', '國元證券'), ('002939', '長城證券'), ('000617', '中油資本')],
    '白酒/食品': [('600519', '貴州茅台'), ('000858', '五糧液'), ('000568', '瀘州老窖'), ('600809', '山西汾酒'), ('002304', '洋河股份'), ('000596', '古井貢酒'), ('000799', '酒鬼酒'), ('600887', '伊利股份'), ('603288', '海天味業'), ('600600', '青島啤酒'), ('600132', '重慶啤酒'), ('000729', '燕京啤酒'), ('000895', '雙匯發展'), ('002714', '牧原股份'), ('000876', '新希望'), ('002311', '海大集團')],
    '家電/消費': [('000333', '美的集團'), ('000651', '格力電器'), ('600690', '海爾智家'), ('000921', '海信家電'), ('002032', '蘇泊爾'), ('002508', '老闆電器'), ('603833', '歐派家居'), ('601888', '中國中免'), ('600754', '錦江酒店'), ('002027', '分眾傳媒'), ('002739', '萬達電影'), ('000681', '視覺中國')],
    '醫藥': [('600276', '恒瑞醫藥'), ('603259', '藥明康德'), ('600436', '片仔癀'), ('600196', '復星醫藥'), ('600085', '同仁堂'), ('600079', '人福醫藥'), ('600161', '天壇生物'), ('600763', '通策醫療'), ('603392', '萬泰生物'), ('600332', '白雲山'), ('600867', '通化東寶'), ('600998', '九州通'), ('601607', '上海醫藥'), ('000538', '雲南白藥'), ('000963', '華東醫藥'), ('002007', '華蘭生物'), ('000661', '長春高新'), ('002001', '新和成'), ('002252', '上海萊士'), ('000423', '東阿阿膠'), ('002821', '凱萊英'), ('000999', '華潤三九'), ('002603', '以嶺藥業')],
    '半導體/電子': [('600584', '長電科技'), ('603501', '豪威集團'), ('600745', '聞泰科技'), ('601138', '工業富聯'), ('600183', '生益科技'), ('603986', '兆易創新'), ('600460', '士蘭微'), ('603290', '斯達半導'), ('002371', '北方華創'), ('002049', '紫光國微'), ('000725', '京東方A'), ('002475', '立訊精密'), ('002241', '歌爾股份'), ('002456', '歐菲光'), ('002916', '深南電路'), ('002463', '滬電股份'), ('002138', '順絡電子'), ('002384', '東山精密'), ('002600', '領益智造'), ('000050', '深天馬A'), ('002185', '華天科技'), ('002156', '通富微電'), ('000100', 'TCL科技'), ('000021', '深科技')],
    '科技/通訊': [('600588', '用友網絡'), ('600570', '恒生電子'), ('603019', '中科曙光'), ('601360', '三六零'), ('000063', '中興通訊'), ('002415', '海康威視'), ('002230', '科大訊飛'), ('002236', '大華股份'), ('000977', '浪潮信息'), ('000938', '紫光股份'), ('002410', '廣聯達'), ('002405', '四維圖新'), ('000034', '神州數碼'), ('002439', '啟明星辰'), ('000988', '華工科技'), ('002281', '光迅科技'), ('000066', '中國長城'), ('002261', '拓維信息'), ('600522', '中天科技'), ('600487', '亨通光電'), ('600498', '烽火通信'), ('600050', '中國聯通'), ('600941', '中國移動'), ('601728', '中國電信')],
    '遊戲/傳媒': [('002602', '世紀華通'), ('002555', '三七互娛'), ('002624', '完美世界'), ('002558', '巨人網絡'), ('002517', '愷英網絡'), ('002292', '奧飛娛樂')],
    '汽車': [('002594', '比亞迪'), ('600104', '上汽集團'), ('601633', '長城汽車'), ('601127', '賽力斯'), ('000625', '長安汽車'), ('601238', '廣汽集團'), ('600418', '江淮汽車'), ('000800', '一汽解放'), ('600066', '宇通客車'), ('000550', '江鈴汽車'), ('600660', '福耀玻璃'), ('600741', '華域汽車'), ('601689', '拓普集團'), ('603596', '伯特利'), ('002050', '三花智控'), ('002920', '德賽西威'), ('002906', '華陽集團'), ('000559', '萬向錢潮'), ('002085', '萬豐奧威'), ('002126', '銀輪股份'), ('002048', '寧波華翔'), ('002472', '雙環傳動'), ('000338', '濰柴動力')],
    '新能源/鋰電': [('601012', '隆基綠能'), ('600438', '通威股份'), ('601865', '福萊特'), ('603806', '福斯特'), ('002459', '晶澳科技'), ('002129', 'TCL中環'), ('002202', '金風科技'), ('601615', '明陽智能'), ('603799', '華友鈷業'), ('002460', '贛鋒鋰業'), ('002466', '天齊鋰業'), ('002709', '天賜材料'), ('002812', '恩捷股份'), ('002074', '國軒高科'), ('002340', '格林美'), ('002056', '橫店東磁'), ('002407', '多氟多'), ('002176', '江特電機'), ('002738', '中礦資源'), ('002497', '雅化集團'), ('002756', '永興材料'), ('002240', '盛新鋰能'), ('000792', '鹽湖股份'), ('000408', '藏格礦業'), ('000762', '西藏礦業')],
    '電力/公用': [('600900', '長江電力'), ('600011', '華能國際'), ('600795', '國電電力'), ('600886', '國投電力'), ('601985', '中國核電'), ('600905', '三峽能源'), ('600025', '華能水電'), ('003816', '中國廣核'), ('000027', '深圳能源'), ('000591', '太陽能'), ('000883', '湖北能源'), ('000155', '川能動力'), ('600406', '國電南瑞'), ('601877', '正泰電器'), ('600089', '特變電工')],
    '能源/煤炭': [('600028', '中國石化'), ('601857', '中國石油'), ('600938', '中國海油'), ('601088', '中國神華'), ('601225', '陝西煤業'), ('600188', '兗礦能源'), ('601898', '中煤能源'), ('600985', '淮北礦業'), ('601699', '潞安環能'), ('000983', '山西焦煤'), ('600256', '廣匯能源')],
    '有色/鋼鐵': [('601899', '紫金礦業'), ('603993', '洛陽鉬業'), ('600547', '山東黃金'), ('600489', '中金黃金'), ('601600', '中國鋁業'), ('600111', '北方稀土'), ('600362', '江西銅業'), ('601168', '西部礦業'), ('000831', '中國稀土'), ('000960', '錫業股份'), ('000878', '雲南銅業'), ('000630', '銅陵有色'), ('000807', '雲鋁股份'), ('000933', '神火股份'), ('600019', '寶鋼股份'), ('000898', '鞍鋼股份'), ('000709', '河鋼股份')],
    '化工/建材': [('600309', '萬華化學'), ('600346', '恒力石化'), ('601233', '桐昆股份'), ('600426', '華魯恒升'), ('600989', '寶豐能源'), ('603260', '合盛硅業'), ('600160', '巨化股份'), ('002493', '榮盛石化'), ('000301', '東方盛虹'), ('002648', '衛星化學'), ('000703', '恒逸石化'), ('600585', '海螺水泥'), ('600176', '中國巨石'), ('002271', '東方雨虹'), ('000786', '北新建材')],
    '基建/機械': [('601668', '中國建築'), ('601390', '中國中鐵'), ('601186', '中國鐵建'), ('601800', '中國交建'), ('601669', '中國電建'), ('601618', '中國中冶'), ('601117', '中國化學'), ('601766', '中國中車'), ('600031', '三一重工'), ('601100', '恒立液壓'), ('000425', '徐工機械'), ('000157', '中聯重科'), ('000039', '中集集團')],
    '軍工': [('600150', '中國船舶'), ('600760', '中航沈飛'), ('600893', '航發動力'), ('600482', '中國動力'), ('600372', '中航機載'), ('600038', '中直股份'), ('600118', '中國衛星'), ('600879', '航天電子'), ('601698', '中國衛通'), ('002179', '中航光電'), ('000768', '中航西飛'), ('002025', '航天電器'), ('000547', '航天發展')],
    '交通運輸': [('601006', '大秦鐵路'), ('601816', '京滬高鐵'), ('600009', '上海機場'), ('601111', '中國國航'), ('600029', '南方航空'), ('600115', '中國東航'), ('601021', '春秋航空'), ('601919', '中遠海控'), ('600026', '中遠海能'), ('601872', '招商輪船'), ('600018', '上港集團'), ('002352', '順豐控股'), ('002120', '韻達股份'), ('002468', '申通快遞')],
    '地產': [('600048', '保利發展'), ('001979', '招商蛇口'), ('000002', '萬科A'), ('601155', '新城控股'), ('600663', '陸家嘴'), ('000069', '華僑城A')],
}

if MARKET == 'CN':
    SYMBOLS, NAMES, SECTORS, TV_SYMBOLS = [], {}, {}, {}
    for _sec, _lst in CN_SECTOR_SYMBOLS.items():
        for _c, _n in _lst:
            _s = _c + ('.SS' if _c.startswith('6') else '.SZ')
            if _s not in SECTORS:
                SECTORS[_s] = _sec
                NAMES[_s] = _n
                SYMBOLS.append(_s)

TF_LABELS = list(M.get('tfs', ['1D', '4H', '1H']))   # 由高到低（新加坡只有1D）（跟crypto版TF_LABELS的順序相反，這裡直接就是高到低）
TV_INTERVAL  = {'1H': '60', '4H': '240', '1D': 'D'}
# 跟crypto版(scannerrailway.py)共用同一個TradingView Layout（莊家思維指標已經加在上面），
# 預設值bd3vZUwt是crypto版目前使用的Layout代碼；可用環境變數TV_LAYOUT_ID覆寫
TV_LAYOUT_ID = os.environ.get('TV_LAYOUT_ID', 'bd3vZUwt')   # 美股也用同一個Layout（莊家思維指標在上面）

def tv_chart_base():
    return f"https://www.tradingview.com/chart/{TV_LAYOUT_ID}/" if TV_LAYOUT_ID else "https://www.tradingview.com/chart/"

# ============================================================
# C系列參數（對齊 莊家思維 Contraction V53 / scannerrailway.py）
# ============================================================
# C1最小跌幅%（MH自訂，非老師SOP）。2026-10-26回測後決定：股票用7%、加密貨幣維持10%。
# TradingView看馬股時，莊家思維指標的minDropPct也要設成7，圖和scanner才會一致。
# 可用Railway環境變數 MIN_DROP_PCT 覆寫。
MIN_DROP_PCT       = float(menv('MIN_DROP_PCT', '7'))   # 美股可用 US_MIN_DROP_PCT 另外設定（預設同樣7%）
SLOPE_THRESHOLD_PCT = 0.05  # 走平判定閾值(%)，跟Pine的slopeThreshold一致
S3_LOOKBACK_BARS    = 90    # S3判斷「是否曾向上」回看根數

SIGNAL_CLASSES = ('bull-c', 'bull-ready', 'bear-c', 'bear-ready')

cached_results = []
scan_state = {'status': 'idle', 'last_scan': None, 'lock': threading.Lock()}

# ============================================================
# 股票代碼核對：跟Yahoo Finance官方名稱比對，找出SYMBOLS/NAMES錯置的代碼
# （3867.KL / 9296.KL 錯置事件後新增，一次性診斷工具）
# ============================================================
audit_state = {'status': 'idle', 'checked': 0, 'total': 0, 'mismatches': [], 'all_names': [], 'errors': [], 'lock': threading.Lock()}

# ============================================================
# 快速核對：只針對606檔擴充後仍缺NAMES/SECTORS的那批代碼（180檔），
# 避免完整audit_names的606檔結果太大導致抓取時被截斷讀不到後半段資料。
# ============================================================
MISSING_INFO_SYMBOLS = [
    '0025.KL', '0028.KL', '0039.KL', '0040.KL', '0058.KL', '0089.KL', '0106.KL', '0131.KL',
    '0149.KL', '0158.KL', '0167.KL', '0192.KL', '0202.KL', '0206.KL', '0212.KL', '0222.KL',
    '0237.KL', '0250.KL', '0252.KL', '0256.KL', '0257.KL', '0258.KL', '0277.KL', '0284.KL',
    '0290.KL', '0299.KL', '0302.KL', '0307.KL', '0313.KL', '0317.KL', '0319.KL', '0323.KL',
    '0327.KL', '0331.KL', '0333.KL', '0336.KL', '0340.KL', '0341.KL', '0342.KL', '0346.KL',
    '0348.KL', '0353.KL', '0355.KL', '0357.KL', '0363.KL', '0370.KL', '0380.KL', '0383.KL',
    '0386.KL', '0396.KL', '0455.KL', '0460.KL', '0465.KL', '3247.KL', '3913.KL', '5036.KL',
    '5070.KL', '5078.KL', '5147.KL', '5149.KL', '5219.KL', '5300.KL', '6203.KL', '6297.KL',
    '6912.KL', '7004.KL', '7055.KL', '7085.KL', '7115.KL', '7131.KL', '7133.KL', '7134.KL',
    '7145.KL', '7170.KL', '7176.KL', '7211.KL', '7230.KL', '7382.KL', '7579.KL', '7935.KL',
    '8192.KL', '8273.KL', '8435.KL', '8613.KL', '9326.KL', '9369.KL', '9776.KL', '5238.KL',
    '0391.KL', '5308.KL', '7155.KL', '6378.KL', '5073.KL', '5703.KL', '2097.KL', '2054.KL',
    '5010.KL', '0012.KL', '7501.KL', '0368.KL', '0246.KL', '7210.KL', '5303.KL', '7108.KL',
    '5196.KL', '5077.KL', '7192.KL', '0006.KL', '0034.KL', '0066.KL', '0074.KL', '0080.KL',
    '0109.KL', '0116.KL', '0136.KL', '0143.KL', '0174.KL', '0175.KL', '0188.KL', '0195.KL',
    '0200.KL', '0281.KL', '0289.KL', '0347.KL', '0350.KL', '0365.KL', '0367.KL', '0379.KL',
    '0393.KL', '0457.KL', '0458.KL', '0459.KL', '0463.KL', '0466.KL', '1236.KL', '3778.KL',
    '3891.KL', '4057.KL', '4235.KL', '4316.KL', '5098.KL', '5127.KL', '5157.KL', '5175.KL',
    '5179.KL', '5222.KL', '5305.KL', '5322.KL', '5345.KL', '5533.KL', '5576.KL', '5738.KL',
    '5797.KL', '6025.KL', '6637.KL', '7020.KL', '7068.KL', '7071.KL', '7078.KL', '7080.KL',
    '7112.KL', '7120.KL', '7123.KL', '7140.KL', '7164.KL', '7173.KL', '7213.KL', '7215.KL',
    '7219.KL', '7315.KL', '7439.KL', '7854.KL', '8699.KL', '8826.KL', '8893.KL', '9148.KL',
    '9237.KL', '9288.KL', '9334.KL', '9881.KL',
] if MARKET == 'KLSE' else []
missing_audit_state = {'status': 'idle', 'checked': 0, 'total': 0, 'results': [], 'lock': threading.Lock()}

def run_missing_audit():
    global missing_audit_state
    with missing_audit_state['lock']:
        if missing_audit_state['status'] == 'running':
            return
        missing_audit_state['status'] = 'running'
        missing_audit_state['checked'] = 0
        missing_audit_state['results'] = []
        missing_audit_state['total'] = len(MISSING_INFO_SYMBOLS)
    for sym in MISSING_INFO_SYMBOLS:
        yahoo_name = ''
        yahoo_sector = ''
        yahoo_industry = ''
        try:
            info = yf.Ticker(sym).get_info()
            yahoo_name     = info.get('longName') or info.get('shortName') or ''
            yahoo_sector   = info.get('sector', '') or ''
            yahoo_industry = info.get('industry', '') or ''
        except Exception as e:
            yahoo_name = f'ERROR:{e}'
        with missing_audit_state['lock']:
            missing_audit_state['results'].append({
                'symbol': sym,
                'yahoo_name': yahoo_name,
                'yahoo_sector': yahoo_sector,
                'yahoo_industry': yahoo_industry,
            })
            missing_audit_state['checked'] += 1
        time.sleep(0.35)
    with missing_audit_state['lock']:
        missing_audit_state['status'] = 'done'
    log.info(f"缺NAMES/SECTORS快速核對完成：共{len(MISSING_INFO_SYMBOLS)}檔")

def _name_matches(local_name, yahoo_name):
    """寬鬆比對：只要任一方的關鍵字出現在另一方就算符合，避免誤報太多。"""
    if not yahoo_name:
        return True  # 抓不到Yahoo名稱時不算錯，避免因網路問題洗版
    a = local_name.upper().replace('BHD', '').replace('BERHAD', '').strip()
    b = yahoo_name.upper().replace('BHD', '').replace('BERHAD', '').strip()
    if not a or not b:
        return True
    return (a in b) or (b in a) or any(w in b for w in a.split() if len(w) >= 4) or any(w in a for w in b.split() if len(w) >= 4)

def run_name_audit():
    """核對全部156檔：不只記錄「疑似錯置」，同時把Yahoo官方資料(全名/sector/industry/symbol)
    完整記下來(all_names)，方便之後直接用Yahoo的資料重建NAMES/SECTORS表，
    而不用一檔一檔手動網路搜尋核對。"""
    global audit_state
    with audit_state['lock']:
        if audit_state['status'] == 'running':
            return
        audit_state['status'] = 'running'
        audit_state['checked'] = 0
        audit_state['mismatches'] = []
        audit_state['all_names'] = []
        audit_state['errors'] = []
        audit_state['total'] = len(SYMBOLS)
    for sym in SYMBOLS:
        local_name = NAMES.get(sym, '')
        yahoo_name = ''
        yahoo_sector = ''
        yahoo_industry = ''
        yahoo_symbol = ''
        try:
            info = yf.Ticker(sym).get_info()
            yahoo_name     = info.get('longName') or info.get('shortName') or ''
            yahoo_sector   = info.get('sector', '') or ''
            yahoo_industry = info.get('industry', '') or ''
            yahoo_symbol   = info.get('symbol', '') or ''
        except Exception as e:
            with audit_state['lock']:
                audit_state['errors'].append({'symbol': sym, 'error': str(e)})
        with audit_state['lock']:
            audit_state['all_names'].append({
                'symbol': sym,
                'local_name': local_name,
                'local_sector': SECTORS.get(sym, ''),
                'local_tv': TV_SYMBOLS.get(sym, ''),
                'yahoo_name': yahoo_name,
                'yahoo_sector': yahoo_sector,
                'yahoo_industry': yahoo_industry,
                'yahoo_symbol': yahoo_symbol,
            })
            if yahoo_name and not _name_matches(local_name, yahoo_name):
                audit_state['mismatches'].append({
                    'symbol': sym,
                    'local_name': local_name,
                    'yahoo_name': yahoo_name,
                    'local_sector': SECTORS.get(sym, ''),
                    'local_tv': TV_SYMBOLS.get(sym, ''),
                })
            audit_state['checked'] += 1
        time.sleep(0.4)
    with audit_state['lock']:
        audit_state['status'] = 'done'
    log.info(f"股票代碼核對完成：共{len(SYMBOLS)}檔，發現{len(audit_state['mismatches'])}個疑似錯置")

def is_market_hours():
    now = datetime.now(MKT_TZ)
    if now.weekday() >= 5:
        return False
    open_t  = now.replace(hour=M['open'][0],  minute=M['open'][1],  second=0, microsecond=0)
    close_t = now.replace(hour=M['close'][0], minute=M['close'][1], second=0, microsecond=0)
    return open_t <= now <= close_t

def _clean_ohlcv(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]
    need = ['open', 'high', 'low', 'close', 'volume']
    if not all(c in df.columns for c in need):
        return pd.DataFrame()
    df = df[need].dropna(subset=['open', 'high', 'low', 'close'])
    df = df[df['high'] > 0]
    return df

def resample_4h_us(df_1h):
    """美股4H：對齊TradingView，每天兩根（美東 09:30-13:30、13:30-16:00），用「日期+上下半場」分組，夏令/冬令都不會錯位"""
    if df_1h.empty:
        return df_1h
    idx = df_1h.index
    local = idx.tz_convert(MKT_TZ) if getattr(idx, 'tz', None) is not None else idx
    mins = local.hour * 60 + local.minute
    half = np.where(mins >= 13 * 60 + 30, 1, 0)
    tmp = df_1h.copy()
    tmp['_k'] = [f"{d}_{h}" for d, h in zip(local.date, half)]
    tmp['_ts'] = idx
    g = tmp.groupby('_k', sort=False).agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'),
                                          close=('close', 'last'), volume=('volume', 'sum'), ts=('_ts', 'first'))
    g = g.set_index('ts').sort_index()
    g.index.name = None
    return g[['open', 'high', 'low', 'close', 'volume']].astype(float)

def _fetch_1h_raw(symbol, retries=2):
    """抓取原始1小時K線（730天，yfinance 60m interval上限）。
    4H和1H共用同一份原始資料，避免同一symbol重複下載造成Yahoo限流。
    帶簡單重試，因為批次掃描時intraday端點比daily端點更容易被限流/逾時。"""
    for attempt in range(retries):
        try:
            df = yf.download(symbol, period='730d', interval='1h', progress=False,
                             auto_adjust=M['auto_adjust'], prepost=False)
        except Exception as e:
            log.warning(f"fetch {symbol} 1H raw attempt{attempt+1}: {e}")
            df = pd.DataFrame()
        df = _clean_ohlcv(df)
        if not df.empty:
            if getattr(df.index, 'tz', None) is None:
                df.index = df.index.tz_localize('UTC').tz_convert(MKT_TZ)
            else:
                df.index = df.index.tz_convert(MKT_TZ)
            return df
        if attempt < retries - 1:
            time.sleep(1.0)
    return pd.DataFrame()

def fetch_ohlcv(symbol, timeframe, raw_1h=None):
    """抓取OHLCV。1H/4H改用最大可取範圍(730天，yfinance 60m interval上限)，
    確保有足夠根數計算MA150/MA200，避免C系列判斷因資料不足而失真。
    raw_1h: 可選，傳入已抓好的1H原始資料，4H/1H會直接沿用，不重複下載。"""
    try:
        if timeframe == '1D':
            df = _clean_ohlcv(yf.download(symbol, period='5y', interval='1d', progress=False,
                                          auto_adjust=M['auto_adjust'], prepost=False))
            if not df.empty and getattr(df.index, 'tz', None) is not None:
                df.index = df.index.tz_localize(None)
            return df
        elif timeframe == '4H':
            base = raw_1h if raw_1h is not None else _fetch_1h_raw(symbol)
            if base.empty:
                return pd.DataFrame()
            if MARKET == 'US':
                return resample_4h_us(base)
            return base.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
        elif timeframe == '1H':
            return raw_1h if raw_1h is not None else _fetch_1h_raw(symbol)
        else:
            return pd.DataFrame()
    except Exception as e:
        log.warning(f"fetch {symbol} {timeframe}: {e}")
        return pd.DataFrame()

# ============================================================
# MA / Stage（對齊scannerrailway.py的get_stage，Weinstein四階段模型）
# ============================================================
def calc_sma(series, period):
    return series.rolling(period, min_periods=period).mean()

def get_stage(df_daily: pd.DataFrame) -> tuple:
    """回傳 (stage, s1_strong, divergence)，邏輯跟crypto版scannerrailway.py完全一致。"""
    min_len = 150 + 20
    if len(df_daily) < min_len:
        return 0, False, ''
    c = df_daily['close']
    v = df_daily['volume']
    ma150   = c.rolling(150).mean()
    volma50 = v.rolling(50).mean()

    cur150   = ma150.iloc[-1]
    prev150  = ma150.iloc[-10]
    ma150_20 = ma150.iloc[-20]
    price    = c.iloc[-1]
    cur_vol  = v.iloc[-1]
    cur_volma50 = volma50.iloc[-1]

    if pd.isna(cur150) or pd.isna(prev150) or pd.isna(ma150_20):
        return 0, False, ''

    slope10 = (cur150 - prev150)  / prev150  * 100
    slope20 = (cur150 - ma150_20) / ma150_20 * 100

    is_up   = slope10 >=  SLOPE_THRESHOLD_PCT and slope20 >=  SLOPE_THRESHOLD_PCT
    is_down = slope10 <= -SLOPE_THRESHOLD_PCT and slope20 <= -SLOPE_THRESHOLD_PCT
    is_flat = not is_up and not is_down

    ab150 = price > cur150

    if is_up:
        return 2, False, ('' if ab150 else 'down')
    if is_down:
        return 4, False, ('up' if ab150 else '')

    if is_flat and ab150:
        if not pd.isna(cur_volma50) and cur_vol < cur_volma50:
            consolidation_days = _count_consolidation_days(ma150)
            s1_strong = consolidation_days >= 180
            return 1, s1_strong, ''
        return 0, False, ''

    if is_flat and not ab150:
        idx_a = S3_LOOKBACK_BARS + 10
        idx_b = S3_LOOKBACK_BARS + 20
        if len(ma150) <= idx_b:
            return 0, False, ''
        ma150_lb      = ma150.iloc[-idx_a]
        ma150_lb_prev = ma150.iloc[-idx_b]
        if pd.isna(ma150_lb) or pd.isna(ma150_lb_prev):
            return 0, False, ''
        slope_lb = (ma150_lb - ma150_lb_prev) / ma150_lb_prev * 100
        was_up   = slope_lb >= SLOPE_THRESHOLD_PCT
        if was_up:
            return 3, False, ''
        return 0, False, ''

    return 0, False, ''

def _count_consolidation_days(ma150: pd.Series) -> int:
    days = 0
    n = len(ma150)
    max_check = min(400, n - 10)
    for back in range(10, max_check, 10):
        cur  = ma150.iloc[-back]
        prev = ma150.iloc[-(back + 10)] if (back + 10) <= n else None
        if prev is None or pd.isna(cur) or pd.isna(prev) or prev == 0:
            break
        slope = (cur - prev) / prev * 100
        if -SLOPE_THRESHOLD_PCT < slope < SLOPE_THRESHOLD_PCT:
            days += 10
        else:
            break
    return days

# ============================================================
# Swing High/Low + K棒組合判定（跟crypto版scannerrailway.py逐行對齊）
# ============================================================
def is_swing_high2(high_arr, idx):
    if idx < 2 or idx >= len(high_arr) - 2: return False
    h = high_arr[idx]
    return h > high_arr[idx-1] and h > high_arr[idx-2] and h > high_arr[idx+1] and h > high_arr[idx+2]

def is_swing_low2(low_arr, idx):
    if idx < 2 or idx >= len(low_arr) - 2: return False
    l = low_arr[idx]
    return l < low_arr[idx-1] and l < low_arr[idx-2] and l < low_arr[idx+1] and l < low_arr[idx+2]

def is_valid_bar_bull(o, h, l, c):
    body = abs(c - o)
    uw   = h - max(c, o)
    dw   = min(c, o) - l
    tw   = uw + dw
    is_bear = c < o
    is_doji = (c >= o) and (tw > body) and (uw > dw)
    return is_bear or is_doji

def has_three_combo(open_arr, high_arr, low_arr, close_arr, start_idx, end_idx):
    lo = min(start_idx, end_idx)
    hi = max(start_idx, end_idx)
    for j in range(lo, hi - 1):
        if j + 2 >= len(close_arr): break
        if (is_valid_bar_bull(open_arr[j],   high_arr[j],   low_arr[j],   close_arr[j]) and
            is_valid_bar_bull(open_arr[j+1], high_arr[j+1], low_arr[j+1], close_arr[j+1]) and
            is_valid_bar_bull(open_arr[j+2], high_arr[j+2], low_arr[j+2], close_arr[j+2])):
            return True
    return False

def is_valid_bar_bear(o, h, l, c):
    body = abs(c - o)
    uw   = h - max(c, o)
    dw   = min(c, o) - l
    tw   = uw + dw
    is_bull = c > o
    is_doji = (c <= o) and (tw > body) and (uw > dw)
    return is_bull or is_doji

def has_three_combo_bear(open_arr, high_arr, low_arr, close_arr, start_idx, end_idx):
    lo = min(start_idx, end_idx)
    hi = max(start_idx, end_idx)
    for j in range(lo, hi - 1):
        if j + 2 >= len(close_arr): break
        if (is_valid_bar_bear(open_arr[j],   high_arr[j],   low_arr[j],   close_arr[j]) and
            is_valid_bar_bear(open_arr[j+1], high_arr[j+1], low_arr[j+1], close_arr[j+1]) and
            is_valid_bar_bear(open_arr[j+2], high_arr[j+2], low_arr[j+2], close_arr[j+2])):
            return True
    return False

# ============================================================
# 多頭/空頭起點
# ============================================================
def find_start_bar_bull(df: pd.DataFrame) -> int:
    s50  = calc_sma(df['close'], 50)
    s150 = calc_sma(df['close'], 150)
    s200 = calc_sma(df['close'], 200)
    has200 = not s200.isna().all()
    if has200:
        bull = (s50 > s150) & (s150 > s200)
        ref  = s200
    else:
        bull = (s50 > s150)
        ref  = s150
    if not bull.iloc[-1]: return -1
    bull_arr = bull.values
    n = len(bull_arr)
    for i in range(n - 1, -1, -1):
        if not bull_arr[i]: return i + 1
    for i in range(n):
        if not pd.isna(ref.iloc[i]) and bull_arr[i]: return i
    return -1

def find_start_bar_bear(df: pd.DataFrame) -> int:
    s50  = calc_sma(df['close'], 50)
    s150 = calc_sma(df['close'], 150)
    s200 = calc_sma(df['close'], 200)
    has200 = not s200.isna().all()
    if has200:
        bear = (s50 < s150) & (s150 < s200)
        ref  = s200
    else:
        bear = (s50 < s150)
        ref  = s150
    if not bear.iloc[-1]: return -1
    bear_arr = bear.values
    n = len(bear_arr)
    for i in range(n - 1, -1, -1):
        if not bear_arr[i]: return i + 1
    for i in range(n):
        if not pd.isna(ref.iloc[i]) and bear_arr[i]: return i
    return -1

# ============================================================
# C1 搜尋（含兩個已在crypto版驗證過的邊界修正：
#   1) 候選轉折點掃描不排除barsAgo=4；2) 低點追蹤排除最後2根未確認K棒）
# ============================================================
def find_c1(df: pd.DataFrame, start_idx: int, min_drop=None, atr_mult=None) -> dict:
    """min_drop / atr_mult 只給回測用：不傳就是原本的 MIN_DROP_PCT（正式掃描、跟Pine對齊的邏輯不變）。
    atr_mult：C1跌幅門檻改成「候選高點那根的ATR14% × 倍數」。"""
    result = {'found': False}
    n = len(df)
    total_bars = n - 1 - start_idx
    if total_bars <= 7: return result

    high_arr  = df['high'].values
    low_arr   = df['low'].values
    open_arr  = df['open'].values
    close_arr = df['close'].values
    s50_arr   = calc_sma(df['close'], 50).values
    base_thr  = MIN_DROP_PCT if min_drop is None else float(min_drop)
    atr_pct_arr = None
    if atr_mult is not None:
        _pc = df['close'].shift(1)
        _tr = pd.concat([df['high'] - df['low'], (df['high'] - _pc).abs(), (df['low'] - _pc).abs()], axis=1).max(axis=1)
        atr_pct_arr = (_tr.rolling(14).mean() / df['close'] * 100).values

    start_off = min(total_bars - 2, 498)
    scan_i = start_off
    max_loop = 11
    fail_priority = 0
    fail_msg = ''

    for _loop in range(max_loop):
        if scan_i <= 4:
            break

        sh_v, sh_i_off = None, None
        for i_off in range(scan_i, 3, -1):
            bar_idx = (n - 1) - i_off
            if bar_idx < start_idx: continue
            if bar_idx < 2 or bar_idx >= n - 2: continue
            if is_swing_high2(high_arr, bar_idx):
                sh_v = high_arr[bar_idx]
                sh_i_off = i_off
                break

        if sh_v is None:
            if fail_priority < 1:
                fail_msg = '找不到更多候選高點'
                fail_priority = 1
            break

        sh_bar = (n - 1) - sh_i_off

        sl_v, sl_bar = None, None
        aborted = False
        for k in range(sh_bar + 1, n - 2):
            if high_arr[k] > sh_v:
                aborted = True
                break
            if sl_v is None or low_arr[k] < sl_v:
                sl_v = low_arr[k]
                sl_bar = k

        if sl_v is None or aborted:
            scan_i = sh_i_off - 1
            if fail_priority < 1:
                fail_msg = f'高點被更高K線突破 (高={sh_v:.4f})' if aborted else '找不到對應低點'
                fail_priority = 1
            continue

        pct = (sh_v - sl_v) / sh_v * 100
        thr = base_thr
        if atr_pct_arr is not None and not pd.isna(atr_pct_arr[sh_bar]):
            thr = float(atr_mult) * float(atr_pct_arr[sh_bar])

        if pct < thr:
            if fail_priority < 2:
                fail_msg = f'跌幅不足 {pct:.2f}% < {thr:.2f}% (高={sh_v:.4f} 低={sl_v:.4f})'
                fail_priority = 2
            scan_i = sh_i_off - 1
            continue

        touched = any(
            not pd.isna(s50_arr[m]) and low_arr[m] <= s50_arr[m]
            for m in range(sh_bar, sl_bar + 1)
        )
        if not touched:
            if fail_priority < 3:
                fail_msg = f'跌幅夠但未觸碰MA50 (高={sh_v:.4f} 低={sl_v:.4f} 跌幅={pct:.2f}%)'
                fail_priority = 3
            scan_i = sh_i_off - 1
            continue

        if not has_three_combo(open_arr, high_arr, low_arr, close_arr, sh_bar, sl_bar):
            if fail_priority < 4:
                fail_msg = f'跌幅與MA50都符合，但無combo (高={sh_v:.4f} 低={sl_v:.4f} 跌幅={pct:.2f}%)'
                fail_priority = 4
            scan_i = sh_i_off - 1
            continue

        return {'found': True, 'hv': sh_v, 'hb': sh_bar,
                'lv': sl_v, 'lb': sl_bar,
                'pct': pct}

    result['fail_msg'] = fail_msg
    return result

def find_c1_bear(df: pd.DataFrame, start_idx: int) -> dict:
    result = {'found': False}
    n = len(df)
    total_bars = n - 1 - start_idx
    if total_bars <= 7: return result

    high_arr  = df['high'].values
    low_arr   = df['low'].values
    open_arr  = df['open'].values
    close_arr = df['close'].values
    s50_arr   = calc_sma(df['close'], 50).values

    start_off = min(total_bars - 2, 498)
    scan_i = start_off
    max_loop = 11
    fail_priority = 0
    fail_msg = ''

    for _loop in range(max_loop):
        if scan_i <= 4:
            break

        sl_v, sl_i_off = None, None
        for i_off in range(scan_i, 3, -1):
            bar_idx = (n - 1) - i_off
            if bar_idx < start_idx: continue
            if bar_idx < 2 or bar_idx >= n - 2: continue
            if is_swing_low2(low_arr, bar_idx):
                sl_v = low_arr[bar_idx]
                sl_i_off = i_off
                break

        if sl_v is None:
            if fail_priority < 1:
                fail_msg = '找不到更多候選低點'
                fail_priority = 1
            break

        sl_bar = (n - 1) - sl_i_off

        sh_v, sh_bar = None, None
        aborted = False
        for k in range(sl_bar + 1, n - 2):
            if low_arr[k] < sl_v:
                aborted = True
                break
            if sh_v is None or high_arr[k] > sh_v:
                sh_v = high_arr[k]
                sh_bar = k

        if sh_v is None or aborted:
            scan_i = sl_i_off - 1
            if fail_priority < 1:
                fail_msg = f'低點被更低K線突破 (低={sl_v:.4f})' if aborted else '找不到對應高點'
                fail_priority = 1
            continue

        pct = (sh_v - sl_v) / sl_v * 100

        if pct < MIN_DROP_PCT:
            if fail_priority < 2:
                fail_msg = f'漲幅不足 {pct:.2f}% < {MIN_DROP_PCT}% (低={sl_v:.4f} 高={sh_v:.4f})'
                fail_priority = 2
            scan_i = sl_i_off - 1
            continue

        touched = any(
            not pd.isna(s50_arr[m]) and high_arr[m] >= s50_arr[m]
            for m in range(sl_bar, sh_bar + 1)
        )
        if not touched:
            if fail_priority < 3:
                fail_msg = f'漲幅夠但未觸碰MA50 (低={sl_v:.4f} 高={sh_v:.4f} 漲幅={pct:.2f}%)'
                fail_priority = 3
            scan_i = sl_i_off - 1
            continue

        if not has_three_combo_bear(open_arr, high_arr, low_arr, close_arr, sl_bar, sh_bar):
            if fail_priority < 4:
                fail_msg = f'漲幅與MA50都符合，但無combo (低={sl_v:.4f} 高={sh_v:.4f} 漲幅={pct:.2f}%)'
                fail_priority = 4
            scan_i = sl_i_off - 1
            continue

        return {'found': True, 'lv': sl_v, 'lb': sl_bar,
                'hv': sh_v, 'hb': sh_bar,
                'pct': pct}

    result['fail_msg'] = fail_msg
    return result

# ============================================================
# C2~C6 搜尋（含breakout override + 兩個邊界修正）
# ============================================================
def find_next_c(df, prev_lv, prev_lb, start_bar_bull=0, prev_hb=None, debug=False, c1_hv=None):
    result = {'found': False}
    trace = [] if debug else None
    n = len(df)
    high_arr  = df['high'].values
    low_arr   = df['low'].values
    open_arr  = df['open'].values
    close_arr = df['close'].values

    scan_start_bar = max(prev_lb + 1, start_bar_bull)
    if scan_start_bar >= n - 4:
        if debug: result['trace'] = trace
        return result

    scan_i_off = (n - 1) - scan_start_bar

    for _loop in range(11):
        if scan_i_off <= 4:
            break

        sh_v, sh_i_off = None, None
        for i_off in range(scan_i_off, 3, -1):
            bar_idx = (n - 1) - i_off
            if bar_idx < scan_start_bar: continue
            if bar_idx < 2 or bar_idx >= n - 2: continue
            if is_swing_high2(high_arr, bar_idx):
                sh_v = high_arr[bar_idx]
                sh_i_off = i_off
                break

        if sh_v is None:
            break

        sh_bar = (n - 1) - sh_i_off

        sl_v, sl_bar = None, None
        aborted = False
        for k in range(sh_bar + 1, n - 2):
            if high_arr[k] > sh_v:
                aborted = True
                break
            if sl_v is None or low_arr[k] < sl_v:
                sl_v = low_arr[k]
                sl_bar = k

        if sl_v is None or aborted:
            scan_i_off = sh_i_off - 1
            if debug: trace.append({'h_idx': sh_bar, 'hv': round(sh_v,6), 'reason': '高點被突破或找不到低點'})
            continue

        is_breakout = (c1_hv is not None) and (sh_v > c1_hv)
        low_ok = is_breakout or (sl_v > prev_lv)
        if not low_ok:
            scan_i_off = sh_i_off - 1
            if debug: trace.append({'h_idx': sh_bar, 'hv': round(sh_v,6), 'l_idx': sl_bar, 'lv': round(sl_v,6), 'reason': f'低點未越抬越高 ({sl_v:.6f} <= {prev_lv:.6f})'})
            continue

        if not has_three_combo(open_arr, high_arr, low_arr, close_arr, sh_bar, sl_bar):
            scan_i_off = sh_i_off - 1
            if debug: trace.append({'h_idx': sh_bar, 'hv': round(sh_v,6), 'l_idx': sl_bar, 'lv': round(sl_v,6), 'reason': '沒有combo'})
            continue

        drop_pct = (sh_v - sl_v) / sh_v * 100
        if debug: result['trace'] = trace
        result.update({'found': True, 'hv': sh_v, 'hb': sh_bar,
                'lv': sl_v, 'lb': sl_bar,
                'pct': drop_pct})
        return result

    if debug: result['trace'] = trace
    return result

def find_next_c_bear(df, prev_hv, prev_hb, start_bar_bear=0, prev_lb=None, debug=False, c1_lv=None):
    result = {'found': False}
    trace = [] if debug else None
    n = len(df)
    high_arr  = df['high'].values
    low_arr   = df['low'].values
    open_arr  = df['open'].values
    close_arr = df['close'].values

    scan_start_bar = max(prev_hb + 1, start_bar_bear)
    if scan_start_bar >= n - 4:
        if debug: result['trace'] = trace
        return result

    scan_i_off = (n - 1) - scan_start_bar

    for _loop in range(11):
        if scan_i_off <= 4:
            break

        sl_v, sl_i_off = None, None
        for i_off in range(scan_i_off, 3, -1):
            bar_idx = (n - 1) - i_off
            if bar_idx < scan_start_bar: continue
            if bar_idx < 2 or bar_idx >= n - 2: continue
            if is_swing_low2(low_arr, bar_idx):
                sl_v = low_arr[bar_idx]
                sl_i_off = i_off
                break

        if sl_v is None:
            break

        sl_bar = (n - 1) - sl_i_off

        sh_v, sh_bar = None, None
        aborted = False
        for k in range(sl_bar + 1, n - 2):
            if low_arr[k] < sl_v:
                aborted = True
                break
            if sh_v is None or high_arr[k] > sh_v:
                sh_v = high_arr[k]
                sh_bar = k

        if sh_v is None or aborted:
            scan_i_off = sl_i_off - 1
            if debug: trace.append({'l_idx': sl_bar, 'lv': round(sl_v,6), 'reason': '低點被突破或找不到高點'})
            continue

        is_breakout = (c1_lv is not None) and (sl_v < c1_lv)
        high_ok = is_breakout or (sh_v < prev_hv)

        if not high_ok:
            scan_i_off = sl_i_off - 1
            if debug: trace.append({'l_idx': sl_bar, 'lv': round(sl_v,6), 'h_idx': sh_bar, 'hv': round(sh_v,6), 'reason': f'高點未越壓越低 ({sh_v:.6f} >= {prev_hv:.6f})'})
            continue

        if not has_three_combo_bear(open_arr, high_arr, low_arr, close_arr, sl_bar, sh_bar):
            scan_i_off = sl_i_off - 1
            if debug: trace.append({'l_idx': sl_bar, 'lv': round(sl_v,6), 'h_idx': sh_bar, 'hv': round(sh_v,6), 'reason': '沒有combo'})
            continue

        rise_pct = (sh_v - sl_v) / sl_v * 100
        if debug: result['trace'] = trace
        result.update({'found': True, 'lv': sl_v, 'lb': sl_bar,
                'hv': sh_v, 'hb': sh_bar,
                'pct': rise_pct})
        return result

    if debug: result['trace'] = trace
    return result

# ============================================================
# BASE 偵測 / 進場區間
# ============================================================
def detect_base(c_list):
    if len(c_list) < 2: return 0
    base_count = 0
    base_hv = c_list[0]['hv']
    for i in range(1, len(c_list)):
        if c_list[i]['hv'] > base_hv:
            base_count += 1
            base_hv = c_list[i]['hv']
    return base_count

def get_entry_zone(c1_hv, c1_lv, last_c_lv):
    c1_range = c1_hv - c1_lv
    pivot    = c1_hv - c1_range / 3
    cheat    = c1_hv - c1_range * 2 / 3
    if last_c_lv >= pivot:   return 'Pivot'
    elif last_c_lv >= cheat: return 'Cheat'
    else:                    return 'LCheat'

def detect_base_bear(c_list):
    if len(c_list) < 2: return 0
    base_count = 0
    base_lv = c_list[0]['lv']
    for i in range(1, len(c_list)):
        if c_list[i]['lv'] < base_lv:
            base_count += 1
            base_lv = c_list[i]['lv']
    return base_count

def get_entry_zone_bear(c1_lv, c1_hv, last_c_hv):
    c1_range = c1_hv - c1_lv
    pivot    = c1_lv + c1_range / 3
    cheat    = c1_lv + c1_range * 2 / 3
    if last_c_hv <= pivot:   return 'Pivot'
    elif last_c_hv <= cheat: return 'Cheat'
    else:                     return 'LCheat'

# ============================================================
# 分析（對齊scannerrailway.py的analyze()）
# ============================================================
def analyze(df: pd.DataFrame, df_daily: pd.DataFrame, c1_cfg=None) -> dict:
    """c1_cfg只給回測用（例如 {'min_drop': 7} 或 {'atr_mult': 3}），正式掃描不傳。"""
    empty = {'stage': 0, 's1_strong': False, 'divergence': '', 'has_c': False, 'c_count': 0,
             'base': 0, 'entry_zone': '', 'ready': False, 'is_bear': False, 'last_pct': None}
    if df.empty or len(df) < 50: return empty
    if df_daily.empty or len(df_daily) < 50: return empty

    stage, s1_strong, divergence = get_stage(df_daily)

    start_idx_bull = find_start_bar_bull(df)
    c_list = []
    is_bear = False

    if start_idx_bull >= 0:
        c1 = find_c1(df, start_idx_bull, **(c1_cfg or {}))
        if c1['found']:
            c_list = [c1]
            prev_lv = c1['lv']
            prev_lb = c1['lb']
            for _ in range(5):
                cx = find_next_c(df, prev_lv, prev_lb, start_idx_bull, c1_hv=c1['hv'])
                if not cx['found']: break
                c_list.append(cx)
                prev_lv = cx['lv']
                prev_lb = cx['lb']
                if cx['pct'] < 2.0:
                    break
    else:
        start_idx_bear = find_start_bar_bear(df)
        if start_idx_bear >= 0:
            is_bear = True
            c1b = find_c1_bear(df, start_idx_bear)
            if c1b['found']:
                c_list = [c1b]
                prev_hv = c1b['hv']
                prev_hb = c1b['hb']
                for _ in range(5):
                    cxb = find_next_c_bear(df, prev_hv, prev_hb, start_idx_bear, c1_lv=c1b['lv'])
                    if not cxb['found']: break
                    c_list.append(cxb)
                    prev_hv = cxb['hv']
                    prev_hb = cxb['hb']
                    if cxb['pct'] < 2.0:
                        break

    has_c = len(c_list) > 0
    c_count = len(c_list)
    if has_c and is_bear:
        base = detect_base_bear(c_list)
        entry_zone = get_entry_zone_bear(c_list[0]['lv'], c_list[0]['hv'], c_list[-1]['hv'])
    elif has_c:
        base = detect_base(c_list)
        entry_zone = get_entry_zone(c_list[0]['hv'], c_list[0]['lv'], c_list[-1]['lv'])
    else:
        base = 0
        entry_zone = ''
    ready = c_list[-1]['pct'] < 10.0 if c_list else False
    last_pct = round(c_list[-1]['pct'], 1) if c_list else None

    # 突破卡片需要最後一個C的高低點（BO=C高×1.01、SL=C低−0.5%），原有欄位完全不變
    provisional = False
    if c_list:   # ⏳：最後一個C的極值之後，確認K線不到2根（跟crypto版、舊美股版同一個定義）
        _ext = c_list[-1]['hb'] if is_bear else c_list[-1]['lb']
        provisional = ((len(df) - 3) - int(_ext)) < 2
    return {'stage': stage, 's1_strong': s1_strong, 'divergence': divergence, 'has_c': has_c, 'c_count': c_count,
            'base': base, 'entry_zone': entry_zone, 'ready': ready, 'is_bear': is_bear, 'last_pct': last_pct,
            'last_c': (c_list[-1] if c_list else None), 'provisional': provisional}

# ============================================================
# 掃描單一股票
# ============================================================
def scan_symbol(symbol):
    result = {'symbol': symbol}
    result['name'] = NAMES.get(symbol, sym_code(symbol))
    result['sector'] = SECTORS.get(symbol, '其他')
    # 改用數字代碼直接組TradingView連結（MYX:5168這種），TradingView會自動導向正確股票，
    # 不再依賴容易錯置的TV_SYMBOLS簡稱對照表（見audit_names發現的大量代碼錯置問題）
    result['tv_symbol'] = tv_sym(symbol)

    df_daily = fetch_ohlcv(symbol, '1D')
    # 4H/1H共用同一份原始資料，只下載一次；只掃日線的市場（新加坡）完全不抓1H
    raw_1h = _fetch_1h_raw(symbol) if any(t in TF_LABELS for t in ('4H', '1H')) else pd.DataFrame()
    # 📨 Telegram流動性過濾：最近20個已收盤交易日的平均成交額（收盤價×成交量，單位RM）
    result['turnover'] = None
    try:
        if not df_daily.empty:
            _dc = closed_bars(df_daily, '1D').tail(20)
            if len(_dc):
                result['turnover'] = float((_dc['close'] * _dc['volume']).mean())
    except Exception as e:
        log.warning(f"turnover {symbol}: {e}")
    result['nodata'] = df_daily.empty
    result['RS_raw'] = None
    if not df_daily.empty and RS_BENCHMARK and symbol != RS_BENCHMARK:
        try:
            result['RS_raw'] = calc_rs_raw(df_daily, BENCH_CLOSE)
        except Exception as e:
            log.warning(f"RS {symbol}: {e}")
    if not df_daily.empty:
        wy_process_symbol(result, df_daily)   # 🧱 威科夫：用同一份日線，不多抓資料

    for tf in TF_LABELS:
        try:
            df = df_daily if tf == '1D' else fetch_ohlcv(symbol, tf, raw_1h=raw_1h)
            if df.empty or len(df) < 50 or df_daily.empty or len(df_daily) < 50:
                result[tf] = '-'
                result[f'{tf}_cls'] = 'gray'
                continue

            res = analyze(df, df_daily)
            # 🃏 突破卡片：記錄快突破/已突破/結果（獨立try，出錯也不影響原本表格）
            if tf in CARD_TFS:
                try:
                    card_process_tf(result, tf, df, df_daily, res)
                except Exception as ce:
                    log.warning(f"🃏 card {symbol} {tf}: {ce}")
            hc        = res['has_c']
            cnt       = res['c_count']
            pct       = res.get('last_pct')
            is_bear_c = res.get('is_bear', False)
            ready     = res['ready']
            base      = res['base']
            zone      = res['entry_zone']
            div       = res.get('divergence', '')
            s1s       = res.get('s1_strong', False)

            pct_str  = f'({pct}%)' if pct is not None else ''
            if res.get('provisional'):
                pct_str += ' ⏳'   # 低點還沒確認（跟crypto版、舊美股版一樣顯示在格子裡）
            c_suffix = '(空)' if is_bear_c else ''
            base_str = f' B{base}' if base > 0 else ''
            zone_str = f' {zone}' if ready else ''

            if tf == '1D':
                s = res['stage']
                div_mark = '↘' if div == 'down' else ('↗' if div == 'up' else '')
                if s == 0:
                    text, cls = '-', 'gray'
                elif s == 1:
                    text, cls = ('S1⭐' if s1s else 'S1'), 'stage1'
                elif s == 2:
                    if hc:
                        text = f'S2{div_mark} {cnt}C{c_suffix}{pct_str}🎯{base_str}{zone_str}' if ready else f'S2{div_mark} {cnt}C{c_suffix}{pct_str}{base_str}'
                        cls  = 'bull-ready' if ready else 'bull-c'
                    else:
                        text, cls = f'S2{div_mark}', 'bull'
                elif s == 3:
                    text, cls = 'S3⚠️', 'stage3'
                elif s == 4:
                    if hc:
                        text = f'S4{div_mark} {cnt}C{c_suffix}{pct_str}🎯' if ready else f'S4{div_mark} {cnt}C{c_suffix}{pct_str}'
                        cls  = 'bear-ready' if ready else 'bear-c'
                    else:
                        text, cls = f'S4{div_mark}', 'bear'
                else:
                    text, cls = '-', 'gray'
            else:
                if not hc:
                    text, cls = '-', 'gray'
                elif is_bear_c:
                    text = f'{cnt}C{c_suffix}{pct_str}🎯' if ready else f'{cnt}C{c_suffix}{pct_str}'
                    cls  = 'bear-ready' if ready else 'bear-c'
                else:
                    text = f'{cnt}C{c_suffix}{pct_str}🎯{base_str}{zone_str}' if ready else f'{cnt}C{c_suffix}{pct_str}{base_str}'
                    cls  = 'bull-ready' if ready else 'bull-c'

            result[tf]            = text
            result[f'{tf}_cls']   = cls
            result[f'{tf}_pct']   = pct
            result[f'{tf}_isbear'] = is_bear_c
            result[f'{tf}_cnt']    = cnt
            result['stage']        = res.get('stage', 0)   # 日線Stage（每個時間框架都用日線算，值相同）
            # 📨 Telegram「可開單」候選：多頭、≥2C、🎯（是否推送在send_telegram再過濾）
            lc = res.get('last_c')
            if hc and not is_bear_c and cnt >= 2 and ready and lc:
                n_ = len(df)
                result[f'{tf}_sig'] = {
                    'cnt': cnt, 'pct': pct, 'zone': zone,
                    'hv': float(lc['hv']), 'lv': float(lc['lv']),
                    'h_time': _iso(df.index[int(lc['hb'])]),
                    'provisional': ((n_ - 3) - int(lc['lb'])) < PROVISIONAL_BARS,
                    'price': float(df['close'].values[-1]),
                }
        except Exception as e:
            log.warning(f"⚠️ {symbol} {tf}: {e}")
            result[tf] = 'ERR'
            result[f'{tf}_cls'] = 'gray'
    return result

# ============================================================
# 動態錨點（跟crypto版一樣的邏輯，只是TF_LABELS已經是高到低，不用reversed）
# ============================================================
def get_row_anchor_marks(r, tfs=TF_LABELS):
    anchor_label = None
    for tf in tfs:  # KLSE的TF_LABELS已經是高到低(1D→4H→1H)，不用像crypto版那樣reversed
        if r.get(f'{tf}_cls', 'gray') in SIGNAL_CLASSES:
            anchor_label = tf
            break
    if anchor_label is None:
        return {}

    anchor_isbear = r.get(f'{anchor_label}_isbear', False)
    anchor_pct    = r.get(f'{anchor_label}_pct')

    marks = {anchor_label: 'anchor'}
    for tf in tfs:
        if tf == anchor_label:
            continue
        if r.get(f'{tf}_cls', 'gray') not in SIGNAL_CLASSES:
            continue
        isbear = r.get(f'{tf}_isbear', False)
        if isbear == anchor_isbear:
            marks[tf] = 'align'
        elif anchor_pct is not None and anchor_pct > 20.0:
            marks[tf] = 'conflict-loose'
        else:
            marks[tf] = 'conflict-tight'
    return marks

def run_scan():
    global cached_results
    with scan_state['lock']:
        if scan_state['status'] == 'scanning':
            return
        scan_state['status'] = 'scanning'
    seen = set()
    unique_syms = [s for s in SYMBOLS if s not in seen and not seen.add(s)]
    log.info(f"{M['flag']} 莊家思維 {M['name']}掃描器 等待掃描（一次只掃一個市場）({len(unique_syms)} 只)")
    results = []
    GLOBAL_SCAN_LOCK.acquire()
    log.info(f"{M['flag']} 莊家思維 {M['name']}掃描器 開始掃描 ({len(unique_syms)} 只)")
    card_events.clear()
    wy_scan_begin()
    try:
        load_benchmark()
        for i, sym in enumerate(unique_syms):
            r = scan_symbol(sym)
            results.append(r)
            log.info(f"✅ {sym}: " + str({t: r.get(t, '-') for t in TF_LABELS}))
            if (i + 1) % 100 == 0:
                save_cards()
            time.sleep(0.3)
        # 2026-10-28：抓不到日線的（多半是Yahoo暫時限流）等一下再重抓一次，真的下市的才會留在 /debug_missing
        miss_idx = [i for i, r in enumerate(results) if r.get('nodata')]
        if miss_idx:
            log.info(f"{M['flag']} {len(miss_idx)} 只抓不到資料，等20秒後重抓一次")
            time.sleep(20)
            fixed = 0
            for i in miss_idx:
                r2 = scan_symbol(results[i]['symbol'])
                if not r2.get('nodata'):
                    results[i] = r2
                    fixed += 1
                time.sleep(1.0)
            log.info(f"{M['flag']} 重抓完成：救回 {fixed} 只，仍抓不到 {len(miss_idx) - fixed} 只")
        try:
            compute_rs_scores(results)
        except Exception as e:
            log.warning(f"RS計算失敗：{e}")
        cached_results = results
        try:
            wy_scan_finish()
        except Exception as e:
            log.warning(f"🧱 威科夫整理失敗：{e}")
    finally:
        GLOBAL_SCAN_LOCK.release()
        save_cards()
        with WY_LOCK:
            if WY_STATE['status'] == 'running':
                WY_STATE['status'] = 'done' if WY_STATE['rows'] else 'idle'
        with scan_state['lock']:
            scan_state['status'] = 'done'
            scan_state['last_scan'] = datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M:%S')
    log.info(f"掃描完成！共 {len(results)} 只")
    send_telegram(results)
    send_card_telegram()

# ============================================================
# 💪 力量（相對強度）：跟舊美股版、crypto版同一套邏輯；基準＝M['rs_benchmark']（美股SPY；KLSE目前不算）
# ============================================================
RS_BENCHMARK     = M['rs_benchmark']
RS_LOOKBACK_DAYS = 20
RS_MIN_SAMPLES   = 10
BENCH_CLOSE      = None

def load_benchmark():
    global BENCH_CLOSE
    if not RS_BENCHMARK:
        return
    try:
        df = fetch_ohlcv(RS_BENCHMARK, '1D')
        BENCH_CLOSE = df['close'] if not df.empty else None
    except Exception as e:
        log.warning(f"抓 {RS_BENCHMARK} 失敗：{e}")
        BENCH_CLOSE = None

def calc_rs_raw(df_daily, bench_close):
    """「該股/基準」收盤比值在 RS_LOOKBACK_DAYS 天內的漲跌幅(%)"""
    if bench_close is None or df_daily is None or df_daily.empty:
        return None
    aligned = pd.concat([df_daily['close'].rename('sym'), bench_close.rename('bench')], axis=1, join='inner').dropna()
    if len(aligned) < RS_LOOKBACK_DAYS + 1:
        return None
    ratio = aligned['sym'] / aligned['bench']
    now_r, past_r = ratio.iloc[-1], ratio.iloc[-1 - RS_LOOKBACK_DAYS]
    if pd.isna(now_r) or pd.isna(past_r) or past_r == 0:
        return None
    return float((now_r / past_r - 1) * 100)

def compute_rs_scores(results):
    """排名轉成 -5~+5 分數（sign-floor：比值沒漲不給正分、沒跌不給負分），另附「比值%」（100%＝跟基準同步）"""
    if not RS_BENCHMARK:
        return
    valid = [(i, r['RS_raw']) for i, r in enumerate(results) if r.get('RS_raw') is not None]
    for r in results:
        r['RS_score'], r['RS_text'], r['RS_color'], r['RS_pct'] = None, '--', '#2a2a2a', None
    if len(valid) < RS_MIN_SAMPLES:
        return
    valid.sort(key=lambda x: x[1])
    n = len(valid)
    rank_of = {idx: pos for pos, (idx, _) in enumerate(valid)}
    for i, r in enumerate(results):
        raw = r.get('RS_raw')
        if raw is None:
            continue
        score = ((rank_of[i] / (n - 1) * 100) if n > 1 else 50) - 50
        score /= 10
        score = min(score, 0) if raw <= 0 else max(score, 0)
        score = int(max(-5, min(5, round(score))))
        r['RS_score'], r['RS_pct'] = score, round(raw + 100)
        r['RS_text'] = f'{score:+d} ({r["RS_pct"]}%)' if score != 0 else f'0 ({r["RS_pct"]}%)'
        r['RS_color'] = '#1a6b3c' if score >= 2 else ('#8b0000' if score <= -2 else '#4a4a4a')

# ============================================================
# 📨 Telegram「可開單」通知（2026-10-27 MH確認）
# 只推同時符合全部條件的訊號：
#   1) 只看日線（TG_SIGNAL_TFS，預設1D）  2) 多頭、日線Stage=S2
#   3) ≥2C 而且有🎯（Pivot/Cheat/LCheat 都推）  4) 沒有⏳（最後一個C低點還沒確認的不推）
#   5) 現價還沒跌破SL、也沒有高於BO超過3%（老師「不追」規則）
#   6) 最近20日平均成交額 ≥ TG_MIN_TURNOVER_MYR
# 只推「新的」：同一個形態（同一個C高點）推過一次就不再推；形成新的C才會再推。
# 1C、做空、S4、2C還沒🎯的，全部只留在網頁總表。
# ============================================================
TG_SIGNAL_TFS       = [t.strip() for t in menv('TG_SIGNAL_TFS', M['tg_tfs']).split(',') if t.strip() in TF_LABELS]
# 成交額門檻（20日平均，用該市場的貨幣）：KLSE讀 TG_MIN_TURNOVER_MYR（RM），美股讀 US_TG_MIN_TURNOVER（US$）
TG_MIN_TURNOVER_MYR = float(os.environ.get(M['turnover_env'], M.get('min_turnover_default', '1000000')))
SITE_ROOT           = (os.environ.get('SITE_URL') or os.environ.get('KLSE_URL') or 'https://klse-scanner-production-6926.up.railway.app').rstrip('/')
KLSE_URL            = SITE_ROOT + BASE   # 這個市場的網址（美股＝…/us）
TG_SENT_KEEP_DAYS   = 120

def _tg_sent_file():
    return os.path.join(DATA_DIR, 'tg_sent.json')

def _tg_sent_load():
    try:
        with open(_tg_sent_file(), 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _tg_sent_save(d):
    try:
        cutoff = (datetime.now(MY_TZ) - timedelta(days=TG_SENT_KEEP_DAYS)).isoformat()
        d = {k: v for k, v in d.items() if v >= cutoff}
        tmp = _tg_sent_file() + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, _tg_sent_file())
    except Exception as e:
        log.warning(f"📨 儲存Telegram已推紀錄失敗：{e}")

def _fmt_turnover(v):
    if v is None:
        return '-'
    cur = M['currency']
    if v >= 1e9:
        return f'{cur}{v / 1e9:.2f}B'
    return f'{cur}{v / 1e6:.1f}M' if v >= 1e6 else f'{cur}{v / 1e3:.0f}K'

def _tick_round(p, up):
    """BO往上、SL往下對齊Bursa跳動單位，掛單價格才是有效價位"""
    import math
    t = bursa_tick(p)
    k = p / t
    k = math.ceil(k - 1e-9) if up else math.floor(k + 1e-9)
    return round(k * t, 4)

def collect_tradeable(results):
    """回傳 (可開單清單, 被過濾的數量, 觀察中數量)"""
    sigs = []
    skipped = {'prov': 0, 'broken': 0, 'chase': 0, 'liq': 0}
    watch = 0
    for r in results:
        if r.get('stage') != 2:
            continue
        for tf in TG_SIGNAL_TFS:
            if r.get(f'{tf}_cls') == 'bull-c' and (r.get(f'{tf}_cnt') or 0) >= 2:
                watch += 1
            s = r.get(f'{tf}_sig')
            if not s:
                continue
            bo, sl = calc_levels(s['hv'], s['lv'], tf)
            bo, sl = _tick_round(bo, True), _tick_round(sl, False)
            price = s['price']
            if s['provisional']:
                skipped['prov'] += 1; continue
            if price <= sl:
                skipped['broken'] += 1; continue
            if price > bo * (1 + CHASE_MAX_PCT / 100):
                skipped['chase'] += 1; continue
            to = r.get('turnover')
            if to is None or to < TG_MIN_TURNOVER_MYR:
                skipped['liq'] += 1; continue
            sigs.append({
                'key': f"{r['symbol']}|{tf}|{s['h_time']}",
                'symbol': r['symbol'], 'name': r.get('name') or sym_code(r['symbol']),
                'tf': tf, 'cnt': s['cnt'], 'pct': s['pct'], 'zone': s['zone'],
                'bo': bo, 'sl': sl, 'price': price, 'turnover': to,
                'r_pct': (bo - sl) / bo * 100 if bo else 0,
            })
    sigs.sort(key=lambda x: (TF_LABELS.index(x['tf']), x['r_pct']))
    return sigs, skipped, watch

def send_telegram(results):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    sigs, skipped, watch = collect_tradeable(results)
    sent = _tg_sent_load()
    new = [s for s in sigs if s['key'] not in sent]
    old_n = len(sigs) - len(new)
    log.info(f"📨 可開單：{len(sigs)}（新{len(new)}、之前已推{old_n}）・觀察{watch}・過濾{skipped}")
    if not new:
        return
    now_dt = datetime.now(MY_TZ)
    now = now_dt.strftime('%m-%d %H:%M')
    lines = []
    for s in new:
        over = ' ⚡盤中已過BO' if s['price'] >= s['bo'] else ''
        pct = f"({s['pct']}%)" if s['pct'] is not None else ''
        lines.append(f"🎯 {label_of(s['name'], s['symbol'])}｜{s['tf']} {s['cnt']}C{pct}｜{s['zone']}{over}\n"
                     f"   BO {fmt_px(s['bo'])}｜SL {fmt_px(s['sl'])}｜1R {s['r_pct']:.1f}%\n"
                     f"   現價 {fmt_px(s['price'])}｜成交額 {_fmt_turnover(s['turnover'])}")
    footer = (f"{'━' * 12}\n"
              f"仍有效（之前已推）：{old_n} 只\n"
              f"👀 2C 待🎯：{watch} 只\n"
              f"已過濾：成交額<{_fmt_turnover(TG_MIN_TURNOVER_MYR)} {skipped['liq']}・⏳ {skipped['prov']}・"
              f"超BO {CHASE_MAX_PCT:.0f}% {skipped['chase']}・破SL {skipped['broken']}\n"
              f"📄 完整名單：{KLSE_URL}")
    batches = [lines[i:i + 10] for i in range(0, len(lines), 10)]
    ok_all = True
    for i, batch in enumerate(batches):
        part = f" ({i + 1}/{len(batches)})" if len(batches) > 1 else ""
        msg = f"{M['flag']} {M['short']} 可開單｜{now}｜新 {len(new)} 只{part}\n{'━' * 12}\n" + "\n".join(batch)
        if i == len(batches) - 1:
            msg += "\n" + footer
        try:
            resp = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                                 json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'disable_web_page_preview': True},
                                 timeout=10)
            ok_all = ok_all and resp.ok
            time.sleep(1)
        except Exception as e:
            ok_all = False
            log.warning(f"Telegram error: {e}")
    if ok_all:   # 發送成功才記錄，發送失敗下一輪會再試
        for s in new:
            sent[s['key']] = now_dt.isoformat()
        _tg_sent_save(sent)

# ============================================================
# 🃏 突破卡片引擎（BO / SL / 目標 + 已突破追蹤 + 戰績統計）
# 規則（MH 2026-10-26 確認）：
#   BO  = 最後一個C的高點 + 緩衝，K線「收盤」站上才算突破
#   SL  = 最後一個C的低點 − 緩衝（老師規則：天圖1%、時圖0.5%、分圖0.25%）
#   進場 = 還沒突破用BO；已突破用確認那根K線的收盤價
#   目標 = 進場 + 1.5R / 2R（R = 進場 − SL）
#   快突破 = 現價離BO 5%以內；已突破追蹤到碰SL或1:1.5為止，超過20根K線記為「到期」
#   只做多頭、至少C2（SL用C2或之後最新那個C的低點）
# 狀態存在 DATA_DIR/cards_state.json（Railway要掛Volume到/data才會永久保存）
# ============================================================
import json

CARD_TFS          = [t.strip() for t in menv('CARD_TFS', '1D,4H,1H').split(',') if t.strip() in TF_LABELS]
CARD_TELEGRAM_TFS = [t.strip() for t in menv('CARD_TELEGRAM_TFS', M['tg_tfs']).split(',') if t.strip()]
# 老師規則（股票、加密貨幣通用）：天圖 ±1%、時圖 ±0.5%、分圖 ±0.25%
#   BO = C高 × (1 + 緩衝%)，SL = C低 × (1 − 緩衝%)
TF_BUFFER_PCT     = {'1D': 1.0, '4H': 0.5, '1H': 0.5}
QUICK_BO_PCT      = 5.0     # 快突破：現價離BO ≤ 5%
MIN_C_FOR_CARD    = 2       # 至少要有C2
TP1_R             = 1.5
TP2_R             = 2.0
MAX_HOLD_BARS     = 20      # 突破後20根K線內沒碰SL也沒到1:1.5 → 記為到期
CHASE_MAX_PCT     = 3.0     # 進場價高於BO超過3%（掛單模式＝開盤跳空太高）→ 標「⚠️不追」
# 進場方式（MH 2026-10-30，⚖️進場比較回測證實掛單比較好）：
#   'touch' = 盤中最高價碰到BO就算成交（進場價=BO，跳空高開用開盤價）← 預設，跟老師SOP在BO掛單一樣
#   'close' = 收盤站上BO才算突破（進場價=收盤價）← 舊算法；設環境變數 CARD_ENTRY_MODE=close 可切回
# 不管哪一種，都只用「已收盤」的K線判斷（收盤後才記錄），不會用到盤中還沒收完的K線。
CARD_ENTRY_MODE   = 'close' if menv('CARD_ENTRY_MODE', 'touch').lower() == 'close' else 'touch'
VOL_SURGE_X       = 1.5     # 突破量 ≥ 1.5倍20根均量 → 標「🔥放量」
PROVISIONAL_BARS  = 2       # 最後一個C低點之後確認K線少於2根 → 標⏳（跟crypto版同一個定義）
BACKFILL_BARS     = int(os.environ.get('CARD_BACKFILL_BARS', '20'))  # 第一次看到某檔時，回放最近20根K線補抓已突破案例
DONE_KEEP         = 5000

def _resolve_data_dir():
    d = os.environ.get('DATA_DIR') or ('/data' if os.path.isdir('/data') else
                                       os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data'))
    os.makedirs(d, exist_ok=True)
    return d

_ROOT_DATA_DIR  = _resolve_data_dir()
DATA_PERSISTENT = bool(os.environ.get('DATA_DIR')) or _ROOT_DATA_DIR == '/data'
# KLSE沿用原本的位置（舊紀錄不會不見）；其他市場各自一個子資料夾，例：/data/us
DATA_DIR        = os.path.join(_ROOT_DATA_DIR, M['data_sub']) if M['data_sub'] else _ROOT_DATA_DIR
os.makedirs(DATA_DIR, exist_ok=True)
CARDS_FILE      = os.path.join(DATA_DIR, 'cards_state.json')

cards_lock  = threading.Lock()
cards_state = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'seen': {}}
card_events = []   # 這一輪掃描產生的新突破/結果，掃完後發Telegram

def load_cards():
    global cards_state
    try:
        if os.path.exists(CARDS_FILE):
            with open(CARDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k in ('pending', 'active', 'used', 'seen'):
                data.setdefault(k, {})
            data.setdefault('done', [])
            cards_state = data
            log.info(f"🃏 已載入卡片狀態：快突破候選{len(data['pending'])} 進行中{len(data['active'])} 已結束{len(data['done'])}")
    except Exception as e:
        log.warning(f"🃏 載入 {CARDS_FILE} 失敗，改用空白狀態：{e}")

def save_cards():
    try:
        with cards_lock:
            cards_state['done'] = cards_state['done'][-DONE_KEEP:]
            payload = json.dumps(cards_state, ensure_ascii=False, default=str)
        tmp = CARDS_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(payload)
        os.replace(tmp, CARDS_FILE)
    except Exception as e:
        log.warning(f"🃏 儲存 {CARDS_FILE} 失敗：{e}")

def bursa_tick(p):
    """跳動單位：美股 $1以上0.01、$1以下0.0001；其他是 Bursa Malaysia 規則"""
    if MARKET == 'US':
        return 0.01 if p >= 1 else 0.0001
    if MARKET == 'CN':   # 滬深A股：一律0.01
        return 0.01
    if MARKET == 'HK':   # 港交所價位表
        for lim, t in ((0.25, 0.001), (0.5, 0.005), (10, 0.01), (20, 0.02), (100, 0.05), (200, 0.10),
                       (500, 0.20), (1000, 0.50), (2000, 1.00), (5000, 2.00)):
            if p < lim: return t
        return 5.00
    if MARKET == 'SG':   # SGX：S$0.20以下0.001、S$0.20–1.00 0.005、S$1以上0.01
        if p < 0.2: return 0.001
        if p < 1:   return 0.005
        return 0.01
    if p < 1:    return 0.005
    if p < 10:   return 0.01
    if p < 100:  return 0.02
    return 0.10

def calc_levels(c_hv, c_lv, tf='1D'):
    buf = TF_BUFFER_PCT.get(tf, 1.0) / 100
    return c_hv * (1 + buf), c_lv * (1 - buf)

def calc_targets(entry, sl):
    r = entry - sl
    return entry + TP1_R * r, entry + TP2_R * r

def fmt_px(p):
    if p is None: return '-'
    return f'{p:.3f}' if p < 10 else f'{p:.2f}'

def _iso(t):
    return pd.Timestamp(t).isoformat()

def _to_ts_like(iso, index):
    ts = pd.Timestamp(iso)
    tz = getattr(index, 'tz', None)
    if tz is not None and ts.tzinfo is None:
        ts = ts.tz_localize(tz)
    elif tz is None and ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts

def _positions_after(df, iso):
    """回傳df裡時間晚於iso的K線位置（list of int）"""
    if df.empty: return []
    ts = _to_ts_like(iso, df.index)
    mask = df.index > ts
    return [int(i) for i in np.nonzero(np.asarray(mask))[0]]

def closed_bars(df, tf, now=None):
    """去掉還沒收盤的K線（只檢查最後3根，前面的一定已收盤）。
    1D：收盤後5分鐘才算收盤（KLSE 17:05、美股美東16:05）；4H/1H：K線開始時間+長度 ≤ 現在，或是之前的交易日。
    時間一律用該市場自己的時區判斷。"""
    if df.empty: return df
    now = now.astimezone(MKT_TZ) if now is not None else datetime.now(MKT_TZ)
    dc_h, dc_m = M['daily_close']
    n = len(df)
    keep = n
    for i in range(n - 1, max(-1, n - 4), -1):
        ts = pd.Timestamp(df.index[i])
        ts = ts.tz_localize(MKT_TZ) if ts.tzinfo is None else ts.tz_convert(MKT_TZ)
        if ts.date() < now.date():
            break
        if tf == '1D':
            close_t = ts.normalize() + timedelta(hours=dc_h, minutes=dc_m)
        else:
            close_t = ts + (timedelta(hours=4) if tf == '4H' else timedelta(hours=1))
            sess_end = ts.normalize() + timedelta(hours=M['close'][0], minutes=M['close'][1])
            if ts < sess_end:
                close_t = min(close_t, sess_end)   # 美股下午那根4H只到16:00
        if close_t <= now:
            break
        keep = i
    return df.iloc[:keep]

def _atr14(df, i):
    if i < 15: return None
    h = df['high'].values[i-14:i+1]; l = df['low'].values[i-14:i+1]; pc = df['close'].values[i-15:i]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(np.mean(tr))

def _vol_ratio(df, i):
    if 'volume' not in df.columns or i < 20: return None
    v = df['volume'].values
    avg = float(np.mean(v[i-20:i]))
    return round(float(v[i]) / avg, 2) if avg > 0 else None

def _setup_from_analysis(df, res, tf='1D'):
    """把analyze()結果轉成一個「等待突破」的卡片設定；不符合條件回傳None"""
    if not res.get('has_c') or res.get('is_bear'): return None
    if res.get('c_count', 0) < MIN_C_FOR_CARD: return None
    lc = res.get('last_c')
    if not lc: return None
    n = len(df)
    hb, lb = int(lc['hb']), int(lc['lb'])
    bo, sl = calc_levels(float(lc['hv']), float(lc['lv']), tf)
    if bo <= sl: return None
    return {
        'c_hv': float(lc['hv']), 'c_lv': float(lc['lv']),
        'h_time': _iso(df.index[hb]), 'l_time': _iso(df.index[lb]),
        'bo': bo, 'sl': sl,
        'c_count': int(res.get('c_count', 0)), 'base': int(res.get('base', 0)),
        'pct': res.get('last_pct'), 'stage': int(res.get('stage', 0)),
        'entry_zone': res.get('entry_zone', ''),
        'provisional': ((n - 3) - lb) < PROVISIONAL_BARS,
        # analyze保證lb~n-3之間沒有K線高過C高、也沒有低過C低，所以只要從n-3之後開始檢查
        'last_checked': _iso(df.index[max(lb, n - 3)]),
    }

def _open_case(key, meta, tf, p, dfc, i, backfill, st, entry=None):
    # entry=None → 收盤確認：用收盤價；掛單模式（touch）會傳入成交價（BO或跳空開盤價）
    entry_given = entry is not None
    entry = float(dfc['close'].values[i]) if entry is None else float(entry)
    sl = p['sl']
    r = entry - sl
    if r <= 0: return None
    tp1, tp2 = calc_targets(entry, sl)
    atr = _atr14(dfc, i)                                   # 只記錄參考，不再用來判斷「不追」
    chase = entry > p['bo'] * (1 + CHASE_MAX_PCT / 100)
    cid = f"{key}|{p['h_time']}"
    case = dict(p)
    case.update({
        'id': cid, 'key': key, 'tf': tf,
        'symbol': meta['symbol'], 'name': meta.get('name'), 'sector': meta.get('sector'), 'tv_symbol': meta.get('tv_symbol'),
        'turnover': meta.get('turnover'),
        'entry': entry, 'tp1': tp1, 'tp2': tp2,
        'confirm_time': _iso(dfc.index[i]), 'last_checked': _iso(dfc.index[i]),
        'bars_held': 0, 'last_close': entry, 'vol_x': _vol_ratio(dfc, i),
        'atr': atr, 'chase': bool(chase), 'backfill': bool(backfill),
        'close_ok': bool(float(dfc['close'].values[i]) >= p['bo']),   # 進場那根收盤有沒有站上BO
        'close_px': float(dfc['close'].values[i]),
        'entry_mode': 'touch' if entry_given else 'close',
        'wy_entry': meta.get('wy_stage'),                              # 🧱 進場當下威科夫燈號（統計用）
    })
    st['active'][cid] = case
    st['used'][cid] = case['confirm_time']
    if not backfill:
        st.get('events', card_events).append(('open', case))
    return case

def _check_pending(key, meta, tf, dfc, backfill, st):
    p = st['pending'].get(key)
    if not p: return
    pos = _positions_after(dfc, p['last_checked'])
    closes = dfc['close'].values; lows = dfc['low'].values
    touch = st.get('entry_mode', CARD_ENTRY_MODE) == 'touch'   # 沒指定就跟正式卡片一樣（CARD_ENTRY_MODE）；⚖️進場比較回測會明確指定
    if touch:
        opens = dfc['open'].values; highs = dfc['high'].values
    for i in pos:
        if touch and highs[i] >= p['bo']:
            st['pending'].pop(key, None)
            fill = max(float(opens[i]), p['bo'])          # 跳空高開在BO上面 → 用開盤價成交
            case = _open_case(key, meta, tf, p, dfc, i, backfill, st, entry=fill)
            if case is not None and lows[i] <= p['sl']:   # 同一根又跌到SL（先後不明）→ 保守算止損
                _finish(case, 'SL', -1.0, dfc.index[i], backfill, st)
            return
        if not touch and closes[i] >= p['bo']:
            st['pending'].pop(key, None)
            _open_case(key, meta, tf, p, dfc, i, backfill, st)
            return
        if lows[i] <= p['sl']:          # 還沒突破就先跌破SL → 這個形態作廢
            st['pending'].pop(key, None)
            return
    if pos:
        p['last_checked'] = _iso(dfc.index[pos[-1]])

def _finish(case, result, r_mult, t, backfill, st):
    case.update({'result': result, 'r_mult': round(float(r_mult), 2), 'end_time': _iso(t)})
    st['active'].pop(case['id'], None)
    st['done'].append(case)
    if not backfill and not case.get('backfill'):
        st.get('events', card_events).append(('close', case))

def _check_active(key, dfc, backfill, st):
    highs = dfc['high'].values; lows = dfc['low'].values; closes = dfc['close'].values
    for cid, case in list(st['active'].items()):
        if case.get('key') != key: continue
        r = case['entry'] - case['sl']
        for i in _positions_after(dfc, case['last_checked']):
            case['bars_held'] += 1
            t = dfc.index[i]
            if lows[i] <= case['sl']:                       # 同一根同時碰SL和TP1 → 保守算SL
                _finish(case, 'SL', -1.0, t, backfill, st); break
            if highs[i] >= case['tp1']:
                _finish(case, 'TP1', TP1_R, t, backfill, st); break
            case['last_checked'] = _iso(t)
            case['last_close'] = float(closes[i])
            if case['bars_held'] >= MAX_HOLD_BARS:
                _finish(case, 'TIMEOUT', (closes[i] - case['entry']) / r, t, backfill, st); break

def _card_step(meta, tf, df_all, dfc, res, backfill=False, st=None):
    """一次更新：1)檢查等待中的形態有沒有收盤突破 2)用最新分析更新等待中的形態 3)檢查進行中案例"""
    st = cards_state if st is None else st   # 回測用獨立的st，不影響正式卡片
    key = f"{meta['symbol']}|{tf}"
    _check_pending(key, meta, tf, dfc, backfill, st)
    setup = _setup_from_analysis(df_all, res, tf)
    if setup is None:
        st['pending'].pop(key, None)
    else:
        cid = f"{key}|{setup['h_time']}"
        if cid not in st['used']:
            cur = st['pending'].get(key)
            if cur and cur['h_time'] == setup['h_time'] and cur['l_time'] == setup['l_time']:
                for k in ('stage', 'provisional', 'base', 'c_count', 'pct', 'entry_zone'):
                    cur[k] = setup[k]
            else:
                setup.update({'key': key, 'tf': tf, 'symbol': meta['symbol'], 'name': meta.get('name'),
                              'sector': meta.get('sector'), 'tv_symbol': meta.get('tv_symbol')})
                st['pending'][key] = setup
                _check_pending(key, meta, tf, dfc, backfill, st)   # 最後2根K線可能已經收盤突破
        else:
            st['pending'].pop(key, None)
    p = st['pending'].get(key)
    if p is not None and not df_all.empty:
        p['price'] = float(df_all['close'].values[-1])
        p['price_time'] = _iso(df_all.index[-1])
        p['turnover'] = meta.get('turnover')
        p['wy'] = meta.get('wy_stage')
    _check_active(key, dfc, backfill, st)
    for case in st['active'].values():
        if case.get('key') == key and not df_all.empty:
            case['price'] = float(df_all['close'].values[-1])
            case['turnover'] = meta.get('turnover')
            case['wy'] = meta.get('wy_stage')

def card_process_tf(meta, tf, df, df_daily, res):
    """scan_symbol()每個時間框架分析完後呼叫"""
    dfc = closed_bars(df, tf)
    if len(dfc) < 60: return
    key = f"{meta['symbol']}|{tf}"
    with cards_lock:
        if key not in cards_state['seen'] and BACKFILL_BARS > 0:
            # 第一次看到：回放最近N根已收盤K線，把最近已經突破、還在進行中的案例補抓回來
            for k in range(BACKFILL_BARS, 0, -1):
                dfk = dfc.iloc[:len(dfc) - k]
                if len(dfk) < 60: continue
                dd = dfk if tf == '1D' else df_daily
                try:
                    rk = analyze(dfk, dd)
                    _card_step(meta, tf, dfk, dfk, rk, backfill=True)
                except Exception as e:
                    log.warning(f"🃏 backfill {key} k={k}: {e}")
        cards_state['seen'][key] = datetime.now(MY_TZ).isoformat()
        _card_step(meta, tf, df, dfc, res, backfill=False)

def compute_card_stats(tf=None):
    with cards_lock:
        rows = [d for d in cards_state['done'] if tf is None or d.get('tf') == tf]
    def agg(sub):
        n = len(sub)
        w = sum(1 for d in sub if d['result'] == 'TP1')
        l = sum(1 for d in sub if d['result'] == 'SL')
        to = sum(1 for d in sub if d['result'] == 'TIMEOUT')
        wr = (w / (w + l) * 100) if (w + l) else None
        avg = (sum(d['r_mult'] for d in sub) / n) if n else None
        return {'n': n, 'win': w, 'loss': l, 'timeout': to, 'winrate': wr, 'avg_r': avg}
    groups = [
        ('全部', [('全部', lambda d: True)]),
        ('日線Stage', [('S2', lambda d: d.get('stage') == 2), ('非S2', lambda d: d.get('stage') != 2)]),
        ('追高', [('可追', lambda d: not d.get('chase')), ('⚠️不追', lambda d: d.get('chase'))]),
        ('突破量', [(f'🔥≥{VOL_SURGE_X}x', lambda d: (d.get('vol_x') or 0) >= VOL_SURGE_X),
                    (f'<{VOL_SURGE_X}x', lambda d: (d.get('vol_x') or 0) < VOL_SURGE_X)]),
        ('⏳', [('無⏳', lambda d: not d.get('provisional')), ('有⏳', lambda d: d.get('provisional'))]),
        ('Base', [('第1個base', lambda d: d.get('base', 0) == 0), ('第2個base以上', lambda d: d.get('base', 0) > 0)]),
        ('收盤站穩', [('✅ 進場當天收盤站上BO', lambda d: d.get('entry_mode') == 'touch' and d.get('close_ok') is True),
                     ('⚠️ 進場當天收盤沒站上', lambda d: d.get('entry_mode') == 'touch' and d.get('close_ok') is False)]),
        ('進場時威科夫', [('🧱🟢🟠🟡 有吸籌背景', lambda d: d.get('wy_entry') in ('green', 'orange', 'yellow')),
                         ('⚪❌ 條件不全／跌回', lambda d: d.get('wy_entry') in ('weak', 'fail')),
                         ('沒有威科夫燈號', lambda d: d.get('entry_mode') == 'touch' and d.get('wy_entry') not in WY_CARD_TAG)]),
    ]
    out = []
    for gname, items in groups:
        for label, fn in items:
            out.append((gname, label, agg([d for d in rows if fn(d)])))
    return out

def send_card_telegram():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not card_events:
        return
    lines = []
    thin = 0
    for kind, c in card_events:
        if c.get('tf') not in CARD_TELEGRAM_TFS: continue
        to = c.get('turnover')
        if to is None or to < TG_MIN_TURNOVER_MYR:   # 成交額不足：網頁照樣記錄，Telegram不推（突破和結果都不推）
            if kind == 'open': thin += 1
            continue
        head = f"{label_of(c.get('name'), c['symbol'])} {c['tf']}"
        if kind == 'open':
            tags = [f"S{c.get('stage')}" if c.get('stage') else 'S?']
            if c.get('vol_x') is not None: tags.append(f"量{c['vol_x']}x" + ('🔥' if c['vol_x'] >= VOL_SURGE_X else ''))
            if c.get('provisional'): tags.append('⏳')
            if c.get('chase'): tags.append('⚠️不追')
            if c.get('wy_entry') in WY_CARD_TAG: tags.append(WY_CARD_TAG[c['wy_entry']][0])
            if c.get('entry_mode') == 'touch':
                tags.insert(0, '✅收盤站穩' if c.get('close_ok') else '⚠️收盤沒站穩')
                lines.append(f"🚀 觸價成交 {head}\n  進場{fmt_px(c['entry'])}（BO{fmt_px(c['bo'])}）收盤{fmt_px(c.get('close_px'))} SL{fmt_px(c['sl'])} "
                             f"1:1.5={fmt_px(c['tp1'])} 1:2={fmt_px(c['tp2'])}\n  {' '.join(tags)}")
            else:
                lines.append(f"🚀 突破 {head}\n  確認價{fmt_px(c['entry'])} BO{fmt_px(c['bo'])} SL{fmt_px(c['sl'])} "
                             f"1:1.5={fmt_px(c['tp1'])} 1:2={fmt_px(c['tp2'])}\n  {' '.join(tags)}")
        else:
            icon = {'TP1': '✅ 達1:1.5', 'SL': '❌ 止損', 'TIMEOUT': '⏱ 20根到期'}.get(c['result'], c['result'])
            lines.append(f"{icon} {head} R={c['r_mult']:+.2f}")
    if not lines:
        if thin: log.info(f"🃏 有{thin}個突破因成交額不足沒推")
        return
    if thin:
        lines.append(f"💧 另有 {thin} 個突破成交額<{_fmt_turnover(TG_MIN_TURNOVER_MYR)}，沒推（網頁有記錄）")
    now = datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')
    batches = [lines[i:i+15] for i in range(0, len(lines), 15)]
    for i, batch in enumerate(batches):
        part = f" ({i+1}/{len(batches)})" if len(batches) > 1 else ""
        msg = f"{M['flag']} 🃏 {M['name']}突破卡片{part}\n{now}\n{'─'*20}\n" + "\n".join(batch)
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
            time.sleep(1)
        except Exception as e:
            log.warning(f"Telegram card error: {e}")

# ============================================================
# 🧪 C1跌幅門檻回測（只用來比較，不影響正式掃描）
# 每一檔、每一種門檻，用歷史K線一步一步重播「突破卡片」的完整規則
# （同樣的BO/SL/1:1.5/20根到期），統計訊號數、勝率、平均R。
# ============================================================
from bisect import bisect_right

BT_CONFIGS = [
    ('固定10%', {'min_drop': 10}),
    ('固定7%',  {'min_drop': 7}),
    ('固定5%',  {'min_drop': 5}),
    ('3×ATR%',        {'atr_mult': 3}),
    ('4×ATR%',        {'atr_mult': 4}),
]
BT_DEFAULT_BARS = {'1D': 500, '4H': 900, '1H': 1500}   # 回測最近幾根K線（1D 500根 ≈ 2年）
BT_STEP = 3   # 每3根重新分析一次；中間的K線照樣逐根檢查突破/SL/TP，幾乎不會漏
bt_state = {'status': 'idle', 'tf': None, 'done': 0, 'total': 0, 'started': None, 'finished': None,
            'results': None, 'error': None, 'lock': threading.Lock()}
BT_CASE_KEYS = ('symbol', 'name', 'sector', 'confirm_time', 'end_time', 'entry', 'bo', 'sl', 'c_hv', 'c_lv',
                'result', 'r_mult', 'stage', 'vol_x', 'chase', 'provisional', 'pct', 'c_count', 'bars_held')

def _bt_file(tf):
    return os.path.join(DATA_DIR, f'backtest_c1_{tf}.json')

def _bt_agg(cases):
    n = len(cases)
    w = sum(1 for d in cases if d['result'] == 'TP1')
    l = sum(1 for d in cases if d['result'] == 'SL')
    to = sum(1 for d in cases if d['result'] == 'TIMEOUT')
    tot = sum(d['r_mult'] for d in cases)
    return {'n': n, 'win': w, 'loss': l, 'timeout': to,
            'winrate': round(w / (w + l) * 100, 1) if (w + l) else None,
            'avg_r': round(tot / n, 3) if n else None, 'total_r': round(tot, 1)}

def run_c1_backtest(tf='1D', bars=None, limit=None):
    with bt_state['lock']:
        if bt_state['status'] == 'running' or ex_state['status'] == 'running' or en_state['status'] == 'running':   # 一次只跑一個回測
            return
        bt_state.update({'status': 'running', 'tf': tf, 'done': 0, 'error': None, 'results': None,
                         'started': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'), 'finished': None})
    bars = bars or BT_DEFAULT_BARS.get(tf, 500)
    seen = set()
    syms = [s for s in SYMBOLS if s not in seen and not seen.add(s)]
    if limit: syms = syms[:limit]
    bt_state['total'] = len(syms)
    per = {name: {'cases': [], 'open': 0} for name, _ in BT_CONFIGS}
    first_date = last_date = None
    try:
        for si, sym in enumerate(syms):
            meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)),
                    'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
            try:
                daily = fetch_ohlcv(sym, '1D')
                df = daily if tf == '1D' else fetch_ohlcv(sym, tf)
                if df.empty or len(df) < 300 or daily.empty:
                    continue
                daily_dates = [pd.Timestamp(x).date() for x in daily.index]
                n = len(df)
                start = max(260, n - bars)
                steps = list(range(start, n, BT_STEP)) + [n]
                d0 = str(df.index[start])[:10]; d1 = str(df.index[-1])[:10]
                first_date = d0 if first_date is None or d0 < first_date else first_date
                last_date = d1 if last_date is None or d1 > last_date else last_date
                for name, cfg in BT_CONFIGS:
                    st = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'events': []}
                    for t in steps:
                        d = df.iloc[:t]
                        if tf == '1D':
                            dd = d
                        else:
                            dd = daily.iloc[:bisect_right(daily_dates, pd.Timestamp(d.index[-1]).date())]
                        res = analyze(d, dd, cfg)
                        _card_step(meta, tf, d, d, res, backfill=True, st=st)
                    per[name]['cases'].extend({k: c.get(k) for k in BT_CASE_KEYS} for c in st['done'])
                    per[name]['open'] += len(st['active'])
            except Exception as e:
                log.warning(f"🧪 backtest {sym}: {e}")
            bt_state['done'] = si + 1
            time.sleep(0.2)

        results = {'tf': tf, 'bars': bars, 'step': BT_STEP, 'symbols': len(syms),
                   'period': [first_date, last_date],
                   'finished': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'), 'configs': []}
        for name, cfg in BT_CONFIGS:
            cases = per[name]['cases']
            label = name + ('（現在）' if cfg.get('min_drop') == MIN_DROP_PCT else '')
            s2 = [c for c in cases if c.get('stage') == 2]
            nochase = [c for c in cases if not c.get('chase')]
            results['configs'].append({
                'name': label, 'cfg': cfg, 'open': per[name]['open'],
                'all': _bt_agg(cases), 's2': _bt_agg(s2), 'nochase': _bt_agg(nochase),
                'stocks': len({c['symbol'] for c in cases}),
                'cases': sorted(cases, key=lambda c: c.get('confirm_time') or '', reverse=True),
            })
        with open(_bt_file(tf), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, default=str)
        with bt_state['lock']:
            bt_state.update({'status': 'done', 'results': results, 'finished': results['finished']})
        log.info(f"🧪 C1門檻回測完成 {tf}：{len(syms)}檔")
    except Exception as e:
        log.error(f"🧪 backtest error: {e}")
        with bt_state['lock']:
            bt_state.update({'status': 'error', 'error': str(e)})

def load_bt_result(tf):
    try:
        with open(_bt_file(tf), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

# ============================================================
# 🚪 出場規則回測：同一批進場（突破卡片規則），只換出場方式比較
# 進場 = 跟突破卡片一樣（預設盤中碰到BO成交、進場價=BO；CARD_ENTRY_MODE=close時是收盤價）；初始SL = 最後一個C低點−緩衝
# 跳空低開到SL下方 → 用開盤價出場（比較接近實際）；同一根同時碰SL和目標 → 保守算SL
# ============================================================
EXIT_RULES = [
    # (名稱, 目標R(None=不設目標), 最多持有根數, 1R後移保本, 收盤跌破MA20出場)
    ('1.5R / 20根（現在）',          1.5, 20,  False, False),
    ('1.5R / 40根',                 1.5, 40,  False, False),
    ('1R / 20根',                   1.0, 20,  False, False),
    ('2R / 40根',                   2.0, 40,  False, False),
    ('1.5R / 20根 + 1R後保本',       1.5, 20,  True,  False),
    ('不設目標：1R後保本＋跌破MA20走（最多60根）', None, 60, True, True),
    ('只看SL或1.5R（不限時間，最多120根）', 1.5, 120, False, False),
]
ex_state = {'status': 'idle', 'tf': None, 'c1': None, 'done': 0, 'total': 0, 'started': None,
            'finished': None, 'error': None, 'lock': threading.Lock()}

def _ex_file(tf, c1):
    return os.path.join(DATA_DIR, f'exit_bt_{tf}_c{int(c1)}.json')

def _simulate_exit(df, e_idx, entry, sl0, rule, ma20):
    """回傳 (R倍數, 出場原因, 持有根數, MFE) ；資料不夠走完回傳 None"""
    name, tgt, max_bars, be, ma_exit = rule
    r = entry - sl0
    if r <= 0: return None
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    sl = sl0; be_on = False; mfe = 0.0
    tp = entry + tgt * r if tgt is not None else None
    n = len(df)
    for k in range(1, max_bars + 1):
        i = e_idx + k
        if i >= n:
            return None
        if l[i] <= sl:
            px = o[i] if o[i] < sl else sl
            return ((px - entry) / r, '保本' if be_on and abs(sl - entry) < 1e-12 else 'SL', k, mfe)
        if tp is not None and h[i] >= tp:
            return (tgt, 'TP', k, max(mfe, tgt))
        mfe = max(mfe, (h[i] - entry) / r)
        if be and not be_on and h[i] >= entry + r:
            be_on = True; sl = max(sl, entry)
        if ma_exit and be_on and not pd.isna(ma20[i]) and c[i] < ma20[i]:
            return ((c[i] - entry) / r, 'MA20', k, mfe)
        if k == max_bars:
            return ((c[i] - entry) / r, '到期', k, mfe)
    return None

def _ex_agg(rows):
    n = len(rows)
    if not n:
        return {'n': 0, 'win': 0, 'loss': 0, 'flat': 0, 'winrate': None, 'avg_r': None, 'total_r': 0.0,
                'avg_bars': None, 'tp': 0, 'sl': 0, 'other': 0}
    w = sum(1 for x in rows if x['r'] > 0.05); lo = sum(1 for x in rows if x['r'] < -0.05)
    tot = sum(x['r'] for x in rows)
    return {'n': n, 'win': w, 'loss': lo, 'flat': n - w - lo,
            'winrate': round(w / n * 100, 1), 'avg_r': round(tot / n, 3), 'total_r': round(tot, 1),
            'avg_bars': round(sum(x['bars'] for x in rows) / n, 1),
            'tp': sum(1 for x in rows if x['why'] == 'TP'), 'sl': sum(1 for x in rows if x['why'] == 'SL'),
            'other': sum(1 for x in rows if x['why'] not in ('TP', 'SL'))}

# ============================================================
# 🔬 進場條件分析（MH 2026-10-29）：把出場回測的每一筆進場，依「進場當下的條件」分組，
# 看哪一組「幾乎沒漲（20根內最多漲不到0.5R）」比例最低 → 找出值得加的進場過濾。
# 只用進場那一刻（含）之前的資料，沒有偷看未來。
# ============================================================
EXF_RS_STRONG = 5.0    # 力量：20天跑贏大盤 ≥ 5% 算「大幅跑贏」

def _exf_bench_ctx():
    """回測開始時抓一次大盤日線（美股SPY；沒有基準的市場回傳None）"""
    if not RS_BENCHMARK:
        return None
    try:
        b = fetch_ohlcv(RS_BENCHMARK, '1D')
        if b.empty or len(b) < 200:
            return None
        return {'close': b['close'], 'df': b, 'dates': [pd.Timestamp(x).date() for x in b.index], 'stage': {}}
    except Exception as e:
        log.warning(f"🔬 抓大盤 {RS_BENCHMARK} 失敗：{e}")
        return None

def _exf_day_pos(dates, d, intraday):
    """日線位置：日線進場用當天收盤（同一時間），盤中時間框架只用前一天收盤（避免偷看）"""
    from bisect import bisect_left
    return (bisect_right(dates, d) if not intraday else bisect_left(dates, d)) - 1

def _exf_bench_stage(ctx, pos):
    if pos < 0:
        return None
    if pos not in ctx['stage']:
        try:
            ctx['stage'][pos] = get_stage(ctx['df'].iloc[:pos + 1])[0]
        except Exception:
            ctx['stage'][pos] = None
    return ctx['stage'][pos]

def _exf_factors(e, daily, tf, ctx):
    """回傳一筆進場的分組條件"""
    f = {
        'vol_x': e.get('vol_x'), 'provisional': bool(e.get('provisional')), 'c_count': e.get('c_count'),
        'pct': e.get('pct'), 'base': e.get('base', 0), 'stage': e.get('stage'), 'chase': bool(e.get('chase')),
        'r_pct': (e['entry'] - e['sl']) / e['entry'] * 100 if e.get('entry') else None,
        'rs': None, 'mkt': None,
    }
    if ctx is None:
        return f
    try:
        d = pd.Timestamp(e['confirm_time']).date()
        intraday = tf != '1D'
        bpos = _exf_day_pos(ctx['dates'], d, intraday)
        f['mkt'] = _exf_bench_stage(ctx, bpos)
        sdates = [pd.Timestamp(x).date() for x in daily.index]
        spos = _exf_day_pos(sdates, d, intraday)
        if spos >= RS_LOOKBACK_DAYS and bpos >= RS_LOOKBACK_DAYS:
            s = daily['close'].iloc[:spos + 1]
            b = ctx['close'].iloc[:bpos + 1]
            al = pd.concat([s.rename('s'), b.rename('b')], axis=1, join='inner').dropna()
            if len(al) > RS_LOOKBACK_DAYS:
                ratio = al['s'] / al['b']
                past = ratio.iloc[-1 - RS_LOOKBACK_DAYS]
                if past:
                    f['rs'] = round(float((ratio.iloc[-1] / past - 1) * 100), 2)
    except Exception as ex:
        log.warning(f"🔬 條件計算 {e.get('symbol')}: {ex}")
    return f

def _exf_groups(has_bench):
    vx = lambda x: x.get('vol_x')
    g = [
        ('🔥 突破量', [(f'≥ {VOL_SURGE_X}倍均量', lambda x: (vx(x) or 0) >= VOL_SURGE_X),
                       (f'1～{VOL_SURGE_X}倍', lambda x: vx(x) is not None and 1 <= vx(x) < VOL_SURGE_X),
                       ('< 1倍（縮量突破）', lambda x: vx(x) is not None and vx(x) < 1)]),
    ]
    if has_bench:
        g += [
            (f'💪 力量（20天 vs {RS_BENCHMARK}）', [(f'大幅跑贏 ≥ {EXF_RS_STRONG:g}%', lambda x: x['rs'] is not None and x['rs'] >= EXF_RS_STRONG),
                                                 (f'小幅跑贏 0～{EXF_RS_STRONG:g}%', lambda x: x['rs'] is not None and 0 <= x['rs'] < EXF_RS_STRONG),
                                                 ('跑輸大盤', lambda x: x['rs'] is not None and x['rs'] < 0)]),
            (f'📈 大盤（{RS_BENCHMARK} 日線）', [('大盤 S2', lambda x: x['mkt'] == 2),
                                                ('大盤不是 S2', lambda x: x['mkt'] is not None and x['mkt'] != 2)]),
        ]
    g += [
        ('📉 最後一個C收縮', [('很緊 < 5%', lambda x: x['pct'] is not None and x['pct'] < 5),
                              ('5～10%', lambda x: x['pct'] is not None and 5 <= x['pct'] < 10),
                              ('≥ 10%（比較鬆）', lambda x: x['pct'] is not None and x['pct'] >= 10)]),
        ('📐 收縮段數', [('2C', lambda x: x['c_count'] == 2), ('3C 以上', lambda x: (x['c_count'] or 0) >= 3)]),
        ('📏 1R 距離（SL多遠）', [('< 5%', lambda x: x['r_pct'] is not None and x['r_pct'] < 5),
                                 ('5～10%', lambda x: x['r_pct'] is not None and 5 <= x['r_pct'] < 10),
                                 ('≥ 10%', lambda x: x['r_pct'] is not None and x['r_pct'] >= 10)]),
        ('⏳ 低點確認', [('已確認', lambda x: not x['provisional']), ('有⏳（未確認）', lambda x: x['provisional'])]),
        ('🧱 Base', [('第1個base', lambda x: (x['base'] or 0) == 0), ('第2個base以上', lambda x: (x['base'] or 0) > 0)]),
        ('📊 日線Stage', [('S2', lambda x: x['stage'] == 2), ('非S2', lambda x: x['stage'] != 2)]),
    ]
    return g

def _exf_agg(sub, best_name, cur_name):
    n = len(sub)
    if not n:
        return {'n': 0}
    none = sum(1 for x in sub if x['mfe'] < 0.5)
    big = sum(1 for x in sub if x['mfe'] >= 1.5)
    rc = [x['r'][cur_name] for x in sub if cur_name in x['r']]
    rb = [x['r'][best_name] for x in sub if best_name in x['r']]
    return {'n': n, 'none_pct': round(none / n * 100, 1), 'big_pct': round(big / n * 100, 1),
            'cur_r': round(sum(rc) / len(rc), 3) if rc else None, 'best_r': round(sum(rb) / len(rb), 3) if rb else None}

def compute_entry_factors(ent_rows, results, has_bench):
    """ent_rows：每筆進場的條件＋各出場規則的R＋20根MFE"""
    if not ent_rows:
        return None
    rules = [rl for rl in results['rules'] if rl['all'].get('avg_r') is not None and rl['all'].get('n')]
    cur_name = EXIT_RULES[0][0]
    best_name = max(rules, key=lambda rl: rl['all']['avg_r'])['name'] if rules else cur_name
    out = {'n': len(ent_rows), 'cur_name': cur_name, 'best_name': best_name,
           'all': _exf_agg(ent_rows, best_name, cur_name), 'groups': []}
    for gname, items in _exf_groups(has_bench):
        out['groups'].append({'name': gname, 'items': [{'label': lab, **_exf_agg([x for x in ent_rows if fn(x)], best_name, cur_name)}
                                                      for lab, fn in items]})
    return out

def run_exit_backtest(tf='1D', c1=10, bars=None, limit=None):
    with ex_state['lock']:
        if ex_state['status'] == 'running' or bt_state['status'] == 'running' or en_state['status'] == 'running':
            return
        ex_state.update({'status': 'running', 'tf': tf, 'c1': c1, 'done': 0, 'error': None, 'finished': None,
                         'started': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')})
    bars = bars or BT_DEFAULT_BARS.get(tf, 500)
    cfg = {} if float(c1) == MIN_DROP_PCT else {'min_drop': float(c1)}
    seen = set()
    syms = [s for s in SYMBOLS if s not in seen and not seen.add(s)]
    if limit: syms = syms[:limit]
    ex_state['total'] = len(syms)
    per_rule = {rule[0]: [] for rule in EXIT_RULES}
    entries_n = 0; open_n = {rule[0]: 0 for rule in EXIT_RULES}; mfes = []
    first_date = last_date = None
    ent_rows = []   # 🔬 進場條件分析用
    try:
        bench_ctx = _exf_bench_ctx()
        for si, sym in enumerate(syms):
            meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)),
                    'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
            try:
                daily = fetch_ohlcv(sym, '1D')
                df = daily if tf == '1D' else fetch_ohlcv(sym, tf)
                if df.empty or len(df) < 300 or daily.empty:
                    continue
                daily_dates = [pd.Timestamp(x).date() for x in daily.index]
                n = len(df)
                start = max(260, n - bars)
                d0 = str(df.index[start])[:10]; d1 = str(df.index[-1])[:10]
                first_date = d0 if first_date is None or d0 < first_date else first_date
                last_date = d1 if last_date is None or d1 > last_date else last_date
                st = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'events': []}
                for t in list(range(start, n, BT_STEP)) + [n]:
                    d = df.iloc[:t]
                    dd = d if tf == '1D' else daily.iloc[:bisect_right(daily_dates, pd.Timestamp(d.index[-1]).date())]
                    _card_step(meta, tf, d, d, analyze(d, dd, cfg), backfill=True, st=st)
                entries = st['done'] + list(st['active'].values())
                ma20 = calc_sma(df['close'], 20).values
                pos_of = {_iso(t): i for i, t in enumerate(df.index)}
                for e in entries:
                    e_idx = pos_of.get(e['confirm_time'])
                    if e_idx is None: continue
                    entries_n += 1
                    ent = None
                    same_bar_sl = e.get('result') == 'SL' and e.get('end_time') == e['confirm_time']   # 掛單成交那根就跌到SL
                    for rule in EXIT_RULES:
                        out = (-1.0, 'SL', 0, 0.0) if same_bar_sl else _simulate_exit(df, e_idx, e['entry'], e['sl'], rule, ma20)
                        if out is None:
                            open_n[rule[0]] += 1; continue
                        rm, why, k, mfe = out
                        if rule is EXIT_RULES[0]:
                            ent = _exf_factors(e, daily, tf, bench_ctx)
                            ent.update({'mfe': round(float(mfe), 2), 'r': {}})
                            ent_rows.append(ent)
                        if ent is not None:
                            ent['r'][rule[0]] = round(float(rm), 3)
                        per_rule[rule[0]].append({'symbol': sym, 'name': meta['name'], 'confirm_time': e['confirm_time'],
                                                  'entry': e['entry'], 'sl': e['sl'], 'r': round(float(rm), 3), 'why': why,
                                                  'bars': k, 'stage': e.get('stage'), 'chase': bool(e.get('chase')),
                                                  'mfe': round(float(mfe), 2)})
            except Exception as ex:
                log.warning(f"🚪 exit backtest {sym}: {ex}")
            ex_state['done'] = si + 1
            time.sleep(0.2)

        # MFE分布：用「不限時間」那條規則之外的20根版本看突破後20根內最多漲到幾R
        base = per_rule[EXIT_RULES[0][0]]
        mfe_bins = {'<0.5R': 0, '0.5~1R': 0, '1~1.5R': 0, '≥1.5R': 0}
        for x in base:
            m = x['mfe']
            k = '<0.5R' if m < 0.5 else ('0.5~1R' if m < 1 else ('1~1.5R' if m < 1.5 else '≥1.5R'))
            mfe_bins[k] += 1
        results = {'tf': tf, 'c1': c1, 'bars': bars, 'symbols': len(syms), 'entries': entries_n,
                   'period': [first_date, last_date], 'mfe_bins_20': mfe_bins,
                   'finished': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'), 'rules': []}
        for rule in EXIT_RULES:
            rows = per_rule[rule[0]]
            results['rules'].append({
                'name': rule[0], 'open': open_n[rule[0]],
                'all': _ex_agg(rows),
                'nochase': _ex_agg([x for x in rows if not x['chase']]),
                's2': _ex_agg([x for x in rows if x.get('stage') == 2]),
                'cases': sorted(rows, key=lambda x: x['confirm_time'], reverse=True)[:40],
            })
        try:
            results['factors'] = compute_entry_factors(ent_rows, results, bench_ctx is not None)
        except Exception as ex:
            log.warning(f"🔬 進場條件分析失敗：{ex}")
        with open(_ex_file(tf, c1), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, default=str)
        with ex_state['lock']:
            ex_state.update({'status': 'done', 'finished': results['finished']})
        log.info(f"🚪 出場規則回測完成 {tf} C1={c1}%：{entries_n}筆進場")
    except Exception as ex:
        log.error(f"🚪 exit backtest error: {ex}")
        with ex_state['lock']:
            ex_state.update({'status': 'error', 'error': str(ex)})

def load_ex_result(tf, c1):
    try:
        with open(_ex_file(tf, c1), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

# ============================================================
# ⚖️ 進場方式比較回測（MH 2026-10-30）：同一批C系列形態，比較兩種進場
#   A 盤中掛單：盤中最高價碰到BO就成交（成交價=BO；跳空高開用開盤價）← 老師SOP／老師SCV網站的算法
#   B 收盤確認：收盤站上BO才進場（進場價=當天收盤）← 突破卡片的舊算法（2026-10-30前）
# SL、1:1.5目標、20根到期，全部跟突破卡片一樣；只換進場方式。正式掃描完全不受影響。
# 拆解：A − B ＝（同一個形態兩邊都進場：掛單價格比較好多賺的）＋（只有A進場的假突破：盤中衝過、收盤沒站上）
# ============================================================
EN_CASE_KEYS = ('id', 'symbol', 'name', 'confirm_time', 'end_time', 'entry', 'bo', 'sl', 'result', 'r_mult',
                'stage', 'chase', 'close_ok', 'bars_held')
en_state = {'status': 'idle', 'tf': None, 'done': 0, 'total': 0, 'started': None, 'finished': None,
            'error': None, 'lock': threading.Lock()}
EN_RISK_MONEY = float(menv('EN_RISK_MONEY', '100'))   # 結論卡「每筆冒多少錢」的示範金額

def _en_file(tf):
    return os.path.join(DATA_DIR, f'entry_bt_{tf}.json')

def _en_agg(cases):
    n = len(cases)
    if not n:
        return {'n': 0, 'win': 0, 'loss': 0, 'timeout': 0, 'winrate': None, 'avg_r': None, 'total_r': 0.0}
    w = sum(1 for d in cases if d['result'] == 'TP1')
    l = sum(1 for d in cases if d['result'] == 'SL')
    tot = sum(d['r_mult'] for d in cases)
    return {'n': n, 'win': w, 'loss': l, 'timeout': n - w - l,
            'winrate': round(w / n * 100, 1), 'avg_r': round(tot / n, 3), 'total_r': round(tot, 1)}

def _en_block(a_cases, b_cases, b_open_ids):
    """一組（全部／只看S2）的完整比較數字"""
    b_by = {c['id']: c for c in b_cases}
    paired_a = [c for c in a_cases if c['id'] in b_by]
    paired_b = [b_by[c['id']] for c in paired_a]
    a_only = [c for c in a_cases if c['id'] not in b_by and c['id'] not in b_open_ids]
    a_ids = {c['id'] for c in a_cases}
    b_only = [c for c in b_cases if c['id'] not in a_ids]
    return {
        'A': _en_agg(a_cases), 'B': _en_agg(b_cases),
        'A_closeok': _en_agg([c for c in a_cases if c.get('close_ok')]),
        'A_fake': _en_agg([c for c in a_cases if not c.get('close_ok')]),
        'paired_A': _en_agg(paired_a), 'paired_B': _en_agg(paired_b),
        'A_only': _en_agg(a_only), 'B_only': _en_agg(b_only),
    }

def run_entry_backtest(tf='1D', bars=None, limit=None):
    with en_state['lock']:
        if en_state['status'] == 'running' or bt_state['status'] == 'running' or ex_state['status'] == 'running':
            return
        en_state.update({'status': 'running', 'tf': tf, 'done': 0, 'error': None, 'finished': None,
                         'started': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')})
    bars = bars or BT_DEFAULT_BARS.get(tf, 500)
    seen = set()
    syms = [s for s in SYMBOLS if s not in seen and not seen.add(s)]
    if limit: syms = syms[:limit]
    en_state['total'] = len(syms)
    all_a, all_b, open_a, open_b = [], [], 0, 0
    b_open_ids = set()
    first_date = last_date = None
    try:
        for si, sym in enumerate(syms):
            meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)),
                    'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
            try:
                daily = fetch_ohlcv(sym, '1D')
                df = daily if tf == '1D' else fetch_ohlcv(sym, tf)
                if df.empty or len(df) < 300 or daily.empty:
                    continue
                df = closed_bars(df, tf); daily = closed_bars(daily, '1D')   # 只用已收盤的K線
                daily_dates = [pd.Timestamp(x).date() for x in daily.index]
                n = len(df)
                start = max(260, n - bars)
                d0 = str(df.index[start])[:10]; d1 = str(df.index[-1])[:10]
                first_date = d0 if first_date is None or d0 < first_date else first_date
                last_date = d1 if last_date is None or d1 > last_date else last_date
                stA = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'events': [], 'entry_mode': 'touch'}
                stB = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'events': [], 'entry_mode': 'close'}
                for t in list(range(start, n, BT_STEP)) + [n]:
                    d = df.iloc[:t]
                    dd = d if tf == '1D' else daily.iloc[:bisect_right(daily_dates, pd.Timestamp(d.index[-1]).date())]
                    res = analyze(d, dd)        # 同一次分析給A、B用 → 兩邊看到的形態完全一樣
                    _card_step(meta, tf, d, d, res, backfill=True, st=stA)
                    _card_step(meta, tf, d, d, res, backfill=True, st=stB)
                all_a.extend({k: c.get(k) for k in EN_CASE_KEYS} for c in stA['done'])
                all_b.extend({k: c.get(k) for k in EN_CASE_KEYS} for c in stB['done'])
                open_a += len(stA['active']); open_b += len(stB['active'])
                b_open_ids.update(stB['active'].keys())
            except Exception as ex:
                log.warning(f"⚖️ entry backtest {sym}: {ex}")
            en_state['done'] = si + 1
            time.sleep(0.2)

        results = {'tf': tf, 'bars': bars, 'symbols': len(syms), 'c1': MIN_DROP_PCT,
                   'period': [first_date, last_date], 'open_a': open_a, 'open_b': open_b,
                   'finished': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'),
                   'all': _en_block(all_a, all_b, b_open_ids),
                   's2': _en_block([c for c in all_a if c.get('stage') == 2],
                                   [c for c in all_b if c.get('stage') == 2], b_open_ids),
                   'fake_cases': sorted([c for c in all_a if not c.get('close_ok')],
                                        key=lambda c: c.get('confirm_time') or '', reverse=True)[:20],
                   'cases_a': sorted(all_a, key=lambda c: c.get('confirm_time') or '', reverse=True)[:20],
                   'cases_b': sorted(all_b, key=lambda c: c.get('confirm_time') or '', reverse=True)[:20]}
        with open(_en_file(tf), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, default=str)
        with en_state['lock']:
            en_state.update({'status': 'done', 'finished': results['finished']})
        log.info(f"⚖️ 進場比較回測完成 {tf}：A {len(all_a)}筆 / B {len(all_b)}筆")
    except Exception as ex:
        log.error(f"⚖️ entry backtest error: {ex}")
        with en_state['lock']:
            en_state.update({'status': 'error', 'error': str(ex)})

def load_en_result(tf):
    try:
        with open(_en_file(tf), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

def _en_r(v):
    return f'{v:+.2f}R' if v is not None else '-'

def entry_summary_html(res, blk_key='all'):
    """📋 一眼看懂：A掛單 vs B收盤確認"""
    b = res[blk_key]
    A, B = b['A'], b['B']
    if not A['n'] or not B['n']:
        return '<div class="exs"><div class="exs-title">📋 一眼看懂</div><div class="exs-v">筆數不夠，沒辦法比較。</div></div>'
    pa, pb, fk, ao = b['paired_A'], b['paired_B'], b['A_fake'], b['A_only']
    money = lambda r: f'RM{r * EN_RISK_MONEY:+,.0f}'
    win_total = 'A 盤中掛單' if A['total_r'] > B['total_r'] else ('B 收盤確認' if B['total_r'] > A['total_r'] else '打平')
    win_avg = 'A' if (A['avg_r'] or 0) > (B['avg_r'] or 0) else 'B'
    nmin = min(A['n'], B['n'])
    trust = '🔴 低（不到30筆，先當參考）' if nmin < 30 else ('🟡 中（30～100筆）' if nmin < 100 else '🟢 高（100筆以上）')
    diff = round(A['total_r'] - B['total_r'], 1)
    price_gain = round(pa['total_r'] - pb['total_r'], 1) if pa['n'] else 0.0
    fake_cost = ao['total_r'] if ao['n'] else 0.0
    fake_pct = round(fk['n'] / A['n'] * 100) if A['n'] else 0

    if A['total_r'] > B['total_r'] and (A['avg_r'] or 0) >= (B['avg_r'] or 0):
        tip = ('<b>掛單（A）比較好</b>：價格優勢大過假突破的損失。照老師SOP在BO掛單就對了；'
               '卡片的「收盤確認」只當作「突破有沒有站穩」的參考，不用等收盤才買。')
    elif B['total_r'] > A['total_r'] and (B['avg_r'] or 0) >= (A['avg_r'] or 0):
        tip = ('<b>收盤確認（B）比較好</b>：假突破虧的錢大過掛單的價格優勢。可以考慮改成：'
               '收盤前（16:30～17:00）確認站上BO才買，不在盤中掛單。')
    elif A['total_r'] > B['total_r']:
        tip = ('<b>A 總賺比較多、但每筆平均比較差</b>：A 是靠交易次數多（多了假突破那些單）。'
               '如果你在意每一筆的品質，或資金有限一次只能做幾筆，B 比較穩。')
    else:
        tip = ('<b>B 總賺比較多、但每筆平均比較差</b>：兩種差不多，選你比較能執行的那一種。'
               '上班沒辦法盯盤 → 掛單（A）；收盤前可以看一眼 → 收盤確認（B）。')
    if nmin < 30:
        tip += ' 不過筆數還少，結論可能會變。'

    return f'''<div class="exs"><div class="exs-title">📋 一眼看懂：A 盤中掛單 vs B 收盤確認</div>
<div class="exs-row"><div class="exs-k">總評</div><div class="exs-v">總賺比較多：<b>{win_total}</b>（差 {abs(diff):.1f}R）・每筆平均比較好：<b>{win_avg}</b>
<div class="exs-sub">假設每筆冒 RM{EN_RISK_MONEY:,.0f} 風險：A 共 {money(A["total_r"])}（{A["n"]}筆），B 共 {money(B["total_r"])}（{B["n"]}筆）</div></div></div>
<div class="exs-row"><div class="exs-k">A 盤中掛單</div><div class="exs-v">{A["n"]}筆・達1:1.5 {A["win"]}・止損 {A["loss"]}・到期 {A["timeout"]}・達標率 {A["winrate"]:.0f}%・平均 <b>{_en_r(A["avg_r"])}</b>・總 <b>{A["total_r"]:+.1f}R</b></div></div>
<div class="exs-row"><div class="exs-k">B 收盤確認</div><div class="exs-v">{B["n"]}筆・達1:1.5 {B["win"]}・止損 {B["loss"]}・到期 {B["timeout"]}・達標率 {B["winrate"]:.0f}%・平均 <b>{_en_r(B["avg_r"])}</b>・總 <b>{B["total_r"]:+.1f}R</b></div></div>
<div class="exs-row"><div class="exs-k">差在哪裡</div><div class="exs-v">
<ul class="exs-ul">
<li>同一個形態兩邊都進場（{pa["n"]}筆）：A 平均 {_en_r(pa["avg_r"])}，B 平均 {_en_r(pb["avg_r"])} → 掛單價格比較好，A 多賺 <b>{price_gain:+.1f}R</b></li>
<li>只有 A 進場（盤中衝過BO、之後一直沒收盤站上，B 沒買）{ao["n"]}筆：平均 {_en_r(ao["avg_r"])} → 這些單 A 共 <b>{fake_cost:+.1f}R</b></li>
<li>A − B ≈ {price_gain:+.1f} ＋ ({fake_cost:+.1f}) ＝ <b>{diff:+.1f}R</b></li>
</ul></div></div>
<div class="exs-row"><div class="exs-k">假突破</div><div class="exs-v">A 的 {A["n"]} 筆裡，<b>{fk["n"]}筆（{fake_pct}%）</b>進場當天收盤沒站上BO：平均 {_en_r(fk["avg_r"])}・達標率 {f'{fk["winrate"]:.0f}%' if fk["winrate"] is not None else '-'}
<div class="exs-sub">對照：當天收盤有站上BO的 {b["A_closeok"]["n"]} 筆，平均 {_en_r(b["A_closeok"]["avg_r"])}</div></div></div>
<div class="exs-row"><div class="exs-k">可信度</div><div class="exs-v">{trust}</div></div>
<div class="exs-tip">💡 {tip}</div></div>'''

# ============================================================
# 📋 出場回測「一眼看懂」結論卡（MH 2026-10-28）：程式自動評分＋寫建議，詳細表格摺疊在下面
# 門檻可用環境變數調整（例：US_EXS_GOOD_R）
# ============================================================
EXS_GOOD_R      = float(menv('EXS_GOOD_R', '0.10'))    # 最好規則平均R > 此值 → 🟢 賺錢
EXS_FLAT_R      = float(menv('EXS_FLAT_R', '-0.05'))   # 平均R ≥ 此值 → 🟡 打平；更低 → 🔴 虧錢
EXS_MFE_GOOD    = float(menv('EXS_MFE_GOOD', '35'))    # 「幾乎沒漲(<0.5R)」比例 < 此% → 🟢 進場品質好
EXS_MFE_BAD     = float(menv('EXS_MFE_BAD', '45'))     # 比例 > 此% → 🔴 差；中間 → 🟡 普通
EXS_FILTER_GOOD = float(menv('EXS_FILTER_GOOD', '0.05'))  # 過濾後平均R改善 ≥ 此值 → 有用
EXS_FILTER_MIN  = float(menv('EXS_FILTER_MIN', '0.01'))   # 改善 ≥ 此值 → 幫助很小；更少 → 沒幫助
EXS_TIE_R       = 0.03   # 平均R相差不到這個，當作「差不多」

def _exs_money(avg_r):
    """平均R → 「每冒100元風險，平均賺/虧多少」"""
    v = avg_r * 100
    cur = M['currency']
    if abs(v) < 0.5:
        return f'每冒 {cur}100 風險，平均打平'
    return f'每冒 {cur}100 風險，平均{"賺" if v > 0 else "虧"} {cur}{abs(v):.0f}'

EXF_MIN_N_PCT  = 15    # 一組至少要有全部的15%（而且≥15筆）才拿來下結論，太小組的結果多半是運氣
EXF_GOOD_DIFF  = float(menv('EXF_GOOD_DIFF', '10'))   # 某組「幾乎沒漲」比全部低 ≥ 10個百分點 → 值得當過濾條件

def _exf_min_n(fx):
    return max(15, fx['n'] * EXF_MIN_N_PCT / 100)

def exf_best(fx):
    """回傳 (最好的一組, 最差的一組)：只看樣本夠大的組，用「幾乎沒漲%」比較"""
    if not fx or not fx.get('groups'):
        return None, None
    mn = _exf_min_n(fx)
    cands = [dict(it, group=g['name']) for g in fx['groups'] for it in g['items'] if it.get('n', 0) >= mn]
    if not cands:
        return None, None
    best = min(cands, key=lambda it: it['none_pct'])
    worst = max(cands, key=lambda it: it['none_pct'])
    return best, worst

def _ex_compare_hint(res):
    """依正在看的那一組，提示還沒比較過的 C1門檻／時間框架"""
    combos = [(t, c) for t in ('1D', '4H') if t in TF_LABELS for c in (10, 7)]
    cur = (res.get('tf'), int(res.get('c1') or 0))
    missing = [f'{t}・C1 {c}%' for t, c in combos if (t, c) != cur and load_ex_result(t, c) is None]
    return missing

def exf_table_html(res):
    fx = res.get('factors')
    if not fx:
        return ('<div class="sec"><h3>🔬 進場條件分析</h3><div class="empty">這份結果是舊版回測跑的，沒有進場條件資料。'
                f'按上面的「▶ 跑 {_h(res.get("tf"))}・C1 {res.get("c1")}%」重跑一次就會出現。</div></div>')
    al = fx['all']
    mn = _exf_min_n(fx)
    best, worst = exf_best(fx)
    pr = lambda v: '-' if v is None else f'{v:+.2f}R'
    rows = ''
    for g in fx['groups']:
        first = True
        for it in g['items']:
            gcell = f'<td class="g" rowspan="{len(g["items"])}"><b>{_h(g["name"])}</b></td>' if first else ''
            first = False
            if not it.get('n'):
                rows += f'<tr>{gcell}<td class="g">{_h(it["label"])}</td><td>0</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>'
                continue
            small = it['n'] < mn
            diff = it['none_pct'] - al['none_pct']
            if small:
                col = 'color:#777'
            elif diff <= -EXF_GOOD_DIFF:
                col = 'background:#1b3d27;color:#a5d6a7;font-weight:bold'
            elif diff >= EXF_GOOD_DIFF:
                col = 'background:#4a1c1c;color:#ff9a9a'
            else:
                col = ''
            star = ' ⭐' if (best and not small and it['label'] == best['label'] and g['name'] == best['group']
                              and al['none_pct'] - best['none_pct'] >= EXF_GOOD_DIFF) else ''
            rows += (f'<tr>{gcell}<td class="g">{_h(it["label"])}{star}{" <span style=color:#777>（太少）</span>" if small else ""}</td>'
                     f'<td>{it["n"]}</td><td style="{col}">{it["none_pct"]:.0f}%</td><td>{it["big_pct"]:.0f}%</td>'
                     f'<td>{pr(it["cur_r"])}</td><td>{pr(it["best_r"])}</td></tr>')
    return f'''<div class="sec"><h3>🔬 進場條件分析（找出「比較會漲」的突破）</h3>
<div class="desc">把 {fx["n"]} 筆進場依「進場當下的條件」分組。看第 4 欄「幾乎沒漲」：
<span style="background:#1b3d27;color:#a5d6a7;padding:0 4px">綠色</span> = 比全部（{al["none_pct"]:.0f}%）低 {EXF_GOOD_DIFF:g} 個百分點以上，值得考慮當進場過濾；
<span style="background:#4a1c1c;color:#ff9a9a;padding:0 4px">紅色</span> = 更容易沒漲；灰色「太少」= 少於 {mn:.0f} 筆，不下結論。⭐ = 最值得加的條件。</div>
<div style="overflow-x:auto"><table class="st"><tr><th>條件</th><th>分組</th><th>筆數</th><th>幾乎沒漲<br>(&lt;0.5R)</th><th>大行情<br>(≥1.5R)</th>
<th>平均R<br>{_h(fx["cur_name"])}</th><th>平均R<br>{_h(fx["best_name"])}</th></tr>
<tr><td class="g"><b>全部</b></td><td class="g">—</td><td>{al["n"]}</td><td>{al["none_pct"]:.0f}%</td><td>{al["big_pct"]:.0f}%</td><td>{pr(al["cur_r"])}</td><td>{pr(al["best_r"])}</td></tr>
{rows}</table></div>
<div class="desc" style="margin-top:6px">只用進場那一刻（含）之前的資料計算，沒有偷看未來。同一個條件裡的組，筆數加起來可能少於全部（有些資料算不出來）。</div></div>'''

def exit_summary_html(res):
    rules = [rl for rl in res.get('rules', []) if rl['all'].get('avg_r') is not None and rl['all'].get('n')]
    if not rules:
        return ''
    cur_rule = res['rules'][0]
    best = max(rules, key=lambda rl: rl['all']['avg_r'])
    b_avg = best['all']['avg_r']
    ties = [rl['name'] for rl in rules if rl is not best and b_avg - rl['all']['avg_r'] < EXS_TIE_R]

    # ① 總評
    if b_avg > EXS_GOOD_R:
        v_icon, v_txt = '🟢', '這套進場有賺錢優勢'
    elif b_avg >= EXS_FLAT_R:
        v_icon, v_txt = '🟡', '接近打平（扣手續費後可能小虧）'
    else:
        v_icon, v_txt = '🔴', '這套進場目前不賺錢'
    n_pos = sum(1 for rl in rules if rl['all']['avg_r'] > 0)
    v_sub = (f'最好的出場方式：{_exs_money(b_avg)}・'
             f'{len(rules)} 種出場方式裡有 {n_pos} 種是賺錢的')

    # ② 進場品質（MFE）
    mb = res.get('mfe_bins_20', {}) or {}
    mtot = sum(mb.values())
    if mtot:
        p_none = mb.get('<0.5R', 0) / mtot * 100
        p_1r = (mb.get('1~1.5R', 0) + mb.get('≥1.5R', 0)) / mtot * 100
        p_big = mb.get('≥1.5R', 0) / mtot * 100
        if p_none < EXS_MFE_GOOD:   m_icon, m_txt = '🟢', '好'
        elif p_none <= EXS_MFE_BAD: m_icon, m_txt = '🟡', '普通'
        else:                       m_icon, m_txt = '🔴', '差'
        mfe_block = (f'<div class="exs-sub">每 100 筆突破（突破後20根K線內）：</div>'
                     f'<ul class="exs-ul"><li><b>{p_none:.0f}</b> 筆 幾乎沒漲（最多漲不到 0.5R）</li>'
                     f'<li><b>{p_1r:.0f}</b> 筆 能漲到 1R 以上</li>'
                     f'<li><b>{p_big:.0f}</b> 筆 走出大行情（≥ 1.5R）</li></ul>')
    else:
        p_none, m_icon, m_txt, mfe_block = None, '⚪', '沒有資料', ''

    # ③ 最好的出場 vs 現在用的
    best_line = f'<b>{_h(best["name"])}</b>（平均 {b_avg:+.2f}R）'
    if ties:
        best_line += f'<div class="exs-sub">和「{_h("」「".join(ties))}」差不多（相差不到 {EXS_TIE_R}R），樣本小時可視為同一級</div>'
    c_avg = cur_rule['all'].get('avg_r')
    if cur_rule is not best and c_avg is not None:
        best_line += f'<div class="exs-sub">現在用的「{_h(cur_rule["name"])}」：{_exs_money(c_avg)}（{c_avg:+.2f}R）</div>'
    elif cur_rule is best:
        best_line += '<div class="exs-sub">就是現在用的規則 👍</div>'

    # ④ 過濾有沒有用：用每條規則「平均R」的改善，取平均（筆數不同，不能比總R）
    def filt(key):
        diffs = [rl[key]['avg_r'] - rl['all']['avg_r'] for rl in rules
                 if rl[key].get('avg_r') is not None and rl[key].get('n')]
        if not diffs:
            return None, '⚪', '沒有資料'
        d = sum(diffs) / len(diffs)
        if d >= EXS_FILTER_GOOD: return d, '🟢', '有用'
        if d >= EXS_FILTER_MIN:  return d, '🟡', '幫助很小'
        return d, '❌', '沒幫助'
    d_nc, i_nc, t_nc = filt('nochase')
    d_s2, i_s2, t_s2 = filt('s2')
    s2_share = (cur_rule['s2']['n'] / cur_rule['all']['n'] * 100) if cur_rule['all'].get('n') else 0
    fmt_d = lambda d: '' if d is None else f'（平均R {d:+.2f}）'
    s2_note = f'・{s2_share:.0f}% 的單本來就是S2，這個過濾幾乎沒過濾到什麼' if s2_share >= 90 else ''
    filt_block = (f'<ul class="exs-ul"><li>排除⚠️不追：{i_nc} {t_nc}{fmt_d(d_nc)}</li>'
                  f'<li>只看日線S2：{i_s2} {t_s2}{fmt_d(d_s2)}{s2_note}</li></ul>')

    # ⑤ 可信度（筆數）
    n = cur_rule['all'].get('n') or 0
    if n > 300:   c_icon, c_txt = '🟢', '高'
    elif n >= 100: c_icon, c_txt = '🟡', '中等（排名容易變動，只看大方向）'
    else:          c_icon, c_txt = '🔴', '低（樣本太少，先別下結論）'

    # 🔬 最有用的進場條件
    fx = res.get('factors')
    fx_best, fx_worst = exf_best(fx)
    fx_good = bool(fx_best and fx['all']['none_pct'] - fx_best['none_pct'] >= EXF_GOOD_DIFF)
    if not fx:
        fx_block = '⚪ 這份是舊版結果，重跑一次回測才會有'
    elif fx_good:
        fx_block = (f'⭐ <b>{_h(fx_best["group"])}：{_h(fx_best["label"])}</b>'
                    f'<div class="exs-sub">這組 {fx_best["n"]} 筆，幾乎沒漲只有 {fx_best["none_pct"]:.0f}%（全部是 {fx["all"]["none_pct"]:.0f}%）'
                    f'・平均R {fx_best["best_r"]:+.2f}（用最好的出場）</div>' if fx_best.get('best_r') is not None else
                    f'⭐ <b>{_h(fx_best["group"])}：{_h(fx_best["label"])}</b>')
    else:
        fx_block = (f'❌ 沒有明顯有用的條件<div class="exs-sub">每一組的「幾乎沒漲」都跟全部（{fx["all"]["none_pct"]:.0f}%）差不到 '
                    f'{EXF_GOOD_DIFF:g} 個百分點</div>')
    if fx and fx_worst and fx_worst['none_pct'] - fx['all']['none_pct'] >= EXF_GOOD_DIFF:
        fx_block += (f'<div class="exs-sub">⚠️ 最該避開：{_h(fx_worst["group"])}「{_h(fx_worst["label"])}」'
                     f'（幾乎沒漲 {fx_worst["none_pct"]:.0f}%）</div>')

    # ⑥ 建議（依燈號組合）
    tips = []
    entry_bad = p_none is not None and p_none > EXS_MFE_BAD
    missing = _ex_compare_hint(res)
    if v_icon == '🟢':
        if cur_rule is best or b_avg - (c_avg or 0) < EXS_TIE_R:
            tips.append('這套進場＋現在的出場已經有優勢，維持不變，繼續累積樣本。')
        else:
            tips.append(f'這套進場有優勢。可以考慮把出場改成「{_h(best["name"])}」，先在突破卡片上紙上追蹤一段時間確認。')
    elif entry_bad:
        tips.append(f'先不要再調出場方式。約 {p_none:.0f}% 的突破進場後根本沒漲，出場怎麼改都救不回來；'
                    f'應該先改善進場篩選，等「幾乎沒漲」降到 {EXS_MFE_GOOD:.0f}% 以下，再回頭優化出場。')
        if fx_good:
            tips.append(f'下一步：試試只做「{_h(fx_best["group"])}：{_h(fx_best["label"])}」的突破'
                        f'（幾乎沒漲 {fx_best["none_pct"]:.0f}%）。先在突破卡片上紙上觀察，樣本夠了再正式加進過濾。')
        elif missing:
            tips.append('下一步：可以先比較 ' + '、'.join(missing) + ' 的結果，看進場品質有沒有比較好。')
        elif fx:
            tips.append('C1門檻、時間框架、目前這些條件都沒有明顯改善，可能要找其他進場確認方式'
                        '（例如等回踩確認再進場，而不是收盤一突破就進）。')
    elif v_icon == '🟡':
        tips.append(f'接近打平。進場品質不算差，出場可以用「{_h(best["name"])}」，'
                    '但扣掉手續費和滑價後優勢很薄，建議再加進場過濾提高勝率。')
    else:
        tips.append('進場後有漲，但最後沒賺到：可能是 SL 太緊被洗出去，或目標太遠。'
                    f'可以試試讓利潤多跑一點（例如「{_h(best["name"])}」），或檢查 SL 的位置。')
    if fx_good and not entry_bad:
        tips.append(f'加上「{_h(fx_best["group"])}：{_h(fx_best["label"])}」這個條件，幾乎沒漲可以從 '
                    f'{fx["all"]["none_pct"]:.0f}% 降到 {fx_best["none_pct"]:.0f}%，值得先紙上觀察。')
    if i_nc == '🟢':
        tips.append('「排除⚠️不追」有效：實際交易時，進場價高於 BO 太多的就不要追。')
    if i_s2 == '❌' and s2_share < 90:
        tips.append('「只看日線S2」沒有幫助，不用特別靠它過濾。')
    if c_icon != '🟢':
        tips.append(f'目前只有約 {n} 筆，資料再多一點（> 300 筆）結論會更可靠。')

    return f'''<div class="exs">
<div class="exs-title">📋 一眼看懂（{_h(res["tf"])}・C1 {res["c1"]}%）</div>
<div class="exs-row"><div class="exs-k">🚦 總評</div><div class="exs-v">{v_icon} <b>{v_txt}</b><div class="exs-sub">{v_sub}</div></div></div>
<div class="exs-row"><div class="exs-k">📏 進場品質</div><div class="exs-v">{m_icon} <b>{m_txt}</b>{mfe_block}</div></div>
<div class="exs-row"><div class="exs-k">🏆 最好的出場</div><div class="exs-v">{best_line}</div></div>
<div class="exs-row"><div class="exs-k">🔬 最有用的條件</div><div class="exs-v">{fx_block}</div></div>
<div class="exs-row"><div class="exs-k">🔍 過濾有沒有用</div><div class="exs-v">{filt_block}</div></div>
<div class="exs-row"><div class="exs-k">📊 可信度</div><div class="exs-v">{c_icon} {c_txt}<div class="exs-sub">約 {n} 筆完成的交易</div></div></div>
<div class="exs-tip"><b>💡 建議</b><ul class="exs-ul">{"".join(f"<li>{t}</li>" for t in tips)}</ul></div>
</div>'''

# ============================================================
# 🧱 威科夫「洗盤 → 真突破」（2026-10-26 從Bybit掃描器 scannerrailway.py 原封不動移植）
# 跟C系列／突破卡片分開，不需要C：區間（天花板、地板）→ 假跌破洗盤 → 突破前安靜 → 突破時大聲 → 回頭站得穩
# 所有門檻跟加密版一樣（Railway環境變數名稱也一樣，可以各自覆蓋）。只做多頭、只看日線。
# ============================================================
HEADROOM_PIVOT_LEN = int(os.environ.get('HEADROOM_PIVOT_LEN', 5))
HEADROOM_RECENT    = os.environ.get('HEADROOM_RECENT', '0') == '1'
HEADROOM_HARD      = os.environ.get('HEADROOM_HARD', '0') == '1'
HEADROOM_MIN_R     = float(os.environ.get('HEADROOM_MIN_R', 1.5))
STAGE_LABEL_MAP    = {0: '--', 1: 'S1', 2: 'S2', 3: 'S3⚠️', 4: 'S4'}

def cf_bars(df):
    return [{'o': float(o), 'h': float(h), 'l': float(l), 'c': float(c), 'v': float(v)}
            for o, h, l, c, v in zip(df['open'], df['high'], df['low'], df['close'], df['volume'])]

def cf_atr14(bars):
    if len(bars) < 15: return None
    trs = [max(bars[i]['h'] - bars[i]['l'], abs(bars[i]['h'] - bars[i-1]['c']), abs(bars[i]['l'] - bars[i-1]['c']))
           for i in range(1, len(bars))]
    atr = sum(trs[:14]) / 14
    for tr in trs[14:]:
        atr = (atr * 13 + tr) / 14        # Wilder平滑，跟TradingView的ATR一致
    return atr

def cf_pivots(bars, key, n, is_high):
    out = []
    for i in range(n, len(bars) - n):
        v = bars[i][key]
        w = [bars[j][key] for j in range(i - n, i + n + 1) if j != i]
        if (is_high and all(v >= x for x in w)) or (not is_high and all(v <= x for x in w)):
            out.append(i)
    return out
# ---- 牆的分級（2026-10-19，SMC「流動性有優先順序」）----
# A級＝硬牆（外部流動性）：碰過≥2次（等高點）、或碰的時候有大量、或是左右各WALL_MAJOR_LEN根日K的最高點（主要高點，而且沒被收盤突破過）
# B級＝軟牆（內部流動性）：只碰過一次、沒有大量的小高點／上影線，或曾被收盤突破過的主要高點
WALL_TOUCH_PCT  = float(os.environ.get('WALL_TOUCH_PCT', 1.5))   # 高點在牆 ±X% 以內算「碰到這道牆」
WALL_MAJOR_LEN  = int(os.environ.get('WALL_MAJOR_LEN', 20))      # 左右各幾根日K的最高點＝主要高點
WALL_BIGVOL     = float(os.environ.get('WALL_BIGVOL', 2.0))      # 碰牆那根K量 ≥ 50日均量幾倍＝大量
WALL_TAKEN_PCT  = float(os.environ.get('WALL_TAKEN_PCT', 2.0))   # 之後收盤高過牆 X% ＝ 這道牆已經被突破過
WALL_TOUCH_GAP  = int(os.environ.get('WALL_TOUCH_GAP', 5))      # 兩次碰牆之間至少隔幾根日K才算「碰過2次」（避免同一波連續幾天算成很多次）


def wall_levels(daily, entry, n=None):
    """回傳 Entry 上方的日線牆（由近到遠），每道牆附等級與原因。只做多頭方向。
    候選＝跟checklist一樣：左右各n根的日線擺動高點＋最近n根日K的高點。"""
    n = n or HEADROOM_PIVOT_LEN
    N = len(daily)
    if N < 30:
        return []
    cands = [(daily[i]['h'], i) for i in cf_pivots(daily, 'h', n, True) if daily[i]['h'] > entry]
    if HEADROOM_RECENT:
        cands += [(daily[i]['h'], i) for i in range(max(0, N - n), N) if daily[i]['h'] > entry]
    if not cands:
        return []
    tol = WALL_TOUCH_PCT / 100
    out = []
    for price, idx in sorted(set(cands)):
        lo, hi = price * (1 - tol), price * (1 + tol)
        touches, last, first, big = 0, -999, None, False
        for i in range(N):
            b = daily[i]
            if lo <= b['h'] <= hi and b['c'] < hi:
                if i - last >= WALL_TOUCH_GAP:
                    touches += 1
                if first is None:
                    first = i
                last = i
                if i >= 50:
                    ma = sum(x['v'] for x in daily[i - 50:i]) / 50
                    if ma > 0 and b['v'] >= ma * WALL_BIGVOL:
                        big = True
        win = daily[max(0, idx - WALL_MAJOR_LEN): idx + WALL_MAJOR_LEN + 1]
        # 主要高點：左右各 WALL_MAJOR_LEN 根都要有資料（最近才出現、右邊還沒走完的高點不算）
        major = price >= max(x['h'] for x in win) and idx - WALL_MAJOR_LEN >= 0 and idx + WALL_MAJOR_LEN < N
        taken = any(x['c'] > price * (1 + WALL_TAKEN_PCT / 100) for x in daily[idx + 1:])
        why = []
        if touches >= 2: why.append(f'碰過{touches}次')
        if big: why.append('碰牆時大量')
        if major: why.append(f'左右{WALL_MAJOR_LEN}天最高點')
        if taken: why.append('曾被收盤突破過')
        # 碰過≥2次或大量：硬牆（就算曾被短暫收盤突破，跌回來後反而多一批被套的追突破者）；
        # 只靠「主要高點」的：曾被收盤突破過就降成B級（流動性已被掃過）
        tier = 'A' if (touches >= 2 or big or (major and not taken)) else 'B'
        if not why: why.append('只碰過一次的小高點')
        age = N - 1 - (first if first is not None else idx)
        if age >= 30 and tier == 'A': why.append(f'約{age}天前形成')
        rec = {'price': price, 'tier': tier, 'why': '、'.join(why), 'touches': touches}
        # 跟前一道牆距離在 tol 以內：合併成同一個區，用比較低的價（最先碰到），等級取比較硬的
        if out and price <= out[-1]['price'] * (1 + tol):
            prev = out[-1]
            if tier == 'A' and prev['tier'] == 'B':
                prev['tier'] = 'A'; prev['why'] = rec['why']
            continue
        out.append(rec)
    return out


def wall_pick(levels, entry, r1):
    """從 wall_levels 的結果取出：最近的牆、最近的A級牆、最近的B級牆，和各自幾R"""
    rr = lambda w: None if (w is None or not r1 or r1 <= 0) else (w['price'] - entry) / r1
    near = levels[0] if levels else None
    a = next((w for w in levels if w['tier'] == 'A'), None)
    b = next((w for w in levels if w['tier'] == 'B'), None)
    return {'near': near, 'near_r': rr(near), 'a': a, 'a_r': rr(a), 'b': b, 'b_r': rr(b)}
def bt_wall(daily_bars, entry, include_recent=True):
    """跟enrich_signal()同一套「上方的牆」：進場價上方最近的日線擺動高點（左右各HEADROOM_PIVOT_LEN根），
    include_recent=True時再加上最近HEADROOM_PIVOT_LEN根日K的高點（checklist現在的做法）。"""
    n = HEADROOM_PIVOT_LEN
    lv = [daily_bars[i]['h'] for i in cf_pivots(daily_bars, 'h', n, True) if daily_bars[i]['h'] > entry]
    if include_recent:
        lv += [b['h'] for b in daily_bars[-n:] if b['h'] > entry]
    return min(lv) if lv else None
WY_RANGE_LENS        = [120, 90, 60, 45, 30, 20]   # 試哪些區間長度（日），越長越優先
WY_MAX_HEIGHT_PCT    = float(os.environ.get('WY_MAX_HEIGHT_PCT', 80))   # 區間高度上限：天花板 ÷ 地板 − 1（%）
WY_CEIL_TOUCH_PCT    = float(os.environ.get('WY_CEIL_TOUCH_PCT', 4))    # 高點在天花板 X% 以內算「碰過天花板」
WY_MIN_CEIL_TOUCHES  = int(os.environ.get('WY_MIN_CEIL_TOUCHES', 2))     # 天花板至少被碰過幾次（間隔≥5天）
WY_SPRING_MIN_PCT    = float(os.environ.get('WY_SPRING_MIN_PCT', 1))    # 洗盤：刺穿地板至少 X%
WY_SPRING_MAX_PCT    = float(os.environ.get('WY_SPRING_MAX_PCT', 15))   # 洗盤：刺穿地板最多 X%（再深就是真跌破）
WY_SPRING_RECOVER    = int(os.environ.get('WY_SPRING_RECOVER', 3))      # 洗盤：幾根K線內收回地板上方
# 2026-10-22 改：安靜＝突破前 WY_QUIET_WIN 天裡「最安靜的連續 WY_QUIET_RUN 天」均量 ÷ 那段之前的50日均量
# （原本是突破前整整10天的均量；洗盤後價格從地板走回天花板那段量本來就會放大，10天均量幾乎不可能 ≤ 0.8）
WY_QUIET_WIN         = int(os.environ.get('WY_QUIET_WIN', 15))          # 突破前看幾天
WY_QUIET_RUN         = int(os.environ.get('WY_QUIET_RUN', 5))           # 裡面找最安靜的連續幾天
WY_QUIET_DAYS        = WY_QUIET_WIN                                     # 舊名稱保留（其他地方用到）
WY_QUIET_MAX         = float(os.environ.get('WY_QUIET_MAX', 0.8))       # 最安靜那幾天均量 ÷ 50日均量 ≤ 此值＝安靜
WY_LOUD_MIN          = float(os.environ.get('WY_LOUD_MIN', 2.0))        # 突破當天量 ÷ 50日均量 ≥ 此值＝大聲
WY_LOUD_MAX          = float(os.environ.get('WY_LOUD_MAX', 20.0))       # 超過此值＝爆量異常（消息／拉盤，不是健康的突破）
WY_RETEST_VOL_MA_MAX = float(os.environ.get('WY_RETEST_VOL_MA_MAX', 1.5))  # 回踩期間均量 ÷ 突破前50日均量 ≤ 此值（避免突破量太大時「站穩」一定過）
WY_DATA_MIN_RATIO    = float(os.environ.get('WY_DATA_MIN_RATIO', 0.03)) # 前段成交量中位數 < 最近10天中位數 × 此值＝歷史量是空的（新合約），資料不足
WY_DATA_MAX_ZERO     = float(os.environ.get('WY_DATA_MAX_ZERO', 0.1))   # 前段零成交量的天數超過此比例＝資料不足
WY_LOUD_CLOSE_POS    = float(os.environ.get('WY_LOUD_CLOSE_POS', 0.5))  # 突破當天收盤在K線的位置 ≥ 此值（0＝最低、1＝最高）
WY_RECENT_DAYS       = int(os.environ.get('WY_RECENT_DAYS', 30))        # 只看最近幾天內發生的突破
WY_RETEST_NEAR_PCT   = float(os.environ.get('WY_RETEST_NEAR_PCT', 3))   # 回踩：低點來到天花板上方 X% 以內
WY_RETEST_TOL_PCT    = float(os.environ.get('WY_RETEST_TOL_PCT', 2))    # 回踩：容許刺穿天花板 X%（看收盤）
WY_RETEST_VOL_MAX    = float(os.environ.get('WY_RETEST_VOL_MAX', 0.7))  # 回踩期間均量 ÷ 突破當天量 ≤ 此值
WY_RETEST_MAX_DAYS   = int(os.environ.get('WY_RETEST_MAX_DAYS', 15))    # 回踩要在突破後幾天內發生（太久＝另一個故事）
WY_RETEST_MAX_DROP   = float(os.environ.get('WY_RETEST_MAX_DROP', 30))  # 從突破後高點回落超過 X%＝回踩太深（像買盤高潮後的自動回落）
WY_FAIL_CLOSE_PCT    = float(os.environ.get('WY_FAIL_CLOSE_PCT', 1))    # 收盤低於天花板 X% ＝ 跌回區間（假突破）
WY_RISK_MAX_ATR      = float(os.environ.get('WY_RISK_MAX_ATR', 2.0))    # SL距離超過幾倍日線ATR＝風險太大
WY_NEAR_CEIL_PCT     = float(os.environ.get('WY_NEAR_CEIL_PCT', 5))     # 🟡 價格離天花板 X% 以內才放進盯盤名單
WY_TG_ON             = menv('WY_TG', '1') == '1'              # 設成0就不推播
# KLSE版：不另外抓資料，跟著C系列主掃描（開市時間每小時＋17:40收盤後）一起跑：
#   用「已收盤日K」判斷階段（開市中＝到昨天為止，收盤後＝包含今天），所以一天內階段只會在收盤後變一次；
#   盯盤（🟡重點名單正在突破、🟠回踩到天花板、🟢觸發Entry／跌破SL）用今天還沒收完的K線，每小時一次。
WY_LOAD_TEXT         = f'{WY_LOUD_MIN:g} 倍均量、收在K線上半部'

WY_STATE = {'status': 'idle', 'progress': '', 'last_update': None, 'rows': [], 'errors': [],
            'run_date': None}
WY_LOCK = threading.Lock()
WY_ALERTED = {}            # (symbol, kind, 日期) -> True，同一件事一天只推一次
# 2026-10-23：每次掃描後把各幣的階段存檔（跟持倉清單同一個Volume資料夾），重新部署後的第一次掃描
# 也能跟上一次比較，新變成🟢／🟠的幣照樣推Telegram（原本重新部署後第一次掃描一律不推，會漏掉）
WY_STAGE_FILE = os.path.join(DATA_DIR, 'wyckoff_state.json')   # KLSE：存在Volume（/data）


def wy_load_stages():
    """讀上一次掃描的 {symbol: stage}；沒有檔案（第一次使用）回傳None"""
    import json
    try:
        with open(WY_STAGE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def wy_save_stages(stages):
    import json
    try:
        with open(WY_STAGE_FILE, 'w', encoding='utf-8') as f:
            json.dump(stages, f, ensure_ascii=False)
    except Exception as e:
        print(f'⚠️ 儲存威科夫階段紀錄失敗：{e}')
WY_STAGE_META = {
    'green':  ('🟢 三個條件全部符合', '#1b5e20'),
    'orange': ('🟠 已放量突破，等回踩', '#e65100'),
    'yellow': ('🟡 洗盤完成，還在區間', '#8d6e00'),
    'weak':   ('⚪ 突破了，但條件不全', '#455a64'),
    'fail':   ('❌ 突破後跌回區間', '#7f1d1d'),
    'nodata': ('⛔ 資料不足（成交量資料不夠／零成交日太多）', '#37474f'),
}
# 卡關統計用：每個 ⚪／⛔ 的原因代碼 → 顯示文字
WY_MISS_LABELS = {
    'quiet': '突破前不夠安靜',
    'loud_low': '突破量不夠（< %g 倍）',
    'loud_high': '爆量異常（> %g 倍，像拉盤）',
    'close_pos': '突破當天收在K線下半部',
    'retest_late': '回踩太晚（> %d 天）',
    'retest_deep': '回踩太深（> %g%%）',
    'no_retest': '突破後 %d 天還沒回踩',
    'high_pos': '漲後高位（可能是出貨）',
    'nodata': '成交量資料不足（零成交日太多／新上市）',
}


def wy_vol_ma(bars, end, n=50):
    """end之前（不含end）的n根平均量"""
    lo = max(0, end - n)
    seg = bars[lo:end]
    return sum(b['v'] for b in seg) / len(seg) if seg else 0


def wy_quiet(bars, end):
    """突破前（end之前）WY_QUIET_WIN 天裡，最安靜的連續 WY_QUIET_RUN 天：
    回傳 (那幾天均量 ÷ 這段之前的50日均量, 最安靜那段的起點index)；算不出來回傳 (None, None)"""
    lo = end - WY_QUIET_WIN
    if lo < 50 or WY_QUIET_RUN > WY_QUIET_WIN:
        return None, None
    ma50 = wy_vol_ma(bars, lo)
    if not ma50:
        return None, None
    best, best_i = None, None
    for i in range(lo, end - WY_QUIET_RUN + 1):
        avg = sum(x['v'] for x in bars[i:i + WY_QUIET_RUN]) / WY_QUIET_RUN
        if best is None or avg < best:
            best, best_i = avg, i
    return best / ma50, best_i


def wy_data_check(bars):
    """歷史成交量是不是真的（新合約上線前的K線常常幾乎沒量，算出來的倍數會失真，例如 RSR 252倍）。
    比較「前段」（最近120天到最近20天）和「最近10天」的成交量中位數。回傳 (ok, 原因)"""
    prior = sorted(b['v'] for b in bars[-120:-20])
    recent = sorted(b['v'] for b in bars[-10:])
    if len(prior) < 50 or not recent:
        return False, '日線K線太少'
    zero = sum(1 for v in prior if v <= 0)
    if zero > len(prior) * WY_DATA_MAX_ZERO:
        return False, f'前段有 {zero} 天零成交量'
    pm = prior[len(prior) // 2]
    rm = recent[len(recent) // 2]
    if rm > 0 and pm < rm * WY_DATA_MIN_RATIO:
        return False, f'前段成交量中位數只有最近10天的 {pm / rm:.1%}'
    return True, ''


def wy_find_spring(bars, s0, e):
    """在區間 [s0, e) 的後70%裡找最後一次假跌破洗盤。回傳dict或None。
    地板＝洗盤之前的區間最低價；洗盤＝低點刺穿地板WY_SPRING_MIN~MAX%，WY_SPRING_RECOVER根內收盤收回地板上方，
    而且之後到e為止沒有再跌破洗盤低點。"""
    first = s0 + max(10, int((e - s0) * 0.3))
    best = None
    support = min(b['l'] for b in bars[s0:first])
    for s in range(first, e):
        if s > first:
            support = min(support, bars[s - 1]['l'])   # 洗盤之前的區間最低價（逐根更新，避免重算）
        low = bars[s]['l']
        depth = (support - low) / support * 100
        if depth < WY_SPRING_MIN_PCT or depth > WY_SPRING_MAX_PCT:
            continue
        rec = None
        for k in range(s, min(e, s + WY_SPRING_RECOVER + 1)):
            if bars[k]['c'] > support:
                rec = k
                break
        if rec is None:
            continue
        if any(b['l'] < low for b in bars[s + 1:e]):
            continue
        ma = wy_vol_ma(bars, s)
        best = {'i': s, 'low': low, 'support': support, 'depth': depth, 'recover_bars': rec - s,
                'vol_mult': (bars[s]['v'] / ma) if ma else None}
    return best


def wy_ceiling_touches(bars, s0, e, ceiling):
    touches, last = 0, -999
    for i in range(s0 + 5, e):              # 區間最前面5根不算（避免把前面一段下跌的高點當成天花板）
        if bars[i]['h'] >= ceiling * (1 - WY_CEIL_TOUCH_PCT / 100):
            if i - last >= 5:
                touches += 1
            last = i
    return touches


def wy_valid_range(bars, s0, e):
    """區間 [s0, e) 是否像一個有洗盤的橫盤；是就回傳 (ceiling, floor, spring)"""
    if s0 < 55 or e - s0 < 20:
        return None
    seg = bars[s0:e]
    ceiling = max(b['h'] for b in seg)
    spring = wy_find_spring(bars, s0, e)
    if not spring:
        return None
    floor = spring['support']
    if floor <= 0 or (ceiling / floor - 1) * 100 > WY_MAX_HEIGHT_PCT:
        return None
    if wy_ceiling_touches(bars, s0, e, ceiling) < WY_MIN_CEIL_TOUCHES:
        return None
    return ceiling, floor, spring


def wy_position(bars, s0):
    """區間開始前的60天，是跌下來還是漲上來"""
    if s0 < 61:
        return '—'
    chg = (bars[s0]['c'] / bars[s0 - 60]['c'] - 1) * 100
    if chg <= -15:
        return '跌後（吸籌）'
    if chg >= 50:
        return '漲後高位（小心出貨）'
    return '中途整理'


def wy_analyze(symbol, ddf):
    """wy_analyze_core 外面加一層「資料足夠」檢查：有結果但歷史成交量是空的 → 改成 ⛔ 資料不足"""
    r = wy_analyze_core(symbol, ddf)
    if r:
        ok, why = wy_data_check(cf_bars(ddf))   # KLSE：傳進來的已經全是收盤K
        if not ok:
            r['orig_stage'] = r['stage']
            r['stage'] = 'nodata'
            r['miss'] = ['nodata']
            r['note'] = f'資料不足：{why}。量比（安靜／大聲／站穩）都會失真，不判斷，自己看圖。'
    return r


def wy_analyze_core(symbol, ddf):
    """回傳一列結果或None。KLSE版：ddf＝只含已收盤日K的DataFrame（呼叫前已用closed_bars去掉今天還沒收完的K線）。"""
    allbars = cf_bars(ddf)
    bars = allbars                         # 全部都是已收盤的日K
    dates = list(ddf.index)
    n = len(bars)
    if n < 120:
        return None
    T = n - 1
    atr = cf_atr14(bars) or 0

    def eval_bo(b, s0, ceiling, floor, spring):
        """評估一次突破：回傳一列結果（stage＝green/orange/weak/fail）"""
        quiet_ratio, quiet_i = wy_quiet(bars, b)
        bo = bars[b]
        ma_b = wy_vol_ma(bars, b)
        loud_mult = bo['v'] / ma_b if ma_b else None
        rng = bo['h'] - bo['l']
        close_pos = (bo['c'] - bo['l']) / rng if rng > 0 else 1
        quiet_ok = quiet_ratio is not None and quiet_ratio <= WY_QUIET_MAX
        loud_big = loud_mult is not None and loud_mult > WY_LOUD_MAX
        loud_ok = (loud_mult is not None and WY_LOUD_MIN <= loud_mult <= WY_LOUD_MAX
                   and close_pos >= WY_LOUD_CLOSE_POS)
        after = bars[b + 1:T + 1]
        row = {'symbol': symbol, 'ceiling': ceiling, 'floor': floor, 'range_days': b - s0,
               'range_from': dates[s0].strftime('%m/%d'), 'position': wy_position(bars, s0),
               'spring_date': dates[spring['i']].strftime('%m/%d'), 'spring_low': spring['low'],
               'spring_depth': spring['depth'], 'spring_vol': spring['vol_mult'],
               'bo_date': dates[b].strftime('%m/%d'), 'bo_days_ago': T - b,
               'quiet_ratio': quiet_ratio, 'quiet_ok': quiet_ok,
               'quiet_from': dates[quiet_i].strftime('%m/%d') if quiet_i is not None else None,
               'loud_mult': loud_mult, 'loud_close_pos': close_pos, 'loud_ok': loud_ok, 'loud_big': loud_big,
               'retest_ok': False, 'price': bars[T]['c'], 'atr': atr, 'miss': []}
        # 跌回區間＝假突破
        if any(x['c'] < ceiling * (1 - WY_FAIL_CLOSE_PCT / 100) for x in after):
            row['stage'] = 'fail'
            row['note'] = '突破後收盤跌回天花板下面：假突破誘多。刪掉。'
            return row
        # 回踩：突破後的最低點有沒有回到天花板附近、收盤都守住
        retest = None
        if after:
            ri = min(range(b + 1, T + 1), key=lambda i: bars[i]['l'])
            rl = bars[ri]['l']
            peak_i = max(range(b, ri + 1), key=lambda i: bars[i]['h'])
            if rl <= ceiling * (1 + WY_RETEST_NEAR_PCT / 100) and rl >= ceiling * (1 - WY_RETEST_TOL_PCT / 100) and ri > peak_i:
                pull = bars[peak_i + 1:ri + 1]
                pull_vol = sum(x['v'] for x in pull) / len(pull) if pull else None
                vol_ratio = pull_vol / bo['v'] if (pull_vol and bo['v']) else None
                vol_ma_ratio = pull_vol / ma_b if (pull_vol and ma_b) else None
                confirmed = ri < T                      # 回踩低點之後至少還有一根K線沒破低
                peak_h = bars[peak_i]['h']
                retest = {'i': ri, 'low': rl, 'vol_ratio': vol_ratio, 'vol_ma_ratio': vol_ma_ratio, 'confirmed': confirmed,
                          'pierced': rl < ceiling, 'days': ri - b, 'peak': peak_h,
                          'drop': (peak_h - rl) / peak_h * 100}
        if retest:
            row['retest_low'] = retest['low']
            row['retest_date'] = dates[retest['i']].strftime('%m/%d')
            row['retest_vol'] = retest['vol_ratio']
            row['retest_vol_ma'] = retest['vol_ma_ratio']
            row['retest_ok'] = (retest['confirmed']
                                and retest['vol_ratio'] is not None and retest['vol_ratio'] <= WY_RETEST_VOL_MAX
                                and retest['vol_ma_ratio'] is not None and retest['vol_ma_ratio'] <= WY_RETEST_VOL_MA_MAX)
        if not (quiet_ok and loud_ok):
            row['stage'] = 'weak'
            miss = []
            if not quiet_ok:
                miss.append('突破前不夠安靜'); row['miss'].append('quiet')
            if not loud_ok:
                if loud_big:
                    miss.append(f'突破當天爆量 {loud_mult:.0f} 倍（上限 {WY_LOUD_MAX:g} 倍），比較像消息或拉盤，不是健康的突破')
                    row['miss'].append('loud_high')
                elif (loud_mult or 0) < WY_LOUD_MIN:
                    miss.append('突破時不夠大聲'); row['miss'].append('loud_low')
                else:
                    miss.append('突破當天收在K線下半部（上影線長）'); row['miss'].append('close_pos')
            row['note'] = '、'.join(miss) + '。容易是假突破，只觀察。'
            return row
        # 回踩太晚或太深：不是「突破後小幅回頭測試」，而是整段漲幅吐回去
        if retest and (retest['days'] > WY_RETEST_MAX_DAYS or retest['drop'] > WY_RETEST_MAX_DROP):
            row['retest_ok'] = False
            row['stage'] = 'weak'
            why = []
            if retest['drop'] > WY_RETEST_MAX_DROP:
                row['miss'].append('retest_deep')
                why.append(f'從突破後高點 {fmt_px(retest["peak"])} 回落了 {retest["drop"]:.0f}%（上限 {WY_RETEST_MAX_DROP:g}%）')
            if retest['days'] > WY_RETEST_MAX_DAYS:
                row['miss'].append('retest_late')
                why.append(f'突破後第 {retest["days"]} 天才回到天花板（上限 {WY_RETEST_MAX_DAYS} 天）')
            row['note'] = ('回踩太深／太晚：' + '、'.join(why) + '。比較像買盤高潮後的自動回落，不是回踩確認。'
                           '等舊天花板附近重新縮量守住、形成新的結構再看。')
            return row
        if not retest and row['bo_days_ago'] > WY_RETEST_MAX_DAYS:
            row['stage'] = 'weak'
            row['miss'].append('no_retest')
            row['note'] = f'突破已經 {row["bo_days_ago"]} 天還沒回踩（上限 {WY_RETEST_MAX_DAYS} 天）。之後再回到天花板，已經不算這次突破的回踩。'
            return row
        if not retest:
            row['stage'] = 'orange'
            row['note'] = f'已放量突破 {row["bo_days_ago"]} 天，還沒回踩到天花板附近。不追，等回踩。'
            return row
        if not row['retest_ok']:
            row['stage'] = 'orange'
            if not retest['confirmed']:
                row['note'] = '回踩中，還沒確認守住（回踩低點後還沒有收盤K線）。'
            else:
                vr, vm = retest['vol_ratio'], retest['vol_ma_ratio']
                row['note'] = (f'回踩到天花板，但回踩的量太大（突破當天量的 {(vr or 0):.0%}、平常量的 {(vm or 0):.1f} 倍；'
                               f'要 ≤ {WY_RETEST_VOL_MAX:.0%} 而且 ≤ {WY_RETEST_VOL_MA_MAX:g} 倍），還不算站穩。')
            return row
        # 漲後高位的區間：可能是出貨，不給🟢
        if row['position'].startswith('漲後'):
            row['stage'] = 'weak'
            row['miss'].append('high_pos')
            row['note'] = '三個條件都過了，但區間在大漲之後（漲後高位），可能是出貨區。不給 🟢，只觀察。'
            return row
        # ---- 🟢：給 Entry / SL / 上方空間 ----
        ri = retest['i']
        bounce_high = max(x['h'] for x in bars[ri:T + 1])
        entry = bounce_high * 1.005
        sl = retest['low'] * 0.995
        r1 = entry - sl
        wall = bt_wall(bars, entry, include_recent=HEADROOM_RECENT)
        pk = wall_pick(wall_levels(bars, entry), entry, entry - sl)
        tps = sorted({bars[i]['h'] for i in cf_pivots(bars, 'h', HEADROOM_PIVOT_LEN, True) if bars[i]['h'] > entry})[:3]
        row.update({'stage': 'green', 'entry': entry, 'sl': sl, 'r1': r1, 'wall': wall,
                    'wall_r': (wall - entry) / r1 if (wall and r1 > 0) else None,
                    'tps': tps, 'risk_atr': r1 / atr if atr else None,
                    'wall_tier': pk['near']['tier'] if pk['near'] else '', 'wall_why': pk['near']['why'] if pk['near'] else '',
                    'wallA': pk['a']['price'] if pk['a'] else None, 'wallA_r': pk['a_r']})
        notes = ['回踩刺穿天花板後收回' if retest['pierced'] else '回踩守在天花板上面']
        if row['wall_r'] is not None and row['wall_r'] < HEADROOM_MIN_R:
            notes.append(f'上方空間只有 {row["wall_r"]:.2f}R，不到 {HEADROOM_MIN_R}R，' + ('不做' if HEADROOM_HARD else '參考：碰牆時看量，可考慮到牆先平一半'))
        if row['risk_atr'] and row['risk_atr'] > WY_RISK_MAX_ATR:
            notes.append(f'SL 距離 {row["risk_atr"]:.1f} 倍日線ATR，風險太大：改到 4H／1H 找 C 進場')
        if bars[T]['c'] > entry:
            notes.append('現價已在 Entry 上面，不追：等下一次回踩')
        row['note'] = '；'.join(notes) + '。'
        return row

    # ---- A：最近 WY_RECENT_DAYS 天內「第一次收盤突破區間天花板」的日子（由舊到新） ----
    cands = []
    for b in range(max(T - WY_RECENT_DAYS, 60), T + 1):
        if bars[b]['c'] <= max(x['h'] for x in bars[b - 20:b]):
            continue                        # 連最近20天高點都沒站上，不可能是區間突破
        for L in WY_RANGE_LENS:
            s0 = b - L
            r = wy_valid_range(bars, s0, b)
            if r and bars[b]['c'] > r[0] and not (bars[b - 1]['c'] > r[0]):
                cands.append((b, s0, r))
                break
    # 由舊到新評估：舊的突破如果已經失敗（跌回區間），就看之後有沒有新的突破；全部失敗就回報最後一次失敗
    last_fail = None
    for b, s0, (ceiling, floor, spring) in cands:
        row = eval_bo(b, s0, ceiling, floor, spring)
        if row['stage'] != 'fail':
            return row
        last_fail = row
    if last_fail and last_fail['bo_days_ago'] <= 10:
        return last_fail                   # 最近10天內的假突破才列出來提醒

    # ---- B：還沒突破：區間裡有洗盤、最近量縮 → 🟡 ----
    for L in WY_RANGE_LENS:
        s0 = T + 1 - L
        r = wy_valid_range(bars, s0, T + 1)
        if not r:
            continue
        ceiling, floor, spring = r
        if bars[T]['c'] > ceiling:
            continue
        if T - spring['i'] > 45:            # 洗盤太久以前，跟現在關係不大
            continue
        quiet_ratio, quiet_i = wy_quiet(bars, T + 1)
        dist = (ceiling / bars[T]['c'] - 1) * 100
        return {'symbol': symbol, 'stage': 'yellow', 'ceiling': ceiling, 'floor': floor, 'range_days': L,
                'range_from': dates[s0].strftime('%m/%d'), 'position': wy_position(bars, s0),
                'spring_date': dates[spring['i']].strftime('%m/%d'), 'spring_low': spring['low'],
                'spring_depth': spring['depth'], 'spring_vol': spring['vol_mult'],
                'quiet_ratio': quiet_ratio, 'quiet_ok': quiet_ratio is not None and quiet_ratio <= WY_QUIET_MAX,
                'quiet_from': dates[quiet_i].strftime('%m/%d') if quiet_i is not None else None, 'miss': [],
                'loud_ok': False, 'retest_ok': False, 'price': bars[T]['c'], 'dist_pct': dist, 'atr': atr,
                'note': (f'離天花板 {dist:.1f}%。' + ('量在縮，' if (quiet_ratio or 9) <= WY_QUIET_MAX else '量還沒縮，')
                         + '等放量收盤突破 ' + f'{fmt_px(ceiling)}。')}
    return None


# ---------------- KLSE 接線：跟著C系列主掃描一起跑，不另外抓Yahoo資料 ----------------
wy_rows_pending = []

def send_telegram_plain(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if not text.startswith(M['flag']):
        text = f"{M['flag']} {text}"   # 同一個Telegram收好幾個市場：每則前面加國旗
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      json={'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'disable_web_page_preview': True}, timeout=10)
        return True
    except Exception as e:
        log.warning(f"🧱 威科夫 Telegram 發送失敗：{e}")
        return False

def wy_alert_once(sym, kind, text):
    key = (sym, kind, datetime.now(MY_TZ).strftime('%Y-%m-%d'))
    if key in WY_ALERTED:
        return
    WY_ALERTED[key] = True
    if WY_TG_ON:
        send_telegram_plain(text)

def _wy_label(r):
    return label_of(r.get('name'), r['symbol'])

def wy_scan_begin():
    wy_rows_pending.clear()
    wy_case_events.clear()
    with WY_LOCK:
        WY_STATE.update({'status': 'running', 'progress': '跟著C系列掃描中', 'errors': []})

def wy_process_symbol(meta, df_daily):
    """scan_symbol()抓到日線後呼叫：1)用已收盤日K判斷階段 2)今天K線還沒收完時，順便盯盤（每小時一次）"""
    sym = meta['symbol']
    meta['wy_stage'] = None
    try:
        closed = closed_bars(df_daily, '1D')
        if len(closed) < 121:
            return
        ddf = closed.tail(500)                     # 跟加密版一樣用最近500根日K
        r = wy_analyze(sym, ddf)
        if not r:
            try:
                wy_track_live(meta, ddf, None)     # 📊 進行中的案例照樣要追
            except Exception as e:
                log.warning(f"📊 追蹤 {sym}: {e}")
            return
        try:
            st, _, _ = get_stage(ddf)
        except Exception:
            st = 0
        r['day_stage'] = STAGE_LABEL_MAP.get(st, '--')
        r['redist'] = (st == 4 and r['position'] == '中途整理')
        if r['redist']:
            r['note'] = '⚠️ 日線S4、下跌途中的橫盤，小心是再派發（中途再出一次貨，之後繼續跌）。' + r.get('note', '')
        r['focus'] = (r['stage'] == 'yellow' and r.get('dist_pct', 99) <= WY_NEAR_CEIL_PCT
                      and r.get('quiet_ok') and not r['redist'])
        r.update({'name': meta.get('name'), 'sector': meta.get('sector'), 'tv_symbol': meta.get('tv_symbol'),
                  'turnover': meta.get('turnover'), 'liquid': wy_liquid(meta.get('turnover'))})
        wy_rows_pending.append(r)
        meta['wy_stage'] = r['stage']            # 🧱 給突破卡片顯示燈號
        try:
            wy_track_live(meta, ddf, r)            # 📊 🟢 結果追蹤
        except Exception as e:
            log.warning(f"📊 追蹤 {sym}: {e}")
        if len(df_daily) > len(closed):            # 今天的日K還沒收完 → 盯盤
            wy_monitor_row(r, df_daily)
    except Exception as e:
        with WY_LOCK:
            WY_STATE['errors'].append(f'{sym}: {type(e).__name__}: {e}')

def wy_liquid(turnover):
    """成交額門檻跟C系列「可開單」同一個（TG_MIN_TURNOVER_MYR）：網頁照樣顯示，Telegram只推夠的"""
    return turnover is not None and turnover >= TG_MIN_TURNOVER_MYR

def wy_monitor_row(r, df_daily):
    """跟加密版 wy_monitor_once 同一套提醒，只是一次看一檔、用主掃描已經抓好的日線"""
    if not r.get('liquid'):
        return   # 成交額不足：不盯盤、不推
    if not (r['stage'] in ('green', 'orange') or (r['stage'] == 'yellow' and r.get('focus'))):
        return
    bars = cf_bars(df_daily.tail(60))
    if len(bars) < 52:
        return
    today = bars[-1]
    ma50 = wy_vol_ma(bars, len(bars) - 1)
    vol_mult = today['v'] / ma50 if ma50 else 0
    px = today['c']
    c = r['ceiling']
    sym = r['symbol']; lab = _wy_label(r)
    if r['stage'] == 'yellow' and px > c:
        wy_alert_once(sym, 'breaking', f'🟡→ {lab} 正在突破天花板 {fmt_px(c)}（現價 {fmt_px(px)}，今天量已是均量 {vol_mult:.1f} 倍）。'
                                       f'K線還沒收完，等日線收盤確認：要收在天花板上面、量 ≥ {WY_LOAD_TEXT}。')
    elif r['stage'] == 'orange' and today['l'] <= c * (1 + WY_RETEST_NEAR_PCT / 100) and r.get('loud_ok'):
        wy_alert_once(sym, 'retest', f'🟠 {lab} 回踩到天花板 {fmt_px(c)} 附近（今天低點 {fmt_px(today["l"])}）。'
                                     f'去看小時圖：縮量守住、不收回區間裡，才算站得穩。')
    elif r['stage'] == 'green':
        if today['h'] >= r['entry']:
            wy_alert_once(sym, 'entry', f'🟢 {lab} 觸發 Entry {fmt_px(r["entry"])}（SL {fmt_px(r["sl"])}）。下單前用 checklist 再確認一次。')
        if today['l'] <= r['sl']:
            wy_alert_once(sym, 'stop', f'❌ {lab} 跌破 SL {fmt_px(r["sl"])}（回踩低點 −0.5%）：「回頭站得穩」不成立。掛單取消，持倉照計劃出場。')

WY_SUMMARY_FLAG = os.path.join(DATA_DIR, 'wyckoff_summary_sent.txt')

def _wy_green_line(r):
    wr = f'{r["wall_r"]:.2f}R' if r.get('wall_r') is not None else '藍天'
    over = '（現價已過Entry，不追）' if r.get('price') and r['price'] > r['entry'] else ''
    return f'🟢 {_wy_label(r)}  Entry {fmt_px(r["entry"])}  SL {fmt_px(r["sl"])}  上方空間 {wr}{over}'

def _wy_orange_line(r):
    return f'🟠 {_wy_label(r)}  {r["bo_date"]} 放量突破 {fmt_px(r["ceiling"])}（{r["loud_mult"]:.1f}倍量），等回踩'

def wy_summary_text(rows, title):
    cand   = [r for r in rows if r['stage'] in ('green', 'orange') or (r['stage'] == 'yellow' and r.get('focus'))]
    thin   = [r for r in cand if not r.get('liquid')]
    green  = [r for r in cand if r['stage'] == 'green' and r.get('liquid')]
    orange = [r for r in cand if r['stage'] == 'orange' and r.get('liquid')]
    focus  = [r for r in cand if r['stage'] == 'yellow' and r.get('liquid')]
    lines = [f'【{M["name"]}威科夫 {title}】', datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')]
    lines.append(f'━━ 🟢 三個條件全部符合（{len(green)}）')
    lines += [_wy_green_line(r) for r in green] or ['沒有']
    lines.append(f'━━ 🟠 已放量突破，等回踩（{len(orange)}）')
    lines += [_wy_orange_line(r) for r in orange] or ['沒有']
    _every = '每小時' if M['scan_every_min'] >= 60 else f"每{M['scan_every_min']}分鐘"
    lines.append(f'━━ 🟡 重點名單（{len(focus)}）：{_every}盯盤，突破時會推')
    lines += [f'🟡 {_wy_label(r)}  離天花板 {fmt_px(r["ceiling"])} 還差 {r.get("dist_pct", 0):.1f}%' for r in focus] or ['沒有']
    if thin:
        lines.append(f'💧 成交額<{_fmt_turnover(TG_MIN_TURNOVER_MYR)}未列：' + '、'.join(_wy_label(r) for r in thin))
    lines.append(f'📄 {KLSE_URL}/wyckoff')
    return '\n'.join(lines)

def wy_scan_finish():
    """主掃描跑完後：整理名單、跟上一次比較，新變成🟢／🟠的推Telegram（跟加密版每日摘要一樣）"""
    rows = list(wy_rows_pending)
    order = {'green': 0, 'orange': 1, 'yellow': 2, 'weak': 3, 'fail': 4, 'nodata': 5}
    rows.sort(key=lambda r: (order[r['stage']], not r.get('focus'), r.get('dist_pct', 0) if r['stage'] == 'yellow' else -(r.get('loud_mult') or 0)))
    with WY_LOCK:
        if WY_STATE['rows']:
            prev, have_prev = {r['symbol']: r['stage'] for r in WY_STATE['rows']}, True
        else:
            saved = wy_load_stages()
            prev, have_prev = (saved or {}), saved is not None
        WY_STATE.update({'rows': rows, 'status': 'done', 'progress': '',
                         'last_update': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'),
                         'run_date': datetime.now(MY_TZ).strftime('%Y-%m-%d')})
    new_green = [r for r in rows if r['stage'] == 'green' and prev.get(r['symbol']) != 'green' and r.get('liquid')]
    new_orange = [r for r in rows if r['stage'] == 'orange' and prev.get(r['symbol']) not in ('orange', 'green') and r.get('liquid')]
    wy_save_stages({r['symbol']: r['stage'] for r in rows})
    wy_cases_save()
    try:
        wy_send_case_results()
    except Exception as e:
        log.warning(f"📊 威科夫結果推播失敗：{e}")
    summary_due = (not have_prev) or (not os.path.exists(WY_SUMMARY_FLAG))
    if summary_due:
        # 第一輪（或這個版本第一次部署）：推一則「目前名單」摘要，之後才只推新的
        if WY_TG_ON:
            send_telegram_plain(wy_summary_text(rows, '目前名單（首次）'))
        try:
            with open(WY_SUMMARY_FLAG, 'w', encoding='utf-8') as f:
                f.write(datetime.now(MY_TZ).isoformat())
        except Exception as e:
            log.warning(f'🧱 寫入威科夫摘要旗標失敗：{e}')
        log.info('🧱 威科夫：已推送首次目前名單摘要')
    elif WY_TG_ON and (new_green or new_orange):
        lines = [f'【{M["name"]}威科夫 洗盤→真突破】']
        for r in new_green:
            lines.append(_wy_green_line(r))
        for r in new_orange:
            lines.append(_wy_orange_line(r))
        send_telegram_plain('\n'.join(lines))


def wy_funnel_html(rows):
    """卡關統計：⚪ 和 ⛔ 各卡在哪一關（一隻幣可能同時卡好幾關）"""
    if not rows:
        return ''
    cnt = {}
    for r in rows:
        if r['stage'] in ('weak', 'nodata'):
            for k in r.get('miss') or []:
                cnt[k] = cnt.get(k, 0) + 1
    stages = {k: sum(1 for r in rows if r['stage'] == k) for k in WY_STAGE_META}
    fmt = {'loud_low': WY_LOUD_MIN, 'loud_high': WY_LOUD_MAX, 'retest_late': WY_RETEST_MAX_DAYS,
           'retest_deep': WY_RETEST_MAX_DROP, 'no_retest': WY_RETEST_MAX_DAYS}
    items = []
    for k, label in WY_MISS_LABELS.items():
        if cnt.get(k):
            items.append(f'{label % fmt[k] if k in fmt else label}：<b>{cnt[k]}</b>')
    head = '｜'.join(f'{WY_STAGE_META[k][0].split(" ")[0]} {v}' for k, v in stages.items())
    body = '、'.join(items) if items else '沒有'
    return (f'<p class=note style="background:#22223f;padding:8px 12px;border-radius:6px">📊 <b>卡關統計</b>　{head}<br>'
            f'⚪／⛔ 卡在哪一關（一隻幣可能卡好幾關）：{body}</p>')


def wy_green_rules_html():
    """🟢 的完整條件（數字直接讀目前的門檻設定，改了Railway變數這裡會跟著變）"""
    return (
        '<div class=note style="background:#1f2b22;border:1px solid #2e5a3a;padding:10px 14px;border-radius:6px;margin:4px 0 10px">'
        '<b>🟢 要全部符合：</b><ol style="margin:6px 0 0;padding-left:20px">'
        f'<li><b>前提：有區間、有洗盤</b>：橫盤 20～120 天、天花板被碰過 ≥ {WY_MIN_CEIL_TOUCHES} 次、高度 ≤ {WY_MAX_HEIGHT_PCT:g}%；'
        f'區間後段有一次假跌破，刺穿地板 {WY_SPRING_MIN_PCT:g}～{WY_SPRING_MAX_PCT:g}%，{WY_SPRING_RECOVER} 根K線內收盤收回地板上方，之後沒再破低。</li>'
        f'<li><b>突破前安靜</b>：突破前 {WY_QUIET_WIN} 天裡最安靜的連續 {WY_QUIET_RUN} 天，均量 ≤ {WY_QUIET_MAX:g} × 50日均量。</li>'
        f'<li><b>突破時大聲</b>：日線收盤站上天花板，當天量 {WY_LOUD_MIN:g}～{WY_LOUD_MAX:g} × 50日均量，收在K線上半部'
        f'（超過 {WY_LOUD_MAX:g} 倍＝爆量異常，像消息或拉盤）。</li>'
        f'<li><b>回頭站得穩</b>：突破後 {WY_RETEST_MAX_DAYS} 天內回踩到天花板上方 {WY_RETEST_NEAR_PCT:g}% 以內'
        f'（容許刺穿 {WY_RETEST_TOL_PCT:g}%，看收盤）、從突破後高點回落 ≤ {WY_RETEST_MAX_DROP:g}%、'
        f'回踩量 ≤ 突破當天 {WY_RETEST_VOL_MAX:.0%} 而且 ≤ 平常量 {WY_RETEST_VOL_MA_MAX:g} 倍、回踩低點之後至少一根K線沒再破低。</li>'
        '<li><b>不是「漲後高位」</b>：區間開始前 60 天漲超過 50% 的，三個條件都過也只放 ⚪（可能是出貨區）。</li>'
        '</ol>'
        '<div style="margin-top:8px"><b>變 🟢 之後，動手前再看：</b>'
        'Entry＝回踩後反彈高點 +0.5%、SL＝回踩低點 −0.5%；'
        f'上方空間 ≥ {HEADROOM_MIN_R:g}R（參考）；SL 距離 ≤ {WY_RISK_MAX_ATR:g} 倍日線ATR（太寬就改到 4H／1H 找 C 進場）；'
        '現價已經過了 Entry 就不追，等下一次回踩。日線S4的吸籌突破，大趨勢還沒確認，倉位要小。</div>'
        '</div>')


# ============================================================
# 📊 威科夫 🟢 結果追蹤（MH 2026-10-28）
# 規則（跟突破卡片同一套出場，方便跟VCP比較）：
#   🟢 出現 → 等觸發：之後某根日K高點 ≥ Entry 就算成交（開盤就跳空高過Entry，用開盤價成交）
#   等觸發期間：每天照最新的 🟢 更新 Entry/SL（跟你移動掛單一樣）；先跌破SL → 作廢；WY_TRIGGER_DAYS 根內沒觸發 → 沒觸發
#   成交後：R = 成交價 − SL；碰SL → −1R；達 1:1.5 → +1.5R；WY_HOLD_DAYS 根都沒碰到 → 到期（用收盤價算R）
#   同一根K線又碰SL又碰目標 → 保守算止損；🟢 出現時現價已經在 Entry 上面 → 照規則「不追」，記為沒追
# 作廢／沒觸發／沒追 都不算勝負，只計數。
# ============================================================
from bisect import bisect_right as _wy_bisect
WY_TRIGGER_DAYS  = int(menv('WY_TRIGGER_DAYS', '10'))
WY_HOLD_DAYS     = int(menv('WY_HOLD_DAYS', '20'))
WY_TP_R          = 1.5
WY_BACKFILL_DAYS = int(menv('WY_BACKFILL_DAYS', '20'))
WY_CASES_FILE    = os.path.join(DATA_DIR, 'wyckoff_cases.json')
WY_BT_FILE       = os.path.join(DATA_DIR, 'wyckoff_backtest.json')
WY_BT_DAYS       = int(menv('WY_BT_DAYS', '500'))     # 回測最近幾根日K（500 ≈ 2年，跟C1回測一樣）
wy_cases_lock    = threading.Lock()
wy_case_events   = []

def _wy_new_state():
    return {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'seen': {}}

wy_cases = _wy_new_state()

def wy_cases_load():
    global wy_cases
    try:
        if os.path.exists(WY_CASES_FILE):
            with open(WY_CASES_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            base = _wy_new_state(); base.update(d); wy_cases = base
            log.info(f"📊 威科夫追蹤：等觸發{len(wy_cases['pending'])} 進行中{len(wy_cases['active'])} 已結束{len(wy_cases['done'])}")
    except Exception as e:
        log.warning(f"📊 載入 {WY_CASES_FILE} 失敗：{e}")

def wy_cases_save():
    try:
        with wy_cases_lock:
            wy_cases['done'] = wy_cases['done'][-DONE_KEEP:]
            payload = json.dumps(wy_cases, ensure_ascii=False, default=str)
        tmp = WY_CASES_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(payload)
        os.replace(tmp, WY_CASES_FILE)
    except Exception as e:
        log.warning(f"📊 儲存 {WY_CASES_FILE} 失敗：{e}")

def _wy_close(st, case, result, r_mult, t, events):
    case.update({'result': result, 'r_mult': round(float(r_mult), 2) if r_mult is not None else None, 'end_time': t})
    st['pending'].pop(case['id'], None)
    st['active'].pop(case['id'], None)
    st['done'].append(case)
    if events is not None and not case.get('backfill') and result in ('TP1', 'SL', 'TIMEOUT'):
        events.append(case)

def wy_track_step(st, sym, dates, bars, row, meta, backfill=False, events=None, day_stage_fn=None):
    """dates/bars＝這一檔到「今天」為止的已收盤日K；row＝今天的威科夫結果（可以是None）。只處理上次檢查之後的新K線。"""
    for cid, p in list(st['pending'].items()):
        if p['symbol'] != sym: continue
        for i in range(_wy_bisect(dates, p['last_checked']), len(dates)):
            b = bars[i]
            if b['h'] >= p['entry']:
                fill = max(p['entry'], b['o'])
                R = fill - p['sl']
                if R <= 0:
                    _wy_close(st, p, 'CANCEL', None, dates[i], events); break
                p.update({'fill': fill, 'R': R, 'tp': fill + WY_TP_R * R, 'trigger_time': dates[i],
                          'bars_held': 0, 'last_checked': dates[i]})
                st['pending'].pop(cid, None)
                st['active'][cid] = p
                if b['l'] <= p['sl']:
                    _wy_close(st, p, 'SL', -1.0, dates[i], events)
                break
            if b['l'] <= p['sl']:
                _wy_close(st, p, 'CANCEL', None, dates[i], events); break
            p['waited'] = p.get('waited', 0) + 1
            p['last_checked'] = dates[i]
            if p['waited'] >= WY_TRIGGER_DAYS:
                _wy_close(st, p, 'NOFILL', None, dates[i], events); break
    for cid, a in list(st['active'].items()):
        if a['symbol'] != sym: continue
        for i in range(_wy_bisect(dates, a['last_checked']), len(dates)):
            b = bars[i]
            a['bars_held'] += 1
            a['last_checked'] = dates[i]
            a['last_close'] = b['c']
            if b['l'] <= a['sl']:
                _wy_close(st, a, 'SL', -1.0, dates[i], events); break
            if b['h'] >= a['tp']:
                _wy_close(st, a, 'TP1', WY_TP_R, dates[i], events); break
            if a['bars_held'] >= WY_HOLD_DAYS:
                _wy_close(st, a, 'TIMEOUT', (b['c'] - a['fill']) / a['R'], dates[i], events); break
    if not row or row.get('stage') != 'green' or not row.get('entry') or not row.get('sl'):
        return
    cid = f"{sym}|{row.get('bo_date')}|{row.get('retest_date')}|{float(row.get('ceiling') or 0):.4f}"
    if cid in st['pending']:                      # 還沒觸發：照最新的🟢移動 Entry／SL
        p = st['pending'][cid]
        p['entry'], p['sl'] = float(row['entry']), float(row['sl'])
        return
    if cid in st['used']:
        return
    st['used'][cid] = dates[-1]
    tail = bars[-20:]
    turnover = sum(x['c'] * x['v'] for x in tail) / len(tail) if tail else None
    case = {
        'id': cid, 'symbol': sym, 'name': meta.get('name'), 'sector': meta.get('sector'), 'tv_symbol': meta.get('tv_symbol'),
        'created': dates[-1], 'last_checked': dates[-1], 'waited': 0,
        'entry': float(row['entry']), 'sl': float(row['sl']), 'entry0': float(row['entry']), 'ceiling': row.get('ceiling'),
        'bo_date': row.get('bo_date'), 'retest_date': row.get('retest_date'),
        'day_stage': row.get('day_stage') or (day_stage_fn() if day_stage_fn else '--'),
        'wall_r': row.get('wall_r'), 'risk_atr': row.get('risk_atr'), 'turnover': turnover,
        'liquid': wy_liquid(turnover), 'backfill': bool(backfill),
    }
    if bars[-1]['c'] > case['entry']:            # 規則：現價已過Entry就不追
        case['result'], case['r_mult'], case['end_time'] = 'CHASE', None, dates[-1]
        st['done'].append(case)
        return
    st['pending'][cid] = case

def wy_track_live(meta, ddf, row):
    """主掃描每一檔都呼叫（用已收盤日K）。第一次看到某檔時，先回放最近 WY_BACKFILL_DAYS 天補抓（標「回補」，不推Telegram）"""
    sym = meta['symbol']
    dates = [pd.Timestamp(t).strftime('%Y-%m-%d') for t in ddf.index]
    bars = cf_bars(ddf)
    with wy_cases_lock:
        if sym not in wy_cases['seen'] and WY_BACKFILL_DAYS > 0:
            for k in range(WY_BACKFILL_DAYS, 0, -1):
                n = len(ddf) - k
                if n < 121: continue
                sub = ddf.iloc[:n]
                try:
                    rk = wy_analyze(sym, sub)
                    stage_fn = lambda sub=sub: STAGE_LABEL_MAP.get(get_stage(sub)[0], '--')
                    wy_track_step(wy_cases, sym, dates[:n], bars[:n], rk, meta, backfill=True, day_stage_fn=stage_fn)
                except Exception as e:
                    log.warning(f"📊 回補 {sym} k={k}: {e}")
        wy_cases['seen'][sym] = dates[-1]
        wy_track_step(wy_cases, sym, dates, bars, row, meta, backfill=False, events=wy_case_events)
        for c in list(wy_cases['pending'].values()) + list(wy_cases['active'].values()):
            if c['symbol'] == sym:
                c['price'] = bars[-1]['c']

def wy_stats(done):
    """跟突破卡片同樣的算法：勝率＝達1:1.5÷(達1:1.5＋止損)；平均R含到期"""
    traded = [d for d in done if d.get('result') in ('TP1', 'SL', 'TIMEOUT')]
    def agg(sub):
        n = len(sub); w = sum(1 for d in sub if d['result'] == 'TP1'); l = sum(1 for d in sub if d['result'] == 'SL')
        to = n - w - l; tot = sum(d['r_mult'] for d in sub)
        return {'n': n, 'win': w, 'loss': l, 'timeout': to, 'winrate': round(w / (w + l) * 100, 1) if (w + l) else None,
                'avg_r': round(tot / n, 3) if n else None, 'total_r': round(tot, 1)}
    groups = [
        ('全部', '全部', lambda d: True),
        ('日線Stage', 'S2', lambda d: d.get('day_stage') == 'S2'),
        ('日線Stage', '非S2', lambda d: d.get('day_stage') != 'S2'),
        ('上方空間', f'≥{HEADROOM_MIN_R:g}R或藍天', lambda d: d.get('wall_r') is None or d['wall_r'] >= HEADROOM_MIN_R),
        ('上方空間', f'<{HEADROOM_MIN_R:g}R', lambda d: d.get('wall_r') is not None and d['wall_r'] < HEADROOM_MIN_R),
        ('SL距離', f'≤{WY_RISK_MAX_ATR:g}倍ATR', lambda d: (d.get('risk_atr') or 0) <= WY_RISK_MAX_ATR),
        ('SL距離', f'>{WY_RISK_MAX_ATR:g}倍ATR', lambda d: (d.get('risk_atr') or 0) > WY_RISK_MAX_ATR),
        ('成交額', '夠（會推）', lambda d: d.get('liquid')),
        ('成交額', '💧不夠', lambda d: not d.get('liquid')),
    ]
    rows = [(g, lab, agg([d for d in traded if fn(d)])) for g, lab, fn in groups]
    counts = {k: sum(1 for d in done if d.get('result') == k) for k in ('NOFILL', 'CANCEL', 'CHASE')}
    return rows, counts

def wy_send_case_results():
    evs = [c for c in wy_case_events if c.get('liquid')]
    if not evs or not WY_TG_ON:
        return
    icon = {'TP1': '✅ 達1:1.5', 'SL': '❌ 止損', 'TIMEOUT': f'⏱ {WY_HOLD_DAYS}天到期'}
    lines = [f'【{M["name"]}威科夫 🟢 結果】']
    for c in evs:
        lines.append(f"{icon.get(c['result'], c['result'])} {label_of(c.get('name'), c['symbol'])}  "
                     f"成交 {fmt_px(c['fill'])} → {c['r_mult']:+.2f}R（🟢 {c['created'][5:]}）")
    send_telegram_plain('\n'.join(lines))

# ---------------- 歷史回測：把過去 WY_BT_DAYS 天每一天都重播一次 ----------------
wy_bt_state = {'status': 'idle', 'done': 0, 'total': 0, 'error': None, 'started': None, 'lock': threading.Lock()}

def run_wy_backtest(limit=None):
    with wy_bt_state['lock']:
        if wy_bt_state['status'] == 'running':
            return
        wy_bt_state.update({'status': 'running', 'done': 0, 'error': None,
                            'started': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')})
    try:
        syms = list(dict.fromkeys(SYMBOLS))[:limit] if limit else list(dict.fromkeys(SYMBOLS))
        wy_bt_state['total'] = len(syms)
        st = _wy_new_state()
        for si, sym in enumerate(syms):
            try:
                df = closed_bars(fetch_ohlcv(sym, '1D'), '1D')
                if len(df) >= 250:
                    meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)), 'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
                    dates = [pd.Timestamp(t).strftime('%Y-%m-%d') for t in df.index]
                    bars = cf_bars(df)
                    for T in range(max(130, len(df) - WY_BT_DAYS), len(df)):
                        sub = df.iloc[max(0, T - 499):T + 1]
                        r = wy_analyze(sym, sub)
                        stage_fn = lambda sub=sub: STAGE_LABEL_MAP.get(get_stage(sub)[0], '--')
                        wy_track_step(st, sym, dates[:T + 1], bars[:T + 1], r, meta, day_stage_fn=stage_fn)
            except Exception as e:
                log.warning(f"📊 威科夫回測 {sym}: {e}")
            wy_bt_state['done'] = si + 1
            time.sleep(0.2)
        rows, counts = wy_stats(st['done'])
        res = {'finished': datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M'), 'days': WY_BT_DAYS, 'symbols': len(syms),
               'rows': rows, 'counts': counts, 'open': len(st['pending']) + len(st['active']),
               'cases': sorted([d for d in st['done'] if d.get('result') in ('TP1', 'SL', 'TIMEOUT')],
                               key=lambda d: d.get('trigger_time', ''), reverse=True)[:300]}
        with open(WY_BT_FILE, 'w', encoding='utf-8') as f:
            json.dump(res, f, ensure_ascii=False, default=str)
        with wy_bt_state['lock']:
            wy_bt_state['status'] = 'done'
    except Exception as e:
        log.error(f"📊 威科夫回測失敗：{e}")
        with wy_bt_state['lock']:
            wy_bt_state.update({'status': 'error', 'error': str(e)})

def load_wy_bt():
    try:
        with open(WY_BT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

wy_cases_load()

def _wy_stat_table(rows):
    out = '<table class=wy><tr><th>分組</th><th>條件</th><th>筆數</th><th>✅</th><th>❌</th><th>⏱</th><th>勝率</th><th>平均R</th><th>總R</th></tr>'
    for g, lab, s in rows:
        wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
        ar = f'{s["avg_r"]:+.2f}R' if s['avg_r'] is not None else '-'
        out += (f'<tr><td>{_h(g)}</td><td>{_h(lab)}</td><td class=c>{s["n"]}</td><td class=c>{s["win"]}</td><td class=c>{s["loss"]}</td>'
                f'<td class=c>{s["timeout"]}</td><td class=c>{wr}</td><td class=c>{ar}</td><td class=c>{s["total_r"]:+.1f}</td></tr>')
    return out + '</table>'

def wy_tracking_html():
    """威科夫頁面最下面：🟢 結果追蹤＋歷史回測＋跟VCP對照"""
    f = lambda v: '—' if v is None else fmt_px(v)
    with wy_cases_lock:
        pend = sorted(wy_cases['pending'].values(), key=lambda c: c['created'], reverse=True)
        act = sorted(wy_cases['active'].values(), key=lambda c: c.get('trigger_time', ''), reverse=True)
        done = list(wy_cases['done'])
    rows, counts = wy_stats(done)
    def lab(c):
        tv = f"{tv_chart_base()}?symbol={c.get('tv_symbol') or tv_sym(c['symbol'])}&interval=D"
        nm = c.get('name') or ''
        nm = '' if nm == sym_code(c['symbol']) else f' <span class=small>{_h(nm)}</span>'
        tags = (' <span class=small>回補</span>' if c.get('backfill') else '') + ('' if c.get('liquid') else ' <span class=small style="color:#ee7373">💧</span>')
        return f'<a href="{tv}" target="_blank"><b>{sym_code(c["symbol"])}</b></a>{nm}{tags}'
    h = ('<h3 class=wyh id=wytrack style="border-left:6px solid #4cc28e;padding-left:8px">📊 🟢 結果追蹤</h3>'
         f'<p class=note>每個 🟢 出現後自動追蹤：等價格碰到 Entry（{WY_TRIGGER_DAYS} 天內），成交後看先碰 SL（−1R）還是先到 1:{WY_TP_R:g}（+{WY_TP_R:g}R），'
         f'{WY_HOLD_DAYS} 天都沒碰到算到期。出場規則跟突破卡片一樣，所以可以直接比較。還沒觸發時，Entry／SL 每天照最新的 🟢 移動。'
         f'「回補」＝第一次部署時回放最近 {WY_BACKFILL_DAYS} 天補抓的。💧＝成交額不夠（只記錄、不推）。</p>')
    h += f'<p class=note><b>等觸發（{len(pend)}）</b></p>'
    if pend:
        h += '<div class=wrap><table class=wy><tr><th>股票</th><th>🟢 日期</th><th>日線</th><th>Entry</th><th>SL</th><th>現價</th><th>已等</th></tr>'
        for c in pend:
            h += (f'<tr><td>{lab(c)}</td><td class=c>{c["created"][5:]}</td><td class=c>{c.get("day_stage")}</td><td class=c>{f(c["entry"])}</td>'
                  f'<td class=c>{f(c["sl"])}</td><td class=c>{f(c.get("price"))}</td><td class=c>{c.get("waited", 0)}/{WY_TRIGGER_DAYS}</td></tr>')
        h += '</table></div>'
    else:
        h += '<p class=note>沒有。</p>'
    h += f'<p class=note><b>已成交、進行中（{len(act)}）</b></p>'
    if act:
        h += '<div class=wrap><table class=wy><tr><th>股票</th><th>成交日</th><th>成交價</th><th>SL</th><th>1:1.5</th><th>現價（R）</th><th>已過</th></tr>'
        for c in act:
            px = c.get('price') or c.get('last_close') or c['fill']
            h += (f'<tr><td>{lab(c)}</td><td class=c>{c["trigger_time"][5:]}</td><td class=c>{f(c["fill"])}</td><td class=c>{f(c["sl"])}</td>'
                  f'<td class=c>{f(c["tp"])}</td><td class=c>{f(px)}（{(px - c["fill"]) / c["R"]:+.2f}R）</td><td class=c>{c["bars_held"]}/{WY_HOLD_DAYS}</td></tr>')
        h += '</table></div>'
    else:
        h += '<p class=note>沒有。</p>'
    recent = sorted([d for d in done if d.get('result') in ('TP1', 'SL', 'TIMEOUT')], key=lambda d: d.get('end_time', ''), reverse=True)[:20]
    if recent:
        icon = {'TP1': '✅', 'SL': '❌', 'TIMEOUT': '⏱'}
        h += f'<details><summary class=note>最近結束 {len(recent)} 筆 — 點這裡展開</summary><div class=wrap><table class=wy><tr><th>股票</th><th>結果</th><th>成交</th><th>結束</th><th>R</th></tr>'
        for c in recent:
            h += (f'<tr><td>{lab(c)}</td><td class=c>{icon[c["result"]]}</td><td class=c>{c["trigger_time"][5:]} @ {f(c["fill"])}</td>'
                  f'<td class=c>{c["end_time"][5:]}</td><td class=c>{c["r_mult"]:+.2f}</td></tr>')
        h += '</table></div></details>'
    h += (f'<p class=note><b>即時戰績</b>（從部署這天開始累積；不算勝負的：沒觸發 {counts["NOFILL"]}、觸發前就破SL作廢 {counts["CANCEL"]}、'
          f'現價已過Entry沒追 {counts["CHASE"]}）</p>' + '<div class=wrap>' + _wy_stat_table(rows) + '</div>')

    # ---- 歷史回測 + 跟VCP對照 ----
    with wy_bt_state['lock']:
        bst = dict(wy_bt_state)
    bt = load_wy_bt()
    h += '<h3 class=wyh id=wybt style="border-left:6px solid #84aedb;padding-left:8px">🧪 歷史回測：威科夫 🟢 vs VCP 突破卡片</h3>'
    if bst['status'] == 'running':
        h += f'<p class=note>⏳ 回測進行中：{bst["done"]}/{bst["total"]} 檔（{bst["started"]} 開始）。跑完重新整理這一頁。</p>'
    else:
        if bst['status'] == 'error':
            h += f'<p class=note style="color:#ee7373">上次回測出錯：{_h(bst["error"])}</p>'
        h += (f'<p class=note><a href="/wyckoff_backtest?run=1" style="{BRIGHT_BTN}" onclick="return confirm(\'開始跑威科夫歷史回測？會在背景跑大約10～30分鐘，不影響正常掃描\')">'
              f'▶ 跑威科夫歷史回測（最近 {WY_BT_DAYS} 個交易日）</a>　<span class=small>可以先加 &amp;limit=50 試50檔</span></p>')
    if bt:
        h += (f'<p class=note>{bt["finished"]} 完成・{bt["symbols"]} 檔・最近 {bt["days"]} 個交易日・'
              f'沒觸發 {bt["counts"]["NOFILL"]}、作廢 {bt["counts"]["CANCEL"]}、沒追 {bt["counts"]["CHASE"]}、回測結束時還沒結果 {bt["open"]}</p>')
        h += '<div class=wrap>' + _wy_stat_table(bt['rows']) + '</div>'
        vcp = load_bt_result('1D')
        cfg = None
        if vcp:
            cfg = next((c for c in vcp.get('configs', []) if c.get('cfg', {}).get('min_drop') == MIN_DROP_PCT), None)
        def line(name, s):
            wr = f'{s["winrate"]:.0f}%' if s.get('winrate') is not None else '-'
            ar = f'{s["avg_r"]:+.2f}R' if s.get('avg_r') is not None else '-'
            return f'<tr><td>{name}</td><td class=c>{s["n"]}</td><td class=c>{wr}</td><td class=c>{ar}</td><td class=c>{s.get("total_r", 0):+.1f}</td></tr>'
        h += ('<p class=note><b>對照（同樣的出場規則：SL −1R／1:1.5／20根到期）</b></p><div class=wrap><table class=wy>'
              '<tr><th>策略</th><th>筆數</th><th>勝率</th><th>平均R</th><th>總R</th></tr>')
        h += line('🧱 威科夫 🟢・全部', bt['rows'][0][2]) + line('🧱 威科夫 🟢・日線S2', bt['rows'][1][2])
        if cfg:
            h += line(f'🃏 VCP 突破卡片 1D（C1 {MIN_DROP_PCT:g}%）・全部', cfg['all']) + line(f'🃏 VCP 突破卡片 1D・日線S2', cfg['s2'])
            h += '</table></div><p class=note>VCP 數字來自「🧪 C1門檻回測」1D 的結果（' + _h(vcp.get('finished', '')) + '）。'
        else:
            h += (f'</table></div><p class=note>還沒有 VCP 1D 的回測結果可以對照：到「🧪 C1門檻回測」跑一次 1D（C1 {MIN_DROP_PCT:g}%），這裡就會出現。')
        h += ('差別：VCP 卡片用「突破那根K線的收盤價」進場，威科夫用 Entry 觸價成交；樣本少於 30 筆時參考就好。'
              '過去的結果不代表未來，只供自己研究。</p>')
        cases = bt.get('cases') or []
        if cases:
            icon = {'TP1': '✅', 'SL': '❌', 'TIMEOUT': '⏱'}
            li = ''.join(
                f'<div><a href="/stock_bt?symbol={_h(sym_code(c["symbol"]))}&amp;strategy=wy&amp;tf=1D&amp;focus={_h(c.get("trigger_time") or "")}">'
                f'<b>{_h(sym_code(c["symbol"]))}</b></a> {_nm(c)} ・ {_h((c.get("trigger_time") or "")[:10])} 成交 {fmt_px(c.get("fill"))} → '
                f'{icon.get(c["result"], c["result"])} <span style="color:{"#4cc28e" if (c.get("r_mult") or 0) > 0 else "#ee7373"}">{(c.get("r_mult") or 0):+.2f}R</span></div>'
                for c in cases)
            h += (f'<details><summary class=note>🔍 回測裡的 {len(cases)} 筆交易（點代碼看圖）— 點這裡展開</summary>'
                  f'<div class=note style="line-height:1.9;max-height:420px;overflow-y:auto">{li}</div></details>')
    return h

load_cards()

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</title>
<style>
  body{font-family:monospace;background:#1a1a2e;color:#eee;margin:20px}
  h2{color:#fff;margin-bottom:4px}
  .subtitle{color:#aaa;font-size:13px;margin-bottom:12px}
  .info{color:#aaa;margin-bottom:15px;font-size:14px}
  table{border-collapse:collapse;width:auto}
  th{background:#333;color:#fff;padding:8px 12px;font-size:13px;border:1px solid #444}
  .sym{background:#2a2a3e;color:#fff;padding:6px 12px;font-size:13px;border:1px solid #444;font-weight:bold}
  .sym a{color:#fff;text-decoration:none} .sym a:hover{color:#7ab3ff}
  .cell{text-align:center;padding:6px 10px;font-size:12px;border:1px solid #444;font-weight:bold;min-width:80px}
  .gray{background:#333;color:#888}
  .stage1{background:#1a3a6e;color:#7ab3ff}
  .bull{background:#1a3a6e;color:#7ab3ff}
  .bull-c{background:#1565c0;color:#fff}
  .bull-ready{background:#e65100;color:#fff}
  .stage3{background:#5a3a00;color:#ffb74d}
  .bear{background:#5a1a1a;color:#ff8a8a}
  .bear-c{background:#c62828;color:#fff}
  .bear-ready{background:#e65100;color:#fff}
  .mark-anchor{outline:2px solid #ffffff;outline-offset:-2px}
  .mark-align{outline:2px solid #2e7d32;outline-offset:-2px}
  .mark-conflict-loose{outline:2px dashed #ffb300;outline-offset:-2px}
  .mark-conflict-tight{outline:2px solid #e53935;outline-offset:-2px}
  .hidden{display:none}
  .ctrl-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}
  .btn{color:#fff;border:none;padding:10px 20px;font-size:14px;cursor:pointer;border-radius:6px;font-family:monospace;font-weight:bold}
  .btn-blue{background:#1565c0} .btn-blue:hover{background:#1976d2}
  .btn-green{background:#2e7d32} .btn-green:hover{background:#388e3c}
  .btn-gray{background:#333} .btn-gray:hover{background:#555}
  .btn:disabled{background:#555;cursor:not-allowed}
  select{background:#2a2a3e;color:#fff;border:1px solid #444;padding:9px 14px;border-radius:6px;font-size:14px;font-family:monospace}
  .search-box{padding:8px 14px;font-size:14px;border-radius:6px;border:1px solid #444;background:#2a2a3e;color:#fff;font-family:monospace;width:180px}
  .scanning-banner{background:#1565c0;color:#fff;padding:12px 20px;border-radius:6px;margin-bottom:15px;font-size:15px;font-weight:bold}
  .chk-label{color:#aaa;font-size:13px;display:flex;align-items:center;gap:4px;cursor:pointer}
  .nav{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
  .nav a{color:#aaa;text-decoration:none;padding:7px 14px;border:1px solid #444;border-radius:6px;font-size:13px}
  .nav a:hover{color:#fff;border-color:#7ab3ff}
  .nav a.nav-on{color:#fff;background:#1565c0;border-color:#1565c0}
</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</h2>
<div class="subtitle">KLSE股票 · 操盤跟莊（邏輯已對齊 莊家思維 Contraction V53）</div>
<div class="nav"><a class="nav-on" href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a><a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>
SCANNING_BANNER
<div class="ctrl-bar">
  <button class="btn btn-blue" onclick="startRefresh()" id="refreshBtn">&#x1F504; 重新掃描</button>
  <select id="stageFilter" onchange="applyFilter()">
    <option value="all">全部 Stage</option>
    <option value="2">S2 只看牛市</option>
    <option value="4">S4 只看熊市</option>
    <option value="1">S1 橫盤</option>
    <option value="3">S3 頂部</option>
  </select>
  <select id="sectorFilter" onchange="applyFilter()">
    <option value="">全部板塊</option>
    SECTOR_OPTIONS
  </select>
  <input class="search-box" type="text" id="searchBox" placeholder="搜尋股票..." oninput="applyFilter()">
  <button class="btn btn-gray" onclick="clearSearch()">&#x2715;</button>
  <label class="chk-label"><input type="checkbox" id="onlyC" onchange="applyFilter()"> 只顯示有C的</label>
  <button class="btn btn-green" onclick="exportWatchlist()">&#x1F4CB; Export Watchlist</button>
</div>
<div class="info">更新：LAST_SCAN (MYT) | MKT_STATUS | 共 TOTAL 只 | 顯示 <span id="countDisplay">TOTAL</span> 個MISSING_INFO</div>
<textarea id="watchlistBox" readonly style="background:#1a1a2e;color:#0f0;border:1px solid #444;padding:12px;border-radius:6px;width:500px;height:150px;font-family:monospace;font-size:12px;margin-top:8px;display:none"></textarea>
<br id="watchlistBr" style="display:none">
<table id="mainTable">
  <tr><th>股票</th><th>板塊</th><th>日均額</th>RS_HEADTF_HEAD</tr>
  ROWS
</table>
<br>
<div class="info">
  <span style="background:#1a3a6e;color:#7ab3ff;padding:2px 6px">■</span> S1橫盤 &nbsp;
  <span style="background:#1565c0;color:#fff;padding:2px 6px">■</span> S2/多頭有C &nbsp;
  <span style="background:#e65100;color:#fff;padding:2px 6px">🎯</span> 進場信號 &nbsp;
  <span style="background:#5a3a00;color:#ffb74d;padding:2px 6px">■</span> S3頂部 &nbsp;
  <span style="background:#c62828;color:#fff;padding:2px 6px">■</span> S4/空頭有C &nbsp;|&nbsp;
  <span style="outline:2px solid #ffffff;outline-offset:-2px;padding:2px 6px">■</span> 動態錨點 &nbsp;
  <span style="outline:2px solid #2e7d32;outline-offset:-2px;padding:2px 6px">■</span> 順勢 &nbsp;
  <span style="outline:2px dashed #ffb300;outline-offset:-2px;padding:2px 6px">■</span> 逆勢-新 &nbsp;
  <span style="outline:2px solid #e53935;outline-offset:-2px;padding:2px 6px">■</span> 逆勢-舊
</div>
<script>
function applyFilter() {
  var stage  = document.getElementById('stageFilter').value;
  var sector = document.getElementById('sectorFilter').value;
  var search = document.getElementById('searchBox').value.toUpperCase();
  var onlyC  = document.getElementById('onlyC').checked;
  var rows   = document.querySelectorAll('#mainTable tr:not(:first-child)');
  var count  = 0;
  rows.forEach(function(row) {
    var sym = row.querySelector('.sym');
    if (!sym) return;
    var rowStage  = row.getAttribute('data-stage');
    var rowSector = row.getAttribute('data-sector');
    var hasC      = row.getAttribute('data-hasc') === '1';
    var matchStage  = (stage === 'all') || (rowStage === stage);
    var matchSector = (sector === '') || (rowSector === sector);
    var matchSearch = sym.textContent.toUpperCase().indexOf(search) > -1;
    if (matchStage && matchSector && matchSearch && (!onlyC || hasC)) {
      row.classList.remove('hidden'); count++;
    } else {
      row.classList.add('hidden');
    }
  });
  document.getElementById('countDisplay').textContent = count;
}
function clearSearch() {
  document.getElementById('searchBox').value = '';
  applyFilter();
}
function exportWatchlist() {
  var stage = document.getElementById('stageFilter').value;
  var rows  = document.querySelectorAll('#mainTable tr:not(:first-child)');
  var list  = [];
  rows.forEach(function(row) {
    if (row.classList.contains('hidden')) return;
    var sym = row.getAttribute('data-symbol');
    if (sym) list.push(sym);
  });
  var box = document.getElementById('watchlistBox');
  var br  = document.getElementById('watchlistBr');
  if (list.length === 0) {
    box.value = '沒有符合條件的股票！';
  } else {
    box.value = list.join(',');
  }
  box.style.display = 'block';
  br.style.display  = 'block';
  box.select();
  try { document.execCommand('copy'); } catch(e) {}
  alert('已複製 ' + list.length + ' 支股票到剪貼板！\\n直接貼到 TradingView Watchlist！');
}
function startRefresh() {
  var btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 掃描中...';
  fetch('/rescan', {method:'POST'}).then(function() { pollStatus(); })
    .catch(function() { btn.disabled=false; btn.textContent='🔄 重新掃描'; });
}
function pollStatus() {
  fetch('/status').then(function(r){return r.json();}).then(function(d) {
    if (d.status === 'done') { location.reload(); }
    else { setTimeout(pollStatus, 5000); }
  });
}
AUTOPOLL
</script>
</body></html>"""

def build_html(status='done'):
    rows = ''
    for r in (cached_results or []):
        sym = r['symbol']
        tv  = r.get('tv_symbol', tv_sym(sym))
        tv_url = f"{tv_chart_base()}?symbol={tv}&interval=D"  # 股票名稱欄預設跳日線
        name = r.get('name', sym)
        sector = r.get('sector', '其他')
        alias = TV_SYMBOLS.get(sym, '')  # 常見簡稱（如MPI/TM），只用來讓搜尋找得到，不影響顯示或連結

        d_cls = r.get('1D_cls', 'gray')
        if d_cls in ('bull', 'bull-c', 'bull-ready'):   stage_val = '2'
        elif d_cls in ('bear', 'bear-c', 'bear-ready'): stage_val = '4'
        elif d_cls == 'stage1':                          stage_val = '1'
        elif d_cls == 'stage3':                          stage_val = '3'
        else:                                            stage_val = '0'

        has_c_any = any(r.get(f'{t}_cls','gray') in SIGNAL_CLASSES for t in TF_LABELS)
        anchor_marks = get_row_anchor_marks(r)

        rows += f'<tr data-stage="{stage_val}" data-sector="{sector}" data-symbol="{tv}" data-hasc="{"1" if has_c_any else "0"}">'
        sub = f'<br><span style="color:#8b949e;font-size:10px">{sym}</span>' if name != sym else ''
        rows += f'<td class="sym"><a href="{tv_url}" target="_blank">{name}</a>{sub}<span style="display:none">{alias}</span></td>'
        rows += f'<td style="color:#aaa;font-size:12px;text-align:center">{sector}</td>'
        to = r.get('turnover')
        to_bg = '#2a2a2a' if to is None else ('#1a6b3c' if to >= TG_MIN_TURNOVER_MYR else '#8b0000')
        rows += f'<td class="cell" style="background:{to_bg};color:#fff">{_fmt_turnover(to)}</td>'
        if RS_BENCHMARK:
            rows += f'<td class="cell" style="background:{r.get("RS_color", "#2a2a2a")};color:#fff">{r.get("RS_text", "--")}</td>'
        for tf in TF_LABELS:
            text = r.get(tf, '-')
            cls  = r.get(f'{tf}_cls', 'gray')
            mark = anchor_marks.get(tf, '')
            mark_cls = f' mark-{mark}' if mark else ''
            tf_url = f"{tv_chart_base()}?symbol={tv}&interval={TV_INTERVAL.get(tf, 'D')}"  # 點哪個時間段的欄位就跳到那個時間段
            rows += f'<td class="cell {cls}{mark_cls}"><a href="{tf_url}" target="_blank" style="color:inherit;text-decoration:none;display:block">{text}</a></td>'
        rows += '</tr>\n'

    last = scan_state.get('last_scan') or '-'
    total = len(cached_results)
    scanning_banner = '<div class="scanning-banner">⏳ 掃描中，請稍候...（約需10分鐘）</div>' if status == 'scanning' else ''
    sector_opts = ''.join(f'<option value="{s}">{s}</option>' for s in sorted(set(SECTORS.values())))
    rs_head = f'<th title="20天 vs {RS_BENCHMARK}：-5~+5排名分數（比值%，100%＝同步）">力量</th>' if RS_BENCHMARK else ''
    mkt_status = '🟢 開盤中' if is_market_hours() else '⚪ 已收盤'
    n_missing = sum(1 for r in (cached_results or []) if r.get('nodata'))
    missing_info = f' | <a href="/debug_missing" style="color:#ffb74d">⚠️ {n_missing} 只抓不到資料</a>' if n_missing else ''

    # 掃描中打開頁面時自動輪詢，掃完自動刷新（之前要手動重新整理）
    autopoll = 'pollStatus();' if status == 'scanning' else ''
    return (HTML
        .replace('SCANNING_BANNER', scanning_banner)
        .replace('SECTOR_OPTIONS', sector_opts)
        .replace('LAST_SCAN', last)
        .replace('RS_HEAD', rs_head)
        .replace('TF_HEAD', ''.join(f'<th>{t}</th>' for t in TF_LABELS))
        .replace('MKT_STATUS', mkt_status)
        .replace('MISSING_INFO', missing_info)
        .replace('TOTAL', str(total))
        .replace('AUTOPOLL', autopoll)
        .replace('ROWS', rows))

@app.route('/')
def index():
    with scan_state['lock']:
        status = scan_state['status']
    if status == 'idle':
        threading.Thread(target=run_scan, daemon=True).start()
        return Response('''<!DOCTYPE html><html><head><meta charset="utf-8"><title>莊家思維</title>
<meta http-equiv="refresh" content="15">
<style>body{font-family:monospace;background:#1a1a2e;color:#eee;margin:40px;text-align:center}</style>
</head><body><h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</h2>
<p style="color:#7ab3ff;font-size:18px">⏳ 首次啟動，正在掃描中...</p>
<p style="color:#aaa">約需10分鐘，頁面將自動刷新</p>
</body></html>''', mimetype='text/html')
    try:
        return build_html(status)
    except Exception as e:
        log.error(f"build_html error: {e}")
        return f"<html><body style='background:#1a1a2e;color:#eee;font-family:monospace;padding:40px'><h2>🇲🇾 大馬莊家思維掃描器</h2><p>⏳ 掃描中，請稍候...</p><p style='color:#8b949e'>Error: {e}</p></body></html>", 200

# ============================================================
# 🃏 突破卡片頁面 /cards?tf=1D
# ============================================================
CARDS_CSS = """
body{font-family:monospace;background:#1a1a2e;color:#eee;margin:20px}
h2{color:#fff;margin-bottom:4px} .subtitle{color:#aaa;font-size:13px;margin-bottom:12px}
.nav{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.nav a{color:#aaa;text-decoration:none;padding:7px 14px;border:1px solid #444;border-radius:6px;font-size:13px}
.nav a:hover{color:#fff;border-color:#7ab3ff} .nav a.nav-on{color:#fff;background:#1565c0;border-color:#1565c0}
.tfbar{display:flex;gap:6px;margin:6px 0 14px;flex-wrap:wrap}
.tfbar a{color:#ccc;text-decoration:none;padding:7px 16px;border-radius:18px;border:1px solid #444;font-size:13px}
.tfbar a.on{background:#e65100;border-color:#e65100;color:#fff;font-weight:bold}
.ctrl{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}
select,.search-box{background:#2a2a3e;color:#fff;border:1px solid #444;padding:8px 12px;border-radius:6px;font-size:13px;font-family:monospace}
.search-box{width:200px}
.sec{margin-top:26px} .sec h3{margin:0 0 4px;color:#ffb74d;font-size:16px}
.sec .desc{color:#8b949e;font-size:12px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;max-width:1150px}
.card{background:#22223a;border:1px solid #3a3a55;border-left:3px solid #7ab3ff;border-radius:8px;padding:12px 14px}
.card.pend{border-left-color:#ffb74d}
.card.res-TP1{border-left-color:#43a047} .card.res-SL{border-left-color:#e53935} .card.res-TIMEOUT{border-left-color:#888}
.hd{display:flex;align-items:baseline;gap:8px}
.hd a{color:#fff;text-decoration:none;font-size:19px;font-weight:bold} .hd a:hover{color:#7ab3ff}
.hd .nm{color:#aaa;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.hd .dt{color:#aaa;font-size:12px}
.dist{background:#5a3a00;color:#ffb74d;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:bold;white-space:nowrap}
.dist.over{background:#1b5e20;color:#a5d6a7}
.tags{margin:7px 0;display:flex;gap:5px;flex-wrap:wrap}
.tag{border:1px solid #444;color:#bbb;font-size:11px;padding:1px 6px;border-radius:4px}
.tag.s2{border-color:#1565c0;color:#7ab3ff} .tag.sx{border-color:#c62828;color:#ff8a8a}
.tag.warn{border-color:#e65100;color:#ffb74d} .tag.hot{border-color:#2e7d32;color:#a5d6a7}
a.tag{text-decoration:none}
.line{font-size:12px;color:#ddd;display:flex;justify-content:space-between;margin-bottom:6px}
.line .muted{color:#8b949e}
.pxrow{display:flex;justify-content:space-between;border-top:1px solid #333;padding-top:7px;margin-top:4px}
.lbl{color:#8b949e;font-size:11px} .big{font-size:18px;font-weight:bold;color:#fff} .r{text-align:right}
.lv{border-top:1px solid #333;margin-top:7px;padding-top:6px;font-size:12px}
.lv div{display:flex;justify-content:space-between;padding:1px 0}
.neg{color:#ff6b6b} .pos{color:#9ccc65}
.empty{background:#22223a;border:1px solid #3a3a55;border-radius:8px;padding:14px;color:#aaa;max-width:1150px}
table.st{border-collapse:collapse;font-size:12px}
table.st th,table.st td{border:1px solid #444;padding:5px 10px;text-align:center}
table.st th{background:#333;color:#fff} table.st td.g{color:#8b949e;text-align:left}
.warnbox{background:#5a3a00;color:#ffb74d;padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px;max-width:1150px}
.scanning-banner{background:#1565c0;color:#fff;padding:10px 16px;border-radius:6px;margin-bottom:12px;font-size:14px;font-weight:bold;max-width:1150px}
.foot{color:#666;font-size:11px;margin-top:28px;max-width:1150px;line-height:1.6}
.flow{background:#22223a;border:1px solid #3a3a55;border-radius:6px;padding:9px 12px;font-size:12px;color:#ccc;margin-top:12px;max-width:1150px;line-height:1.7}
.flow b{color:#ffb74d}
details.help{max-width:1150px;margin:-4px 0 10px;font-size:12px}
details.help summary{cursor:pointer;color:#7ab3ff}
details.help div{background:#22223a;border:1px solid #3a3a55;border-radius:6px;padding:9px 12px;margin-top:6px;line-height:1.8;color:#ccc}
details.help b{color:#fff}
"""

def _h(s):
    return (str(s) if s is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def _pct(a, b):
    return (a - b) / b * 100 if b else 0.0

def _fmt_time(iso, tf):
    try:
        t = pd.Timestamp(iso)
        return t.strftime('%m/%d') if tf == '1D' else t.strftime('%m/%d %H:%M')
    except Exception:
        return str(iso)[:10]

# 🧱 卡片上的威科夫燈號（同一檔在威科夫突破頁目前的狀態；⛔資料不足不顯示）
WY_CARD_TAG = {
    'green':  ('🧱🟢 威科夫真突破', 'hot'),
    'orange': ('🧱🟠 威科夫等回踩', ''),
    'yellow': ('🧱🟡 威科夫洗盤完成', ''),
    'weak':   ('🧱⚪ 威科夫條件不全', ''),
    'fail':   ('🧱❌ 威科夫跌回區間', 'warn'),
}

def _card_tags(c, tf, extra=None):
    tags = [f'<span class="tag">{_h(c.get("sector") or "其他")}</span>', f'<span class="tag">{tf}</span>']
    s = c.get('stage', 0)
    tags.append(f'<span class="tag {"s2" if s == 2 else "sx"}">日線S{s if s else "?"}</span>')
    if c.get('entry_zone'): tags.append(f'<span class="tag">{_h(c["entry_zone"])}</span>')
    if c.get('provisional'): tags.append('<span class="tag warn">⏳ 低點未確認</span>')
    if c.get('vol_x') is not None:
        hot = c['vol_x'] >= VOL_SURGE_X
        tags.append(f'<span class="tag {"hot" if hot else ""}">{"🔥" if hot else ""}量{c["vol_x"]}x</span>')
    if c.get('chase'): tags.append('<span class="tag warn">⚠️不追</span>')
    if c.get('close_ok') is True:  tags.append('<span class="tag hot">✅ 收盤站穩</span>')
    if c.get('close_ok') is False: tags.append('<span class="tag warn">⚠️ 收盤沒站穩</span>')
    wy = c.get('wy')
    if wy in WY_CARD_TAG:
        txt, cls = WY_CARD_TAG[wy]
        tags.append(f'<a class="tag {cls}" href="/wyckoff" title="同一檔在威科夫突破頁的燈號">{txt}</a>')
    _to = c.get('turnover')
    if _to is not None:
        tags.append(f'<span class="tag{"" if _to >= TG_MIN_TURNOVER_MYR else " warn"}">成交額{_fmt_turnover(_to)}'
                    + ('' if _to >= TG_MIN_TURNOVER_MYR else ' 💧不推') + '</span>')
    if extra: tags.extend(extra)
    return '<div class="tags">' + ''.join(tags) + '</div>'

def _nm(c):
    n = c.get('name') or ''
    return '' if n == sym_code(c['symbol']) else _h(n)

def _search_attr(c):
    code = c['symbol'].replace('.KL', '')
    return f'data-sector="{_h(c.get("sector") or "其他")}" data-q="{_h((code + " " + (c.get("name") or "")).upper())}"'

def _tv_url(c, tf):
    tv = c.get('tv_symbol') or tv_sym(c['symbol'])
    return f"{tv_chart_base()}?symbol={tv}&interval={TV_INTERVAL.get(tf, 'D')}"

def _render_pending(c, tf):
    code = c['symbol'].replace('.KL', '')
    price = c.get('price') or 0
    bo, sl = c['bo'], c['sl']
    tp1, tp2 = calc_targets(bo, sl)
    dist = _pct(bo, price) if price else None
    if dist is None:      dist_html = ''
    elif dist <= 0:       dist_html = ('<span class="dist over">盤中已碰BO・收盤後記錄</span>' if CARD_ENTRY_MODE == 'touch'
                                       else '<span class="dist over">盤中已過BO・等收盤</span>')
    else:                 dist_html = f'<span class="dist">差 {dist:.1f}%</span>'
    return f'''<div class="card pend" {_search_attr(c)}>
<div class="hd"><a href="{_tv_url(c, tf)}" target="_blank">{code}</a><span class="nm">{_nm(c)}</span>{dist_html}</div>
{_card_tags(c, tf)}
<div class="line"><span>第 {c.get("base", 0) + 1} 個 base ・ 收縮 {c.get("c_count")} 段</span><span class="muted">還沒突破</span></div>
<div class="pxrow"><div><div class="lbl">現價</div><div class="big">{fmt_px(price)}</div></div>
<div class="r"><div class="lbl">BO</div><div class="big">{fmt_px(bo)}</div><div class="lbl">C高點 {fmt_px(c["c_hv"])}・{"在BO掛觸價單" if CARD_ENTRY_MODE == "touch" else "收盤站上才算突破"}</div></div></div>
<div class="lv"><div><span>SL</span><span>{fmt_px(sl)} <span class="neg">({_pct(sl, bo):.1f}%)</span></span></div>
<div><span>1:1.5</span><span>{fmt_px(tp1)} <span class="pos">(+{_pct(tp1, bo):.1f}%)</span></span></div>
<div><span>1:2</span><span>{fmt_px(tp2)} <span class="pos">(+{_pct(tp2, bo):.1f}%)</span></span></div></div>
</div>'''

def _render_active(c, tf):
    code = c['symbol'].replace('.KL', '')
    entry, sl = c['entry'], c['sl']
    r = entry - sl
    price = c.get('price') or c.get('last_close') or entry
    cur_r = (price - entry) / r if r else 0
    extra = [f'<span class="tag">已過 {c.get("bars_held", 0)}/{MAX_HOLD_BARS} 根</span>']
    if c.get('backfill'): extra.append('<span class="tag">回補</span>')
    if c.get('entry_mode') == 'touch':
        how = '觸價成交'
        elbl = '進場價（BO成交）' if abs(entry - c['bo']) < 1e-9 else '進場價（跳空開盤成交）'
        sub = f'當天收盤 {fmt_px(c.get("close_px"))}・現價 {fmt_px(price)}（{cur_r:+.2f}R）'
    else:
        how, elbl = '收盤確認', '確認價（進場）'
        sub = f'現價 {fmt_px(price)}（{cur_r:+.2f}R）'
    return f'''<div class="card" {_search_attr(c)}>
<div class="hd"><a href="{_tv_url(c, tf)}" target="_blank">{code}</a><span class="nm">{_nm(c)}</span><span class="dt">{_fmt_time(c["confirm_time"], tf)}</span></div>
{_card_tags(c, tf, extra)}
<div class="line"><span>第 {c.get("base", 0) + 1} 個 base ・ 收縮 {c.get("c_count")} 段</span><span class="muted">{_fmt_time(c["confirm_time"], tf)} {how}</span></div>
<div class="pxrow"><div><div class="lbl">{elbl}</div><div class="big">{fmt_px(entry)}</div><div class="lbl">{sub}</div></div>
<div class="r"><div class="lbl">BO</div><div class="big">{fmt_px(c["bo"])}</div><div class="lbl">C高點 {fmt_px(c["c_hv"])}</div></div></div>
<div class="lv"><div><span>SL</span><span>{fmt_px(sl)} <span class="neg">({_pct(sl, entry):.1f}%)</span></span></div>
<div><span>1:1.5</span><span>{fmt_px(c["tp1"])} <span class="pos">(+{_pct(c["tp1"], entry):.1f}%)</span></span></div>
<div><span>1:2</span><span>{fmt_px(c["tp2"])} <span class="pos">(+{_pct(c["tp2"], entry):.1f}%)</span></span></div></div>
</div>'''

def _render_done(c, tf):
    code = c['symbol'].replace('.KL', '')
    label = {'TP1': '✅ 達1:1.5', 'SL': '❌ 止損', 'TIMEOUT': '⏱ 20根到期'}.get(c['result'], c['result'])
    cls = 'pos' if c['r_mult'] > 0 else 'neg'
    return f'''<div class="card res-{c["result"]}" {_search_attr(c)}>
<div class="hd"><a href="{_tv_url(c, tf)}" target="_blank">{code}</a><span class="nm">{_nm(c)}</span><span class="dt">{label}</span></div>
{_card_tags(c, tf)}
<div class="line"><span>{_fmt_time(c["confirm_time"], tf)} 進場 {fmt_px(c["entry"])} → {_fmt_time(c.get("end_time"), tf)}</span><span class="{cls}">{c["r_mult"]:+.2f}R</span></div>
</div>'''

CARD_HELP_TOUCH = f"""・<b>條件</b>：某一根已收盤K線的「最高價」≥ BO，等於你在BO掛的觸價單成交了；收盤後才記錄（不用盤中還沒收完的K線）。<br>
・<b>進場價</b>= BO；如果當天開盤就跳空高過BO，觸價單會用開盤價成交，進場價＝開盤價。1:1.5 / 1:2 用進場價計算。<br>
・<b>為什麼這樣算</b>：⚖️進場比較回測證實，在BO掛單比等收盤確認才買總R比較好（價格優勢大過假突破的損失），而且跟你實際下單一樣，戰績才對得上交易日誌。<br>
・<b>✅ 收盤站穩</b>＝成交當天收盤也站上BO；<b>⚠️ 收盤沒站穩</b>＝盤中衝過、收盤跌回BO下面（假突破風險比較高，回測平均明顯比較差）。<br>
・<b>當天收盤</b>＝成交那天的收盤價；<b>現價（±R）</b>＝現在賺／虧幾R（R = 進場價 − SL）。<br>
・<b>已過 x/{MAX_HOLD_BARS} 根</b>= 成交後過了幾根K線。<b>⚠️不追</b>= 開盤跳空高過BO超過{CHASE_MAX_PCT:.0f}%（成交價離SL太遠）。<b>回補</b>= 第一次部署時回放最近{BACKFILL_BARS}根K線補抓的案例。<br>
・<b>🧱 威科夫燈號</b>：同一檔在威科夫頁目前的狀態，可以幫你決定成交後要不要繼續拿（特別是 ⚠️ 收盤沒站穩的單）。<br>
"""

def build_cards_html(tf):
    with cards_lock:
        pend = [dict(p) for p in cards_state['pending'].values() if p.get('tf') == tf]
        act  = [dict(a) for a in cards_state['active'].values() if a.get('tf') == tf]
        done = [dict(d) for d in cards_state['done'] if d.get('tf') == tf]
    quick = []
    for p in pend:
        price = p.get('price')
        if not price: continue
        d = _pct(p['bo'], price)
        if d <= QUICK_BO_PCT:
            quick.append((d, p))
    quick.sort(key=lambda x: x[0])
    act.sort(key=lambda a: a['confirm_time'], reverse=True)
    recent = sorted(done, key=lambda d: d.get('end_time', ''), reverse=True)[:24]

    with scan_state['lock']:
        status = scan_state['status']
        last = scan_state.get('last_scan') or '-'

    tfbar = ''.join(f'<a class="{"on" if t == tf else ""}" href="/cards?tf={t}">{t}</a>' for t in CARD_TFS)
    sector_opts = ''.join(f'<option value="{_h(s)}">{_h(s)}</option>' for s in sorted(set(SECTORS.values())))

    def grid(items, render, empty_msg):
        if not items:
            return f'<div class="empty">{empty_msg}</div>'
        return '<div class="grid">' + ''.join(render(x, tf) for x in items) + '</div>'

    stats_rows = ''
    for gname, label, s in compute_card_stats(tf):
        wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
        ar = f'{s["avg_r"]:+.2f}R' if s['avg_r'] is not None else '-'
        stats_rows += (f'<tr><td class="g">{gname}</td><td class="g">{label}</td><td>{s["n"]}</td>'
                       f'<td>{s["win"]}</td><td>{s["loss"]}</td><td>{s["timeout"]}</td><td>{wr}</td><td>{ar}</td></tr>')

    warn = '' if DATA_PERSISTENT else ('<div class="warnbox">⚠️ 目前沒有掛載Railway Volume（/data），重新部署後戰績紀錄會清空。'
                                       '請在Railway替這個服務加一個Volume，Mount Path填 /data。</div>')
    banner = '<div class="scanning-banner">⏳ 掃描中，資料會在掃完後自動更新...</div>' if status == 'scanning' else ''
    autopoll = ('<script>(function p(){fetch("/status").then(r=>r.json()).then(d=>{if(d.status==="done")location.reload();'
                'else setTimeout(p,8000)}).catch(()=>setTimeout(p,15000))})();</script>') if status == 'scanning' else ''

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🃏 大馬突破卡片</title><style>{CARDS_CSS}</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ 突破卡片</h2>
<div class="subtitle">BO = 最後一個C高點+緩衝（{"盤中碰到就算成交，收盤後記錄" if CARD_ENTRY_MODE == "touch" else "收盤確認"}）・ SL = 最後一個C低點−緩衝（天圖1%、時圖0.5%）・ 目標 1:1.5 / 1:2 ・ 至少C2、只看多頭</div>
<div class="nav"><a href="/">📊 C系列總表</a><a class="nav-on" href="/cards?tf={tf}">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a><a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>
{warn}{banner}
<div class="tfbar">{tfbar}</div>
<div class="ctrl"><select id="sec" onchange="f()"><option value="">全部板塊</option>{sector_opts}</select>
<input class="search-box" id="q" placeholder="搜尋代碼或名稱..." oninput="f()"></div>
<div style="color:#8b949e;font-size:12px">更新：{last}</div>

<div class="flow">流程：C系列形態成形 → <b>① 快突破</b>（等它突破）→ 某天{"盤中碰到BO（觸價成交）" if CARD_ENTRY_MODE == "touch" else "收盤站上BO"} → <b>② 已突破、進行中</b>（追蹤結果）→ 碰SL／達1:1.5／過{MAX_HOLD_BARS}根 → <b>③ 最近結束</b>（記錄成績）</div>

<div class="sec"><h3>📈 ① 快突破（{len(quick)}）</h3>
<div class="desc">快要突破了，先放進觀察名單：形態已成形，但還沒{"碰到" if CARD_ENTRY_MODE == "touch" else "收盤站上"}BO，現價離BO {QUICK_BO_PCT:.0f}% 以內。{"可以在BO預先掛觸價單。" if CARD_ENTRY_MODE == "touch" else ""}</div>
<details class="help"><summary>📖 詳細說明</summary><div>
・<b>條件</b>：C系列至少到C2、MA多頭排列；還沒有任何一根K線{"的最高價碰到" if CARD_ENTRY_MODE == "touch" else "「收盤」站上"}BO；現價離BO ≤ {QUICK_BO_PCT:.0f}%。<br>
・<b>🧱 威科夫燈號</b>：同一檔在「🧱 威科夫突破」頁目前的狀態（🟢真突破／🟠等回踩／🟡洗盤完成／⚪條件不全／❌跌回區間）。有吸籌背景的BO比較有故事，可以當掛單前的參考；沒有燈號＝威科夫沒看到區間。<br>
・<b>用途</b>：提前準備——先看圖、決定要不要做，可以在券商預先設好觸價單。<br>
・<b>BO（Trigger／進場點）</b>= 最後一個C的高點 + 緩衝（天圖1%、時圖0.5%）。<br>
・<b>SL</b> = 最後一個C的低點 − 緩衝（天圖1%、時圖0.5%）。<br>
・<b>1:1.5 / 1:2</b>：假設在BO價格進場來計算；括號裡的%是相對BO的距離。「差 x%」= 現價還要漲多少才到BO。<br>
・<b>接下來</b>：哪天{"最高價 ≥ BO（收盤後判斷）" if CARD_ENTRY_MODE == "touch" else "收盤 ≥ BO"} → 移到 ②；還沒突破就先跌破SL → 形態失敗，直接從名單消失（不會進 ③）。
</div></details>
{grid([p for _, p in quick], _render_pending, f"{tf}：目前沒有快突破的。")}</div>

<div class="sec"><h3>🚀 ② 已突破、進行中（{len(act)}）</h3>
<div class="desc">{"已經碰到BO（掛單已成交）" if CARD_ENTRY_MODE == "touch" else "已經收盤站上BO"}，正在追蹤結果：還沒碰到SL、也還沒到1:1.5，最多追蹤{MAX_HOLD_BARS}根K線。</div>
<details class="help"><summary>📖 詳細說明</summary><div>
{CARD_HELP_TOUCH if CARD_ENTRY_MODE == "touch" else ""}<div{" style='display:none'" if CARD_ENTRY_MODE == "touch" else ""}>
・<b>條件</b>：某一根K線「收盤價」≥ BO，系統就把那根的收盤價當成進場價，開始追蹤。<br>
・<b>為什麼要收盤才算</b>：盤中衝過BO、收盤又跌回來是常見的假突破，等收盤確認可以過濾一部分。<br>
・<b>確認價（進場）</b>= 突破那根K線的收盤價；1:1.5 / 1:2 改用確認價重新計算（括號%是相對確認價）。<br>
・<b>現價（±R）</b>= 如果在確認價進場，現在賺／虧幾R（R = 確認價 − SL）。<br>
・<b>已過 x/{MAX_HOLD_BARS} 根</b>= 突破後過了幾根K線。<br>
・<b>⚠️不追</b>= 確認價比BO高超過{CHASE_MAX_PCT:.0f}%（突破那天漲太多，追進去SL會很遠）。<b>回補</b>= 第一次部署時回放最近{BACKFILL_BARS}根K線補抓的案例。<br>
・<b>注意</b>：如果你實際在BO掛觸價買單，盤中一突破就成交，進場價會比確認價低、R會比卡片算的好。<br>
</div>・<b>接下來</b>：碰到SL、或達1:1.5、或過了{MAX_HOLD_BARS}根 → 移到 ③。<br>
・2026-10-30 前開始的卡片是舊算法（收盤確認，顯示「確認價」），會照舊走完。
</div></details>
{grid(act, _render_active, f"{tf}：目前沒有進行中的突破。")}</div>

<div class="sec"><h3>🏁 ③ 最近結束（{len(recent)}）</h3>
<div class="desc">已經有結果的案例，記錄下來算戰績（顯示最近24筆）。</div>
<details class="help"><summary>📖 詳細說明</summary><div>
・<b>✅ 達1:1.5</b>：碰到第一個目標，記 +1.5R。<br>
・<b>❌ 止損</b>：跌破SL，記 −1R（同一根K線同時碰到SL和目標，保守算止損）。<br>
・<b>⏱ {MAX_HOLD_BARS}根到期</b>：{MAX_HOLD_BARS}根K線內兩個都沒碰到，用當時收盤價算R（可能小賺或小虧）。<br>
・下方的<b>戰績統計</b>就是用這一區所有案例計算的（存在Volume，不會因部署消失）。
</div></details>
{grid(recent, _render_done, f"{tf}：還沒有結束的案例。")}</div>

<div class="sec"><h3>📊 戰績統計（{tf}・共{len(done)}筆）</h3>
<div class="desc">勝率 = 達1:1.5 ÷（達1:1.5 + 止損），到期的不算勝負但計入平均R。樣本少於30筆時參考就好。</div>
<table class="st"><tr><th>分組</th><th>條件</th><th>筆數</th><th>✅</th><th>❌</th><th>⏱</th><th>勝率</th><th>平均R</th></tr>{stats_rows}</table></div>

<div class="foot">只供自己研究：數字照規則自動計算，不是投資建議；過去戰績不代表未來。「回補」= 第一次部署時回放最近{BACKFILL_BARS}根K線補抓的案例。<br>
⏳ = 最後一個C的低點之後確認K線不到{PROVISIONAL_BARS}根 ・ 🔥 = 突破量 ≥ 20根均量{VOL_SURGE_X}倍 ・ ⚠️不追 = 進場價高於BO超過{CHASE_MAX_PCT:.0f}% ・ ✅／⚠️ = 進場當天收盤有沒有站上BO ・ 🧱 = 威科夫燈號 ・ 緩衝：天圖±1%、時圖±0.5%</div>
<script>
function f(){{var s=document.getElementById('sec').value,q=document.getElementById('q').value.toUpperCase();
document.querySelectorAll('.card').forEach(function(c){{var ok=(!s||c.getAttribute('data-sector')===s)&&(c.getAttribute('data-q')||'').indexOf(q)>-1;
c.style.display=ok?'':'none';}});}}
</script>{autopoll}
</body></html>'''

@app.route('/cards')
def cards_page():
    tf = request.args.get('tf', CARD_TFS[0] if CARD_TFS else '1D').upper()
    if tf not in CARD_TFS:
        tf = CARD_TFS[0] if CARD_TFS else '1D'
    try:
        return build_cards_html(tf)
    except Exception as e:
        log.error(f"build_cards_html error: {e}")
        return f"<html><body style='background:#1a1a2e;color:#eee;font-family:monospace;padding:40px'>🃏 卡片頁錯誤：{_h(e)}</body></html>", 200

@app.route('/cards_json')
def cards_json():
    """診斷用：看卡片原始資料。?symbol=0024 可只看某一檔"""
    sym = request.args.get('symbol', '').upper()
    with cards_lock:
        def match(k):
            return (not sym) or k.startswith(norm_sym(sym) + '|')
        out = {
            'data_dir': DATA_DIR, 'persistent': DATA_PERSISTENT,
            'pending': {k: v for k, v in cards_state['pending'].items() if match(k)},
            'active':  {k: v for k, v in cards_state['active'].items() if match(k)},
            'done':    [d for d in cards_state['done'] if match(d.get('key', ''))][-200:],
            'counts':  {'pending': len(cards_state['pending']), 'active': len(cards_state['active']),
                        'done': len(cards_state['done']), 'seen': len(cards_state['seen'])},
        }
    return Response(json.dumps(out, indent=2, ensure_ascii=False, default=str), mimetype='application/json')

@app.route('/backtest')
def backtest_page():
    """🧪 C1跌幅門檻回測頁面。?run=1D 開始跑（背景執行），可加 &limit=50 先試50檔"""
    run_tf = request.args.get('run', '').upper()
    if run_tf in TF_LABELS:
        limit = request.args.get('limit')
        limit = int(limit) if limit and limit.isdigit() else None
        threading.Thread(target=run_c1_backtest, args=(run_tf, None, limit), daemon=True).start()
        time.sleep(0.5)
        # 轉回不帶run參數的網址：否則頁面每30秒自動刷新時，跑完又會重新開始一次
        return redirect(f'{BASE}/backtest?tf={run_tf}')
    view_tf = request.args.get('tf', run_tf if run_tf in TF_LABELS else (bt_state.get('tf') or '1D')).upper()
    if view_tf not in TF_LABELS: view_tf = '1D'

    with bt_state['lock']:
        st = {k: v for k, v in bt_state.items() if k not in ('lock', 'results')}
        live_res = bt_state['results'] if bt_state.get('tf') == view_tf else None
    res = live_res or load_bt_result(view_tf)

    if st['status'] == 'running':
        pct = st['done'] / st['total'] * 100 if st['total'] else 0
        status_html = (f'<div class="scanning-banner">⏳ 回測中（{st["tf"]}）：{st["done"]}/{st["total"]} 檔（{pct:.0f}%）・'
                       f'開始於 {st["started"]}・全部約需20～60分鐘，頁面每30秒自動更新</div>'
                       '<script>setTimeout(function(){location.reload()},30000)</script>')
    elif st['status'] == 'error':
        status_html = f'<div class="warnbox">❌ 回測出錯：{_h(st["error"])}</div>'
    else:
        status_html = ''

    runbar = ''.join(f'<a href="/backtest?run={t}" onclick="return confirm(\'開始跑 {t} 回測？會在背景跑20～60分鐘\')">▶ 跑 {t} 回測</a>'
                     for t in TF_LABELS)
    tfbar = ''.join(f'<a class="{"on" if t == view_tf else ""}" href="/backtest?tf={t}">{t} 結果</a>' for t in TF_LABELS)

    body = ''
    if res:
        def row(c, key):
            s = c[key]
            wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
            ar = f'{s["avg_r"]:+.2f}R' if s['avg_r'] is not None else '-'
            return f'<td>{s["n"]}</td><td>{s["win"]}</td><td>{s["loss"]}</td><td>{s["timeout"]}</td><td>{wr}</td><td>{ar}</td><td>{s["total_r"]:+.1f}R</td>'
        rows = ''
        for c in res['configs']:
            rows += (f'<tr><td class="g"><b>{_h(c["name"])}</b></td><td class="g">全部</td>{row(c, "all")}'
                     f'<td>{c["stocks"]}</td><td>{c["open"]}</td></tr>')
            rows += f'<tr><td></td><td class="g">只看日線S2</td>{row(c, "s2")}<td></td><td></td></tr>'
            rows += f'<tr><td></td><td class="g">排除⚠️不追</td>{row(c, "nochase")}<td></td><td></td></tr>'
        recent = ''
        for c in res['configs']:
            items = c['cases'][:15]
            _cur = c.get('cfg', {}).get('min_drop') == MIN_DROP_PCT
            _lk = lambda x: (f'<a href="/stock_bt?symbol={_h(sym_code(x["symbol"]))}&amp;strategy=vcp&amp;tf={res["tf"]}&amp;focus={_h(x.get("confirm_time") or "")}" style="color:#7ab3ff">'
                             f'<b>{_h(sym_code(x["symbol"]))}</b></a>') if _cur else f'<b>{_h(sym_code(x["symbol"]))}</b>'
            li = ''.join(
                f'<div>{_fmt_time(x["confirm_time"], res["tf"])} {_lk(x)} {_h(x.get("name") or "")} '
                f'進場{fmt_px(x["entry"])} SL{fmt_px(x["sl"])} → '
                f'<span class="{"pos" if x["r_mult"] > 0 else "neg"}">{x["result"]} {x["r_mult"]:+.2f}R</span></div>'
                for x in items)
            recent += f'<details><summary>{_h(c["name"])}：最近15筆案例</summary><div class="lst">{li or "沒有案例"}</div></details>'
        body = f'''
<div class="desc">期間 {res["period"][0]} ～ {res["period"][1]}・{res["symbols"]}檔・每檔最近{res["bars"]}根{res["tf"]}K線・完成於 {res["finished"]}</div>
<table class="st"><tr><th>C1門檻</th><th>範圍</th><th>筆數</th><th>✅</th><th>❌</th><th>⏱</th><th>勝率</th><th>平均R</th><th>總R</th><th>出現股票數</th><th>結尾未結束</th></tr>{rows}</table>
<div class="sec"><h3>🔍 抽查案例</h3><div class="desc">可以挑幾筆到TradingView核對，確認回測有照規則跑。</div>{recent}</div>'''
    else:
        body = f'<div class="empty">{view_tf}：還沒有回測結果。按上面「▶ 跑 {view_tf} 回測」開始。</div>'

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🧪 C1門檻回測</title><style>{CARDS_CSS}
details{{background:#22223a;border:1px solid #3a3a55;border-radius:6px;padding:8px 12px;margin-bottom:6px;max-width:1150px}}
summary{{cursor:pointer;color:#ffb74d}} .lst{{font-size:12px;line-height:1.8;margin-top:6px}}</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ C1跌幅門檻回測</h2>
<div class="subtitle">用歷史K線重播突破卡片的完整規則（BO/SL/1:1.5/20根到期），只改C1跌幅門檻，比較哪一種比較好。正式掃描完全不受影響。</div>
<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a><a class="nav-on" href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>
{status_html}
<div class="tfbar">{runbar}</div>
<div class="tfbar">{tfbar}</div>
{body}
<div class="foot">勝率 = ✅ ÷（✅+❌）；⏱ = 20根到期（不算勝負，但計入平均R和總R）。「總R」= 每筆都冒1R風險時累積的結果，比勝率更能看出整體賺不賺。<br>
ATR% = 14根平均真實波幅 ÷ 收盤價；「3×ATR%」= C1跌幅要超過候選高點那根的ATR%的3倍（波動大的股票門檻自動變高）。<br>
注意：回測沒算手續費和滑價；同一檔可能同時出現多筆；樣本少於30筆的結果參考就好。</div>
</body></html>'''


# ============================================================
# 🧱 威科夫卡片（MH 2026-10-28 選B）：🟢 和 🟠 用卡片顯示，🟡／⚪／❌／⛔ 維持表格
# ============================================================
WY_CARD_CSS = ('.card.wyg{border-left-color:#4cc28e}.card.wyo{border-left-color:#ff8a3d}'
               '.story{font-size:11px;color:#aab;line-height:1.7;margin:4px 0 2px}.story b{color:#ddd}'
               '.wynote{font-size:11px;color:#8b949e;margin-top:7px;line-height:1.5}'
               '.tag.track{border-color:#4cc28e;color:#a5d6a7}.hd a.sclk{font-size:12px;margin-left:6px;text-decoration:none}')

def _wy_fp(v):
    return '—' if v is None else fmt_px(v)

def _wy_card_tags(r, extra=None):
    st = r.get('day_stage', '--')
    tags = [f'<span class="tag">{_h(r.get("sector") or "其他")}</span>',
            f'<span class="tag {"s2" if st == "S2" else "sx"}">日線{_h(st)}</span>',
            f'<span class="tag">{_h(r.get("position") or "")}</span>']
    if r.get('loud_mult') is not None:
        tags.append(f'<span class="tag hot">🔥突破量{r["loud_mult"]:.1f}x</span>')
    if r.get('redist'):
        tags.append('<span class="tag warn">⚠️ S4再派發？</span>')
    to = r.get('turnover')
    if to is not None:
        tags.append(f'<span class="tag{"" if r.get("liquid") else " warn"}">成交額{_fmt_turnover(to)}{"" if r.get("liquid") else " 💧不推"}</span>')
    if extra:
        tags.extend(extra)
    return '<div class="tags">' + ''.join(tags) + '</div>'

def _wy_story(r):
    ok = lambda b: '✓' if b else '✗'
    parts = [f'<b>區間</b> {r["range_from"]} 起 {r["range_days"]} 天（天花板 {_wy_fp(r["ceiling"])}／地板 {_wy_fp(r["floor"])}）',
             f'<b>洗盤</b> {r["spring_date"]} 刺穿 {r["spring_depth"]:.1f}%']
    if r.get('quiet_ratio') is not None:
        parts.append(f'<b>安靜</b> {ok(r.get("quiet_ok"))} {r["quiet_ratio"]:.1f}x')
    if r.get('bo_date'):
        parts.append(f'<b>大聲</b> {ok(r.get("loud_ok"))} {r["bo_date"]} {r.get("loud_mult") or 0:.1f}x')
    if r.get('retest_date'):
        parts.append(f'<b>站穩</b> {ok(r.get("retest_ok"))} {r["retest_date"]} 低點 {_wy_fp(r.get("retest_low"))}')
    return '<div class="story">' + ' → '.join(parts) + '</div>'

def _wy_head(r, badge):
    tv = f"{tv_chart_base()}?symbol={r.get('tv_symbol') or tv_sym(r['symbol'])}&interval=D"
    return (f'<div class="hd"><a href="{tv}" target="_blank">{sym_code(r["symbol"])}</a>'
            f'<span class="nm">{_nm(r)}</span><a class="sclk" href="/stock_card?symbol={sym_code(r["symbol"])}" title="單股卡片＋分析">🔎</a>{badge}</div>')

def _wy_track_tag(sym):
    with wy_cases_lock:
        for c in wy_cases['active'].values():
            if c['symbol'] == sym:
                px = c.get('price') or c.get('last_close') or c['fill']
                return f'<span class="tag track">📊 已成交 {fmt_px(c["fill"])}・{(px - c["fill"]) / c["R"]:+.2f}R</span>'
        for c in wy_cases['pending'].values():
            if c['symbol'] == sym:
                return f'<span class="tag track">📊 等觸發 {c.get("waited", 0)}/{WY_TRIGGER_DAYS} 天</span>'
    return None

def wy_card_green(r):
    entry, sl, price = r['entry'], r['sl'], r.get('price') or 0
    r1 = entry - sl
    tp = entry + WY_TP_R * r1
    if price and price > entry:
        badge = '<span class="dist over">現價已過Entry・不追</span>'
    elif price:
        badge = f'<span class="dist">差 {_pct(entry, price):.1f}%</span>'
    else:
        badge = ''
    extra = []
    if r.get('risk_atr') and r['risk_atr'] > WY_RISK_MAX_ATR:
        extra.append(f'<span class="tag warn">⚠️ SL {r["risk_atr"]:.1f}倍ATR・改4H/1H找C</span>')
    tt = _wy_track_tag(r['symbol'])
    if tt:
        extra.append(tt)
    wr = r.get('wall_r')
    if r.get('wall') is None:
        wall_txt, wall_cls = '藍天（上方沒有日線牆）', 'pos'
    else:
        wall_txt = f'{wr:.2f}R（{r.get("wall_tier") or ""}級牆 {_wy_fp(r["wall"])}）'
        wall_cls = 'pos' if wr >= HEADROOM_MIN_R else 'neg'
    tps = '、'.join(_wy_fp(t) for t in r.get('tps') or []) or '—'
    return f'''<div class="card wyg">
{_wy_head(r, badge)}
{_wy_card_tags(r, extra)}
{_wy_story(r)}
<div class="pxrow"><div><div class="lbl">現價</div><div class="big">{_wy_fp(price)}</div></div>
<div class="r"><div class="lbl">Entry（觸價買入）</div><div class="big">{_wy_fp(entry)}</div><div class="lbl">回踩後反彈高點 +0.5%</div></div></div>
<div class="lv"><div><span>SL</span><span>{_wy_fp(sl)} <span class="neg">({_pct(sl, entry):.1f}%)</span></span></div>
<div><span>1:{WY_TP_R:g}</span><span>{_wy_fp(tp)} <span class="pos">(+{_pct(tp, entry):.1f}%)</span></span></div>
<div><span>上方空間</span><span class="{wall_cls}">{wall_txt}</span></div>
<div><span>TP參考</span><span>{tps}</span></div></div>
<div class="wynote">{r.get("note", "")}</div>
</div>'''

def wy_card_orange(r):
    price, ceil = r.get('price') or 0, r['ceiling']
    badge = f'<span class="dist">突破 {r.get("bo_days_ago", 0)} 天</span>'
    near = ceil * (1 + WY_RETEST_NEAR_PCT / 100)
    to_ceil = _pct(price, ceil) if price else None
    return f'''<div class="card wyo">
{_wy_head(r, badge)}
{_wy_card_tags(r)}
{_wy_story(r)}
<div class="pxrow"><div><div class="lbl">現價</div><div class="big">{_wy_fp(price)}</div></div>
<div class="r"><div class="lbl">天花板（等回踩到這裡）</div><div class="big">{_wy_fp(ceil)}</div>
<div class="lbl">{"高於天花板 " + f"{to_ceil:+.1f}%" if to_ceil is not None else ""}</div></div></div>
<div class="lv"><div><span>回踩區</span><span>{_wy_fp(ceil)} ～ {_wy_fp(near)}</span></div>
<div><span>突破那天</span><span>{r.get("bo_date") or "—"}・量 {r.get("loud_mult") or 0:.1f}x・收盤位置 {r.get("loud_close_pos") or 0:.2f}</span></div>
<div><span>地板</span><span>{_wy_fp(r.get("floor"))}</span></div></div>
<div class="wynote">{r.get("note", "")}</div>
</div>'''

def generate_wyckoff_html():
    """跟加密版 /wyckoff 同一個版面（表格欄位、階段、說明文字），只換成馬股的顯示方式"""
    with WY_LOCK:
        st = {k: v for k, v in WY_STATE.items() if k != 'rows'}
        rows = list(WY_STATE['rows'])
    with scan_state['lock']:
        scanning = scan_state['status'] == 'scanning'
    f = lambda v: '—' if v is None else fmt_px(v)
    x = lambda v: '—' if v is None else f'{v:.1f}x'
    ok = lambda b: '<span style="color:#4cc28e">✓</span>' if b else '<span style="color:#ee7373">✗</span>'
    css = ('table.wy{border-collapse:collapse;font-size:13px;min-width:900px}table.wy th,table.wy td{border:1px solid #444;padding:5px 8px;vertical-align:top}'
           'table.wy th{background:#26264a;position:sticky;top:0}table.wy td.c{text-align:center}table.wy a{color:#84aedb;text-decoration:none}'
           '.note{color:#aab;font-size:13px;max-width:1100px;line-height:1.6}.wrap{overflow-x:auto}.small{font-size:12px;color:#bbb}'
           'h3.wyh{margin:20px 0 6px;font-size:16px}details summary{cursor:pointer}')
    autopoll = ('<script>(function p(){fetch("/status").then(r=>r.json()).then(d=>{if(d.status==="done")location.reload();'
                'else setTimeout(p,15000)}).catch(()=>setTimeout(p,20000))})();</script>') if scanning else ''
    banner = '<div class="scanning-banner">⏳ C系列掃描進行中，威科夫名單會在掃完後自動更新...</div>' if scanning else ''
    html = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>🧱 大馬威科夫</title><style>{CARDS_CSS}{css}{WY_CARD_CSS}</style></head><body>'
            '<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ 威科夫：洗盤 → 真突破（日線）</h2>'
            '<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a class="nav-on" href="/wyckoff">🧱 威科夫突破</a>'
            '<a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>'
            f'{banner}'
            f'<p class=note>最後更新 {st["last_update"] or "—"}｜跟著C系列掃描一起跑：開市時間每小時一次＋17:40收盤後一次。'
            '階段只用「已收盤」的日K判斷（收盤後才會變）；重點名單／🟠／🟢 在開市時間每小時盯盤，有事推 Telegram。</p>'
            f'<p class=note>三個條件：<b>突破前安靜</b>（突破前 {WY_QUIET_WIN} 天裡最安靜的連續 {WY_QUIET_RUN} 天，均量 ≤ {WY_QUIET_MAX:g}×50日均量）、'
            f'<b>突破時大聲</b>（{WY_LOUD_MIN:g}～{WY_LOUD_MAX:g}× 均量、收在K線上半部；超過 {WY_LOUD_MAX:g} 倍＝爆量異常，像拉盤）、'
            f'<b>回頭站得穩</b>（突破後 {WY_RETEST_MAX_DAYS} 天內回踩到天花板、從高點回落 ≤ {WY_RETEST_MAX_DROP:g}%、收盤守住、'
            f'回踩量 ≤ 突破當天 {WY_RETEST_VOL_MAX:.0%} 而且 ≤ 平常量 {WY_RETEST_VOL_MA_MAX:g} 倍）。'
            '「漲後高位」的區間就算三個條件都過，也只放在 ⚪。成交量資料不夠（零成交日太多）放在 ⛔，不判斷。'
            '前提：區間裡要先有一次假跌破洗盤。這是找圖的漁網，故事和上方的牆還是要自己看。</p>'
            + wy_funnel_html(rows))

    def table(sub, stage):
        h = ('<div class=wrap><table class=wy><tr><th>股票</th><th>日線</th><th>位置</th><th>區間</th><th>洗盤</th>'
             '<th>安靜</th><th>大聲</th><th>站穩</th>')
        h += '<th>Entry / SL / 上方空間</th>' if stage == 'green' else ''
        h += '<th>說明</th></tr>'
        for r in sub:
            code = sym_code(r['symbol'])
            tv = f"{tv_chart_base()}?symbol={r.get('tv_symbol') or tv_sym(r['symbol'])}&interval=D"
            rng = f'{r["range_from"]} 起 {r["range_days"]} 天<br><span class=small>天花板 {f(r["ceiling"])}<br>地板 {f(r["floor"])}</span>'
            spring = f'{r["spring_date"]} 刺穿 {r["spring_depth"]:.1f}%<br><span class=small>低點 {f(r["spring_low"])}，量 {x(r.get("spring_vol"))}</span>'
            quiet = f'{ok(r["quiet_ok"])} {x(r.get("quiet_ratio"))}'
            if r.get('quiet_from'):
                quiet += f'<br><span class=small>{r["quiet_from"]} 起{WY_QUIET_RUN}天</span>'
            loud = (f'{ok(r["loud_ok"])} {r["bo_date"]} {x(r.get("loud_mult"))}<br><span class=small>收盤位置 {r["loud_close_pos"]:.2f}</span>'
                    if r.get('bo_date') else '—')
            if r.get('retest_date'):
                vm = r.get('retest_vol_ma')
                vm_txt = f'，平常量 {vm:.1f}x' if vm is not None else ''
                hold = (f'{ok(r["retest_ok"])} {r["retest_date"]}<br><span class=small>低點 {f(r["retest_low"])}，'
                        f'突破量的 {(r["retest_vol"] or 0):.0%}{vm_txt}</span>')
            else:
                hold = '—'
            h += (f'<tr><td><a href="{tv}" target="_blank"><b>{code}</b></a> <span class=small>{_nm(r)}</span>'
                  f'<br><span class=small>{_h(r.get("sector") or "")}・{f(r["price"])}</span>'
                  f'<br><span class=small>成交額 {_fmt_turnover(r.get("turnover"))}'
                  + ('' if r.get('liquid') else ' <span style="color:#ee7373">💧不推</span>') + '</span></td>'
                  f'<td class=c>{r.get("day_stage", "--")}</td><td>{r["position"]}</td><td>{rng}</td><td>{spring}</td>'
                  f'<td class=c>{quiet}</td><td>{loud}</td><td>{hold}</td>')
            if stage == 'green':
                wr = r.get('wall_r')
                wr_txt = '藍天（上方沒有日線牆）' if r.get('wall') is None else f'{wr:.2f}R（{r.get("wall_tier") or ""}級牆 {f(r["wall"])}）'
                if r.get('wall') is not None and r.get('wall_tier') == 'B':
                    ar = r.get('wallA_r')
                    wr_txt += '<br><span class=small>' + (f'最近A級牆 {f(r["wallA"])}：{ar:.2f}R' if r.get('wallA') else '上方沒有A級牆') + '</span>'
                col = '#4cc28e' if (wr is None or wr >= HEADROOM_MIN_R) else '#ee7373'
                tps = '、'.join(f(t) for t in r.get('tps') or []) or '—'
                h += (f'<td>Entry <b>{f(r["entry"])}</b><br>SL <b>{f(r["sl"])}</b>（1R {f(r["r1"])}）<br>'
                      f'<span style="color:{col}">上方空間 {wr_txt}</span><br><span class=small>TP參考：{tps}</span></td>')
            h += f'<td class=small>{r.get("note", "")}</td></tr>'
        return h + '</table></div>'

    if not rows and st['status'] != 'done':
        html += '<div class="empty">還沒有威科夫結果：等這一輪C系列掃描跑完（約10分鐘）就會出現。</div>'
    for stage in ('green', 'orange', 'yellow', 'weak', 'fail', 'nodata'):
        sub = [r for r in rows if r['stage'] == stage]
        label, bg = WY_STAGE_META[stage]
        if stage == 'nodata':
            if sub:
                html += (f'<details><summary class=note style="border-left:6px solid {bg};padding-left:8px">'
                         f'{label}（{len(sub)}）— 點這裡展開</summary>' + table(sub, stage) + '</details>')
            continue
        html += f'<h3 class=wyh style="border-left:6px solid {bg};padding-left:8px">{label}（{len(sub)}）</h3>'
        if stage == 'green':
            html += wy_green_rules_html()
        if not sub:
            html += '<p class=note>沒有。</p>'
            continue
        if stage in ('green', 'orange'):          # 🧱 卡片
            render = wy_card_green if stage == 'green' else wy_card_orange
            html += '<div class="grid">' + ''.join(render(r) for r in sub) + '</div>'
            continue
        if stage == 'yellow':
            focus = [r for r in sub if r.get('focus')]
            rest = [r for r in sub if not r.get('focus')]
            html += (f'<p class=note><b>重點名單（{len(focus)}）</b>：離天花板 ≤ {WY_NEAR_CEIL_PCT:g}%、安靜 ✓、不是「S4＋中途整理」。'
                     '這些股票在開市時間每小時盯盤，正在突破時會推 Telegram（成交額 < '+_fmt_turnover(TG_MIN_TURNOVER_MYR)+' 的標 💧不推，只在網頁顯示）。</p>')
            html += table(focus, stage) if focus else '<p class=note>今天沒有。</p>'
            if rest:
                html += (f'<details><summary class=note>其他 {len(rest)} 個（離天花板太遠、量還沒縮，或下跌途中的橫盤）'
                         '— 點這裡展開</summary>' + table(rest, stage) + '</details>')
            continue
        html += table(sub, stage)
    try:
        html += wy_tracking_html()
    except Exception as e:
        html += f'<p class=note>結果追蹤顯示錯誤：{_h(e)}</p>'
    if st['errors']:
        html += ('<details><summary class=note>錯誤 ' + str(len(st['errors'])) + ' 筆</summary><pre>'
                 + _h('\n'.join(st['errors'][:50])) + '</pre></details>')
    return html + autopoll + '</body></html>'

@app.route('/wyckoff')
def wyckoff_page():
    try:
        return Response(generate_wyckoff_html(), mimetype='text/html')
    except Exception as e:
        log.error(f"wyckoff page error: {e}")
        return f"<html><body style='background:#1a1a2e;color:#eee;font-family:monospace;padding:40px'>🧱 威科夫頁錯誤：{_h(e)}</body></html>", 200

@app.route('/wyckoff_push')
def wyckoff_push():
    """手動推一次目前威科夫名單到Telegram：/wyckoff_push"""
    with WY_LOCK:
        rows = list(WY_STATE['rows'])
    if not rows:
        return jsonify({'sent': False, 'reason': '還沒有威科夫結果，等掃描跑完'})
    ok = send_telegram_plain(wy_summary_text(rows, '目前名單（手動）'))
    return jsonify({'sent': bool(ok), 'rows': len(rows)})

@app.route('/wyckoff_backtest')
def wyckoff_backtest_route():
    """▶ 開始威科夫歷史回測（背景執行）：/wyckoff_backtest?run=1&limit=50"""
    if request.args.get('run'):
        lim = request.args.get('limit')
        threading.Thread(target=run_wy_backtest, kwargs={'limit': int(lim) if lim and lim.isdigit() else None}, daemon=True).start()
    return redirect(f'{BASE}/wyckoff#wybt')

@app.route('/debug_wyckoff')
def debug_wyckoff():
    """診斷用：/debug_wyckoff?symbol=0128"""
    sym = norm_sym(request.args.get('symbol', M['default_sym']))
    try:
        df = fetch_ohlcv(sym, '1D')
        closed = closed_bars(df, '1D').tail(500)
        r = wy_analyze(sym, closed) if len(closed) >= 121 else None
        out = {'symbol': sym, 'bars': len(closed), 'last_closed': str(closed.index[-1]) if len(closed) else None, 'result': r}
    except Exception as e:
        out = {'error': f'{type(e).__name__}: {e}'}
    return Response(json.dumps(out, ensure_ascii=False, indent=2, default=str), mimetype='application/json')

# ============================================================
# 🔎 單股卡片（MH 2026-10-30）：選一檔，看它現在的威科夫卡片＋VCP卡片＋「一眼看懂」分析
# 用跟正式掃描同一套函式（wy_analyze／analyze／_setup_from_analysis），只是即時只算這一檔
# ============================================================
SC_CACHE = {}
SC_CACHE_SEC = 300   # 同一檔5分鐘內重看不重新抓資料

WY_STAGE_PLAIN = {
    'green':  ('三個條件都過了：洗盤 → 安靜 → 大聲突破 → 回踩站穩。', '看上方空間和SL距離，合格就在 Entry 掛觸價單。'),
    'orange': ('已經放量突破天花板，還在等回踩確認。', '不追。等價格回到回踩區、守住天花板，變成 🟢 再說。'),
    'yellow': ('區間裡已經洗過盤，還沒突破。', '等放量收盤突破天花板（變 🟠）；離天花板近、量在縮的最值得盯。'),
    'weak':   ('突破了，但條件不全（量、回踩或位置有問題）。', '容易是假突破，只觀察，不動手。'),
    'fail':   ('突破後收盤跌回區間：假突破。', '不做。等它重新整理出新的區間。'),
    'nodata': ('成交量資料不足，量比會失真。', '系統不判斷，自己看圖。'),
}

def wy_card_generic(r):
    """🟡／⚪／❌／⛔ 也用卡片格式顯示（威科夫頁本來是表格）"""
    stage = r['stage']
    label, color = WY_STAGE_META.get(stage, ('', '#555'))
    price, ceil = r.get('price') or 0, r.get('ceiling')
    to_ceil = _pct(price, ceil) if (price and ceil) else None
    badge = f'<span class="dist" style="background:{color};color:#fff">{label.split(" ")[0]}</span>'
    rows = f'<div><span>天花板</span><span>{_wy_fp(ceil)}{f"（現價 {to_ceil:+.1f}%）" if to_ceil is not None else ""}</span></div>'
    rows += f'<div><span>地板</span><span>{_wy_fp(r.get("floor"))}</span></div>'
    if r.get('bo_date'):
        rows += f'<div><span>突破那天</span><span>{r["bo_date"]}・量 {r.get("loud_mult") or 0:.1f}x・收盤位置 {r.get("loud_close_pos") or 0:.2f}</span></div>'
    elif r.get('quiet_ratio') is not None:
        rows += f'<div><span>最近量能</span><span>{r["quiet_ratio"]:.2f}x 50日均量（{"在縮 ✓" if r.get("quiet_ok") else "還沒縮"}）</span></div>'
    return f'''<div class="card" style="border-left-color:{color}">
{_wy_head(r, badge)}
{_wy_card_tags(r)}
{_wy_story(r) if r.get("spring_date") else ""}
<div class="pxrow"><div><div class="lbl">現價</div><div class="big">{_wy_fp(price)}</div></div>
<div class="r"><div class="lbl">{"天花板（突破點）" if stage == "yellow" else "天花板"}</div><div class="big">{_wy_fp(ceil)}</div></div></div>
<div class="lv">{rows}</div>
<div class="wynote">{r.get("note", "")}</div>
</div>'''

def stock_card_data(sym):
    hit = SC_CACHE.get(sym)
    if hit and time.time() - hit[0] < SC_CACHE_SEC:
        return hit[1]
    meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)), 'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
    out = {'meta': meta, 'error': None, 'wy': None, 'vcp': None}
    df = fetch_ohlcv(sym, '1D')
    if df.empty or len(df) < 130:
        out['error'] = f'日線資料不夠（只有 {len(df)} 根）。'
        return out
    closed = closed_bars(df, '1D')
    tail = closed.tail(20)
    meta['turnover'] = float((tail['close'] * tail['volume']).mean()) if len(tail) else None
    meta['price'] = float(df['close'].values[-1])
    meta['price_time'] = str(df.index[-1])[:10]
    liquid = meta['turnover'] is not None and meta['turnover'] >= TG_MIN_TURNOVER_MYR
    try:
        meta['day_stage'] = STAGE_LABEL_MAP.get(get_stage(closed)[0], '--')
    except Exception:
        meta['day_stage'] = '--'
    # 🧱 威科夫（跟 wy_process_symbol 同一套）
    if len(closed) >= 121:
        ddf = closed.tail(500)
        r = wy_analyze(sym, ddf)
        if r:
            r['day_stage'] = meta['day_stage']
            r['redist'] = (meta['day_stage'] == 'S4' and r['position'] == '中途整理')
            if r['redist']:
                r['note'] = '⚠️ 日線S4、下跌途中的橫盤，小心是再派發（中途再出一次貨，之後繼續跌）。' + r.get('note', '')
            r.update({'name': meta['name'], 'sector': meta['sector'], 'tv_symbol': meta['tv_symbol'],
                      'turnover': meta['turnover'], 'liquid': liquid, 'price': meta['price']})
            out['wy'] = r
    # 🃏 VCP：先看正式卡片有沒有這一檔，沒有就即時算一次
    key = f'{sym}|1D'
    with cards_lock:
        act = next((dict(c) for c in cards_state['active'].values() if c.get('key') == key), None)
        pend = dict(cards_state['pending'][key]) if key in cards_state['pending'] else None
    wy_stage = out['wy']['stage'] if out['wy'] else None
    if act:
        act.update({'price': meta['price'], 'wy': wy_stage})
        out['vcp'] = {'kind': 'active', 'card': act}
    else:
        res = analyze(df, df)
        setup = pend or _setup_from_analysis(df, res, '1D')
        if setup:
            setup = dict(setup)
            setup.update({'symbol': sym, 'name': meta['name'], 'sector': meta['sector'], 'tv_symbol': meta['tv_symbol'],
                          'price': meta['price'], 'turnover': meta['turnover'], 'wy': wy_stage, 'tf': '1D'})
            used = f"{key}|{setup['h_time']}" in cards_state['used']
            out['vcp'] = {'kind': 'used' if used else 'pending', 'card': setup}
        else:
            out['vcp'] = {'kind': 'none', 'c_count': res.get('c_count', 0), 'has_c': res.get('has_c'),
                          'is_bear': res.get('is_bear'), 'stage': res.get('stage', 0)}
    SC_CACHE[sym] = (time.time(), out)
    return out

def wy_story_plain(r):
    """🧱 把威科夫的每一步翻成白話故事（只用已經算出來的數字，不另外判斷）"""
    if not r:
        return ['這一檔最近沒有出現「先洗盤、再整理」的橫盤區間，所以威科夫沒有故事可以講。']
    fp = _wy_fp
    miss = set(r.get('miss') or [])
    out = []
    pos = r.get('position') or ''
    out.append(f'從 {r.get("range_from")} 開始，股價在 {fp(r.get("floor"))}～{fp(r.get("ceiling"))} 之間橫盤了大約 {r.get("range_days")} 天'
               + (f'（{pos}）' if pos else '') + '。上面的天花板是賣壓，下面的地板是買盤。')
    if r.get('spring_date'):
        sv = r.get('spring_vol')
        vtxt = '' if sv is None else ('，當時量不大，代表真正想賣的人不多' if sv < 1.2 else f'，當時量放到 {sv:.1f} 倍，有人恐慌賣出')
        out.append(f'{r["spring_date"]} 股價跌破地板 {r.get("spring_depth") or 0:.1f}%，但很快又收回來{vtxt}。'
                   '這就是「洗盤」：故意製造跌破，把怕跌的人洗出去，籌碼落到有耐心的人手上。')
    qr = r.get('quiet_ratio')
    if qr is not None:
        if r.get('quiet_ok'):
            out.append(f'之後成交量縮到平常的 {qr:.1f} 倍，市場變得很安靜：想賣的人差不多賣完了，籌碼越來越穩。')
        else:
            out.append(f'不過成交量只縮到平常的 {qr:.1f} 倍，還不夠安靜：市場上還有人在賣，籌碼還沒完全沉澱。')
    if r.get('bo_date'):
        lm, cp = r.get('loud_mult') or 0, r.get('loud_close_pos') or 0
        if 'loud_high' in miss or r.get('loud_big'):
            out.append(f'{r["bo_date"]} 爆量 {lm:.0f} 倍衝過天花板。量太誇張，比較像消息或拉盤，不像有計劃的吸籌後突破。')
        elif 'loud_low' in miss:
            out.append(f'{r["bo_date"]} 收盤站上天花板，但量只有 {lm:.1f} 倍，買盤不夠積極，突破的力道偏弱。')
        elif 'close_pos' in miss:
            out.append(f'{r["bo_date"]} 突破天花板，量 {lm:.1f} 倍，但收在K線下半部（上影線長）：衝上去後馬上有人在高位賣。')
        else:
            out.append(f'{r["bo_date"]} 放量 {lm:.1f} 倍收盤站上天花板，而且收在K線上半部：買盤主動進場，把賣壓一口氣吃掉。')
    st = r['stage']
    if st == 'fail':
        out.append('可惜之後收盤又跌回天花板下面：突破是假的，追進去的人被套。這種情況先放一邊，等它重新整理。')
    elif st == 'orange' and r.get('retest_date'):
        out.append(f'{r["retest_date"]} 已經回踩到天花板附近，但還沒確認守住（或回踩時量太大）。要等回踩結束、價格重新站穩，才知道舊天花板是不是變成新地板。')
    elif st == 'orange':
        out.append(f'突破到現在 {r.get("bo_days_ago", 0)} 天，還沒回頭測試天花板。舊天花板能不能變成新地板還不知道，現在追就是買在高位。')
    elif st == 'green' and r.get('retest_date'):
        out.append(f'{r["retest_date"]} 價格回踩到天花板附近，低點 {fp(r.get("retest_low"))} 守住了，回踩時量也小：'
                   '舊的天花板變成新的地板，賣壓沒有回來。這是「回頭站得穩」。')
    elif st == 'weak':
        if 'retest_deep' in miss or 'retest_late' in miss:
            out.append('之後回落太深（或拖太久）才回來，比較像追高的人在獲利了結，不是健康的回踩確認。')
        elif 'no_retest' in miss:
            out.append(f'突破已經 {r.get("bo_days_ago", 0)} 天都沒回踩，這次突破的回踩窗口已經過了。')
    elif st == 'yellow':
        out.append(f'現在價格離天花板 {r.get("dist_pct") or 0:.1f}%，還在區間裡。'
                   + ('量在縮，像是在等待突破的那一天。' if r.get('quiet_ok') else '量還沒縮，還要再等等。'))
    if 'high_pos' in miss or pos.startswith('漲後'):
        out.append('⚠️ 要小心：這個區間出現在一大段上漲之後，同樣的走勢也可能是莊家在高位出貨，不一定是吸籌。')
    if r.get('redist'):
        out.append('⚠️ 日線是 S4（下跌趨勢），下跌途中的橫盤可能是「再派發」：中途再出一次貨，之後繼續跌。')
    ending = {
        'green': '整個故事：橫盤吸籌 → 洗盤 → 安靜 → 大聲突破 → 回頭站穩，四步都齊了。',
        'orange': '故事走到「大聲突破」，還差最後一步「回頭站穩」。',
        'yellow': '故事走到「洗盤、整理」，還在等突破。',
        'weak': '故事有破綻，所以系統只放在觀察。',
        'fail': '故事在突破這一步失敗了。',
        'nodata': '成交量資料不夠，量的部分可能不準，故事要自己看圖確認。',
    }.get(st)
    if ending:
        out.append(ending)
    return out

def vcp_story_plain(v, m):
    """🃏 VCP（C系列收縮）的白話故事"""
    kind = v['kind'] if v else 'none'
    stage_txt = '日線 S2 上升趨勢裡' if m.get('day_stage') == 'S2' else f'日線 {m.get("day_stage", "--")}（不是上升趨勢）'
    if kind == 'none':
        if v and v.get('is_bear'):
            return ['最近的收縮是空頭方向（越跌越收斂），不是做多的形態。']
        if v and v.get('has_c'):
            return [f'{stage_txt}，目前只看到 {v.get("c_count", 0)} 段收縮，還要再收縮一次（至少 C2）才算成形。']
        return ['目前沒有看到一段一段越來越小的收縮，VCP 還沒開始。']
    c = v['card']
    out = []
    pct = c.get('pct')
    out.append(f'{stage_txt}，股價拉回整理，出現 {c.get("c_count")} 段收縮'
               + (f'，最後一段只有 {pct:.1f}%' if isinstance(pct, (int, float)) else '')
               + '。每一次拉回都比上一次小，代表賣壓一次比一次輕，籌碼越來越集中。')
    if c.get('provisional'):
        out.append('⏳ 不過最後一段的低點才剛出現、還沒被確認，可能還會再低一點。')
    out.append(f'最後一段收縮的高點是 {fmt_px(c.get("c_hv"))}，突破 BO {fmt_px(c.get("bo"))} 就代表價格脫離收縮、重新轉強；'
               f'跌破 SL {fmt_px(c.get("sl"))} 就代表形態失敗。')
    if kind == 'active':
        ok = c.get('close_ok')
        out.append(f'{_fmt_time(c.get("confirm_time"), "1D")} 已經碰到 BO 成交'
                   + ('，當天收盤也站穩在 BO 上面 ✅，突破比較可信。' if ok is True else
                      ('，但當天收盤跌回 BO 下面 ⚠️，要小心假突破。' if ok is False else '。')))
    elif kind == 'used':
        out.append('這個形態已經突破過、結束了，要等新的收縮出現。')
    else:
        px = m.get('price')
        if px and c.get('bo'):
            d = _pct(c['bo'], px)
            out.append('現在價格已經碰到 BO，收盤後系統會記錄。' if d <= 0 else f'現在價格離 BO 還有 {d:.1f}%。')
    return out

def stock_card_summary(d):
    """📋 一眼看懂：現在在哪一步、檢查清單、結論"""
    m, r, v = d['meta'], d['wy'], d['vcp']
    ok = lambda b: '✅' if b else '❌'
    s2 = m.get('day_stage') == 'S2'
    liquid = m.get('turnover') is not None and m['turnover'] >= TG_MIN_TURNOVER_MYR
    checks = [f'{ok(s2)} 日線 {m.get("day_stage", "--")}（只做 S2）',
              f'{ok(liquid)} 平均每日成交額 {_fmt_turnover(m.get("turnover"))}（門檻 {_fmt_turnover(TG_MIN_TURNOVER_MYR)}）']
    ready, watch = [], []

    # 威科夫
    if r:
        label = WY_STAGE_META.get(r['stage'], ('',))[0]
        now_txt, next_txt = WY_STAGE_PLAIN.get(r['stage'], ('', ''))
        wy_html = f'<b>{label}</b><div class="exs-sub">{now_txt} 下一步：{next_txt}</div>'
        if r['stage'] == 'green':
            wall_ok = r.get('wall') is None or (r.get('wall_r') or 0) >= HEADROOM_MIN_R
            atr_ok = not (r.get('risk_atr') and r['risk_atr'] > WY_RISK_MAX_ATR)
            px_ok = not (m.get('price') and m['price'] > r['entry'])
            wtxt = '藍天' if r.get('wall') is None else f'{r.get("wall_r") or 0:.2f}R'
            checks += [f'{ok(wall_ok)} 威科夫上方空間 {wtxt}（要 ≥ {HEADROOM_MIN_R:g}R）',
                       f'{ok(atr_ok)} SL 距離 {r.get("risk_atr") or 0:.1f} 倍日線ATR（要 ≤ {WY_RISK_MAX_ATR:g}）',
                       f'{ok(px_ok)} 現價還沒過 Entry {_wy_fp(r["entry"])}']
            if wall_ok and atr_ok and px_ok:
                ready.append(f'威科夫 🟢：在 Entry <b>{_wy_fp(r["entry"])}</b> 掛觸價單，SL {_wy_fp(r["sl"])}')
            elif not atr_ok:
                watch.append('威科夫 🟢 但 SL 太寬：改看 4H／1H 找 C 進場')
            else:
                watch.append('威科夫 🟢 但' + ('上方空間不夠' if not wall_ok else '現價已過 Entry，等下一次回踩'))
        elif r['stage'] == 'orange':
            watch.append(f'威科夫 🟠：等回踩到 {_wy_fp(r["ceiling"])}～{_wy_fp(r["ceiling"] * (1 + WY_RETEST_NEAR_PCT / 100))} 守住')
        elif r['stage'] == 'yellow':
            watch.append(f'威科夫 🟡：等放量收盤突破 {_wy_fp(r["ceiling"])}（離 {r.get("dist_pct") or 0:.1f}%）')
    else:
        wy_html = '<b>沒有看到區間</b><div class="exs-sub">威科夫找不到「有洗盤的橫盤區間」（或區間太久以前），這一檔目前沒有威科夫故事。</div>'

    # VCP
    kind = v['kind'] if v else 'none'
    if kind == 'active':
        c = v['card']
        cur_r = (m['price'] - c['entry']) / (c['entry'] - c['sl']) if c['entry'] > c['sl'] else 0
        vcp_html = (f'<b>已突破、進行中</b>（{_fmt_time(c["confirm_time"], "1D")} 進場 {fmt_px(c["entry"])}，現在 {cur_r:+.2f}R）'
                    f'<div class="exs-sub">已經成交的單：照 SL／1:1.5／20根規則管理。</div>')
        watch.append('VCP 已突破：按計劃管理持倉')
    elif kind == 'pending':
        c = v['card']
        dist = _pct(c['bo'], m['price']) if m.get('price') else None
        dtxt = '盤中已碰 BO，收盤後記錄' if dist is not None and dist <= 0 else f'現價離 BO {dist:.1f}%'
        vcp_html = (f'<b>{c.get("c_count")}C 形態成形，還沒突破</b>（BO {fmt_px(c["bo"])}・SL {fmt_px(c["sl"])}・{dtxt}）'
                    f'<div class="exs-sub">{"⏳ 最後一個C的低點還沒確認。" if c.get("provisional") else ""}在 BO 掛觸價單，碰到就成交。</div>')
        if dist is not None and 0 < dist <= QUICK_BO_PCT:
            ready.append(f'VCP：在 BO <b>{fmt_px(c["bo"])}</b> 掛觸價單，SL {fmt_px(c["sl"])}（離 {dist:.1f}%，在快突破範圍）')
        elif dist is not None and dist > QUICK_BO_PCT:
            watch.append(f'VCP：離 BO 還有 {dist:.1f}%，等靠近到 {QUICK_BO_PCT:g}% 以內再掛')
    elif kind == 'used':
        vcp_html = '<b>這個形態已經突破過</b><div class="exs-sub">最後一個C已經用過了（突破後結束），等新的C形成。</div>'
    else:
        cc = v.get('c_count', 0) if v else 0
        why = ('最近的C系列是空頭方向' if v and v.get('is_bear') else
               (f'只有 {cc}C，至少要 C2' if v and v.get('has_c') else '目前沒有C系列收縮'))
        vcp_html = f'<b>沒有可交易的形態</b><div class="exs-sub">{why}。</div>'

    # 結論
    bad = []
    if not s2: bad.append('日線不是 S2')
    if not liquid: bad.append('成交額不夠，買賣容易滑價')
    if bad and ready:
        verdict, vcls = '🟡 有訊號，但要小心：' + '、'.join(bad), '#6b5a1e'
    elif bad:
        verdict, vcls = '🔴 不做：' + '、'.join(bad), '#7f1d1d'
    elif ready:
        verdict, vcls = '🟢 可以準備掛單', '#1b5e20'
    elif watch:
        verdict, vcls = '🟡 觀察，還不能動手', '#6b5a1e'
    else:
        verdict, vcls = '⚪ 目前沒有訊號', '#37474f'
    todo = ''.join(f'<li>{x}</li>' for x in ready + watch) or '<li>暫時不用管這一檔。</li>'
    both = r and r['stage'] in ('green', 'orange', 'yellow') and kind in ('pending', 'active')
    extra = ('<div class="exs-sub" style="margin-top:6px">🧱＋🃏 威科夫和 VCP 同時有故事：兩個系統都看到，比較少見，值得特別留意'
             '（是不是真的比較好，等卡片的「進場時威科夫」戰績累積再驗證）。</div>') if both else ''
    return f'''<div class="exs"><div class="exs-title">📋 一眼看懂：{_h(sym_code(m["symbol"]))} {_h(m["name"] if m["name"] != sym_code(m["symbol"]) else "")}</div>
<div class="exs-row"><div class="exs-k">結論</div><div class="exs-v"><span style="background:{vcls};padding:2px 8px;border-radius:4px;color:#fff"><b>{verdict}</b></span>
<ul class="exs-ul">{todo}</ul>{extra}</div></div>
<div class="exs-row"><div class="exs-k">📖 故事</div><div class="exs-v">
<div class="sty"><b>🧱 威科夫</b>{"".join(f"<p>{x}</p>" for x in wy_story_plain(r))}</div>
<div class="sty"><b>🃏 VCP</b>{"".join(f"<p>{x}</p>" for x in vcp_story_plain(v, m))}</div></div></div>
<div class="exs-row"><div class="exs-k">🧱 威科夫</div><div class="exs-v">{wy_html}</div></div>
<div class="exs-row"><div class="exs-k">🃏 VCP（1D）</div><div class="exs-v">{vcp_html}</div></div>
<div class="exs-row"><div class="exs-k">檢查清單</div><div class="exs-v"><ul class="exs-ul" style="list-style:none;padding-left:0">{"".join(f"<li>{x}</li>" for x in checks)}</ul></div></div>
<div class="exs-tip">💡 這是系統照規則算出來的，不是買賣建議。動手前還是要打開圖，自己看故事和上方的牆。</div></div>'''

@app.route('/stock_card')
def stock_card_page():
    sym_raw = (request.args.get('symbol') or '').strip()
    opts = ''.join(f'<option value="{_h(sym_code(x))}">{_h(NAMES.get(x, ""))}</option>' for x in dict.fromkeys(SYMBOLS))
    nav = ('<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a>'
           '<a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a>'
           '<a class="nav-on" href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>')
    form = (f'<form class="sbform" method="get" action="/stock_card">'
            f'<input name="symbol" list="scsyms" placeholder="股票代碼，例：{_h(sym_code(M["default_sym"]))}" value="{_h(sym_raw)}" autocomplete="off">'
            f'<datalist id="scsyms">{opts}</datalist><button type="submit">🔎 看卡片</button></form>')
    head = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>🔎 單股卡片</title><style>{CARDS_CSS}{SB_CSS}{WY_CARD_CSS}'
            '.exs{background:#1f2440;border:1px solid #3d4780;border-radius:10px;padding:14px 18px;margin:10px 0 14px;max-width:820px}'
            '.exs-title{font-size:17px;font-weight:bold;color:#fff;margin-bottom:10px}'
            '.exs-row{display:flex;gap:12px;padding:9px 0;border-top:1px solid #333a66;font-size:14px}'
            '.exs-k{min-width:110px;color:#9fb3e8;font-weight:bold}.exs-v{flex:1;color:#eee;line-height:1.6}'
            '.exs-sub{color:#9aa0b8;font-size:12px;margin-top:2px}.exs-ul{margin:6px 0 0;padding-left:20px;line-height:1.8}'
            '.exs-tip{background:#2a2410;border:1px solid #6b5a1e;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:13px;color:#f3e3b0}'
            '.sty{margin-bottom:8px}.sty b{color:#ffd54f}.sty p{margin:3px 0;line-height:1.7;font-size:13.5px}'
            '.scsec{margin-top:14px}.scsec h3{font-size:15px;margin:10px 0 6px}.sclinks a{color:#7ab3ff;margin-right:14px;font-size:13px}'
            '@media (max-width:600px){.exs-row{flex-direction:column;gap:2px}.exs-k{min-width:0}}</style></head><body>'
            f'<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ 🔎 單股卡片</h2>'
            f'<div class="subtitle">選一檔股票，看它現在的 🧱 威科夫卡片和 🃏 VCP 卡片（日線），加上一眼看懂的分析。用的是跟正式掃描同一套規則。</div>'
            f'{nav}{form}')
    if not sym_raw:
        return head + ('<div class="sbsum">輸入股票代碼，按 <b>🔎 看卡片</b>。<br>'
                       '<span class="muted">每一種威科夫燈號（🟢🟠🟡⚪❌）都會用卡片顯示；沒有燈號的股票也會告訴你為什麼。'
                       '同一檔 5 分鐘內重看會用暫存結果。</span></div></body></html>')
    sym = norm_sym(sym_raw)
    try:
        d = stock_card_data(sym)
    except Exception as e:
        log.warning(f"🔎 單股卡片 {sym}: {e}")
        return head + f'<div class="sbsum neg">出錯：{_h(e)}</div></body></html>'
    if d.get('error'):
        return head + f'<div class="sbsum">{_h(sym_code(sym))}：{_h(d["error"])}<br><span class="muted">代碼對嗎？可以用搜尋框的下拉選單挑。</span></div></body></html>'
    m, r, v = d['meta'], d['wy'], d['vcp']
    code = sym_code(sym)
    links = (f'<div class="sclinks"><a href="{tv_chart_base()}?symbol={m["tv_symbol"]}&interval=D" target="_blank">📈 TradingView 日線</a>'
             f'<a href="/stock_bt?symbol={_h(code)}&strategy=wy">🔍 威科夫單股回測</a>'
             f'<a href="/stock_bt?symbol={_h(code)}&strategy=vcp&tf=1D">🔍 VCP 單股回測</a>'
             f'<span class="muted" style="font-size:12px">現價 {fmt_px(m["price"])}（{m["price_time"]}）</span></div>')
    if r:
        wy_card = wy_card_green(r) if r['stage'] == 'green' else (wy_card_orange(r) if r['stage'] == 'orange' else wy_card_generic(r))
    else:
        wy_card = '<div class="empty">威科夫：沒有看到有洗盤的橫盤區間，這一檔目前沒有威科夫卡片。</div>'
    kind = v['kind']
    if kind == 'active':
        vcp_card = _render_active(v['card'], '1D')
    elif kind in ('pending', 'used'):
        vcp_card = _render_pending(v['card'], '1D')
    else:
        vcp_card = '<div class="empty">VCP：目前沒有至少 C2 的多頭形態，沒有突破卡片。</div>'
    return head + (f'{links}{stock_card_summary(d)}'
                   f'<div class="scsec"><h3>🧱 威科夫卡片</h3><div class="grid">{wy_card}</div></div>'
                   f'<div class="scsec"><h3>🃏 VCP 突破卡片（1D）</h3><div class="grid">{vcp_card}</div></div>'
                   '<div class="foot">威科夫用已收盤的日K判斷（收盤後才會變）；現價是最新價格。VCP 卡片如果已經在「🃏 突破卡片」頁，'
                   '這裡顯示的就是同一張；不在的話是即時算出來的（只顯示，不會記錄）。只供自己研究，不是投資建議。</div></body></html>')

@app.route('/exit_backtest')
def exit_backtest_page():
    """🚪 出場規則回測。?run=1D&c1=10 開始（背景執行），可加 &limit=50 先試"""
    run_tf = request.args.get('run', '').upper()
    c1 = request.args.get('c1', '10')
    c1 = int(c1) if c1.isdigit() and 1 <= int(c1) <= 30 else 10
    if run_tf in TF_LABELS:
        limit = request.args.get('limit')
        limit = int(limit) if limit and limit.isdigit() else None
        threading.Thread(target=run_exit_backtest, args=(run_tf, c1, None, limit), daemon=True).start()
        time.sleep(0.5)
        return redirect(f'{BASE}/exit_backtest?tf={run_tf}&c1={c1}')
    view_tf = request.args.get('tf', ex_state.get('tf') or '1D').upper()
    if view_tf not in TF_LABELS: view_tf = '1D'

    with ex_state['lock']:
        st = {k: v for k, v in ex_state.items() if k != 'lock'}
    busy_c1 = bt_state['status'] == 'running'
    res = load_ex_result(view_tf, c1)

    if st['status'] == 'running':
        pct = st['done'] / st['total'] * 100 if st['total'] else 0
        status_html = (f'<div class="scanning-banner">⏳ 出場回測中（{st["tf"]}・C1 {st["c1"]}%）：{st["done"]}/{st["total"]} 檔（{pct:.0f}%）・'
                       f'開始於 {st["started"]}・頁面每30秒自動更新</div>'
                       '<script>setTimeout(function(){location.reload()},30000)</script>')
    elif st['status'] == 'error':
        status_html = f'<div class="warnbox">❌ 回測出錯：{_h(st["error"])}</div>'
    elif busy_c1:
        status_html = '<div class="warnbox">🧪 C1門檻回測正在跑，等它跑完才能開始出場回測。</div>'
    else:
        status_html = ''

    runbar = ''.join(
        f'<a href="/exit_backtest?run={t}&c1={c}" onclick="return confirm(\'開始跑 {t}（C1 {c}%）出場回測？\')">▶ 跑 {t}・C1 {c}%</a>'
        for t in ('1D', '4H') if t in TF_LABELS for c in (10, 7))
    viewbar = ''.join(
        f'<a class="{"on" if (t == view_tf and c == c1) else ""}" href="/exit_backtest?tf={t}&c1={c}">{t}・C1 {c}% 結果</a>'
        for t in ('1D', '4H', '1H') if t in TF_LABELS for c in (10, 7))

    if res:
        def cells(s):
            wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
            ar = f'{s["avg_r"]:+.2f}R' if s['avg_r'] is not None else '-'
            ab = f'{s["avg_bars"]}' if s['avg_bars'] is not None else '-'
            return (f'<td>{s["n"]}</td><td>{s["tp"]}</td><td>{s["sl"]}</td><td>{s["other"]}</td>'
                    f'<td>{wr}</td><td>{ar}</td><td><b>{s["total_r"]:+.1f}R</b></td><td>{ab}</td>')
        rows = ''
        for rl in res['rules']:
            rows += f'<tr><td class="g"><b>{_h(rl["name"])}</b></td><td class="g">全部</td>{cells(rl["all"])}<td>{rl["open"]}</td></tr>'
            rows += f'<tr><td></td><td class="g">排除⚠️不追</td>{cells(rl["nochase"])}<td></td></tr>'
            rows += f'<tr><td></td><td class="g">只看日線S2</td>{cells(rl["s2"])}<td></td></tr>'
        mb = res.get('mfe_bins_20', {})
        mtot = sum(mb.values()) or 1
        mfe_html = '・'.join(f'{k}：{v}筆（{v / mtot * 100:.0f}%）' for k, v in mb.items())
        lists = ''
        for rl in res['rules']:
            li = ''.join(
                f'<div>{_fmt_time(x["confirm_time"], res["tf"])} <b>{_h(x["symbol"].replace(".KL", ""))}</b> {_h(x.get("name") or "")} '
                f'進場{fmt_px(x["entry"])} SL{fmt_px(x["sl"])} → {x["why"]} 第{x["bars"]}根 '
                f'<span class="{"pos" if x["r"] > 0 else "neg"}">{x["r"]:+.2f}R</span>（最多漲到{x["mfe"]:.1f}R）</div>'
                for x in rl['cases'][:15])
            lists += f'<details><summary>{_h(rl["name"])}：最近15筆</summary><div class="lst">{li or "沒有案例"}</div></details>'
        try:
            summary = exit_summary_html(res)
        except Exception as e:
            log.warning(f"🚪 結論卡錯誤：{e}")
            summary = ''
        try:
            factor_html = exf_table_html(res)
        except Exception as e:
            log.warning(f"🔬 進場條件表錯誤：{e}")
            factor_html = ''
        body = f'''
<div class="desc">期間 {res["period"][0]} ～ {res["period"][1]}・{res["symbols"]}檔・進場共 {res["entries"]} 筆（C1門檻 {res["c1"]}%）・完成於 {res["finished"]}</div>
{summary}
{factor_html}
<details class="exs-detail"><summary>📊 詳細數據（每條出場規則的完整表格）— 點這裡展開</summary>
<div class="desc" style="margin-top:8px">📏 突破後20根內「最多漲到幾R」（MFE）：{mfe_html}</div>
<div style="overflow-x:auto"><table class="st"><tr><th>出場規則</th><th>範圍</th><th>筆數</th><th>🎯達標</th><th>❌SL</th><th>其他出場</th><th>賺錢比例</th><th>平均R</th><th>總R</th><th>平均持有根數</th><th>未走完</th></tr>{rows}</table></div>
</details>
<div class="sec"><h3>🔍 抽查案例</h3>{lists}</div>'''
    else:
        body = f'<div class="empty">{view_tf}・C1 {c1}%：還沒有出場回測結果。按上面的「▶ 跑」開始。</div>'

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🚪 出場規則回測</title><style>{CARDS_CSS}
details{{background:#22223a;border:1px solid #3a3a55;border-radius:6px;padding:8px 12px;margin-bottom:6px;max-width:1150px}}
summary{{cursor:pointer;color:#ffb74d}} .lst{{font-size:12px;line-height:1.8;margin-top:6px}}
.exs{{background:#1f2440;border:1px solid #3d4780;border-radius:10px;padding:14px 18px;margin:10px 0 14px;max-width:820px}}
.exs-title{{font-size:17px;font-weight:bold;color:#fff;margin-bottom:10px}}
.exs-row{{display:flex;gap:12px;padding:9px 0;border-top:1px solid #333a66;font-size:14px}}
.exs-k{{min-width:120px;color:#9fb3e8;font-weight:bold}} .exs-v{{flex:1;color:#eee;line-height:1.6}}
.exs-sub{{color:#9aa0b8;font-size:12px;margin-top:2px}}
.exs-ul{{margin:4px 0 0;padding-left:20px;line-height:1.7}}
.exs-tip{{background:#2a2410;border:1px solid #6b5a1e;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:14px;color:#f3e3b0;line-height:1.6}}
.exs-tip b{{color:#ffd54f}}
details.exs-detail summary{{color:#7ab3ff}}
@media (max-width:600px){{.exs-row{{flex-direction:column;gap:2px}} .exs-k{{min-width:0}}}}</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ 出場規則回測</h2>
<div class="subtitle">同一批進場（跟突破卡片同一套規則：{"盤中碰到BO就成交、進場價=BO" if CARD_ENTRY_MODE == "touch" else "收盤站上BO進場"}、SL在最後一個C低點下方），只換出場方式，看哪一種總R最好。正式掃描完全不受影響。</div>
<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a><a href="/backtest">🧪 C1門檻回測</a><a class="nav-on" href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>
{status_html}
<div class="tfbar">{runbar}</div>
<div class="tfbar">{viewbar}</div>
{body}
<div class="foot">「賺錢比例」= R > 0 的筆數 ÷ 全部（保本出場算打平，不算賺也不算虧）。「總R」= 每筆冒1R風險時累積的結果，最能看出整體賺不賺。<br>
「保本」= 漲到1R後把SL移到進場價。「跌破MA20走」= 保本啟動後，收盤跌破20根均線就用收盤價出場。<br>
跳空低開到SL下方用開盤價計算；同一根同時碰SL和目標保守算SL；沒算手續費和滑價；「未走完」= 資料到今天還沒出場的筆數，不計入統計。</div>
</body></html>'''

@app.route('/entry_backtest')
def entry_backtest_page():
    """⚖️ 進場方式比較回測。?run=1D 開始（背景執行），可加 &limit=50 先試"""
    run_tf = request.args.get('run', '').upper()
    if run_tf in TF_LABELS:
        limit = request.args.get('limit')
        limit = int(limit) if limit and limit.isdigit() else None
        threading.Thread(target=run_entry_backtest, args=(run_tf, None, limit), daemon=True).start()
        time.sleep(0.5)
        return redirect(f'{BASE}/entry_backtest?tf={run_tf}')
    view_tf = request.args.get('tf', en_state.get('tf') or '1D').upper()
    if view_tf not in TF_LABELS: view_tf = '1D'
    blk = 's2' if request.args.get('s2') == '1' else 'all'

    with en_state['lock']:
        st = {k: v for k, v in en_state.items() if k != 'lock'}
    other_busy = bt_state['status'] == 'running' or ex_state['status'] == 'running'
    res = load_en_result(view_tf)

    if st['status'] == 'running':
        pct = st['done'] / st['total'] * 100 if st['total'] else 0
        status_html = (f'<div class="scanning-banner">⏳ 進場比較回測中（{st["tf"]}）：{st["done"]}/{st["total"]} 檔（{pct:.0f}%）・'
                       f'開始於 {st["started"]}・頁面每30秒自動更新</div>'
                       '<script>setTimeout(function(){location.reload()},30000)</script>')
    elif st['status'] == 'error':
        status_html = f'<div class="warnbox">❌ 回測出錯：{_h(st["error"])}</div>'
    elif other_busy:
        status_html = '<div class="warnbox">🧪 另一個回測正在跑，等它跑完才能開始進場比較回測。</div>'
    else:
        status_html = ''

    runbar = ''.join(
        f'<a class="runbtn" href="/entry_backtest?run={t}" onclick="return confirm(\'開始跑 {t} 進場比較回測？（大約要幾分鐘到十幾分鐘）\')">▶ 跑 {t} 進場比較回測</a>'
        for t in ('1D', '4H', '1H') if t in TF_LABELS)
    viewbar = ''.join(
        f'<a class="{"on" if (t == view_tf and b_ == blk) else ""}" href="/entry_backtest?tf={t}{"&s2=1" if b_ == "s2" else ""}">{t}・{lab}</a>'
        for t in ('1D', '4H', '1H') if t in TF_LABELS for b_, lab in (('all', '全部'), ('s2', '只看日線S2')))

    if res:
        b = res[blk]
        def cells(s):
            wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
            return (f'<td>{s["n"]}</td><td>{s["win"]}</td><td>{s["loss"]}</td><td>{s["timeout"]}</td>'
                    f'<td>{wr}</td><td>{_en_r(s["avg_r"])}</td><td><b>{s["total_r"]:+.1f}R</b></td>')
        trows = [('A 盤中掛單（全部）', b['A']), ('B 收盤確認（全部）', b['B']),
                 ('A 裡：當天收盤站上BO', b['A_closeok']), ('A 裡：當天收盤沒站上（假突破）', b['A_fake']),
                 ('同一形態兩邊都進場 → A', b['paired_A']), ('同一形態兩邊都進場 → B', b['paired_B']),
                 ('只有A進場（B沒買）', b['A_only']), ('只有B進場', b['B_only'])]
        rows = ''.join(f'<tr><td class="g"><b>{_h(lab)}</b></td>{cells(s)}</tr>' for lab, s in trows)

        def li(cs):
            return ''.join(
                f'<div>{_fmt_time(x["confirm_time"], res["tf"])} <b>{_h(x["symbol"].replace(".KL", ""))}</b> {_h(x.get("name") or "")} '
                f'進場{fmt_px(x["entry"])}（BO {fmt_px(x["bo"])}） SL{fmt_px(x["sl"])} → {x["result"]} 第{x["bars_held"]}根 '
                f'<span class="{"pos" if x["r_mult"] > 0 else "neg"}">{x["r_mult"]:+.2f}R</span></div>'
                for x in cs) or '沒有案例'
        try:
            summary = entry_summary_html(res, blk)
        except Exception as e:
            log.warning(f"⚖️ 結論卡錯誤：{e}")
            summary = ''
        body = f'''
<div class="desc">期間 {res["period"][0]} ～ {res["period"][1]}・{res["symbols"]}檔・C1門檻 {res["c1"]:g}%・範圍：{"只看日線S2" if blk == "s2" else "全部"}・完成於 {res["finished"]}・
還沒走完（不計入）：A {res["open_a"]}筆、B {res["open_b"]}筆</div>
{summary}
<details class="exs-detail"><summary>📊 詳細數據 — 點這裡展開</summary>
<div style="overflow-x:auto"><table class="st"><tr><th>組別</th><th>筆數</th><th>🎯達1:1.5</th><th>❌SL</th><th>⏱到期</th><th>達標率</th><th>平均R</th><th>總R</th></tr>{rows}</table></div>
</details>
<div class="sec"><h3>🔍 抽查案例（用 TradingView 對圖）</h3>
<details><summary>假突破：A 有進場、當天收盤沒站上BO（最近20筆）</summary><div class="lst">{li(res.get("fake_cases", []))}</div></details>
<details><summary>A 盤中掛單：最近20筆</summary><div class="lst">{li(res.get("cases_a", []))}</div></details>
<details><summary>B 收盤確認：最近20筆</summary><div class="lst">{li(res.get("cases_b", []))}</div></details>
</div>'''
    else:
        body = f'<div class="empty">{view_tf}：還沒有進場比較回測結果。按上面的「▶ 跑」開始。</div>'

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>⚖️ 進場方式比較</title><style>{CARDS_CSS}
details{{background:#22223a;border:1px solid #3a3a55;border-radius:6px;padding:8px 12px;margin-bottom:6px;max-width:1150px}}
summary{{cursor:pointer;color:#ffb74d}} .lst{{font-size:12px;line-height:1.8;margin-top:6px}}
.exs{{background:#1f2440;border:1px solid #3d4780;border-radius:10px;padding:14px 18px;margin:10px 0 14px;max-width:820px}}
.exs-title{{font-size:17px;font-weight:bold;color:#fff;margin-bottom:10px}}
.exs-row{{display:flex;gap:12px;padding:9px 0;border-top:1px solid #333a66;font-size:14px}}
.exs-k{{min-width:120px;color:#9fb3e8;font-weight:bold}} .exs-v{{flex:1;color:#eee;line-height:1.6}}
.exs-sub{{color:#9aa0b8;font-size:12px;margin-top:2px}}
.exs-ul{{margin:4px 0 0;padding-left:20px;line-height:1.7}}
.exs-tip{{background:#2a2410;border:1px solid #6b5a1e;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:14px;color:#f3e3b0;line-height:1.6}}
.exs-tip b{{color:#ffd54f}}
details.exs-detail summary{{color:#7ab3ff}}
.tfbar a.runbtn{{background:#ffb300;color:#1a1a1a;font-weight:bold;border-color:#ffb300}}
@media (max-width:600px){{.exs-row{{flex-direction:column;gap:2px}} .exs-k{{min-width:0}}}}</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ ⚖️ 進場方式比較</h2>
<div class="subtitle">同一批C系列形態、同樣的SL／1:1.5／20根到期，只換進場方式：<b>A 盤中掛單</b>（盤中碰到BO就成交，老師SOP）vs <b>B 收盤確認</b>（收盤站上BO才進場，突破卡片的舊算法）。正式掃描完全不受影響。</div>
<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a><a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a class="nav-on" href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a href="/stock_bt">🔍 單股回測</a></div>
{status_html}
<div class="tfbar">{runbar}</div>
<div class="tfbar">{viewbar}</div>
{body}
<div class="foot">A 成交價 = BO；如果當天開盤已經跳空高過BO，用開盤價成交。A 進場那一根如果又跌到SL（先後不明）保守算止損。<br>
B 進場價 = 收盤站上BO那天的收盤價。兩邊的R都用「進場價 − SL」計算，所以同一個形態，A 的1R比較小、目標也比較近。<br>
「總R」= 每筆冒一樣的錢（1R）累積的結果，最能看出哪一種整體賺比較多。沒算手續費和滑價；「還沒走完」= 資料到今天還沒出場，不計入統計。</div>
</body></html>'''

@app.route('/backtest_json')
def backtest_json():
    tf = request.args.get('tf', '1D').upper()
    with bt_state['lock']:
        st = {k: v for k, v in bt_state.items() if k not in ('lock', 'results')}
    res = load_bt_result(tf)
    return Response(json.dumps({'state': st, 'result': res}, ensure_ascii=False, default=str, indent=1), mimetype='application/json')

@app.route('/rescan', methods=['POST'])
def rescan():
    threading.Thread(target=run_scan, daemon=True).start()
    return 'ok'

@app.route('/status')
def status():
    with scan_state['lock']:
        s = scan_state['status']
    return jsonify({'status': s})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/audit_names', methods=['POST', 'GET'])
def audit_names():
    """一次性診斷：核對SYMBOLS清單裡每個代碼的NAMES是否跟Yahoo Finance官方名稱相符。
    背景執行（160檔逐一查詢，每檔間隔0.4秒，全部跑完約需2-3分鐘），
    用 /audit_names_result 輪詢進度與結果。"""
    with audit_state['lock']:
        already_running = audit_state['status'] == 'running'
    if not already_running:
        threading.Thread(target=run_name_audit, daemon=True).start()
    return jsonify({'started': not already_running})

@app.route('/audit_names_result')
def audit_names_result():
    include_all = request.args.get('all', '') == '1'
    with audit_state['lock']:
        out = {
            'status': audit_state['status'],
            'checked': audit_state['checked'],
            'total': audit_state['total'],
            'mismatches': audit_state['mismatches'],
            'error_count': len(audit_state['errors']),
        }
        if include_all:
            out['all_names'] = audit_state['all_names']
        return jsonify(out)

@app.route('/audit_missing', methods=['POST', 'GET'])
def audit_missing():
    with missing_audit_state['lock']:
        already_running = missing_audit_state['status'] == 'running'
    if not already_running:
        threading.Thread(target=run_missing_audit, daemon=True).start()
    return jsonify({'started': not already_running})

@app.route('/audit_missing_result')
def audit_missing_result():
    with missing_audit_state['lock']:
        return jsonify({
            'status': missing_audit_state['status'],
            'checked': missing_audit_state['checked'],
            'total': missing_audit_state['total'],
            'results': missing_audit_state['results'],
        })

@app.route('/debug_bars')
def debug_bars():
    """診斷用：把某symbol最近N根原始K線(日期/OHLC)連同is_swing_high2/is_swing_low2旗標一起
    印出來，方便跟Pine的isSwingHigh2結果逐根比對（跟crypto版scannerrailway.py的同名路由對齊）。"""
    symbol = norm_sym(request.args.get('symbol', M['default_sym']))
    tf = request.args.get('tf', '1D')
    last_n = int(request.args.get('last', 20))
    df = fetch_ohlcv(symbol, tf)
    if df.empty:
        return jsonify({'error': 'no data'})
    high_arr = df['high'].values
    low_arr  = df['low'].values
    n = len(df)
    start = max(0, n - last_n)
    bars = []
    for idx in range(start, n):
        bars.append({
            'idx': idx,
            'bars_ago': (n - 1) - idx,
            'date': str(df.index[idx]),
            'open': round(float(df['open'].values[idx]), 4),
            'high': round(float(high_arr[idx]), 4),
            'low': round(float(low_arr[idx]), 4),
            'close': round(float(df['close'].values[idx]), 4),
            'is_swing_high2': bool(is_swing_high2(high_arr, idx)),
            'is_swing_low2': bool(is_swing_low2(low_arr, idx)),
        })
    return jsonify({'symbol': symbol, 'tf': tf, 'n_bars': n, 'bars': bars})

@app.route('/debug_c')
def debug_c():
    import json as _json
    symbol = norm_sym(request.args.get('symbol', M['default_sym']))
    tf = request.args.get('tf', '1D').upper()
    if tf not in TF_LABELS:
        tf = '1D'

    df_daily = fetch_ohlcv(symbol, '1D')
    df = df_daily if tf == '1D' else fetch_ohlcv(symbol, tf)
    if df.empty:
        return Response(_json.dumps({'error': 'no data'}), mimetype='application/json')

    def fmt_idx(i):
        if i is None or i < 0 or i >= len(df): return None
        t = df.index[i]
        return {'idx': int(i), 'time': str(t)}

    out = {'symbol': symbol, 'tf': tf, 'n_bars': len(df)}

    # 診斷用：MA50/150/200現值 + 最近5根K棒，方便核對Yahoo資料是否與TradingView一致
    _s50  = calc_sma(df['close'], 50)
    _s150 = calc_sma(df['close'], 150)
    _s200 = calc_sma(df['close'], 200)
    _ma50  = None if pd.isna(_s50.iloc[-1])  else round(float(_s50.iloc[-1]), 4)
    _ma150 = None if pd.isna(_s150.iloc[-1]) else round(float(_s150.iloc[-1]), 4)
    _ma200 = None if pd.isna(_s200.iloc[-1]) else round(float(_s200.iloc[-1]), 4)
    out['last_date']  = str(df.index[-1])
    out['last_close'] = round(float(df['close'].iloc[-1]), 4)
    out['ma50']  = _ma50
    out['ma150'] = _ma150
    out['ma200'] = _ma200
    out['bull_aligned'] = bool(_ma50 is not None and _ma150 is not None and _ma200 is not None and _ma50 > _ma150 > _ma200)
    out['bear_aligned'] = bool(_ma50 is not None and _ma150 is not None and _ma200 is not None and _ma50 < _ma150 < _ma200)
    out['last5'] = [
        {'date': str(df.index[i]),
         'o': round(float(df['open'].iloc[i]), 4), 'h': round(float(df['high'].iloc[i]), 4),
         'l': round(float(df['low'].iloc[i]), 4), 'c': round(float(df['close'].iloc[i]), 4)}
        for i in range(max(0, len(df) - 5), len(df))
    ]

    start_idx_bull = find_start_bar_bull(df)
    start_idx_bear = find_start_bar_bear(df)
    out['start_idx_bull'] = fmt_idx(start_idx_bull) if start_idx_bull >= 0 else None
    out['start_idx_bear'] = fmt_idx(start_idx_bear) if start_idx_bear >= 0 else None

    c_list = []
    next_c_fail_trace = None
    if start_idx_bull >= 0:
        c1 = find_c1(df, start_idx_bull)
        if c1['found']:
            c1['label'] = 'C1'
            c_list = [c1]
            prev_lv = c1['lv']; prev_lb = c1['lb']
            for n in range(5):
                cx = find_next_c(df, prev_lv, prev_lb, start_idx_bull, debug=True, c1_hv=c1['hv'])
                if not cx['found']:
                    next_c_fail_trace = cx.get('trace')
                    break
                next_c_fail_trace = None
                cx['label'] = f'C{len(c_list)+1}'
                c_list.append(cx)
                prev_lv = cx['lv']; prev_lb = cx['lb']
                if cx['pct'] < 2.0: break
        else:
            out['c1_fail_msg'] = c1.get('fail_msg')
        out['direction'] = 'bull'
    elif start_idx_bear >= 0:
        c1b = find_c1_bear(df, start_idx_bear)
        if c1b['found']:
            c1b['label'] = 'C1'
            c_list = [c1b]
            prev_hv = c1b['hv']; prev_hb = c1b['hb']
            for n in range(5):
                cxb = find_next_c_bear(df, prev_hv, prev_hb, start_idx_bear, debug=True, c1_lv=c1b['lv'])
                if not cxb['found']:
                    next_c_fail_trace = cxb.get('trace')
                    break
                next_c_fail_trace = None
                cxb['label'] = f'C{len(c_list)+1}'
                c_list.append(cxb)
                prev_hv = cxb['hv']; prev_hb = cxb['hb']
                if cxb['pct'] < 2.0: break
        else:
            out['c1_fail_msg'] = c1b.get('fail_msg')
        out['direction'] = 'bear'
    else:
        out['direction'] = 'none'

    detail = []
    for c in c_list:
        hb = c.get('hb'); lb = c.get('lb')
        detail.append({
            'label': c['label'],
            'hv': round(c['hv'], 6), 'h_time': fmt_idx(hb),
            'lv': round(c['lv'], 6), 'l_time': fmt_idx(lb),
            'pct': round(c['pct'], 3)
        })
    out['c_list'] = detail

    if next_c_fail_trace:
        trace_out = []
        for t in next_c_fail_trace:
            t2 = dict(t)
            if 'h_idx' in t2: t2['h_time'] = fmt_idx(t2['h_idx'])
            if 'l_idx' in t2: t2['l_time'] = fmt_idx(t2['l_idx'])
            trace_out.append(t2)
        out['next_c_fail_trace'] = trace_out
    else:
        out['next_c_fail_trace'] = []

    return Response(_json.dumps(out, indent=2, ensure_ascii=False, default=str), mimetype='application/json')


# ============================================================
# 🔍 單股回測（MH 2026-10-29）：選一檔股票＋策略＋時間框架，在 K 線圖上看每一筆怎麼進、怎麼出
# 用的是跟「🧪 C1門檻回測」「🧱 威科夫歷史回測」完全同一套程式（同樣的根數、同樣的規則），
# 所以這裡看到的交易，就是整體回測裡這一檔的那幾筆。
# ============================================================
BRIGHT_BTN = ('display:inline-block;background:#ffb300;color:#1a1a2e;font-weight:bold;padding:9px 18px;'
              'border-radius:6px;text-decoration:none;font-size:14px')
SB_CACHE = {}           # (symbol, strategy, tf) -> (時間, 結果)，同一檔 30 分鐘內不重算
SB_CACHE_SEC = 1800

def _sb_chart_time(ts, tf):
    t = pd.Timestamp(ts)
    if tf == '1D':
        return t.strftime('%Y-%m-%d')
    if t.tzinfo is None:
        t = t.tz_localize(MKT_TZ)
    loc = t.tz_convert(MKT_TZ)
    return int(loc.timestamp() + loc.utcoffset().total_seconds())   # 圖表時間＝當地時間

def _sb_stats(trades):
    done = [t for t in trades if t.get('result') in ('TP1', 'SL', 'TIMEOUT')]
    n = len(done); w = sum(1 for t in done if t['result'] == 'TP1'); l = sum(1 for t in done if t['result'] == 'SL')
    tot = sum(t['r_mult'] for t in done)
    return {'n': n, 'win': w, 'loss': l, 'timeout': n - w - l,
            'winrate': (w / (w + l) * 100) if (w + l) else None, 'avg_r': (tot / n) if n else None, 'total_r': tot}

def stock_backtest(sym, strategy, tf):
    key = (sym, strategy, tf)
    hit = SB_CACHE.get(key)
    if hit and time.time() - hit[0] < SB_CACHE_SEC:
        return hit[1]
    meta = {'symbol': sym, 'name': NAMES.get(sym, sym_code(sym)), 'sector': SECTORS.get(sym, '其他'), 'tv_symbol': tv_sym(sym)}
    out = {'symbol': sym, 'strategy': strategy, 'tf': tf, 'meta': meta, 'error': None, 'trades': [], 'others': []}
    if strategy == 'wy':
        df = closed_bars(fetch_ohlcv(sym, '1D'), '1D')
        if len(df) < 250:
            out['error'] = f'日線資料不夠（只有 {len(df)} 根，至少要 250 根）。'
            return out
        dates = [pd.Timestamp(t).strftime('%Y-%m-%d') for t in df.index]
        bars = cf_bars(df)
        st = _wy_new_state()
        start = max(130, len(df) - WY_BT_DAYS)
        for T in range(start, len(df)):
            sub = df.iloc[max(0, T - 499):T + 1]
            r = wy_analyze(sym, sub)
            stage_fn = lambda sub=sub: STAGE_LABEL_MAP.get(get_stage(sub)[0], '--')
            wy_track_step(st, sym, dates[:T + 1], bars[:T + 1], r, meta, day_stage_fn=stage_fn)
        for c in st['done']:
            (out['trades'] if c.get('result') in ('TP1', 'SL', 'TIMEOUT') else out['others']).append(dict(c))
        for c in st['active'].values():
            out['trades'].append(dict(c, result='OPEN'))
        for c in st['pending'].values():
            out['others'].append(dict(c, result='PENDING'))
        out['bars_used'] = len(df) - start
        chart_df = df.iloc[max(0, start - 60):]
    else:
        daily = fetch_ohlcv(sym, '1D')
        df = daily if tf == '1D' else fetch_ohlcv(sym, tf)
        if df.empty or len(df) < 300 or daily.empty:
            out['error'] = f'{tf} 資料不夠（只有 {len(df)} 根，至少要 300 根）。'
            return out
        daily_dates = [pd.Timestamp(x).date() for x in daily.index]
        n = len(df)
        start = max(260, n - BT_DEFAULT_BARS.get(tf, 500))
        st = {'pending': {}, 'active': {}, 'done': [], 'used': {}, 'events': []}
        for t in list(range(start, n, BT_STEP)) + [n]:
            d = df.iloc[:t]
            dd = d if tf == '1D' else daily.iloc[:bisect_right(daily_dates, pd.Timestamp(d.index[-1]).date())]
            _card_step(meta, tf, d, d, analyze(d, dd), backfill=True, st=st)
        out['trades'] = [dict(c) for c in st['done']] + [dict(c, result='OPEN') for c in st['active'].values()]
        out['others'] = [dict(c, result='PENDING') for c in st['pending'].values()]
        out['bars_used'] = n - start
        chart_df = df.iloc[max(0, start - 60):]
    tkey = 'trigger_time' if strategy == 'wy' else 'confirm_time'
    out['trades'].sort(key=lambda c: c.get(tkey) or '')
    out['stats'] = _sb_stats(out['trades'])
    out['period'] = (str(chart_df.index[60 if len(chart_df) > 60 else 0])[:10], str(chart_df.index[-1])[:10])
    out['candles'] = [{'time': _sb_chart_time(i, tf), 'open': round(float(o), 6), 'high': round(float(h), 6),
                       'low': round(float(l), 6), 'close': round(float(c), 6)}
                      for i, o, h, l, c in zip(chart_df.index, chart_df['open'], chart_df['high'], chart_df['low'], chart_df['close'])]
    SB_CACHE[key] = (time.time(), out)
    return out

def _sb_trade_rows(res):
    """把每一筆交易整理成：表格一列＋圖上的標記＋點下去要畫的價格線"""
    tf, wy = res['tf'], res['strategy'] == 'wy'
    label = {'TP1': '✅ 達 1:1.5', 'SL': '❌ 止損', 'TIMEOUT': f'⏱ {WY_HOLD_DAYS if wy else MAX_HOLD_BARS} 根到期', 'OPEN': '⏳ 還在進行'}
    rows, js = [], []
    for i, c in enumerate(res['trades']):
        t_in = c.get('trigger_time') if wy else c.get('confirm_time')
        entry = c.get('fill') if wy else c.get('entry')
        tp = c.get('tp') if wy else c.get('tp1')
        r = c.get('r_mult')
        if c['result'] == 'OPEN':
            px = c.get('last_close') or entry
            risk = (entry - c['sl']) if entry and c.get('sl') else None
            r = (px - entry) / risk if risk else None
        tags = []
        st = c.get('day_stage') if wy else (f"S{c.get('stage')}" if c.get('stage') else '')
        if st: tags.append(f'日線{st}')
        if not wy:
            if c.get('chase'): tags.append('⚠️不追')
            if c.get('provisional'): tags.append('⏳低點未確認')
            if c.get('vol_x') is not None: tags.append(f'量{c["vol_x"]}x')
            if c.get('entry_mode') == 'touch': tags.append('✅收盤站穩' if c.get('close_ok') else '⚠️收盤沒站穩')
        else:
            if c.get('wall_r') is not None: tags.append(f'上方空間 {c["wall_r"]:.2f}R')
            else: tags.append('上方藍天')
            tags.append(f'🟢 {(c.get("created") or "")[5:]}')
        rows.append({'i': i, 't_in': t_in, 't_out': c.get('end_time'), 'entry': entry, 'sl': c.get('sl'), 'tp': tp,
                     'bo': c.get('bo'), 'result': label.get(c['result'], c['result']), 'res': c['result'], 'r': r, 'tags': tags})
        js.append({'i': i, 'in': _sb_chart_time(t_in, tf) if t_in else None,
                   'out': _sb_chart_time(c['end_time'], tf) if c.get('end_time') else None,
                   'entry': entry, 'sl': c.get('sl'), 'tp': tp, 'bo': c.get('bo'), 'ceil': c.get('ceiling') if wy else None,
                   'res': c['result'], 'r': r,
                   'created': _sb_chart_time(c['created'], tf) if (wy and c.get('created')) else None})
    return rows, js

SB_CSS = """
.sbform{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:4px 0 14px}
.sbform input,.sbform select{background:#2a2a3e;color:#fff;border:1px solid #444;padding:9px 12px;border-radius:6px;font-size:14px;font-family:monospace}
.sbform input{width:170px}
.sbform button{background:#ffb300;color:#1a1a2e;border:none;font-weight:bold;padding:10px 20px;border-radius:6px;font-size:14px;cursor:pointer;font-family:monospace}
.sbsum{background:#22223a;border:1px solid #3a3a55;border-radius:8px;padding:12px 16px;max-width:1150px;margin-bottom:12px;line-height:1.7}
.sbsum b{color:#fff} .pos{color:#4cc28e} .neg{color:#ee7373} .muted{color:#8b949e}
#sbchart{width:100%;max-width:1150px;height:440px;border:1px solid #3a3a55;border-radius:8px}
table.sbt{border-collapse:collapse;font-size:13px;margin-top:12px;max-width:1150px;width:100%}
table.sbt th,table.sbt td{border:1px solid #444;padding:6px 8px;text-align:center}
table.sbt th{background:#26264a;color:#fff} table.sbt tr.tr{cursor:pointer} table.sbt tr.tr:hover{background:#2a2a48}
table.sbt tr.sel{background:#3a2f10} table.sbt td.l{text-align:left}
.sbtag{display:inline-block;border:1px solid #555;color:#bbb;font-size:11px;padding:0 5px;border-radius:4px;margin:1px}
.sbleg{font-size:12px;color:#aab;margin:6px 0;max-width:1150px;line-height:1.7}
"""

def build_stock_bt_html(sym_raw, strategy, tf, focus):
    tfs = [t for t in CARD_TFS] or ['1D']
    strategy = strategy if strategy in ('vcp', 'wy') else 'wy'
    tf = '1D' if strategy == 'wy' else (tf if tf in tfs else tfs[0])
    opts = ''.join(f'<option value="{_h(sym_code(x))}">{_h(NAMES.get(x, ""))}</option>' for x in dict.fromkeys(SYMBOLS))
    tf_opts = ''.join(f'<option value="{t}"{" selected" if t == tf else ""}>{t}</option>' for t in tfs)
    nav = ('<div class="nav"><a href="/">📊 C系列總表</a><a href="/cards">🃏 突破卡片</a><a href="/wyckoff">🧱 威科夫突破</a>'
           '<a href="/backtest">🧪 C1門檻回測</a><a href="/exit_backtest">🚪 出場回測</a><a href="/entry_backtest">⚖️ 進場比較</a><a href="/stock_card">🔎 單股卡片</a><a class="nav-on" href="/stock_bt">🔍 單股回測</a></div>')
    form = (f'<form class="sbform" method="get" action="/stock_bt">'
            f'<input name="symbol" list="sbsyms" placeholder="股票代碼，例：{_h(sym_code(M["default_sym"]))}" value="{_h(sym_raw)}" autocomplete="off">'
            f'<datalist id="sbsyms">{opts}</datalist>'
            f'<select name="strategy" id="sbstrat" onchange="document.getElementById(\'sbtf\').disabled=this.value===\'wy\'">'
            f'<option value="wy"{" selected" if strategy == "wy" else ""}>🧱 威科夫 🟢（日線）</option>'
            f'<option value="vcp"{" selected" if strategy == "vcp" else ""}>🃏 VCP 突破卡片</option></select>'
            f'<select name="tf" id="sbtf"{" disabled" if strategy == "wy" else ""}>{tf_opts}</select>'
            f'<button type="submit">▶ 跑回測</button></form>')
    head = (f'<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>🔍 單股回測</title><style>{CARDS_CSS}{SB_CSS}</style></head><body>'
            f'<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維 ・ 單股回測</h2>'
            f'<div class="subtitle">選一檔股票，在 K 線圖上看每一筆交易怎麼進、怎麼出。用的是跟整體回測完全同一套規則，只是只看這一檔。</div>'
            f'{nav}{form}')
    if not sym_raw:
        return head + ('<div class="sbsum">輸入股票代碼、選策略，按 <b>▶ 跑回測</b>。<br>'
                       '<span class="muted">也可以從「🧱 威科夫突破」頁最下面、或「🧪 C1門檻回測」的抽查案例，直接點代碼進來。</span><br><br>'
                       '<b>小提醒：</b>一檔股票兩年通常只有幾筆交易，這頁是用來<b>看懂</b>系統怎麼交易的；'
                       '規則好不好，要看整體回測幾百筆的結果，不要用一兩檔的結果去改規則（overfitting）。</div></body></html>')
    sym = norm_sym(sym_raw)
    try:
        res = stock_backtest(sym, strategy, tf)
    except Exception as e:
        log.warning(f"🔍 單股回測 {sym}: {e}")
        return head + f'<div class="sbsum neg">回測出錯：{_h(e)}</div></body></html>'
    if res.get('error'):
        return head + f'<div class="sbsum">{_h(sym_code(sym))}：{_h(res["error"])}<br><span class="muted">代碼對嗎？可以用搜尋框的下拉選單挑。</span></div></body></html>'
    meta, s, wy = res['meta'], res['stats'], strategy == 'wy'
    rows, js = _sb_trade_rows(res)
    code = sym_code(sym)
    nm = '' if meta['name'] == code else f' {_h(meta["name"])}'
    wr = f'{s["winrate"]:.0f}%' if s['winrate'] is not None else '-'
    ar = f'{s["avg_r"]:+.2f}R' if s['avg_r'] is not None else '-'
    tv = f"{tv_chart_base()}?symbol={tv_sym(sym)}&interval={TV_INTERVAL.get(tf, 'D')}"
    strat_name = '🧱 威科夫 🟢' if wy else f'🃏 VCP 突破卡片（C1 {MIN_DROP_PCT:g}%）'
    if s['n']:
        verdict = (f'這一檔有 <b>{s["n"]}</b> 筆有結果的交易：✅ {s["win"]}、❌ {s["loss"]}、⏱ {s["timeout"]}，'
                   f'勝率 <b>{wr}</b>、平均 <b>{ar}</b>、總共 <b class="{"pos" if s["total_r"] > 0 else "neg"}">{s["total_r"]:+.1f}R</b>。')
    else:
        verdict = '這段期間<b>沒有</b>完成的交易。'
    if wy:
        cnt = {k: sum(1 for c in res['others'] if c.get('result') == k) for k in ('NOFILL', 'CANCEL', 'CHASE', 'PENDING')}
        extra = (f'<br><span class="muted">不算勝負的 🟢：沒觸發 {cnt["NOFILL"]}、觸發前就破 SL（作廢）{cnt["CANCEL"]}、現價已過 Entry 沒追 {cnt["CHASE"]}、'
                 f'還在等觸發 {cnt["PENDING"]}。這些在圖上用灰色 G 標出 🟢 出現的日子。</span>')
        rules = (f'規則：🟢 出現後 {WY_TRIGGER_DAYS} 天內價格碰到 Entry 才成交（跳空就用開盤價）；成交後先碰 SL ＝ −1R、'
                 f'先到 1:{WY_TP_R:g} ＝ +{WY_TP_R:g}R、{WY_HOLD_DAYS} 天都沒碰到 ＝ 到期。')
    else:
        extra = (f'<br><span class="muted">回測結束時還在等突破的形態：{len(res["others"])} 個。</span>' if res['others'] else '')
        how = ('K 線<b>最高價</b>碰到 BO 就成交（進場價＝BO，跳空高開用開盤價；跟在 BO 掛觸價單一樣）' if CARD_ENTRY_MODE == 'touch'
               else 'K 線<b>收盤</b>站上 BO 才進場（用收盤價）')
        rules = (f'規則：最後一個 C 的高點＋緩衝＝BO，{how}；SL＝最後一個 C 低點−緩衝；'
                 f'先碰 SL ＝ −1R、先到 1:1.5 ＝ +1.5R、{MAX_HOLD_BARS} 根都沒碰到 ＝ 到期。進場價高於 BO 超過 {CHASE_MAX_PCT:.0f}% 標 ⚠️不追。')
    summ = (f'<div class="sbsum"><b style="font-size:17px"><a href="{tv}" target="_blank" style="color:#fff">{_h(code)}</a></b>{nm}'
            f'　<span class="muted">{_h(meta.get("sector") or "")}・{strat_name}・{tf}・{res["period"][0]} ～ {res["period"][1]}（最近 {res["bars_used"]} 根）</span><br>'
            f'{verdict}{extra}<br><span class="muted">{rules}</span></div>')
    trs = ''
    for r in rows:
        rcls = 'pos' if (r['r'] or 0) > 0 else ('neg' if (r['r'] or 0) < 0 else '')
        rtxt = f'{r["r"]:+.2f}R' if r['r'] is not None else '-'
        trs += (f'<tr class="tr" data-i="{r["i"]}" onclick="pick({r["i"]})"><td>{r["i"] + 1}</td>'
                f'<td>{_fmt_time(r["t_in"], tf)}</td><td>{fmt_px(r["entry"])}</td><td>{fmt_px(r["sl"])}</td><td>{fmt_px(r["tp"])}</td>'
                f'<td>{r["result"]}</td><td>{_fmt_time(r["t_out"], tf) if r["t_out"] else "-"}</td><td class="{rcls}"><b>{rtxt}</b></td>'
                f'<td class="l">{"".join(f"<span class=sbtag>{_h(t)}</span>" for t in r["tags"])}</td></tr>')
    table = ('<table class="sbt"><tr><th>#</th><th>進場</th><th>進場價</th><th>SL</th><th>1:1.5</th><th>結果</th><th>出場</th><th>R</th><th>標籤</th></tr>'
             + (trs or '<tr><td colspan="9" class="muted">沒有交易</td></tr>') + '</table>')
    focus_i = -1
    if focus:
        f0 = str(focus)[:16]
        for r in rows:
            if (r['t_in'] or '')[:16] == f0 or (r['t_in'] or '')[:10] == f0[:10]:
                focus_i = r['i']; break
    others_js = [{'t': _sb_chart_time(c['created'], tf)} for c in res['others'] if wy and c.get('created')]
    legend = ('<div class="sbleg">圖上標記：<b style="color:#42a5f5">▲ 進</b> 進場 ・ <b style="color:#4cc28e">● +1.5R</b> 達標 ・ '
              '<b style="color:#ee7373">▼ −1R</b> 止損 ・ <b style="color:#aaa">■ 到期</b>'
              + (' ・ <b style="color:#4cc28e">G</b> 🟢 出現的日子（灰色 G＝沒成交）' if wy else '') +
              '。<b>點下面表格的任何一列</b>，圖會跳到那一筆，並畫出進場（藍）、SL（紅）、1:1.5（綠）' + ('、天花板（黃）' if wy else '、BO（黃）') + '的線。</div>')
    payload = json.dumps({'candles': res['candles'], 'trades': js, 'others': others_js, 'focus': focus_i, 'wy': wy, 'intraday': tf != '1D'})
    script = """
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
var D = """ + payload + """;
var lines = [], chart = null, series = null;
function pick(i){
  document.querySelectorAll('tr.tr').forEach(function(r){ r.classList.toggle('sel', +r.dataset.i === i); });
  if(!series) return;
  lines.forEach(function(l){ series.removePriceLine(l); }); lines = [];
  var t = D.trades[i]; if(!t) return;
  function pl(p, c, title){ if(p){ lines.push(series.createPriceLine({price:p, color:c, lineWidth:1, lineStyle:2, axisLabelVisible:true, title:title})); } }
  pl(t.entry, '#42a5f5', '進場'); pl(t.sl, '#ee7373', 'SL'); pl(t.tp, '#4cc28e', '1:1.5');
  pl(t.wy ? null : t.bo, '#ffb300', 'BO'); pl(t.ceil, '#ffb300', '天花板');
  var idx = D.candles.findIndex(function(c){ return c.time === t.in; });
  var j = D.candles.findIndex(function(c){ return c.time === (t.out || t.in); });
  if(idx >= 0){ chart.timeScale().setVisibleLogicalRange({from: Math.max(0, idx - 45), to: Math.min(D.candles.length + 5, (j >= 0 ? j : idx) + 20)}); }
  var row = document.querySelector('tr.tr[data-i="' + i + '"]'); if(row && D.focus === i){ row.scrollIntoView({block:'center'}); }
}
(function(){
  var el = document.getElementById('sbchart');
  if(!window.LightweightCharts){ el.innerHTML = '<div style="padding:20px;color:#aab">圖表載入失敗（網路擋住了圖表程式），下面的交易表照樣可以用。</div>'; return; }
  chart = LightweightCharts.createChart(el, {layout:{background:{color:'#1a1a2e'}, textColor:'#ccc'},
    grid:{vertLines:{color:'#26264a'}, horzLines:{color:'#26264a'}}, rightPriceScale:{borderColor:'#3a3a55'},
    timeScale:{borderColor:'#3a3a55', timeVisible: D.intraday, secondsVisible:false}, crosshair:{mode:0}});
  series = chart.addCandlestickSeries({upColor:'#26a69a', downColor:'#ef5350', borderVisible:false, wickUpColor:'#26a69a', wickDownColor:'#ef5350'});
  series.setData(D.candles);
  var mk = [];
  D.others.forEach(function(o){ mk.push({time:o.t, position:'belowBar', color:'#777', shape:'circle', text:'G'}); });
  D.trades.forEach(function(t){
    if(t.created){ mk.push({time:t.created, position:'belowBar', color:'#4cc28e', shape:'circle', text:'G'}); }
    if(t.in){ mk.push({time:t.in, position:'belowBar', color:'#42a5f5', shape:'arrowUp', text:'進' + (t.i + 1)}); }
    if(t.out){
      var r = t.res === 'TP1' ? {position:'aboveBar', color:'#4cc28e', shape:'circle', text:'+1.5R'}
            : t.res === 'SL' ? {position:'aboveBar', color:'#ee7373', shape:'arrowDown', text:'-1R'}
            : {position:'aboveBar', color:'#aaa', shape:'square', text:(t.r >= 0 ? '+' : '') + (t.r || 0).toFixed(2) + 'R'};
      r.time = t.out; mk.push(r);
    }
  });
  mk.sort(function(a, b){ return a.time < b.time ? -1 : (a.time > b.time ? 1 : 0); });
  series.setMarkers(mk);
  D.trades.forEach(function(t){ t.wy = D.wy; });
  window.addEventListener('resize', function(){ chart.applyOptions({width: el.clientWidth}); });
  if(D.focus >= 0){ pick(D.focus); } else { chart.timeScale().fitContent(); }
})();
</script>"""
    return (head + summ + '<div id="sbchart"></div>' + legend + table +
            '<div class="foot">只供自己研究：照規則自動計算，不是投資建議；一檔股票的幾筆交易樣本太少，不要拿來改規則。</div>'
            + script + '</body></html>')

@app.route('/stock_bt')
def stock_bt_page():
    try:
        return Response(build_stock_bt_html(request.args.get('symbol', '').strip(), request.args.get('strategy', 'wy'),
                                            request.args.get('tf', '1D').upper(), request.args.get('focus', '')),
                        mimetype='text/html')
    except Exception as e:
        log.error(f"🔍 stock_bt error: {e}")
        return f"<html><body style='background:#1a1a2e;color:#eee;font-family:monospace;padding:40px'>🔍 單股回測錯誤：{_h(e)}</body></html>", 200

@app.route('/debug_missing')
def debug_missing():
    """哪幾隻抓不到日線資料（代碼改名或下市時會出現）"""
    miss = [r['symbol'] for r in (cached_results or []) if r.get('nodata')]
    return jsonify({'market': MARKET, 'missing': miss, 'count': len(miss), 'total': len(cached_results or [])})

# ============================================================
# 🌏 多市場網頁：網址前綴（美股在 /us）＋上方市場切換按鈕＋文字換成該市場
# ============================================================
_HREF_RE  = re.compile(r'''((?:href|action)=["'])/(?!/)''')
_FETCH_RE = re.compile(r'''(fetch\(\s*["'])/(?!/)''')

NAV_LABEL_STYLE = 'color:#8b949e;font-size:12px;font-weight:bold;align-self:center;min-width:76px'

def market_switch_html():
    """上面一行：🌏 國家（市場切換）；下面一行：📊 數據報告（原本的頁面按鈕）"""
    if len(ACTIVE_MARKETS) < 2:
        return ''
    out = f'<div class="nav" style="margin-bottom:8px"><span style="{NAV_LABEL_STYLE}">🌏 國家</span>'
    for mk in ACTIVE_MARKETS:
        c = MKT_CFG[mk]
        on = 'background:#6a1b9a;border-color:#6a1b9a;color:#fff;' if mk == MARKET else ''
        out += f'<a href="{c["base"]}/" style="{on}font-weight:bold">{c["tab"]}</a>'
    return out + '</div>'

@app.after_request
def _market_html(resp):
    try:
        if resp.mimetype != 'text/html' or resp.direct_passthrough:
            return resp
        html = resp.get_data(as_text=True)
        if BASE:
            html = _HREF_RE.sub(lambda m_: m_.group(1) + BASE + '/', html)
            html = _FETCH_RE.sub(lambda m_: m_.group(1) + BASE + '/', html)
        for a, b in M['html_replace']:
            html = html.replace(a, b)
        sw = market_switch_html()
        if sw:
            html = html.replace('<div class="nav">',
                                sw + f'<div class="nav"><span style="{NAV_LABEL_STYLE}">📊 數據報告</span>', 1)
        resp.set_data(html)
    except Exception as e:
        log.warning(f"html rewrite: {e}")
    return resp

def scheduler():
    """開盤時間每 scan_every_min 分鐘掃一次（KLSE 60、美股 30），收盤後再補掃一次確認日K。時間用該市場自己的時區。"""
    last_post_close = None
    every = int(menv('SCAN_EVERY_MIN', str(M['scan_every_min'])))
    while True:
        now = datetime.now(MKT_TZ)
        hm = (now.hour, now.minute)
        if is_market_hours():
            run_scan()
            time.sleep(every * 60)
        elif now.weekday() < 5 and M['post_close'] <= hm < M['post_close_end'] and last_post_close != now.date():
            # 收盤後補掃一次：日線/最後一根1H收盤後才會被確認，突破卡片才能當天記錄
            last_post_close = now.date()
            run_scan()
        else:
            time.sleep(300)

def _load_market_module(mk):
    """把這一份程式再載入一次，當成另一個市場（各自的狀態、資料檔、排程完全分開）"""
    import importlib.util, sys
    os.environ['SCANNER_MARKET'] = mk
    spec = importlib.util.spec_from_file_location(f'scanner_{mk.lower()}', os.path.abspath(__file__))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

if __name__ == '__main__':
    import sys
    from werkzeug.serving import run_simple
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    wanted = [x.strip().upper() for x in os.environ.get('MARKETS', 'KLSE,US,SG,HK,CN').split(',') if x.strip().upper() in MKT_CFG]
    mods = {MARKET: sys.modules[__name__]}
    for mk in wanted:
        if mk not in mods:
            mods[mk] = _load_market_module(mk)
    order = [mk for mk in MKT_CFG if mk in mods]
    for mod in mods.values():
        mod.ACTIVE_MARKETS = order
        mod.GLOBAL_SCAN_LOCK = GLOBAL_SCAN_LOCK     # 全部市場共用一把鎖：一次只掃一個
    root = DispatcherMiddleware(app, {MKT_CFG[mk]['base']: mods[mk].app for mk in order if MKT_CFG[mk]['base']})
    log.info(f"莊家思維 股票掃描器 啟動：{' + '.join(MKT_CFG[mk]['flag'] + ' ' + mk for mk in order)}")
    for mk in order:
        threading.Thread(target=mods[mk].scheduler, daemon=True).start()
        threading.Thread(target=mods[mk].run_scan, daemon=True).start()
    port = int(os.environ.get('PORT', 8082))
    run_simple('0.0.0.0', port, root, threaded=True, use_reloader=False, use_debugger=False)
