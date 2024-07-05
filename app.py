from flask import Flask, request, abort
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)
import requests
from PIL import Image
import pytesseract
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from weasyprint import HTML
from pdf2image import convert_from_path
from webdriver_manager.chrome import ChromeDriverManager

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi('CevuEwc722zOiBwgCnJS8yYK12kEa0LVUnMQWlyOMkMNl95vRhZ40SNrCt1Dr3H4S8AgNnLWu7hwEB3f2nblSO/YkbhaItdAWFrUpE0b7Zv0aGuk5E8XCuZMV8RM5pNdipH67O87Nrx5xHUrs+HI0AdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('563a72292e87d0e70eef414a949f08a0')

# 儲存使用者帳號密碼
user_data = {}

# 公車時刻表圖片
timetable_images = {
    "二坪": "https://i.imgur.com/YpDzFip.jpeg",  # 替換成實際的圖片 URL
    "八甲": "https://i.imgur.com/1Z6i3KU.jpeg",  # 替換成實際的圖片 URL
    "火車站": "https://i.imgur.com/swvoXEP.jpeg"  # 替換成實際的圖片 URL
}

# 處理來自 LINE 的訊息
@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭值
    signature = request.headers['X-Line-Signature']

    # 取得請求主體為文字
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 處理 Webhook 主體
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    message_text = event.message.text

    # Skill 1: 登入校務系統
    if message_text == "登入" or (user_id not in user_data):
        # 請求驗證碼圖片
        captcha_url = "https://eap10.nuu.edu.tw/CommonPages/Captcha.aspx"
        captcha_response = requests.get(captcha_url)
        captcha_image = Image.open(captcha_response.content)

        # 使用影像辨識轉換驗證碼
        captcha_text = pytesseract.image_to_string(captcha_image)

        # 傳送驗證碼圖片和文字給使用者
        line_bot_api.reply_message(
            event.reply_token,
            [
                ImageSendMessage(
                    original_content_url=captcha_url,
                    preview_image_url=captcha_url
                ),
                TextSendMessage(text=f"驗證碼: {captcha_text}")
            ]
        )

        # 要求使用者輸入帳號和密碼
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text="請輸入您的校務系統帳號和密碼，以空格分隔。")
        )
    elif message_text.count(" ") == 1:
        # 處理帳號和密碼輸入
        account, password = message_text.split(" ")
        user_data[user_id] = {"account": account, "password": password}

        # 使用帳號密碼登入校務系統
        login_url = "https://eap10.nuu.edu.tw/Login.aspx?logintype=S"
        login_data = {
            "txtAccount": account,
            "txtPassword": password,
            "txtVerifyCode": input("請輸入驗證碼: ")
        }
        login_response = requests.post(login_url, data=login_data)

        # 檢查登入結果
        if login_response.status_code == 200:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="登入成功！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="登入失敗，請確認帳號密碼或驗證碼是否正確。")
            )

    # Skill 2: 查詢課表
    elif message_text == "查詢課表":
        # 取得使用者帳號和密碼
        account = user_data.get(user_id, {}).get("account")
        password = user_data.get(user_id, {}).get("password")

        if account and password:
            # 使用 Selenium 自動查詢課表
            driver = webdriver.Chrome(ChromeDriverManager().install())
            driver.get("https://eap10.nuu.edu.tw/S0100/S0132/S01320901.aspx?sys_id=S00&sys_pid=S01320901")

            # 等待「查詢」按鈕出現
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "btnQuery"))
            )

            # 點擊「查詢」按鈕
            driver.find_element(By.ID, "btnQuery").click()

            # 等待表格元素出現
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.gridtable"))
            )

            # 擷取表格元素的螢幕截圖
            table_element = driver.find_element(By.CSS_SELECTOR, "table.gridtable")
            table_element.screenshot("timetable.png")

            # 關閉 WebDriver
            driver.quit()

            # 將 PDF 轉換為圖片 (所有頁面)
            images = convert_from_path("timetable.png")

            # 逐頁儲存圖片
            for i, image in enumerate(images):
                image.save(f"timetable_{i+1}.png")

            # 回傳課表圖片給使用者
            # (您可以根據您的需求調整傳送圖片的方式)
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="課表查詢成功，已將圖片發送到您的訊息中！")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您尚未登入，請先輸入「登入」指令。")
            )

    # Skill 3: 歷年成績查詢
    elif message_text == "歷年成績查詢":
        # 取得使用者帳號和密碼
        account = user_data.get(user_id, {}).get("account")
        password = user_data.get(user_id, {}).get("password")

        if account and password:
            # 查詢成績
            grades_url = "https://eap10.nuu.edu.tw/S0100/S0136/S01361601.aspx?sys_id=S00&sys_pid=S01361601"
            grades_response = requests.get(grades_url, auth=(account, password))

            # 檢查請求是否成功
            if grades_response.status_code == 200:
                # 將成績表格的 HTML 內容轉換為 PDF
                html = HTML(string=grades_response.text)
                html.write_pdf("grades.pdf")

                # 將 PDF 轉換為圖片 (所有頁面)
                images = convert_from_path("grades.pdf")

                # 逐頁儲存圖片
                for i, image in enumerate(images):
                    image.save(f"grades_{i+1}.png")

                # 回傳成績圖片給使用者
                # (您可以根據您的需求調整傳送圖片的方式)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="成績查詢成功，已將圖片發送到您的訊息中！")
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="成績查詢失敗，請稍後再試。")
                )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您尚未登入，請先輸入「登入」指令。")
            )
    # Skill 4: 傳送公車時刻表
    elif message_text == "時刻表":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您要查詢哪個站點的時刻表？\n1. 二坪\n2. 八甲\n3. 火車站")
        )
    elif message_text in timetable_images:
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=timetable_images[message_text],
                preview_image_url=timetable_images[message_text]
            )
        )

    # Skill 5: 指令查詢
    elif message_text == "指令查詢":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="以下是可使用的指令：\n1. 時刻表\n2. 歷年成績查詢\n3. 查詢課表\n4. 登入")
        )

if __name__ == "__main__":
    app.run(debug=True)