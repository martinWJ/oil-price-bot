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
imagekit = ImageKit(public_key=IMAGEKIT_PUBLIC_KEY, private_key=IMAGEKIT_PRIVATE_KEY, url_endpoint=IMAGEKIT_URL_ENDPOINT)

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
        
        match = re.search(r'var\s+priceData\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            match = re.search(r'var\s+[a-zA-Z0-9_]+\s*=\s*(\[.*?\]);', html, re.DOTALL)
            if not match:
                logger.error("找不到油價資料")
                return None
                
        price_data_str = match.group(1)
        logger.info(f"找到的資料字串: {price_data_str[:100]}...")
        
        try:
            price_data_str = price_data_str.replace("'", '"')
            price_data = json.loads(price_data_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析油價資料時發生錯誤: {e}")
            return None
            
        if not price_data:
            logger.error("油價資料為空")
            return None
            
        dates = []
        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []
        
        for item in price_data:
            if isinstance(item, dict) and 'data' in item:
                if '92' in item.get('label', ''):
                    prices_92 = [float(x) for x in item['data']]
                elif '95' in item.get('label', ''):
                    prices_95 = [float(x) for x in item['data']]
                elif '98' in item.get('label', ''):
                    prices_98 = [float(x) for x in item['data']]
                elif '柴油' in item.get('label', ''):
                    prices_diesel = [float(x) for x in item['data']]
        
        if prices_92:
            dates = list(range(1, len(prices_92) + 1))
        
        if not all([dates, prices_92, prices_95, prices_98, prices_diesel]):
            logger.error("無法取得完整的油價資料")
            return None
        
        plt.figure(figsize=(10, 6))
        plt.plot(dates, prices_92, marker='o', label='92 Unleaded')
        plt.plot(dates, prices_95, marker='o', label='95 Unleaded')
        plt.plot(dates, prices_98, marker='o', label='98 Unleaded')
        plt.plot(dates, prices_diesel, marker='o', label='Super Diesel')
        
        for x, y in zip(dates, prices_92):
            plt.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_95):
            plt.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_98):
            plt.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_diesel):
            plt.text(x, y, f"{y:.1f}", ha='center', va='bottom', fontsize=10)
            
        plt.xlabel('Date')
        plt.ylabel('Price (NTD/L)')
        plt.title('CPC Oil Price Trend')
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        logger.info("Oil price trend chart generated in memory")
        return buffer
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
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
                            upload_result = imagekit.upload_file(
                                file=file_bytes,
                                file_name=f"oil_price_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                                options={
                                    "response_fields": ["url"],
                                    "tags": ["oil_price", "trend"]
                                }
                            )
                            
                            logger.info(f"ImageKit upload result: {upload_result}")
                            
                            # 檢查上傳結果
                            if isinstance(upload_result, dict) and 'url' in upload_result:
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
                                raise ValueError("Invalid upload result format")
                            
                        except Exception as e:
                            logger.error(f"Error uploading image: {str(e)}")
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
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 