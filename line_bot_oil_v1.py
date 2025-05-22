import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

def get_oil_price():
    try:
        # 從中油歷史油價網頁抓取資料
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        response = requests.get(url)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 找到油價表格
        table = soup.find('table', {'class': 'table'})
        if not table:
            logger.error("找不到油價表格")
            return "無法取得油價資訊"
            
        # 找到最新一筆油價資料
        rows = table.find_all('tr')
        if len(rows) < 2:
            logger.error("找不到油價資料")
            return "無法取得油價資訊"
            
        # 取得最新一筆資料
        latest_row = rows[1]  # 第一行是標題，所以取第二行
        cells = latest_row.find_all('td')
        
        if len(cells) < 5:
            logger.error("油價資料格式不正確")
            return "無法取得油價資訊"
            
        # 解析日期和油價
        date = cells[0].text.strip()
        price_92 = cells[1].text.strip()
        price_95 = cells[2].text.strip()
        price_98 = cells[3].text.strip()
        price_diesel = cells[4].text.strip()
        
        # 組合回覆訊息
        message = f"中油最新油價資訊 ({date}):\n"
        message += f"92無鉛汽油: {price_92} 元/公升\n"
        message += f"95無鉛汽油: {price_95} 元/公升\n"
        message += f"98無鉛汽油: {price_98} 元/公升\n"
        message += f"超級柴油: {price_diesel} 元/公升"
        
        return message
        
    except Exception as e:
        logger.error(f"抓取油價時發生錯誤: {str(e)}")
        return "抓取油價時發生錯誤，請稍後再試"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if event.message.text in ['油價', '查詢油價']:
        oil_price_info = get_oil_price()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=oil_price_info)
        )

if __name__ == "__main__":
    app.run()
