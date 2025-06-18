import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, FlexSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
from imagekitio import ImageKit
import matplotlib
import base64
import tempfile
from apscheduler.schedulers.background import BackgroundScheduler
matplotlib.use('Agg')  # 使用 Agg 後端

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定字體
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 初始化 Flask 應用程式
app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 檢查環境變數
logger.info("檢查環境變數...")
if not os.getenv('LINE_CHANNEL_ACCESS_TOKEN'):
    logger.error("LINE_CHANNEL_ACCESS_TOKEN 未設置")
if not os.getenv('LINE_CHANNEL_SECRET'):
    logger.error("LINE_CHANNEL_SECRET 未設置")
if not os.getenv('IMAGEKIT_PUBLIC_KEY'):
    logger.error("IMAGEKIT_PUBLIC_KEY 未設置")
if not os.getenv('IMAGEKIT_PRIVATE_KEY'):
    logger.error("IMAGEKIT_PRIVATE_KEY 未設置")
if not os.getenv('IMAGEKIT_URL_ENDPOINT'):
    logger.error("IMAGEKIT_URL_ENDPOINT 未設置")

# ImageKit.io 相關配置
IMAGEKIT_PUBLIC_KEY = os.getenv('IMAGEKIT_PUBLIC_KEY')
IMAGEKIT_PRIVATE_KEY = os.getenv('IMAGEKIT_PRIVATE_KEY')
IMAGEKIT_URL_ENDPOINT = os.getenv('IMAGEKIT_URL_ENDPOINT')

# 初始化 ImageKit
imagekit = ImageKit(
    private_key=os.getenv('IMAGEKIT_PRIVATE_KEY'),
    public_key=os.getenv('IMAGEKIT_PUBLIC_KEY'),
    url_endpoint=os.getenv('IMAGEKIT_URL_ENDPOINT')
)

# 訂閱用戶檔案路徑
SUBSCRIBERS_FILE = 'subscribed_users.txt'

def load_subscribers():
    """從檔案載入訂閱用戶 ID 列表。"""
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, 'r') as f:
                # 讀取每一行並去除空白字元，如果行不為空則加入集合
                subscribers = {line.strip() for line in f if line.strip()}
            logger.info(f"成功載入 {len(subscribers)} 個訂閱用戶 ID。")
            return subscribers
        logger.info(f"訂閱用戶檔案 {SUBSCRIBERS_FILE} 不存在，返回空集合。")
        return set()
    except Exception as e:
        logger.error(f"載入訂閱用戶檔案時發生錯誤: {str(e)}")
        return set()

def save_subscribers(subscribers):
    """將訂閱用戶 ID 列表儲存到檔案。"""
    try:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            for user_id in sorted(subscribers):
                f.write(user_id + '\n')
        logger.info(f"成功儲存 {len(subscribers)} 個訂閱用戶 ID。")
    except Exception as e:
        logger.error(f"儲存訂閱用戶檔案時發生錯誤: {str(e)}")

def add_subscriber(user_id):
    """新增一個訂閱用戶 ID。"""
    subscribers = load_subscribers()
    if user_id not in subscribers:
        subscribers.add(user_id)
        save_subscribers(subscribers)
        logger.info(f"用戶 {user_id} 已新增至訂閱列表。")
        return True
    logger.info(f"用戶 {user_id} 已存在於訂閱列表中。")
    return False

def remove_subscriber(user_id):
    """移除一個訂閱用戶 ID。"""
    subscribers = load_subscribers()
    if user_id in subscribers:
        subscribers.remove(user_id)
        save_subscribers(subscribers)
        logger.info(f"用戶 {user_id} 已從訂閱列表中移除。")
        return True
    logger.info(f"用戶 {user_id} 不存在於訂閱列表中。")
    return False

