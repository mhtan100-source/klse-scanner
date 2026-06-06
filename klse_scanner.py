"""
莊家思維 大馬股票掃描器 (KLSE)
- 數據來源：yfinance (.KL)
- 邏輯：C系列收縮（ZigZag pivot）
- 通知：Telegram
- 界面：Flask Web
"""

import os
import time
import threading
import logging
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
MY_TZ = pytz.timezone('Asia/Kuala_Lumpur')

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
    '1597.KL',
    '1277.KL',
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
    '1532.KL',
    '3948.KL',
    '2771.KL',
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
    '2220.KL',
    '5135.KL',
    '5033.KL',
    '4731.KL',
    '0146.KL',
    '1589.KL',
    '5211.KL',
    '0148.KL',
    '3867.KL',
    '2658.KL',
    '3026.KL',
    '4588.KL',
    '5285.KL',
    '5081.KL',
    '7222.KL',
    '4609.KL',
    '5878.KL',
    '6556.KL',
    '7293.KL',
    '7178.KL',
    '5242.KL',
    '4162.KL',
    '3255.KL',
    '5822.KL',
    '5264.KL',
    '3182.KL',
    '4715.KL',
    '3336.KL',
    '1996.KL',
    '9679.KL',
    '3549.KL',
    '5148.KL',
    '5141.KL',
    '1724.KL',
    '9261.KL',
    '2194.KL',
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
    '7090.KL',
    '0177.KL',
    '7212.KL',
    '0197.KL',
    '5250.KL',
    '5216.KL',
    '1301.KL',
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
    '5124.KL',
    '5269.KL',
    '5020.KL',
    '5275.KL',
    '4898.KL',
    '5008.KL',
    '5246.KL',
    '7028.KL',
    '8869.KL',
    '9075.KL',
    '5139.KL',
    '8230.KL',
    '5294.KL',
    '6599.KL',
    '5247.KL',
    '5106.KL',
    '5109.KL',
    '5119.KL',
    '3786.KL',
    '4635.KL',
    '4665.KL',
    '1562.KL',
    '7076.KL',
    '2267.KL',
    '7182.KL',
    '0023.KL',
    '5205.KL',
    '5879.KL',
    '6076.KL',
    '5299.KL',
    '0820EA.KL',
    '5143.KL',
    '3689.KL',
    '5398.KL',
    '8532.KL',
    '0249.KL',
    '5134.KL',
    '3042.KL',
    '7084.KL',
    '0163.KL',
    '3417.KL',
    '5014.KL',
    '3239.KL',
    '4502.KL',
]


