from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import pytz
from line_bot_oil.line_bot_oil_v1 import get_oil_price, get_trend_image, send_push_notification
import os
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 設定 LINE Bot API
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 設定排程器
logger.info("開始設定排程器...")
scheduler = BackgroundScheduler(timezone='Asia/Singapore')
logger.info("排程器時區設定為：Asia/Singapore")

# 測試用：每分鐘執行一次
scheduler.add_job(
    send_push_notification,
    'interval',
    minutes=1,
    id='oil_price_notification',
    replace_existing=True
)
logger.info("已設定每分鐘執行一次的排程任務")

# 正式用：每週日中午12點執行
# scheduler.add_job(send_push_notification, 'cron', day_of_week='sun', hour=12, minute=0)

try:
    scheduler.start()
    logger.info("排程器成功啟動！")
except Exception as e:
    logger.error(f"排程器啟動失敗：{str(e)}")
    raise e

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
    if event.message.text == "油價":
        oil_price = get_oil_price()
        trend_image_url = get_trend_image()
        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=oil_price),
                ImageSendMessage(
                    original_content_url=trend_image_url,
                    preview_image_url=trend_image_url
                )
            ]
        )
    elif event.message.text == "訂閱":
        user_id = event.source.user_id
        with open('subscribed_users.txt', 'a') as f:
            f.write(f"{user_id}\n")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您已成功訂閱油價推播！")
        )
    elif event.message.text == "取消訂閱":
        user_id = event.source.user_id
        with open('subscribed_users.txt', 'r') as f:
            users = f.readlines()
        with open('subscribed_users.txt', 'w') as f:
            for user in users:
                if user.strip() != user_id:
                    f.write(user)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您已取消訂閱油價推播。")
        )
    elif event.message.text == "測試推播":
        send_push_notification()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="已發送測試推播！")
        )

# 新增 Cron Job API endpoint
@app.route("/cron/push", methods=['POST'])
def cron_push():
    # 驗證請求是否來自 Render Cron
    auth_header = request.headers.get('Authorization')
    if auth_header != f"Bearer {os.getenv('CRON_SECRET')}":
        logger.warning("收到未授權的 Cron 請求")
        abort(401)
    
    logger.info("收到 Cron 請求，開始執行推播")
    send_push_notification()
    return 'OK'

if __name__ == "__main__":
    app.run() 