def tw_date_to_ad_date(tw_date_str):
    """Converts a Republic of China (Taiwan) calendar date string (YYY/MM/DD) to a Western calendar date string (YYYY-MM-DD)."""
    try:
        year_roc, month, day = map(int, tw_date_str.split('/'))
        year_ad = year_roc + 1911
        # Use datetime to format the date correctly, ensuring leading zeros for month/day
        date_obj = datetime(year_ad, month, day)
        return date_obj.strftime('%Y-%m-%d')
    except Exception as e:
        logger.error(f"Error converting ROC date {tw_date_str} to AD date: {str(e)}")
        return tw_date_str # Return original string if conversion fails

def get_current_oil_price():
    try:
        url = 'https://www.cpc.com.tw/'
        logger.info(f"開始抓取當前油價，URL: {url}")
        
        # 設定 headers 模擬瀏覽器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找包含油價資訊的文字
        price_text = None
        for text in soup.find_all(string=re.compile(r'92無鉛汽油每公升|95無鉛汽油每公升|98無鉛汽油每公升|超級柴油每公升')):
            if '每公升' in text:
                price_text = text
                break
        
        if not price_text:
            logger.error("找不到油價資訊")
            return None
            
        # 使用正則表達式提取油價資訊
        price_pattern = r'(92無鉛汽油|95無鉛汽油|98無鉛汽油|超級柴油)每公升(\d+\.\d+)元'
        matches = re.findall(price_pattern, price_text)
        
        if not matches:
            logger.error("無法解析油價資訊")
            return None
            
        # 計算本週日期範圍
        today = datetime.now()
        # 找到最近的週日
        days_since_sunday = today.weekday() + 1
        start_date = today - timedelta(days=days_since_sunday)
        end_date = start_date + timedelta(days=6)
        
        # 格式化日期
        date_range = f"{start_date.strftime('%m/%d')}~{end_date.strftime('%m/%d')}"
        
        oil_prices = []
        for name, price in matches:
            # 移除「汽油」字樣
            name = name.replace('汽油', '')
            oil_prices.append({"name": name, "price": price})
        
        return {"date_range": date_range, "oil_prices": oil_prices}
    except Exception as e:
        logger.error(f"抓取當前油價時發生錯誤: {str(e)}")
        return None