# 股票名稱對照表
NAMES = {
    '1155.KL': 'Maybank', '1023.KL': 'CIMB', '1295.KL': 'Public Bank',
    '5819.KL': 'Hong Leong Bank', '1066.KL': 'RHB Bank', '1015.KL': 'AMMB',
    '5185.KL': 'Affin Bank', '1082.KL': 'Alliance Bank', '6947.KL': 'Axiata',
    '6888.KL': 'Maxis', '5168.KL': 'TM', '6012.KL': 'Digi/CelcomDigi',
    '1597.KL': 'BIMB', '5258.KL': 'MBSB', '6399.KL': 'Astro',
    '5183.KL': 'Petronas Gas', '3816.KL': 'Petronas Dagangan',
    '5071.KL': 'Dialog', '1532.KL': 'Hibiscus', '6033.KL': 'Sapura Energy',
    '3948.KL': 'Bumi Armada', '5026.KL': 'Velesto', '2771.KL': 'Wah Seong',
    '5116.KL': 'Yinson', '1929.KL': 'Serba Dinamik',
    '4863.KL': 'Telekom', '6742.KL': 'Time dotcom', '5053.KL': 'Inari',
    '2445.KL': 'IOI Corp', '1961.KL': 'KL Kepong', '2291.KL': 'Sime Darby Plant',
    '1899.KL': 'Genting Plant', '2038.KL': 'Boustead Plant',
    '5029.KL': 'FGV', '2220.KL': 'Berjaya Land',
    '5135.KL': 'Sarawak Plant', '5033.KL': 'Kulim',
    '4731.KL': 'PPB Group', '3182.KL': 'Genting', '4715.KL': 'Genting Malaysia',
    '3336.KL': 'IJM Corp', '1996.KL': 'Gamuda', '9679.KL': 'Sunway',
    '3549.KL': 'YTL Corp', '5148.KL': 'YTL Power', '8583.KL': 'Parkson',
    '5141.KL': 'Hap Seng', '1724.KL': 'Sime Darby',
    '9261.KL': 'Berjaya Corp', '2194.KL': 'WCT Holdings',
    '3476.KL': 'MMC Corp', '5053.KL': 'Inari', '6742.KL': 'Time dotcom',
    '2267.KL': 'Lafarge', '1562.KL': 'Panasonic', '7076.KL': 'Poh Kong',
    '0177.KL': 'Datasonic', '5878.KL': 'Aeon', '7153.KL': 'Top Glove',
    '5027.KL': 'Kossan', '7113.KL': 'Supermax', '0138.KL': 'MyEG',
    '7090.KL': 'Hartalega', '0197.KL': 'Genetec', '7212.KL': 'Karex',
    '4665.KL': 'Pos Malaysia', '0049.KL': 'Vitrox', '5296.KL': 'Revenue Group',
    '0078.KL': 'GHL Systems', '0090.KL': 'Globetronics', '7034.KL': 'Unisem',
    '9814.KL': 'Pentamaster', '5243.KL': 'UWC', '0097.KL': 'Coraza',
    '0196.KL': 'Dagang NeXchange', '0065.KL': 'Scicom', '9296.KL': 'Malaysian Pacific',
    '7073.KL': 'Frontken', '0050.KL': 'Prestariang', '0186.KL': 'D&O Green',
    '5216.KL': 'IHH Healthcare', '1301.KL': 'KPJ Healthcare',
    '5236.KL': 'Sunway REIT', '5180.KL': 'KLCC REIT', '5111.KL': 'Pavilion REIT',
    '5227.KL': 'Axis REIT', '5124.KL': 'Amanahraya REIT',
    '5269.KL': 'IGB REIT', '5020.KL': 'Suria Capital', '5275.KL': 'Sentral REIT',
    '6599.KL': 'Malaysia Airports', '5247.KL': 'MAS (MAB)',
    '5106.KL': 'Westports', '5109.KL': 'Bintulu Port',
    '5119.KL': 'Lingkaran Trans', '3786.KL': 'PLUS (Litrak)',
    '4898.KL': 'UEM Sunrise', '5008.KL': 'SP Setia',
    '5246.KL': 'Eco World', '7028.KL': 'Mah Sing',
    '3557.KL': 'Pharmaniaga', '5079.KL': 'Apex Healthcare',
    '3794.KL': 'Duopharma', '5007.KL': 'Hovid',
    '9121.KL': 'CCK Consolidated', '5136.KL': 'Caring Pharmacy',
    '8869.KL': 'Matrix Concepts', '9075.KL': 'Signature International',
    '5139.KL': 'Sarawak Consolidated', '8230.KL': 'Tambun Indah',
    '4635.KL': 'Misc', '5983.KL': 'KKB Engineering',
    '1619.KL': 'Berjaya Land Dev', '7293.KL': 'Aeon Credit',
    '4588.KL': 'Nestle', '5285.KL': 'QL Resources',
    '5081.KL': 'Dutch Lady', '7222.KL': 'Fraser & Neave',
    '4609.KL': 'Heineken', '0051.KL': 'TWL Holdings',
    '3026.KL': 'Tradewinds Plant', '3867.KL': 'Chin Teck Plant',
    '2658.KL': 'TH Plantation', '4162.KL': 'Scientex',
    '7178.KL': 'Padini', '5242.KL': 'Bonia',
    '6556.KL': 'Mr DIY', '3255.KL': 'V.S. Industry',
    '4197.KL': 'Kerjaya Prospek', '5347.KL': 'Tenaga Nasional',
    '2488.KL': 'KLCC Property', '5099.KL': 'Bursa Malaysia',
    '5250.KL': 'Press Metal', '5822.KL': '99 Speed Mart',
    '5264.KL': 'Farm Fresh', '5294.KL': 'IOI Properties',
    '5879.KL': 'AirAsia X', '6076.KL': 'AmBank Group',
    '7182.KL': '7-Eleven Malaysia', '0023.KL': 'Revenue Group',
    '5209.KL': 'Eco World Dev', '5205.KL': 'Technove Global',
    '5299.KL': 'Teladan Setia', '5143.KL': 'Malayan Flour',
    '3689.KL': 'Batu Kawan', '5134.KL': 'Capital A',
    '3042.KL': 'Hai-O Enterprise', '0163.KL': 'Berjaya Food',
    '3417.KL': 'Tan Chong Motor', '5014.KL': 'Magnum',
    '4502.KL': 'IJM Plantations', '0249.KL': 'Sentoria Group',
    '3239.KL': 'TSM Global', '7084.KL': 'QL Resources',
    '5398.KL': 'Genting Plant Dev', '8532.KL': 'Aeon Credit',
    '0820EA.KL': 'Eco-Arc',
}

