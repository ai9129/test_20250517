import os
from flask import Flask, request, abort
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    ImageMessageContent
)
from linebot.v3.webhook import WebhookHandler
from linebot.exceptions import InvalidSignatureError
from dotenv import load_dotenv
import traceback
import google.generativeai as genai
from PIL import Image
import io
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数の確認
access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
google_api_key = os.getenv('GOOGLE_API_KEY')
spreadsheet_id = os.getenv('SPREADSHEET_ID')
sheet_name = os.getenv('SHEET_NAME', 'Sheet1')

if not all([access_token, channel_secret, google_api_key, spreadsheet_id]):
    raise ValueError("必要な環境変数が設定されていません。.envファイルを確認してください。")

# Gemini APIの設定
genai.configure(api_key=google_api_key)

app = Flask(__name__)
app.debug = True  # デバッグモードを有効化

# LINE Messaging APIの設定
configuration = Configuration(access_token=access_token)
handler = WebhookHandler(channel_secret)

# 画像を保存するディレクトリ
SAVE_DIR = 'saved_images'
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# Google Sheets APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_google_sheets_service():
    """
    Google Sheets APIのサービスを取得する関数
    """
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('sheets', 'v4', credentials=creds)

def clear_sheet(service, spreadsheet_id, sheet_name):
    """
    スプレッドシートの内容をクリアする関数
    """
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f'{sheet_name}!A:Z'
        ).execute()
        app.logger.info("スプレッドシートの内容をクリアしました。")
    except Exception as e:
        app.logger.error(f"スプレッドシートのクリア中にエラーが発生しました: {str(e)}")

def format_text_to_table(text):
    """
    テキストを表形式に整形する関数
    """
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        以下のテキストを表形式に整形してください。
        各行は「|」で区切られ、最初の行はヘッダーとしてください。
        可能な限り情報を整理し、見やすい表にしてください。
        
        テキスト:
        {text}
        """
        
        response = model.generate_content(prompt)
        formatted_text = response.text
        
        table_data = []
        for line in formatted_text.strip().split('\n'):
            if '|' in line:
                row = [cell.strip() for cell in line.split('|') if cell.strip()]
                if row:
                    table_data.append(row)
        
        return table_data
    
    except Exception as e:
        app.logger.error(f"テキストの整形中にエラーが発生しました: {str(e)}")
        return None

def append_to_spreadsheet(table_data, image_path):
    """
    スプレッドシートにデータを追加する関数
    """
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        image_info = [current_time, image_path]
        
        service = get_google_sheets_service()
        
        # シートの内容をクリア
        clear_sheet(service, spreadsheet_id, sheet_name)
        
        # ヘッダー行を追加
        header = ['日時', '画像パス'] + table_data[0]
        body = {'values': [header]}
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f'{sheet_name}!A:Z',
            valueInputOption='RAW',
            body=body
        ).execute()
        
        # データ行を追加
        for row in table_data[1:]:
            values = image_info + row
            body = {'values': [values]}
            result = service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A:Z',
                valueInputOption='RAW',
                body=body
            ).execute()
            app.logger.info(f"スプレッドシートにデータを追加しました: {result.get('updates').get('updatedCells')} セル")
        
    except Exception as e:
        app.logger.error(f"スプレッドシートへの追加中にエラーが発生しました: {str(e)}")

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    app.logger.info(f"Headers: {dict(request.headers)}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Please check your channel access token/channel secret.")
        app.logger.error(f"Signature: {signature}")
        app.logger.error(f"Channel Secret: {channel_secret[:5]}...")
        abort(400)
    except Exception as e:
        app.logger.error(f"Error occurred: {str(e)}")
        app.logger.error(traceback.format_exc())
        abort(500)

    return 'OK'

@handler.add(MessageEvent)
def handle_message(event):
    try:
        if isinstance(event.message, ImageMessageContent):
            message_id = event.message.id
            app.logger.info(f"Received image message: {message_id}")
            
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                messaging_api = MessagingApi(api_client)
                
                # 画像のバイナリデータを取得
                app.logger.info("Getting message content...")
                message_content = blob_api.get_message_content(message_id)
                
                # 保存するファイル名を生成
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_name = f'image_{timestamp}.jpg'
                file_path = os.path.join(SAVE_DIR, file_name)
                
                # 画像を保存
                app.logger.info(f"Saving image to: {file_path}")
                with open(file_path, 'wb') as f:
                    f.write(message_content)
                
                # 画像からテキストを抽出
                app.logger.info("Extracting text from image...")
                image = Image.open(io.BytesIO(message_content))
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(["この画像から文字を抽出してください。", image])
                extracted_text = response.text
                
                # テキストを表形式に整形
                app.logger.info("Formatting text to table...")
                table_data = format_text_to_table(extracted_text)
                
                if table_data:
                    # スプレッドシートにデータを追加
                    app.logger.info("Appending data to spreadsheet...")
                    append_to_spreadsheet(table_data, file_path)
                    
                    # ユーザーに完了を通知
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text=f'画像を保存し、文字を抽出しました。\nスプレッドシートに保存しました。')]
                        )
                    )
                else:
                    messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text='文字の抽出に失敗しました。')]
                        )
                    )
                
    except Exception as e:
        app.logger.error(f"Error in handle_message: {str(e)}")
        app.logger.error(traceback.format_exc())
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=f'エラーが発生しました: {str(e)}')]
                )
            )

if __name__ == "__main__":
    app.logger.info("Starting server...")
    app.logger.info(f"Access Token: {access_token[:5]}...")
    app.logger.info(f"Channel Secret: {channel_secret[:5]}...")
    app.run(host='0.0.0.0', port=5000, debug=True) 