def _parse_historical_oil_data(html_content):
    """
    Parses the historical oil price data from the given HTML content.
    Extracts the 'pieSeries' JavaScript variable, parses it, and organizes the data
    into a dictionary where keys are ROC dates and values are dictionaries
    containing oil prices for various types.
    """
    try:
        # 精確匹配 var pieSeries = [...]
        match = re.search(r'var\s+pieSeries\s*=\s*(\[.*?\]);', html_content, re.DOTALL)
        if not match:
            logger.error("找不到 pieSeries 油價資料")
            return None

        price_data_str = match.group(1)
        # logger.info(f"找到的資料字串 (pieSeries): {price_data_str[:100]}...") # Removed debugging log
        # logger.info(f"完整 pieSeries 資料字串: {price_data_str}") # Removed debugging log

        try:
            # 將單引號替換為雙引號，並處理 JavaScript 的 undefined
            price_data_str = price_data_str.replace("\'", '"').replace("undefined", "null")
            price_data = json.loads(price_data_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析 pieSeries 油價資料時發生錯誤: {e}")
            return None

        if not price_data:
            logger.error("pieSeries 油價資料為空")
            return None

        dated_oil_prices = {}

        # 定義油品名稱的映射關係，將原始數據中的名稱標準化
        oil_name_mapping = {
            "92 無鉛汽油": "92無鉛汽油",
            "95 無鉛汽油": "95無鉛汽油",
            "98 無鉛汽油": "98無鉛汽油",
            "超級/高級柴油": "超級/高級柴油"
        }

        for entry in price_data:
            if isinstance(entry, dict) and 'name' in entry and 'data' in entry and entry['data']:
                roc_date = entry['name']
                oil_data_point = entry['data'][0]

                if isinstance(oil_data_point, dict) and 'name' in oil_data_point and 'y' in oil_data_point:
                    raw_oil_name = oil_data_point['name']
                    price = oil_data_point['y']

                    standardized_oil_name = oil_name_mapping.get(raw_oil_name)

                    if standardized_oil_name:
                        if roc_date not in dated_oil_prices:
                            dated_oil_prices[roc_date] = {}

                        try:
                            dated_oil_prices[roc_date][standardized_oil_name] = float(price)
                        except (ValueError, TypeError):
                            logger.warning(f"無法將價格轉換為浮點數: {price} for {raw_oil_name} on {roc_date}")
                            dated_oil_prices[roc_date][standardized_oil_name] = None
        return dated_oil_prices
    except Exception as e:
        logger.error(f"解析歷史油價數據時發生錯誤: {str(e)}")
        return None

def get_oil_price_trend():
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        html = response.text

        dated_oil_prices = _parse_historical_oil_data(html)
        if not dated_oil_prices:
            logger.error("沒有有效的油價數據可供繪製圖表")
            return None

        logger.info(f"成功解析歷史油價數據，共有 {len(dated_oil_prices)} 個日期")

        # 按照日期排序
        sorted_dates_roc = sorted(dated_oil_prices.keys())
        logger.info(f"排序後的日期: {sorted_dates_roc}")

        # If after parsing and sorting, there are no dates, return None
        if not sorted_dates_roc:
            logger.error("經過數據解析和排序後，沒有有效的日期數據")
            return None

        # Prepare final lists for plotting, ensuring all oil types have a value (or None) for each date
        dates_roc = []
        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []

        # Define all expected standardized oil names
        # all_oil_types = ['92無鉛汽油', '95無鉛汽油', '98無鉛汽油', '超級/高級柴油'] # Keep this for reference if needed

        for roc_date in sorted_dates_roc:
            dates_roc.append(roc_date)
            current_day_prices = dated_oil_prices.get(roc_date, {})

            prices_92.append(current_day_prices.get('92無鉛汽油', None))
            prices_95.append(current_day_prices.get('95無鉛汽油', None))
            prices_98.append(current_day_prices.get('98無鉛汽油', None))
            prices_diesel.append(current_day_prices.get('超級/高級柴油', None))

        logger.info(f"92無鉛汽油價格: {prices_92}")
        logger.info(f"95無鉛汽油價格: {prices_95}")
        logger.info(f"98無鉛汽油價格: {prices_98}")
        logger.info(f"超級柴油價格: {prices_diesel}")

        # Now, filter out dates where NO oil price is available, even after aggregation.
        # This will prevent plotting empty date points.
        valid_indices = [i for i, date in enumerate(dates_roc) if any(
            [prices_92[i] is not None, prices_95[i] is not None, prices_98[i] is not None, prices_diesel[i] is not None]
        )]

        if not valid_indices:
            logger.error("經過數據整理和過濾後，沒有任何油品數據可供繪製圖表")
            return None

        dates_roc = [dates_roc[i] for i in valid_indices]
        prices_92 = [prices_92[i] for i in valid_indices]
        prices_95 = [prices_95[i] for i in valid_indices]
        prices_98 = [prices_98[i] for i in valid_indices]
        prices_diesel = [prices_diesel[i] for i in valid_indices]

        logger.info(f"過濾後的有效日期: {dates_roc}")
        logger.info(f"過濾後的92無鉛汽油價格: {prices_92}")
        logger.info(f"過濾後的95無鉛汽油價格: {prices_95}")
        logger.info(f"過濾後的98無鉛汽油價格: {prices_98}")
        logger.info(f"過濾後的超級柴油價格: {prices_diesel}")

        # 將民國日期轉換為西元日期用於圖表標籤
        date_labels_ad = [tw_date_to_ad_date(d) for d in dates_roc]
        logger.info(f"轉換後的西元日期標籤: {date_labels_ad}")

        plt.figure(figsize=(12, 7)) # Adjust figure size for better readability
        # 使用索引作為 X 軸數據，並在 xticks 中設置日期標籤
        x_indices = range(len(date_labels_ad))
        
        # 只繪製有數據的線條
        if any(p is not None for p in prices_95):
            plt.plot(x_indices, prices_95, marker='o', label='95 Unleaded', linewidth=2, markersize=6)
        if any(p is not None for p in prices_92):
            plt.plot(x_indices, prices_92, marker='s', label='92 Unleaded', linewidth=2, markersize=6)
        if any(p is not None for p in prices_98):
            plt.plot(x_indices, prices_98, marker='^', label='98 Unleaded', linewidth=2, markersize=6)
        if any(p is not None for p in prices_diesel):
            plt.plot(x_indices, prices_diesel, marker='d', label='Super Diesel', linewidth=2, markersize=6)

        # 在每個點上添加價格標籤，使用索引作為 X 軸位置
        for i in x_indices:
            # 檢查價格是否為 None，如果不是則添加標籤
            if prices_92[i] is not None:
                plt.text(i, prices_92[i], f"{prices_92[i]:.1f}", ha='center', va='bottom', fontsize=10)
            if prices_95[i] is not None:
                plt.text(i, prices_95[i], f"{prices_95[i]:.1f}", ha='center', va='bottom', fontsize=10)
            if prices_98[i] is not None:
                plt.text(i, prices_98[i], f"{prices_98[i]:.1f}", ha='center', va='bottom', fontsize=10)
            if prices_diesel[i] is not None:
                plt.text(i, prices_diesel[i], f"{prices_diesel[i]:.1f}", ha='center', va='bottom', fontsize=10)

        plt.xlabel('Date', fontsize=12)
        plt.ylabel('Price (NTD/L)', fontsize=12)
        plt.title('CPC Oil Price Trend (Last 7 Weeks)', fontsize=14, fontweight='bold')

        # 設置 X 軸刻度位置和標籤
        # 顯示所有日期標籤
        plt.xticks(x_indices, date_labels_ad, rotation=45, ha='right', fontsize=10)

        plt.legend(fontsize=10)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        # 確保圖表有內容
        plt.ylim(min(min(prices_92), min(prices_95), min(prices_98), min(prices_diesel)) - 1, 
                max(max(prices_92), max(prices_95), max(prices_98), max(prices_diesel)) + 1)

        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        buffer.seek(0)
        plt.close()

        logger.info("Oil price trend chart generated in memory with corrected dates")

        # 上傳圖片到 ImageKit
        upload_response = imagekit.upload_file(
            file=buffer.getvalue(),
            file_name="oil_price_trend.png"
        )
        logger.info("Oil price trend chart uploaded to ImageKit")
        return upload_response.url
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc()) # Log full traceback
        return None