# 板塊分類
SECTORS = {
    # 金融
    '1155.KL':'金融','1023.KL':'金融','1295.KL':'金融','5819.KL':'金融',
    '1066.KL':'金融','1015.KL':'金融','5185.KL':'金融','1082.KL':'金融',
    '5258.KL':'金融','5099.KL':'金融','1597.KL':'金融','1277.KL':'金融',
    '5115.KL':'金融','7107.KL':'金融','2488.KL':'金融','6399.KL':'金融',
    '6076.KL':'金融','8532.KL':'金融',
    # 公用/能源
    '5347.KL':'能源','5183.KL':'能源','6033.KL':'能源','5026.KL':'能源',
    '5116.KL':'能源','3816.KL':'能源','5071.KL':'能源','1532.KL':'能源',
    '3948.KL':'能源','2771.KL':'能源','1929.KL':'能源','5250.KL':'能源',
    # 電信
    '6888.KL':'電信','4863.KL':'電信','6012.KL':'電信','6947.KL':'電信',
    '5168.KL':'電信','6742.KL':'電信','6399.KL':'電信',
    # 棕榈油
    '2445.KL':'棕榈油','1961.KL':'棕榈油','2291.KL':'棕榈油','1899.KL':'棕榈油',
    '2038.KL':'棕榈油','5029.KL':'棕榈油','5135.KL':'棕榈油','5033.KL':'棕榈油',
    '4731.KL':'棕榈油','0146.KL':'棕榈油','1589.KL':'棕榈油','5211.KL':'棕榈油',
    '0148.KL':'棕榈油','3867.KL':'棕榈油','2658.KL':'棕榈油','3026.KL':'棕榈油',
    '4502.KL':'棕榈油','5398.KL':'棕榈油',
    # 消費/零售
    '4588.KL':'消費','5285.KL':'消費','5081.KL':'消費','7222.KL':'消費',
    '4609.KL':'消費','5878.KL':'消費','6556.KL':'消費','7293.KL':'消費',
    '7178.KL':'消費','5242.KL':'消費','4162.KL':'消費','3255.KL':'消費',
    '5822.KL':'消費','5264.KL':'消費','3042.KL':'消費','0163.KL':'消費',
    '5014.KL':'消費','3417.KL':'消費','5143.KL':'消費',
    # 工業/建築
    '3182.KL':'工業','4715.KL':'工業','3336.KL':'工業','1996.KL':'工業',
    '9679.KL':'工業','3549.KL':'工業','5148.KL':'工業','5141.KL':'工業',
    '1724.KL':'工業','9261.KL':'工業','2194.KL':'工業','3476.KL':'工業',
    '4197.KL':'工業','8583.KL':'工業','5983.KL':'工業','1619.KL':'工業',
    '2220.KL':'工業','3689.KL':'工業','0249.KL':'工業','3239.KL':'工業',
    # 科技/半導體
    '0049.KL':'科技','5296.KL':'科技','0078.KL':'科技','0090.KL':'科技',
    '7034.KL':'科技','9814.KL':'科技','5243.KL':'科技','0097.KL':'科技',
    '0196.KL':'科技','0065.KL':'科技','9296.KL':'科技','7073.KL':'科技',
    '0050.KL':'科技','0186.KL':'科技','0138.KL':'科技','5053.KL':'科技',
    '0177.KL':'科技','7212.KL':'科技','0197.KL':'科技','5250.KL':'科技',
    '5134.KL':'科技','5205.KL':'科技','5299.KL':'科技',
    # 手套
    '7153.KL':'手套','5027.KL':'手套','7113.KL':'手套','7090.KL':'手套',
    # 醫療
    '5216.KL':'醫療','1301.KL':'醫療','3557.KL':'醫療','5079.KL':'醫療',
    '3794.KL':'醫療','5007.KL':'醫療','9121.KL':'醫療','5136.KL':'醫療',
    # 房地產/REIT
    '5236.KL':'房地產','5180.KL':'房地產','5111.KL':'房地產','5227.KL':'房地產',
    '5124.KL':'房地產','5269.KL':'房地產','5020.KL':'房地產','5275.KL':'房地產',
    '4898.KL':'房地產','5008.KL':'房地產','5246.KL':'房地產','7028.KL':'房地產',
    '8869.KL':'房地產','9075.KL':'房地產','5139.KL':'房地產','8230.KL':'房地產',
    '5294.KL':'房地產','5209.KL':'房地產',
    # 運輸/基建
    '6599.KL':'運輸','5247.KL':'運輸','5106.KL':'運輸','5109.KL':'運輸',
    '5119.KL':'運輸','3786.KL':'運輸','4635.KL':'運輸','4665.KL':'運輸',
    '5879.KL':'運輸','0820EA.KL':'運輸',
    # 其他
    '1562.KL':'其他','7076.KL':'其他','2267.KL':'其他','7084.KL':'其他',
    '0023.KL':'其他','7182.KL':'其他','2488.KL':'其他',
}

