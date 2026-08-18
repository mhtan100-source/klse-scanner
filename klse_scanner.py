"""
莊家思維 大馬股票掃描器 (KLSE)
- 數據來源：yfinance (.KL)
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
from flask import Flask, jsonify, Response, request
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
    '5143.KL',
    '3689.KL',
    '5134.KL',
    '3042.KL',
    '0163.KL',
    '3417.KL',
    '5014.KL',
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
    '5074.KL',
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
    '1503.KL',
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
    '1236.KL',
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
    '5175.KL',
    '5179.KL',
    '5219.KL',
    '5222.KL',
    '5300.KL',
    '5305.KL',
    '5322.KL',
    '5345.KL',
    '5533.KL',
    '5576.KL',
    '5738.KL',
    '5797.KL',
    '6025.KL',
    '6203.KL',
    '6297.KL',
    '6637.KL',
    '6912.KL',
    '7004.KL',
    '7005.KL',
    '7020.KL',
    '7055.KL',
    '7068.KL',
    '7071.KL',
    '7078.KL',
    '7080.KL',
    '7085.KL',
    '7112.KL',
    '7115.KL',
    '7120.KL',
    '7123.KL',
    '7131.KL',
    '7133.KL',
    '7134.KL',
    '7140.KL',
    '7145.KL',
    '7164.KL',
    '7170.KL',
    '7173.KL',
    '7176.KL',
    '7211.KL',
    '7213.KL',
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
    '8699.KL',
    '8826.KL',
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
    '8699.KL': 'Syarikat Kayu Wangi',
    '8826.KL': 'Eng Teknologi Holdings',
    '8893.KL': 'Mk Land Holdings',
    '9148.KL': 'Greater Bay Holdings',
    '9237.KL': 'Sarawak Consolidated Industries',
    '9288.KL': 'Bonia Corporation',
    '9334.KL': 'Kesm Industries',
    '9881.KL': 'Leader Steel Holdings',
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
    '3948.KL':'消費','2771.KL':'工業','1929.KL':'棕榈油','5250.KL':'能源',
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
    '0177.KL':'工業','7212.KL':'工業','0197.KL':'消費','5250.KL':'科技',
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

TF_LABELS = ['1D', '4H', '1H']   # 由高到低（跟crypto版TF_LABELS的順序相反，這裡直接就是高到低）
TV_INTERVAL  = {'1H': '60', '4H': '240', '1D': 'D'}
# 跟crypto版(scannerrailway.py)共用同一個TradingView Layout（莊家思維指標已經加在上面），
# 預設值bd3vZUwt是crypto版目前使用的Layout代碼；可用環境變數TV_LAYOUT_ID覆寫
TV_LAYOUT_ID = os.environ.get('TV_LAYOUT_ID', 'bd3vZUwt')

def tv_chart_base():
    return f"https://www.tradingview.com/chart/{TV_LAYOUT_ID}/" if TV_LAYOUT_ID else "https://www.tradingview.com/chart/"

# ============================================================
# C系列參數（對齊 莊家思維 Contraction V53 / scannerrailway.py）
# ============================================================
MIN_DROP_PCT       = 10.0   # C1最小跌幅%，跟Pine的minDropPct一致；股票波動比crypto小，如果訊號太少可調低
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
]
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
    now = datetime.now(MY_TZ)
    if now.weekday() >= 5:
        return False
    open_t  = now.replace(hour=9,  minute=0,  second=0, microsecond=0)
    close_t = now.replace(hour=17, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t

def _fetch_1h_raw(symbol, retries=2):
    """抓取原始1小時K線（730天，yfinance 60m interval上限）。
    4H和1H共用同一份原始資料，避免同一symbol重複下載造成Yahoo限流。
    帶簡單重試，因為批次掃描時intraday端點比daily端點更容易被限流/逾時。"""
    for attempt in range(retries):
        try:
            df = yf.download(symbol, period='730d', interval='1h', progress=False, auto_adjust=True)
        except Exception as e:
            log.warning(f"fetch {symbol} 1H raw attempt{attempt+1}: {e}")
            df = pd.DataFrame()
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            df = df.dropna()
            if not df.empty:
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
            df = yf.download(symbol, period='2y', interval='1d', progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]
            return df.dropna()
        elif timeframe == '4H':
            base = raw_1h if raw_1h is not None else _fetch_1h_raw(symbol)
            if base.empty:
                return pd.DataFrame()
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
def find_c1(df: pd.DataFrame, start_idx: int) -> dict:
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

        if pct < MIN_DROP_PCT:
            if fail_priority < 2:
                fail_msg = f'跌幅不足 {pct:.2f}% < {MIN_DROP_PCT}% (高={sh_v:.4f} 低={sl_v:.4f})'
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
def analyze(df: pd.DataFrame, df_daily: pd.DataFrame) -> dict:
    empty = {'stage': 0, 's1_strong': False, 'divergence': '', 'has_c': False, 'c_count': 0,
             'base': 0, 'entry_zone': '', 'ready': False, 'is_bear': False, 'last_pct': None}
    if df.empty or len(df) < 50: return empty
    if df_daily.empty or len(df_daily) < 50: return empty

    stage, s1_strong, divergence = get_stage(df_daily)

    start_idx_bull = find_start_bar_bull(df)
    c_list = []
    is_bear = False

    if start_idx_bull >= 0:
        c1 = find_c1(df, start_idx_bull)
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

    return {'stage': stage, 's1_strong': s1_strong, 'divergence': divergence, 'has_c': has_c, 'c_count': c_count,
            'base': base, 'entry_zone': entry_zone, 'ready': ready, 'is_bear': is_bear, 'last_pct': last_pct}

# ============================================================
# 掃描單一股票
# ============================================================
def scan_symbol(symbol):
    result = {'symbol': symbol}
    result['name'] = NAMES.get(symbol, symbol.replace('.KL',''))
    result['sector'] = SECTORS.get(symbol, '其他')
    # 改用數字代碼直接組TradingView連結（MYX:5168這種），TradingView會自動導向正確股票，
    # 不再依賴容易錯置的TV_SYMBOLS簡稱對照表（見audit_names發現的大量代碼錯置問題）
    result['tv_symbol'] = f"MYX:{symbol.replace('.KL', '')}"

    df_daily = fetch_ohlcv(symbol, '1D')
    raw_1h = _fetch_1h_raw(symbol)  # 4H/1H共用同一份原始資料，只下載一次

    for tf in TF_LABELS:
        try:
            df = df_daily if tf == '1D' else fetch_ohlcv(symbol, tf, raw_1h=raw_1h)
            if df.empty or len(df) < 50 or df_daily.empty or len(df_daily) < 50:
                result[tf] = '-'
                result[f'{tf}_cls'] = 'gray'
                continue

            res = analyze(df, df_daily)
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
        d1  = r.get('1D', '-')
        cls = r.get('1D_cls', 'gray')
        # 多頭跟空頭都通知（對齊crypto版後來的改動，原本只看多頭S2）
        if cls not in ('bull-c', 'bull-ready', 'bear-c', 'bear-ready'):
            continue
        name    = r.get('name', r['symbol'].replace('.KL',''))
        sector  = r.get('sector', '')
        h4      = r.get('4H', '-')
        h1      = r.get('1H', '-')
        side    = '空' if r.get('1D_isbear', False) else '多'
        pct     = r.get('1D_pct')
        pct_str = f" | 收斂{pct}%" if pct is not None else ""
        lines.append(f"{name}({sector}) | {side} | 1D:{d1}{pct_str} | 4H:{h4} | 1H:{h1}")
    if not lines:
        return
    header = f"\U0001f1f2\U0001f1fe 大馬莊家思維掃描\n{now}\n共{len(lines)}只 訊號\n{'─'*20}"
    batches = [lines[i:i+25] for i in range(0, len(lines), 25)]
    for i, batch in enumerate(batches):
        part = f" ({i+1}/{len(batches)})" if len(batches) > 1 else ""
        msg = header + part + "\n" + "\n".join(batch)
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg},
                timeout=10
            )
            time.sleep(1)
        except Exception as e:
            log.warning(f"Telegram error: {e}")

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
</style></head><body>
<h2>&#x1F1F2;&#x1F1FE; 大馬莊家思維掃描器</h2>
<div class="subtitle">KLSE股票 · 操盤跟莊（邏輯已對齊 莊家思維 Contraction V53）</div>
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
<div class="info">更新：LAST_SCAN | 共 TOTAL 只 | 顯示 <span id="countDisplay">TOTAL</span> 個</div>
<textarea id="watchlistBox" readonly style="background:#1a1a2e;color:#0f0;border:1px solid #444;padding:12px;border-radius:6px;width:500px;height:150px;font-family:monospace;font-size:12px;margin-top:8px;display:none"></textarea>
<br id="watchlistBr" style="display:none">
<table id="mainTable">
  <tr><th>股票</th><th>板塊</th><th>1D</th><th>4H</th><th>1H</th></tr>
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
</script>
</body></html>"""

def build_html(status='done'):
    rows = ''
    for r in (cached_results or []):
        sym = r['symbol']
        tv  = r.get('tv_symbol', sym.replace('.KL',''))
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
        rows += f'<td class="sym"><a href="{tv_url}" target="_blank">{name}</a><br><span style="color:#8b949e;font-size:10px">{sym}</span><span style="display:none">{alias}</span></td>'
        rows += f'<td style="color:#aaa;font-size:12px;text-align:center">{sector}</td>'
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

    return (HTML
        .replace('SCANNING_BANNER', scanning_banner)
        .replace('SECTOR_OPTIONS', sector_opts)
        .replace('LAST_SCAN', last)
        .replace('TOTAL', str(total))
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
    symbol = request.args.get('symbol', '1155.KL')
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
    symbol = request.args.get('symbol', '1155.KL')
    if not symbol.upper().endswith('.KL'):
        symbol = symbol.upper() + '.KL'
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