def get_weekly_oil_comparison():
    """
    Compares the current week's oil price with the last week's oil price for 95 Unleaded and Super Diesel.
    Returns a Flex Message containing the price changes with color-coded text.
    """
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取歷史油價數據進行週比週比較，URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        html = response.text

        dated_oil_prices = _parse_historical_oil_data(html)
        if not dated_oil_prices:
            logger.error("沒有有效的歷史油價數據可供週比週比較")
            return None

        # 按照日期排序，並轉換為西元日期對象以便比較
        sorted_dates_ad_str = sorted([tw_date_to_ad_date(d) for d in dated_oil_prices.keys()], reverse=True)
        sorted_dates_ad_obj = [datetime.strptime(d, '%Y-%m-%d') for d in sorted_dates_ad_str]

        # 找到最近的兩個週日（或價格調整日）
        current_week_price_date = None
        last_week_price_date = None
        current_week_date_obj = None
        last_week_date_obj = None
        
        for i, date_obj in enumerate(sorted_dates_ad_obj):
            roc_date = sorted_dates_ad_str[i].replace('-', '/')
            roc_date_for_lookup = None
            try:
                roc_year = date_obj.year - 1911
                roc_date_for_lookup = f"{roc_year}/{date_obj.month:02d}/{date_obj.day:02d}"
            except Exception as e:
                logger.warning(f"無法轉換 {date_obj} 為民國日期格式以進行查詢: {e}")
                continue

            if roc_date_for_lookup and roc_date_for_lookup in dated_oil_prices:
                prices_for_date = dated_oil_prices[roc_date_for_lookup]
                if prices_for_date.get('95無鉛汽油') is not None or prices_for_date.get('超級/高級柴油') is not None:
                    if current_week_price_date is None:
                        current_week_price_date = roc_date_for_lookup
                        current_week_date_obj = date_obj
                    elif last_week_price_date is None and date_obj < current_week_date_obj:
                        last_week_price_date = roc_date_for_lookup
                        last_week_date_obj = date_obj
                        break
        
        if not current_week_price_date or not last_week_price_date:
            logger.warning("未能找到足夠的歷史油價數據進行週比週比較")
            return None

        current_week_prices = dated_oil_prices.get(current_week_price_date, {})
        last_week_prices = dated_oil_prices.get(last_week_price_date, {})

        # 準備 Flex Message 的內容
        contents = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "本週與上週油價比較",
                        "weight": "bold",
                        "size": "sm",
                        "margin": "md"
                    }
                ]
            }
        }

        # 比較 95 無鉛汽油
        price_95_current = current_week_prices.get('95無鉛汽油')
        price_95_last = last_week_prices.get('95無鉛汽油')

        if price_95_current is not None and price_95_last is not None:
            diff_95 = price_95_current - price_95_last
            status_95 = "漲" if diff_95 > 0 else "跌" if diff_95 < 0 else "持平"
            color_95 = "#FF0000" if diff_95 > 0 else "#00FF00" if diff_95 < 0 else "#000000"
            msg_95 = f"無鉛汽油本週{status_95}{abs(diff_95):.1f}元/公升"
            contents["body"]["contents"].append({
                "type": "text",
                "text": msg_95,
                "color": color_95,
                "size": "sm",
                "margin": "md"
            })
        elif price_95_current is not None and price_95_last is None:
            contents["body"]["contents"].append({
                "type": "text",
                "text": "無鉛汽油上週數據不完整，無法比較。",
                "size": "sm",
                "margin": "md"
            })
        elif price_95_current is None:
            contents["body"]["contents"].append({
                "type": "text",
                "text": "無鉛汽油本週數據不完整，無法比較。",
                "size": "sm",
                "margin": "md"
            })

        # 比較超級柴油
        price_diesel_current = current_week_prices.get('超級/高級柴油')
        price_diesel_last = last_week_prices.get('超級/高級柴油')

        if price_diesel_current is not None and price_diesel_last is not None:
            diff_diesel = price_diesel_current - price_diesel_last
            status_diesel = "漲" if diff_diesel > 0 else "跌" if diff_diesel < 0 else "持平"
            color_diesel = "#FF0000" if diff_diesel > 0 else "#00FF00" if diff_diesel < 0 else "#000000"
            msg_diesel = f"超級柴油本週{status_diesel}{abs(diff_diesel):.1f}元/公升"
            contents["body"]["contents"].append({
                "type": "text",
                "text": msg_diesel,
                "color": color_diesel,
                "size": "sm",
                "margin": "md"
            })
        elif price_diesel_current is not None and price_diesel_last is None:
            contents["body"]["contents"].append({
                "type": "text",
                "text": "超級柴油上週數據不完整，無法比較。",
                "size": "sm",
                "margin": "md"
            })
        elif price_diesel_current is None:
            contents["body"]["contents"].append({
                "type": "text",
                "text": "超級柴油本週數據不完整，無法比較。",
                "size": "sm",
                "margin": "md"
            })

        return contents

    except Exception as e:
        logger.error(f"生成週比週油價比較時發生錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def send_push_notification():
    """發送推播訊息給所有訂閱用戶。"""
    try:
        # 載入訂閱用戶
        subscribers = load_subscribers()
        if not subscribers:
            logger.info("沒有訂閱用戶，跳過推播。")
            return

        # 取得當前油價
        oil_price_data = get_current_oil_price()
        if not oil_price_data:
            logger.error("無法取得油價資料，跳過推播。")
            return

        # 建立推播訊息
        message = f"📊 本週油價資訊 ({oil_price_data['date_range']})\n\n"
        for price in oil_price_data['oil_prices']:
            message += f"{price['name']}: {price['price']} 元/公升\n"

        # 發送推播訊息給所有訂閱用戶
        for user_id in subscribers:
            try:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=message)
                )
                logger.info(f"成功發送推播訊息給用戶 {user_id}")
            except Exception as e:
                logger.error(f"發送推播訊息給用戶 {user_id} 時發生錯誤: {str(e)}")

    except Exception as e:
        logger.error(f"執行推播任務時發生錯誤: {str(e)}")

