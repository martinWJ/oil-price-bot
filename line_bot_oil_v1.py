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
matplotlib.rc('font', family=['Arial Unicode MS', 'DejaVu Sans', 'sans-serif'])
matplotlib.rc('axes', unicode_minus=False)
# import undetected_chromedriver as uc
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.common.by import By
# import time

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        # 使用更寬鬆的正則表達式來匹配 JavaScript 變數
        match = re.search(r'var\s+priceData\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            # 如果找不到 priceData，嘗試尋找其他可能的變數名稱
            match = re.search(r'var\s+[a-zA-Z0-9_]+\s*=\s*(\[.*?\]);', html, re.DOTALL)
            if not match:
                logger.error("找不到油價資料")
                return None
                
        price_data_str = match.group(1)
        logger.info(f"找到的資料字串: {price_data_str[:100]}...")  # 只記錄前100個字元
        
        try:
            # 清理資料字串
            price_data_str = price_data_str.replace("'", '"')  # 將單引號替換為雙引號
            price_data = json.loads(price_data_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析油價資料時發生錯誤: {e}")
            return None
            
        if not price_data:
            logger.error("油價資料為空")
            return None
            
        # 處理新的資料格式
        dates = []
        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []
        
        for item in price_data:
            if isinstance(item, dict) and 'data' in item:
                if '92' in item.get('label', ''):
                    prices_92 = item['data']
                elif '95' in item.get('label', ''):
                    prices_95 = item['data']
                elif '98' in item.get('label', ''):
                    prices_98 = item['data']
                elif '柴油' in item.get('label', ''):
                    prices_diesel = item['data']
        
        # 從第一個資料集獲取日期
        if prices_92:
            dates = [f"{i+1}" for i in range(len(prices_92))]
        
        if not all([dates, prices_92, prices_95, prices_98, prices_diesel]):
            logger.error("無法取得完整的油價資料")
            return None
        
        # 繪製圖表
        plt.figure(figsize=(10, 6))
        plt.plot(dates, prices_92, marker='o', label='92無鉛汽油')
        plt.plot(dates, prices_95, marker='o', label='95無鉛汽油')
        plt.plot(dates, prices_98, marker='o', label='98無鉛汽油')
        plt.plot(dates, prices_diesel, marker='o', label='超級柴油')
        
        # 在每個點上標註數值
        for x, y in zip(dates, prices_92):
            plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_95):
            plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_98):
            plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
        for x, y in zip(dates, prices_diesel):
            plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
            
        plt.xlabel('日期')
        plt.ylabel('價格 (新台幣元/公升)')
        plt.title('中油油價趨勢')
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        logger.info("油價趨勢圖表已生成到記憶體")
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
                    # 上傳圖片到 ImageKit
                    result = imagekit.upload_file(
                        file=buffer.getvalue(),  # 使用 getvalue() 獲取二進制數據
                        file_name=f"oil_price_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                        options={
                            "response_fields": ["url"],
                            "tags": ["oil_price", "trend"]
                        }
                    )
                    
                    if result and isinstance(result, dict) and 'url' in result:
                        logger.info(f"成功上傳圖片到 ImageKit: {result['url']}")
                        # 回傳圖片訊息
                        line_bot_api.reply_message(
                            event.reply_token,
                            ImageSendMessage(
                                original_content_url=result['url'],
                                preview_image_url=result['url']
                            )
                        )
                        logger.info("已回傳油價趨勢圖")
                    else:
                        logger.error("圖片上傳失敗，ImageKit 回應: " + str(result))
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="抱歉，圖片上傳失敗，請稍後再試")
                        )
                else:
                    logger.error("無法取得油價趨勢資料")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="抱歉，目前無法取得油價趨勢資料，請稍後再試")
                    )
            except Exception as e:
                logger.error(f"處理趨勢請求時發生錯誤: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="抱歉，系統暫時無法處理您的請求，請稍後再試")
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
                    TextSendMessage(text="抱歉，目前無法取得當前油價，請稍後再試")
                )
        else:
            logger.info(f"收到未知指令: {text}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您好！我是油價查詢機器人\n\n請輸入以下指令：\n• 油價：查詢當前油價\n• 趨勢：查看油價趨勢圖")
            )
    except Exception as e:
        logger.error(f"處理訊息時發生錯誤: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="抱歉，系統發生錯誤，請稍後再試")
            )
        except Exception as reply_error:
            logger.error(f"回覆錯誤訊息時發生錯誤: {str(reply_error)}")

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 