# TradingView 代碼對照 (用於Watchlist匯入)
TV_SYMBOLS = {
    '1155.KL': 'MAYBANK', '1295.KL': 'PBBANK', '1023.KL': 'CIMB',
    '5819.KL': 'HLBANK', '1066.KL': 'RHBBANK', '1015.KL': 'AMBANK',
    '5185.KL': 'AFFIN', '1082.KL': 'ABMB', '5258.KL': 'MBSB',
    '5099.KL': 'BURSA', '1597.KL': 'BIMB', '1277.KL': 'HLFG',
    '5115.KL': 'LPI', '7107.KL': 'OSK', '2488.KL': 'KLCCSS',
    '6399.KL': 'ASTRO', '6076.KL': 'AMBANK',
    '5347.KL': 'TENAGA', '5183.KL': 'PETGAS', '6033.KL': 'SAPNRG',
    '5026.KL': 'VELESTO', '5116.KL': 'YINSON', '3816.KL': 'PETDAG',
    '5071.KL': 'DIALOG', '1532.KL': 'HIBISCS', '3948.KL': 'ARMADA',
    '2771.KL': 'WASEONG', '5250.KL': 'PMETAL',
    '6888.KL': 'MAXIS', '4863.KL': 'TM', '6012.KL': 'CDB',
    '6947.KL': 'AXIATA', '5168.KL': 'TELECOM', '6742.KL': 'TIMECOM',
    '2445.KL': 'IOICORP', '1961.KL': 'KLK', '2291.KL': 'SDG',
    '1899.KL': 'GENP', '2038.KL': 'BPLANT', '5029.KL': 'FGV',
    '5135.KL': 'SWKPLNT', '5033.KL': 'KULIM', '4731.KL': 'PPB',
    '0146.KL': 'TSHREIT', '1589.KL': 'CHINTEK', '5211.KL': 'UTDPLT',
    '0148.KL': 'JTIASA', '3867.KL': 'CEPAT', '2658.KL': 'THP',
    '3026.KL': 'TWS', '4502.KL': 'IJMPLNT',
    '4588.KL': 'NESTLE', '5285.KL': 'QL', '5081.KL': 'DLADY',
    '7222.KL': 'F&N', '4609.KL': 'HEIM', '5878.KL': 'AEON',
    '6556.KL': 'MRDIY', '7293.KL': 'AEONCR', '7178.KL': 'PADINI',
    '5242.KL': 'BONIA', '4162.KL': 'SCIENTX', '3255.KL': 'VS',
    '5822.KL': '99SMART', '5264.KL': 'FFB', '3042.KL': 'HAIO',
    '0163.KL': 'BJFOOD', '5014.KL': 'MAGNUM', '3417.KL': 'TCHONG',
    '5143.KL': 'MFM',
    '3182.KL': 'GENTING', '4715.KL': 'GENM', '3336.KL': 'IJM',
    '1996.KL': 'GAMUDA', '9679.KL': 'SUNWAY', '3549.KL': 'YTL',
    '5148.KL': 'YTLPOWR', '5141.KL': 'HAPSENG', '1724.KL': 'SIME',
    '9261.KL': 'BJCORP', '2194.KL': 'WCT', '3476.KL': 'MMC',
    '4197.KL': 'KERJAYA', '8583.KL': 'PARKSON', '5983.KL': 'KKBE',
    '1619.KL': 'BJLAND', '2220.KL': 'BJLAND', '3689.KL': 'BKAWAN',
    '0049.KL': 'VITROX', '5296.KL': 'REVENUE', '0078.KL': 'GHL',
    '0090.KL': 'GTRONIC', '7034.KL': 'UNISEM', '9814.KL': 'PENTA',
    '5243.KL': 'UWC', '0097.KL': 'CORAZA', '0196.KL': 'DNEX',
    '0065.KL': 'SCICOM', '9296.KL': 'MPI', '7073.KL': 'FRONTKN',
    '0050.KL': 'PRESBHD', '0186.KL': 'DKSH', '0138.KL': 'MYEG',
    '5053.KL': 'INARI', '0177.KL': 'DATASONIC', '7212.KL': 'KAREX',
    '0197.KL': 'GENETEC', '5134.KL': 'CAPITALA', '5205.KL': 'TECHNOVE',
    '5299.KL': 'TELADAN', '7153.KL': 'TOPGLOV', '5027.KL': 'KOSSAN',
    '7113.KL': 'SUPERMX', '7090.KL': 'HARTA',
    '5216.KL': 'IHH', '1301.KL': 'KPJ', '3557.KL': 'PHARMA',
    '5079.KL': 'APEX', '3794.KL': 'DUOPHARMA', '5007.KL': 'HOVID',
    '9121.KL': 'CCK', '5136.KL': 'CARING',
    '5236.KL': 'SUNREIT', '5180.KL': 'KLCCSS', '5111.KL': 'PAVREIT',
    '5227.KL': 'AXREIT', '5124.KL': 'AMFIRST', '5269.KL': 'IGBREIT',
    '5020.KL': 'SURIA', '5275.KL': 'SENTRAL', '4898.KL': 'UEMS',
    '5008.KL': 'SPSETIA', '5246.KL': 'ECOWLD', '7028.KL': 'MAHSING',
    '8869.KL': 'MATRIX', '9075.KL': 'SIGN', '5139.KL': 'SWKCORP',
    '8230.KL': 'TAMBUN', '5294.KL': 'IOIPG', '5209.KL': 'EWINT',
    '6599.KL': 'AIRPORT', '5247.KL': 'MAB', '5106.KL': 'WPRTS',
    '5109.KL': 'BIPORT', '5119.KL': 'LITRAK', '3786.KL': 'LITRAK',
    '4635.KL': 'MISC', '4665.KL': 'POS', '5879.KL': 'AAX',
    '1562.KL': 'PANAMY', '7076.KL': 'POHKONG', '2267.KL': 'LAFMSIA',
    '7182.KL': '7ELEVEN', '0023.KL': 'REVENUE', '7084.KL': 'QL',
    '3239.KL': 'TSM', '0249.KL': 'SENTORIA', '5398.KL': 'GENPLANT',
    '8532.KL': 'AEONCR', '0820EA.KL': 'ECOARC',
}