# 設定排程器
def init_scheduler():
    logger.info("開始設定排程器...")
    scheduler = BackgroundScheduler(timezone='Asia/Singapore')
    logger.info("排程器時區設定為：Asia/Singapore")

    # 正式用：每週日中午12點執行
    scheduler.add_job(
        send_push_notification,
        'cron',
        day_of_week='sun',
        hour=12,
        minute=0,
        id='oil_price_notification',
        replace_existing=True
    )
    logger.info("已設定每週日中午 12 點執行排程任務")

    try:
        scheduler.start()
        logger.info("排程器成功啟動！")
    except Exception as e:
        logger.error(f"排程器啟動失敗：{str(e)}")
        raise e

# 在應用程式啟動時初始化排程器
init_scheduler()

@app.route("/", methods=['GET'])
def health_check():
    """健康檢查端點"""
    return "OK", 200

@app.route("/webhook", methods=['POST'])
def callback():
    # 取得 X-Line-Signature header 值
    signature = request.headers['X-Line-Signature']
    logger.info(f"收到 webhook 請求，signature: {signature}")

    # 取得請求內容
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
        logger.info("成功處理 webhook 請求")
    except InvalidSignatureError:
        logger.error("無效的簽名")
        abort(400)
    except Exception as e:
        logger.error(f"處理 webhook 請求時發生錯誤: {str(e)}")
        abort(500)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理收到的文字訊息"""
    logger.info(f"收到訊息: {event.message.text}")
    logger.info(f"訊息來源: {event.source.user_id}")
    
    # 取得用戶 ID
    user_id = event.source.user_id
    
    # 處理訂閱指令
    if event.message.text == "訂閱油價":
        if add_subscriber(user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您已成功訂閱油價推播！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您已經訂閱過了！")
            )
    
    # 處理取消訂閱指令
    elif event.message.text == "取消訂閱":
        if remove_subscriber(user_id):
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您已成功取消訂閱油價推播！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您尚未訂閱油價推播！")
            )
    
    # 處理訂閱人數指令
    elif event.message.text == "訂閱人數":
        subscribers = load_subscribers()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"目前共有 {len(subscribers)} 人訂閱油價推播！")
        )
    
    # 處理油價趨勢指令
    elif event.message.text == "油價趨勢":
        trend_buffer = get_oil_price_trend()
        if trend_buffer:
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url=trend_buffer,
                    preview_image_url=trend_buffer
                )
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="無法取得油價趨勢圖，請稍後再試！")
            )
    
    # 處理測試推播指令
    elif event.message.text == "測試推播":
        try:
            send_push_notification()
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="已發送測試推播！")
            )
        except Exception as e:
            logger.error(f"發送測試推播時發生錯誤: {str(e)}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="發送測試推播時發生錯誤，請稍後再試！")
            )
    
    # 處理說明指令
    elif event.message.text == "說明":
        help_text = """📱 油價推播機器人使用說明：

1️⃣ 訂閱油價：開始接收每週油價推播
2️⃣ 取消訂閱：停止接收油價推播
3️⃣ 測試推播：立即發送一次油價推播
4️⃣ 訂閱人數：查看目前訂閱人數
5️⃣ 油價趨勢：查看油價趨勢圖
6️⃣ 說明：顯示此使用說明

每週日中午 12 點會自動推播最新油價資訊！"""
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=help_text)
        )
    
    # 處理其他訊息
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入「說明」查看使用說明！")
        )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 