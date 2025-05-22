from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import requests
from bs4 import BeautifulSoup
import logging

app = Flask(__name__)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 🔥 從環境變數讀取 LINE Channel Access Token & Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 🌐 拉取中油油價 (簡易版)
def get_current_oil_price():
    try:
        url = 'https://www.cpc.com.tw/'  # 中油首頁
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, headers=headers)
        res.raise_for_status()

        # 為了除錯，印出更多網頁原始碼
        logger.info(f"Fetched HTML (first 10000 chars): {res.text[:10000]}") # 印出前 10000 個字元

        soup = BeautifulSoup(res.text, 'html.parser')

        # 嘗試尋找包含特定文字或 class 的區塊
        price_container = None
        # 嘗試尋找包含「今日汽柴油零售價格」文字的 h 或 div 標籤
        for tag in soup.find_all(['h2', 'h3', 'h4', 'div', 'span']):
            if tag.text and '今日汽柴油零售價格' in tag.text:
                # 找到標題後，嘗試尋找其附近的價格區塊
                # Adjusting search to be broader, maybe find a parent first
                parent = tag.find_parent()
                if parent:
                    price_container = parent.find(['div', 'table'], class_=['price-table', 'today_price', 'oil-price-section', 'price-list'])
                    if price_container:
                         logger.info(f"找到包含價格區塊的標籤附近 HTML: {price_container}")
                         break

        # 如果沒找到標題附近的價格區塊，直接嘗試尋找可能的價格容器 class
        if not price_container:
             # 根據截圖和常見命名，嘗試尋找可能的 class
            possible_classes = ['price-table', 'today_price', 'oil-price-section', 'price-list']
            for class_name in possible_classes:
                price_container = soup.find('div', class_=class_name)
                if price_container:
                    logger.info(f"找到 class 為 {class_name} 的價格區塊 HTML: {price_container}")
                    break

        if not price_container:
            logger.error("找不到油價資訊區塊")
            return "抱歉，目前無法取得油價資訊，請稍後再試。"

        prices = []
        # 嘗試從找到的容器中解析油品與價格
        # 這裡需要根據實際 HTML 結構進一步調整解析邏輯
        # 先嘗試尋找包含數字和「元/公升」的元素
        # Refined parsing logic based on screenshot, looking for specific structure
        for item in price_container.select('div.price_item'):
             name_tag = item.select_one('div.price_name')
             value_tag = item.select_one('div.price_value')
             if name_tag and value_tag:
                 prices.append(f"{name_tag.get_text(strip=True)}: {value_tag.get_text(strip=True)} 元/公升")

        # If the structured search above fails, try a broader search
        if not prices:
            logger.info("結構化解析失敗，嘗試寬鬆解析")
            # 嘗試尋找所有數字或包含油品名稱的文字
            for tag in price_container.find_all(['span', 'div', 'p', 'li']):
                text = tag.get_text(strip=True)
                # 簡單判斷是否為油價資訊
                if '元/公升' in text or ('無鉛' in text and any(char.isdigit() for char in text)) or ('柴油' in text and any(char.isdigit() for char in text)) or ('石油氣' in text and any(char.isdigit() for char in text)) or ('酒精汽油' in text and any(char.isdigit() for char in text)) or ('超級柴油' in text and any(char.isdigit() for char in text)):
                    # Filter out irrelevant text if possible, keeping only relevant parts
                    # This is a basic filter, might need adjustment based on actual HTML
                    if len(text) < 50: # Simple length check to avoid large blocks of text
                         prices.append(text)

        if not prices:
            logger.error("無法解析油價資料")
            return "抱歉，目前無法取得油價資訊，請稍後再試。"

        return "\n".join(prices)

    except Exception as e:
        logger.error(f"發生錯誤: {str(e)}")
        return "抱歉，系統發生錯誤，請稍後再試。"

# 📬 接收 LINE Webhook
@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 🎯 回應訊息邏輯
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.lower()

    if "查油價" in user_msg:
        oil_price = get_current_oil_price()
        reply = f"📊 最新油價如下：\n{oil_price}"
    else:
        reply = "請輸入「查油價」來獲取最新油價唷 ⛽"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