TF_LABELS = ['1D', '4H', '1H']

cached_results = []
scan_state = {'status': 'idle', 'last_scan': None, 'lock': threading.Lock()}

def is_market_hours():
    now = datetime.now(MY_TZ)
    if now.weekday() >= 5:
        return False
    open_t  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    close_t = now.replace(hour=17, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t

def fetch_ohlcv(symbol, timeframe):
    try:
        if timeframe == '1D':
            df = yf.download(symbol, period='1y', interval='1d', progress=False, auto_adjust=True)
        elif timeframe == '4H':
            df = yf.download(symbol, period='60d', interval='1h', progress=False, auto_adjust=True)
            if df.empty:
                return pd.DataFrame()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            df = df.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
            return df
        elif timeframe == '1H':
            df = yf.download(symbol, period='30d', interval='1h', progress=False, auto_adjust=True)
        else:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df.dropna()
    except Exception as e:
        log.warning(f"fetch {symbol} {timeframe}: {e}")
        return pd.DataFrame()

def calc_stage(df):
    if len(df) < 200:
        return '-'
    close = df['close']
    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    c = close.iloc[-1]
    m50  = ma50.iloc[-1]
    m150 = ma150.iloc[-1]
    m200 = ma200.iloc[-1]
    slope150 = ma150.iloc[-1] - ma150.iloc[-10]
    slope200 = ma200.iloc[-1] - ma200.iloc[-10]
    bull_arr = m50 > m150 > m200
    bear_arr = m50 < m150 < m200
    if bull_arr and slope150 > 0 and slope200 > 0 and c > m150:
        return 'S2'
    elif bull_arr and c < m150:
        return 'S3'
    elif bear_arr and slope150 < 0 and c < m150:
        return 'S4'
    else:
        return 'S1'

def is_pivot_high(df, i, length=5):
    if i < length or i >= len(df) - length:
        return False
    h = df['high'].iloc[i]
    return all(h >= df['high'].iloc[i-j] for j in range(1, length+1)) and \
           all(h >= df['high'].iloc[i+j] for j in range(1, length+1))

def is_pivot_low(df, i, length=5):
    if i < length or i >= len(df) - length:
        return False
    l = df['low'].iloc[i]
    return all(l <= df['low'].iloc[i-j] for j in range(1, length+1)) and \
           all(l <= df['low'].iloc[i+j] for j in range(1, length+1))

def has_three_combo(df, start, end):
    count = 0
    for i in range(start, min(end, len(df))):
        o = df['open'].iloc[i]
        c = df['close'].iloc[i]
        h = df['high'].iloc[i]
        body = abs(c - o)
        rng  = h - df['low'].iloc[i]
        is_bear = c < o
        is_doji = rng > 0 and body / rng < 0.3 and (h - max(o,c)) > 2 * body
        if is_bear or is_doji:
            count += 1
            if count >= 3:
                return True
        else:
            count = 0
    return False

def find_c_count(df):
    n = len(df)
    if n < 20:
        return 0
    pivot_lows = [i for i in range(5, n-5) if is_pivot_low(df, i, 5)]
    if not pivot_lows:
        pivot_lows = [i for i in range(3, n-3) if is_pivot_low(df, i, 3)]
    if not pivot_lows:
        return 0
    c_count = 0
    first_pl = pivot_lows[0]
    c1_high_idx = df['high'].iloc[:first_pl].idxmax() if first_pl > 0 else None
    if c1_high_idx is None:
        return 0
    c1_high_pos = df.index.get_loc(c1_high_idx)
    c1_high = df['high'].iloc[c1_high_pos]
    c1_low  = df['low'].iloc[first_pl]
    if not has_three_combo(df, c1_high_pos, first_pl):
        return 0
    c_count = 1
    prev_high = c1_high
    prev_low  = c1_low
    prev_pl   = first_pl
    for pl_idx in pivot_lows[1:]:
        if c_count >= 6:
            break
        segment_high = df['high'].iloc[prev_pl:pl_idx].max() if pl_idx > prev_pl else 0
        segment_low  = df['low'].iloc[pl_idx]
        if segment_high <= prev_high and segment_low >= prev_low:
            if has_three_combo(df, prev_pl, pl_idx):
                c_count += 1
                prev_high = segment_high
                prev_low  = segment_low
                prev_pl   = pl_idx
    return c_count

def scan_symbol(symbol):
    result = {'symbol': symbol}
    # TV symbol for KLSE: remove .KL, use KLSE: prefix
    tv_sym = symbol.replace('.KL', '')
    result['tv_symbol'] = f"KLSE:{tv_sym}"
    for tf in TF_LABELS:
        try:
            df = fetch_ohlcv(symbol, tf)
            if df.empty or len(df) < 20:
                result[tf] = '-'
                result[f'{tf}_cls'] = 'gray'
                continue
            if tf == '1D':
                stage = calc_stage(df)
                c_count = find_c_count(df)
                if c_count > 0:
                    result[tf] = f'{stage} C{c_count}\U0001f3af'
                    result[f'{tf}_cls'] = 'green'
                else:
                    result[tf] = stage
                    result[f'{tf}_cls'] = 'gray'
            else:
                c_count = find_c_count(df)
                if c_count > 0:
                    result[tf] = f'C{c_count}\U0001f3af'
                    result[f'{tf}_cls'] = 'green'
                else:
                    result[tf] = '-'
                    result[f'{tf}_cls'] = 'gray'
        except Exception as e:
            result[tf] = 'ERR'
            result[f'{tf}_cls'] = 'gray'
    return result

def run_scan():
    global cached_results
    with scan_state['lock']:
        if scan_state['status'] == 'scanning':
            return
        scan_state['status'] = 'scanning'
    # Deduplicate symbols
    seen = set()
    unique_syms = [s for s in SYMBOLS if s not in seen and not seen.add(s)]
    log.info(f"🇲🇾 莊家思維 大馬掃描器 開始掃描 ({len(unique_syms)} 只)")
    results = []
    for sym in unique_syms:
        r = scan_symbol(sym)
        results.append(r)
        log.info(f"✅ {sym}: {{'1D': '{r.get('1D','-')}', '4H': '{r.get('4H','-')}', '1H': '{r.get('1H','-')}'}}")
        time.sleep(0.3)
    cached_results = results
    with scan_state['lock']:
        scan_state['status'] = 'done'
        scan_state['last_scan'] = datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M:%S')
    log.info(f"掃描完成！共 {len(results)} 只")
    send_telegram(results)

def send_telegram(results):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    now = datetime.now(MY_TZ).strftime('%Y-%m-%d %H:%M')
    lines = []
    for r in results:
        if not any('\U0001f3af' in str(r.get(tf,'')) for tf in TF_LABELS):
            continue
        sym = r['symbol'].replace('.KL','')
        d1  = r.get('1D', '-')
        h4  = r.get('4H', '-')
        h1  = r.get('1H', '-')
        lines.append(f"{sym} | 1D:{d1} | 4H:{h4} | 1H:{h1}")
    if not lines:
        return
    header = f"\U0001f1f2\U0001f1fe 大馬莊家思維掃描\n{now}\n共{len(lines)}只有C信號\n{'─'*25}"
    msg = header + "\n" + "\n".join(lines[:50])
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg},
            timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram error: {e}")

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:monospace;font-size:13px}
.header{background:#161b22;padding:12px 16px;border-bottom:1px solid #30363d;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.title{font-size:16px;font-weight:bold;color:#58a6ff}
.info{color:#8b949e;font-size:12px}
.btn{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:bold}
.btn-scan{background:#238636;color:#fff}
.btn-scan:hover{background:#2ea043}
.scanning{color:#f0a742;animation:blink 1s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.4}}
.controls{padding:8px 16px;background:#161b22;border-bottom:1px solid #30363d;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
input[type=text]{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:5px 10px;border-radius:6px;font-size:12px;width:180px}
select{background:#0d1117;border:1px solid #30363d;color:#e6edf3;padding:5px 10px;border-radius:6px;font-size:12px}
.btn-export{background:#1f6feb;color:#fff;padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:12px;font-weight:bold}
.chk-label{color:#8b949e;font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer}
table{width:100%;border-collapse:collapse}
th{background:#161b22;padding:8px 6px;text-align:center;border-bottom:2px solid #30363d;color:#8b949e;position:sticky;top:0}
td{padding:7px 6px;text-align:center;border-bottom:1px solid #21262d}
td.sym{text-align:left;padding-left:12px;font-weight:bold}
td.sym a{color:#58a6ff;text-decoration:none}
td.sym a:hover{text-decoration:underline}
tr:hover td{background:#161b22}
.green{color:#3fb950;font-weight:bold}
.gray{color:#8b949e}
</style>
<script>
function doScan(){
  fetch('/rescan',{method:'POST'});
  document.querySelector('.btn-scan').disabled=true;
  document.querySelector('.btn-scan').innerText='⏳ 掃描中...';
  var check=setInterval(function(){
    fetch('/status').then(function(r){return r.json();}).then(function(d){
      if(d.status==='done'){clearInterval(check);location.reload();}
    });
  },10000);
}
function exportTxt(){
  var lines=[];
  document.querySelectorAll('tbody tr').forEach(function(r){
    if(r.style.display==='none') return;
    var sym=r.getAttribute('data-symbol');
    if(sym) lines.push(sym);
  });
  var txt=lines.join(String.fromCharCode(10));
  var blob=new Blob([txt],{type:'text/plain'});
  var a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='klse_watchlist.txt';
  a.click();
}
function filterTable(){
  var q=document.getElementById('search').value.toLowerCase();
  var stage=document.getElementById('stageFilter').value;
  var sector=document.getElementById('sectorFilter').value;
  var onlyC=document.getElementById('onlyC').checked;
  document.querySelectorAll('tbody tr').forEach(function(r){
    var text=r.innerText.toLowerCase();
    var hasC=text.includes('c1')||text.includes('c2')||text.includes('c3')||text.includes('c4')||text.includes('c5')||text.includes('c6');
    var matchQ=q===''||text.includes(q);
    var rowStage=r.getAttribute('data-stage')||'';
    var rowSector=r.getAttribute('data-sector')||'';
    var matchStage=stage===''||rowStage===stage;
    var matchSector=sector===''||rowSector===sector;
    r.style.display=(matchQ&&matchStage&&matchSector&&(!onlyC||hasC))?'':'none';
  });
}
</script>
</head>
<body>
<div class="header">
  <span class="title">&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</span>
  <span class="info">上次掃描：LAST_SCAN</span>
  <button class="btn btn-scan" onclick="doScan()">&#x1F504; 重新掃描</button>
  STATUS_SPAN
</div>
<div class="controls">
  <input type="text" id="search" placeholder="搜尋股票..." oninput="filterTable()">
  <select id="stageFilter" onchange="filterTable()">
    <option value="">全部Stage</option>
    <option value="S1">S1</option>
    <option value="S2">S2</option>
    <option value="S3">S3</option>
    <option value="S4">S4</option>
  </select>
  <select id="sectorFilter" onchange="filterTable()">
    <option value="">全部板塊</option>
    <option value="金融">金融</option>
    <option value="能源">能源</option>
    <option value="電信">電信</option>
    <option value="棕榈油">棕榈油</option>
    <option value="消費">消費</option>
    <option value="工業">工業</option>
    <option value="科技">科技</option>
    <option value="手套">手套</option>
    <option value="醫療">醫療</option>
    <option value="房地產">房地產</option>
    <option value="運輸">運輸</option>
    <option value="其他">其他</option>
  </select>
  <label class="chk-label"><input type="checkbox" id="onlyC" onchange="filterTable()"> 只顯示有C的</label>
  <button class="btn-export" onclick="exportTxt()">&#x1F4E5; Export TXT</button>
  <span class="info">共 TOTAL 只</span>
</div>
BANNER
<table>
<thead><tr>
<th>股票</th><th>板塊</th><th>1D</th><th>4H</th><th>1H</th>
</tr></thead>
<tbody>
ROWS
</tbody>
</table>
</body>
</html>"""

def build_html(status='done'):
    rows = ''
    for r in (cached_results or []):
        sym = r['symbol']
        tv  = r.get('tv_symbol', sym.replace('.KL',''))
        tv_url = f"https://www.tradingview.com/chart/?symbol={tv}"
        d1  = r.get('1D', '-')
        stage = d1.split(' ')[0] if d1 not in ('-', '') else '-'
        name = r.get('name', sym)
        sector = r.get('sector', '其他')
        tv_code = r.get('tv_symbol', 'KLSE:' + sym.replace('.KL',''))
        rows += f'<tr data-stage="{stage}" data-sector="{sector}" data-symbol="{tv_code}"><td class="sym"><a href="{tv_url}" target="_blank">{name}</a><br><span style="color:#8b949e;font-size:10px">{sym}</span></td>'
        rows += f'<td style="color:#8b949e;font-size:12px">{sector}</td>'
        for tf in TF_LABELS:
            txt = r.get(tf, '-')
            cls = r.get(f'{tf}_cls', 'gray')
            rows += f'<td class="{cls}">{txt}</td>'
        rows += '</tr>\n'
    last = scan_state.get('last_scan') or '-'
    total = len(cached_results)
    status_span = '<span class="scanning">⏳ 掃描中...</span>' if status == 'scanning' else ''
    banner = '<div style="background:#f0a742;color:#000;text-align:center;padding:6px;font-weight:bold">⏳ 掃描中，請稍候...</div>' if status == 'scanning' else ''
    return (HTML
        .replace('LAST_SCAN', last)
        .replace('STATUS_SPAN', status_span)
        .replace('TOTAL', str(total))
        .replace('BANNER', banner)
        .replace('ROWS', rows))

@app.route('/')
def index():
    with scan_state['lock']:
        status = scan_state['status']
    try:
        return build_html(status)
    except Exception as e:
        log.error(f"build_html error: {e}")
        return f"<html><body style='background:#0d1117;color:#e6edf3;font-family:monospace;padding:40px'><h2>🇲🇾 大馬莊家思維掃描器</h2><p>⏳ 掃描中，請稍候約10分鐘後刷新頁面...</p><p style='color:#8b949e'>Error: {e}</p></body></html>", 200

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

def scheduler():
    while True:
        if is_market_hours():
            run_scan()
            time.sleep(3600)
        else:
            time.sleep(300)

if __name__ == '__main__':
    log.info("🇲🇾 莊家思維 大馬掃描器 啟動")
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=run_scan, daemon=True).start()
    port = int(os.environ.get('PORT', 8082))
    app.run(host='0.0.0.0', port=port, debug=False)
