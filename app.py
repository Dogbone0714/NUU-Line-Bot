import os
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
import cv2
import requests
from PIL import Image
import pytesseract
import numpy as np
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
    message_text = event.message.text  # 在这里定义 message_text 变量

    # Skill 1: 登入校務系統
    if message_text == "登入" or (user_id not in user_data):
        # 請求驗證碼圖片
        captcha_url = "https://eap10.nuu.edu.tw/CommonPages/Captcha.aspx"
        response = requests.get(captcha_url)

        if response.status_code == 200:
            try:
                # 使用 OpenCV 读取图片
                captcha_image = cv2.imdecode(np.frombuffer(response.content, np.uint8), cv2.IMREAD_COLOR)

                if captcha_image is not None:
                    # 检查图片类型
                    print(f"图片类型: {type(captcha_image)}")

                    # 将图片保存为 PNG 格式，确保 pytesseract 可以识别
                    cv2.imwrite("captcha.png", captcha_image)

                    # 使用 pytesseract 识别验证码
                    try:
                        captcha_text = pytesseract.image_to_string(cv2.imread("captcha.png"))
                        print(f"验证码: {captcha_text}")
                    except Exception as e:
                        print(f"Error recognizing captcha: {e}")
                        captcha_text = "识别失败，请手动输入"  # 识别失败，提示用户手动输入

                    # 将图片数据转换为 base64 编码
                    _, encoded_image = cv2.imencode(".png", captcha_image)
                    base64_image = encoded_image.tobytes().encode("base64").decode("utf-8")

                    # 构建图片 URL
                    image_url = f"data:image/png;base64,{base64_image}"

                    # 傳送驗證碼圖片和文字給使用者
                    line_bot_api.reply_message(
                        event.reply_token,
                        [
                            ImageSendMessage(
                                original_content_url=image_url,  # 使用 base64 编码的图片 URL
                                preview_image_url=image_url
                            ),
                            TextSendMessage(text=f"驗證碼: {captcha_text}")
                        ]
                    )
                else:
                    print("Error decoding image.")
                    # 处理图片解码失败的情况
            except Exception as e:
                print(f"Error decoding image: {e}")
                # 处理图片解码失败的情况
        else:
            print(f"Error fetching captcha image: {response.status_code}")
            # 处理网络请求失败的情况


            # 要求使用者輸入帳號和密碼
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(
                    alt_text='請輸入您的校務系統帳號和密碼',
                    template=ButtonsTemplate(
                        title='登入校務系統',
                        text='請輸入您的校務系統帳號和密碼',
                        actions=[
                            MessageTemplateAction(label='輸入帳號密碼', text='輸入帳號密碼')
                        ]
                    )
                )
            )
        if message_text.count(" ") == 1:  # 缩进与前面的 `else` 保持一致
            # 處理帳號和密碼輸入
            account, password = message_text.split(" ")
            user_data[user_id] = {"account": account, "password": password}

            # 要求使用者輸入验证码
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入您看到的驗證碼:")
            )
        if user_id in user_data:  # 缩进与前面的 `elif` 保持一致
            if 'captcha_code' in user_data[user_id]:
                captcha_code = user_data[user_id]['captcha_code']
                # 使用帳號密碼登入校務系統
                login_url = "https://eap10.nuu.edu.tw/Login.aspx?logintype=S"
                login_data = {
                    "txtAccount": user_data[user_id]["account"],
                    "txtPassword": user_data[user_id]["password"],
                    "txtVerifyCode": captcha_code
                }
                try:
                    login_response = requests.post(login_url, data=login_data)
                    if login_response.status_code == 200:
                        # 登入成功，處理後續操作
                        print("登入成功！")
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="登入成功！")
                        )
                    else:
                        # 登入失敗，處理後續操作
                        print("登入失敗！")
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="登入失敗，請檢查您的帳號密碼或验证码。")
                        )
                except Exception as e:
                    print(f"登入錯誤: {e}")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="登入錯誤，請稍后再試。")
                    )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="請輸入您看到的驗證碼:")
                )
        else:
            # 处理其他情况
            print("其他情况")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入 \"登入\" 開始登入校務系統。")
            )

    # Skill 2: 查詢課表
    if message_text == "查詢課表":
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

            # 擷取表格元素的 HTML 代码
            table_html = driver.find_element(By.CSS_SELECTOR, "table.gridtable").get_attribute('outerHTML')

            # 關閉 WebDriver
            driver.quit()

            # 使用 weasyprint 直接將 HTML 转换为 PDF
            html = HTML(string=table_html)
            html.write_pdf("timetable.pdf")

            # 将 PDF 转化为图片
            images = convert_from_path("timetable.pdf")

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
    if message_text == "歷年成績查詢":
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
    if message_text == "時刻表":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="您要查詢哪個站點的時刻表？\n1. 二坪\n2. 八甲\n3. 火車站")
        )
    if message_text in timetable_images:
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=timetable_images[message_text],
                preview_image_url=timetable_images[message_text]
            )
        )

    # Skill 5: 指令查詢
    if message_text == "指令查詢":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="以下是可使用的指令：\n1. 時刻表\n2. 歷年成績查詢\n3. 查詢課表\n4. 登入")
        )

if __name__ == "__main__":
    app.run(debug=True)
