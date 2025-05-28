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
matplotlib.rc('font', family='Microsoft JhengHei')
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
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找所有表格
        tables = soup.find_all('table')
        logger.info(f"找到 {len(tables)} 個表格")
        
        # 尋找包含油價資訊的表格
        price_table = None
        for table in tables:
            # 檢查表格是否包含油價相關文字
            if table.find(string=re.compile(r'92無鉛|95無鉛|98無鉛|超級柴油')):
                price_table = table
                break
        
        if not price_table:
            logger.error("找不到油價表格")
            return None
            
        # 解析表格內容
        rows = price_table.find_all('tr')
        if len(rows) < 2:
            logger.error("油價表格格式不正確")
            return None
            
        # 取得表頭和資料
        headers = []
        data = []
        
        # 處理表頭
        header_cells = rows[0].find_all(['th', 'td'])
        for cell in header_cells:
            text = cell.get_text(strip=True)
            if text:  # 只加入非空的表頭
                headers.append(text)
                
        # 處理資料行
        data_cells = rows[1].find_all(['th', 'td'])
        for cell in data_cells:
            text = cell.get_text(strip=True)
            if text:  # 只加入非空的資料
                data.append(text)
                
        if len(headers) != len(data):
            logger.error(f"表頭數量 ({len(headers)}) 與資料數量 ({len(data)}) 不符")
            return None
            
        price_info = dict(zip(headers, data))
        logger.info(f"成功抓取當前油價: {price_info}")
        return price_info
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
            
        # 確保資料格式正確
        if not all(isinstance(item, list) and len(item) >= 5 for item in price_data):
            logger.error("油價資料格式不正確")
            return None
            
        dates = [item[0] for item in price_data]
        prices_92 = [float(item[1]) for item in price_data]
        prices_95 = [float(item[2]) for item in price_data]
        prices_98 = [float(item[3]) for item in price_data]
        prices_diesel = [float(item[4]) for item in price_data]
        
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
                        file=buffer,
                        file_name=f"oil_price_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                        options={
                            "response_fields": ["url"],
                            "tags": ["oil_price", "trend"]
                        }
                    )
                    
                    if result and 'url' in result:
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
                message = "中油當前油價：\n"
                for key, value in price_info.items():
                    message += f"{key}: {value}\n"
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=message)
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