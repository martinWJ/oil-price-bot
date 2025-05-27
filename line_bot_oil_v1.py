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
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import time

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 初始化 Flask 應用程式
app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# ImageKit.io 相關配置
IMAGEKIT_PUBLIC_KEY = os.getenv('IMAGEKIT_PUBLIC_KEY')
IMAGEKIT_PRIVATE_KEY = os.getenv('IMAGEKIT_PRIVATE_KEY')
IMAGEKIT_URL_ENDPOINT = os.getenv('IMAGEKIT_URL_ENDPOINT')

# 初始化 ImageKit
imagekit = ImageKit(public_key=IMAGEKIT_PUBLIC_KEY, private_key=IMAGEKIT_PRIVATE_KEY, url_endpoint=IMAGEKIT_URL_ENDPOINT)

def get_oil_price_trend():
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        
        # 設定 Chrome 選項
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--single-process')
        
        # 初始化 undetected-chromedriver
        driver = uc.Chrome(
            options=options,
            version_main=114  # 指定 Chrome 版本
        )
        logger.info("已初始化 Chrome WebDriver")
        
        try:
            driver.get(url)
            logger.info("已開啟網頁")
            wait = WebDriverWait(driver, 20)  # 增加等待時間
            table = wait.until(EC.presence_of_element_located((By.ID, 'tbHistoryPrice')))
            logger.info("表格已載入")
            time.sleep(3)  # 增加等待時間
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table', {'id': 'tbHistoryPrice'})
            if not table:
                logger.error("找不到油價資料表格")
                return None
            tbody = table.find('tbody')
            if not tbody:
                logger.error("找不到 tbody")
                return None
            rows = tbody.find_all('tr')
            logger.info(f"找到 {len(rows)} 列資料")
            dates, prices_92, prices_95, prices_98, prices_diesel = [], [], [], [], []
            for i, row in enumerate(rows):
                cols = row.find_all('td')
                if len(cols) >= 5:
                    try:
                        date = cols[0].text.strip()
                        price_92 = float(cols[1].text.strip())
                        price_95 = float(cols[2].text.strip())
                        price_98 = float(cols[3].text.strip())
                        price_diesel = float(cols[4].text.strip())
                        dates.append(date)
                        prices_92.append(price_92)
                        prices_95.append(price_95)
                        prices_98.append(price_98)
                        prices_diesel.append(price_diesel)
                    except Exception as e:
                        logger.error(f"解析第 {i+1} 列資料時發生錯誤: {e}")
            if not dates:
                logger.error("無法解析油價資料")
                return None
            # 反轉資料順序，讓X軸最左側為最舊日期
            dates = dates[::-1]
            prices_92 = prices_92[::-1]
            prices_95 = prices_95[::-1]
            prices_98 = prices_98[::-1]
            prices_diesel = prices_diesel[::-1]
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
        finally:
            driver.quit()
            logger.info("已關閉 Chrome WebDriver")
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        return None 

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature header 值
    signature = request.headers['X-Line-Signature']

    # 取得請求內容
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    logger.info(f"收到訊息: {text}")
    
    if text == "趨勢":
        try:
            buffer = get_oil_price_trend()
            if buffer:
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
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="無法上傳圖片，請稍後再試")
                    )
                    logger.error("圖片上傳失敗")
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="無法取得油價趨勢資料，請稍後再試")
                )
                logger.error("無法取得油價趨勢資料")
        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"發生錯誤：{str(e)}")
            )
            logger.error(f"處理趨勢請求時發生錯誤: {str(e)}")
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入「趨勢」查看油價趨勢圖")
        )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 