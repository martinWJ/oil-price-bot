import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
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
        
        # 格式化回覆訊息
        message = f"本周{date_range}中油最新油價資訊:\n"
        for name, price in matches:
            # 移除「汽油」字樣
            name = name.replace('汽油', '')
            message += f"{name}: {price} 元/公升\n"
        
        return message
    except Exception as e:
        logger.error(f"抓取當前油價時發生錯誤: {str(e)}")
        return None

def get_oil_price_trend():
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        html = response.text

        # 精確匹配 var pieSeries = [...]
        match = re.search(r'var\s+pieSeries\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            logger.error("找不到 pieSeries 油價資料")
            return None

        price_data_str = match.group(1)
        logger.info(f"找到的資料字串 (pieSeries): {price_data_str[:100]}...")

        try:
            # 將單引號替換為雙引號，並處理 JavaScript 的 undefined
            price_data_str = price_data_str.replace("'", '"').replace("undefined", "null")
            price_data = json.loads(price_data_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析 pieSeries 油價資料時發生錯誤: {e}")
            return None

        if not price_data:
            logger.error("pieSeries 油價資料為空")
            return None

        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []

        # 重新組織數據，根據新的 pieSeries 結構提取日期和價格
        # 使用字典來儲存按日期分類的油價，方便整理
        dated_oil_prices = {}

        for entry in price_data:
            # 檢查 entry 是否是字典且包含 'name' (日期) 和 'data' 列表
            if isinstance(entry, dict) and 'name' in entry and 'data' in entry:
                roc_date = entry['name']
                # 遍歷該日期下的油品數據
                for oil_data_point in entry['data']:
                    # 檢查 oil_data_point 是否是字典且包含 'name' (油品名稱) 和 'y' (價格)
                    if isinstance(oil_data_point, dict) and 'name' in oil_data_point and 'y' in oil_data_point:
                        oil_name = oil_data_point['name']
                        price = oil_data_point['y']

                        if roc_date not in dated_oil_prices:
                            dated_oil_prices[roc_date] = {
                                '92無鉛汽油': None,
                                '95無鉛汽油': None,
                                '98無鉛汽油': None,
                                '超級/高級柴油': None # Use the exact label from the data
                            }
                        # 將提取到的價格存儲到對應的日期和油品下
                        # Convert price to float, handle potential errors later if needed
                        try:
                            dated_oil_prices[roc_date][oil_name] = float(price)
                        except (ValueError, TypeError):
                            logger.warning(f"無法將價格轉換為浮點數: {price} for {oil_name} on {roc_date}")
                            dated_oil_prices[roc_date][oil_name] = None # Store as None if conversion fails


        # 按照日期排序並整理數據
        # 過濾掉日期或價格為 None 的日期，並確保所有油品價格都存在
        sorted_dates_roc = sorted([date for date, prices in dated_oil_prices.items() if
                                  date is not None and
                                  prices.get('92無鉛汽油') is not None and
                                  prices.get('95無鉛汽油') is not None and
                                  prices.get('98無鉛汽油') is not None and
                                  prices.get('超級/高級柴油') is not None])


        dates_roc = []
        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []

        for roc_date in sorted_dates_roc:
            dates_roc.append(roc_date)
            prices = dated_oil_prices[roc_date]
            prices_92.append(prices['92無鉛汽油'])
            prices_95.append(prices['95無鉛汽油'])
            prices_98.append(prices['98無鉛汽油'])
            prices_diesel.append(prices['超級/高級柴油'])


        # 將民國日期轉換為西元日期
        date_labels_ad = [tw_date_to_ad_date(d) for d in dates_roc]


        if not date_labels_ad:
             logger.error("沒有有效的油價數據可供繪製圖表")
             return None

        # 分解有效數據 (實際上已經在上面過濾和整理過了，這裡只是為了命名清晰)
        # date_labels_ad, prices_92, prices_95, prices_98, prices_diesel = date_labels_ad, prices_92, prices_95, prices_98, prices_diesel


        plt.figure(figsize=(12, 7)) # Adjust figure size for better readability
        # 使用索引作為 X 軸數據，並在 xticks 中設置日期標籤
        x_indices = range(len(date_labels_ad))
        plt.plot(x_indices, prices_92, marker='o', label='92 Unleaded')
        plt.plot(x_indices, prices_95, marker='o', label='95 Unleaded')
        plt.plot(x_indices, prices_98, marker='o', label='98 Unleaded')
        plt.plot(x_indices, prices_diesel, marker='o', label='Super Diesel')

        # 在每個點上添加價格標籤，使用索引作為 X 軸位置
        for i in x_indices:
             plt.text(i, prices_92[i], f"{prices_92[i]:.1f}", ha='center', va='bottom', fontsize=9) # Smaller font size
             plt.text(i, prices_95[i], f"{prices_95[i]:.1f}", ha='center', va='bottom', fontsize=9)
             plt.text(i, prices_98[i], f"{prices_98[i]:.1f}", ha='center', va='bottom', fontsize=9)
             plt.text(i, prices_diesel[i], f"{prices_diesel[i]:.1f}", ha='center', va='bottom', fontsize=9)


        plt.xlabel('Date')
        plt.ylabel('Price (NTD/L)')
        plt.title('CPC Oil Price Trend')

        # 設置 X 軸刻度位置和標籤
        # 顯示所有日期標籤
        plt.xticks(x_indices, date_labels_ad, rotation=45, ha='right', fontsize=10) #ha='right' 讓標籤右對齊刻度線

        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()

        logger.info("Oil price trend chart generated in memory with corrected dates")
        return buffer
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        import traceback
        logger.error(traceback.format_exc()) # Log full traceback
        return None

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
    text = event.message.text
    logger.info(f"收到訊息: {text}")
    logger.info(f"訊息來源: {event.source.user_id}")
    
    try:
        if text in ["趨勢", "油價趨勢"]:
            logger.info("開始處理趨勢請求")
            try:
                buffer = get_oil_price_trend()
                if buffer:
                    logger.info("成功取得油價趨勢圖")
                    try:
                        # 將圖片保存到臨時檔案
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                            temp_file.write(buffer.getvalue())
                            temp_file_path = temp_file.name
                        
                        try:
                            # 讀取檔案內容為 bytes
                            with open(temp_file_path, 'rb') as file:
                                file_bytes = file.read()
                            
                            # 上傳到 ImageKit
                            try:
                                # 將圖片轉換為 base64
                                base64_image = base64.b64encode(file_bytes).decode('utf-8')
                                
                                # 使用 requests 直接調用 ImageKit API
                                from urllib.parse import urljoin
                                
                                upload_url = "https://upload.imagekit.io/api/v1/files/upload"
                                private_key = os.getenv('IMAGEKIT_PRIVATE_KEY')
                                auth_string = f"{private_key}:"
                                auth_b64 = base64.b64encode(auth_string.encode()).decode()
                                
                                headers = {
                                    "Authorization": f"Basic {auth_b64}"
                                }
                                
                                data = {
                                    "file": base64_image,
                                    "fileName": f"oil_price_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                                    "useUniqueFileName": "true",
                                    "tags": ["oil_price", "trend"],
                                    "responseFields": ["url"]
                                }
                                
                                response = requests.post(upload_url, headers=headers, data=data)
                                response.raise_for_status()
                                upload_result = response.json()
                                
                                logger.info(f"ImageKit upload response: {upload_result}")
                                
                                if upload_result and 'url' in upload_result:
                                    image_url = upload_result['url']
                                    logger.info(f"Successfully uploaded image to ImageKit: {image_url}")
                                    
                                    # 回傳圖片
                                    line_bot_api.reply_message(
                                        event.reply_token,
                                        ImageSendMessage(
                                            original_content_url=image_url,
                                            preview_image_url=image_url
                                        )
                                    )
                                    logger.info("Oil price trend chart sent")
                                else:
                                    raise ValueError("No URL in upload result")
                                    
                            except Exception as e:
                                logger.error(f"Error uploading image: {str(e)}")
                                logger.error(f"Error type: {type(e)}")
                                # 如果上傳失敗，直接使用本地檔案
                                try:
                                    # 回傳圖片
                                    line_bot_api.reply_message(
                                        event.reply_token,
                                        TextSendMessage(text="Sorry, unable to upload the image. Please try again later.")
                                    )
                                except Exception as direct_error:
                                    logger.error(f"Error sending error message: {str(direct_error)}")
                        finally:
                            # 清理臨時檔案
                            try:
                                os.unlink(temp_file_path)
                            except Exception as cleanup_error:
                                logger.error(f"Error cleaning up temporary file: {str(cleanup_error)}")
                    except Exception as e:
                        logger.error(f"Error processing image: {str(e)}")
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="Sorry, failed to process the image. Please try again later.")
                        )
                else:
                    logger.error("無法取得油價趨勢資料")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="Sorry, unable to get oil price trend data. Please try again later.")
                    )
            except Exception as e:
                logger.error(f"Error processing trend request: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="Sorry, system is temporarily unable to process your request. Please try again later.")
                )
        elif text == "油價":
            logger.info("收到油價指令")
            price_info = get_current_oil_price()
            if price_info:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=price_info)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="Sorry, unable to get current oil price. Please try again later.")
                )
        else:
            logger.info(f"收到未知指令: {text}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="Hello! I am an oil price query bot\n\nPlease enter the following commands:\n• 油價：Query current oil price\n• 趨勢：View oil price trend chart")
            )
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="Sorry, system error occurred. Please try again later.")
            )
        except Exception as reply_error:
            logger.error(f"Error sending error message: {str(reply_error)}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 