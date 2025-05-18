from flask import Flask, request, jsonify
import os
from image_to_text import extract_text_from_image, format_text_to_table, append_to_spreadsheet
import glob
from datetime import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import TextSendMessage

app = Flask(__name__)

# LINE APIの設定
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route('/callback', methods=['POST'])
def callback():
    # リクエストヘッダーからX-Line-Signatureを取得
    signature = request.headers['X-Line-Signature']

    # リクエストボディを取得
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        # 署名を検証し、問題なければhandleに定義されている関数を呼び出す
        handler.handle(body, signature)
    except InvalidSignatureError:
        # 署名検証で失敗したときは例外をあげる
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # 最新の画像ファイルを取得
        image_path = get_latest_image()
        print(f"処理する画像: {image_path}")
        
        # テキスト抽出を実行
        extracted_text = extract_text_from_image(image_path)
        
        if extracted_text:
            print("\n抽出されたテキスト:")
            print(extracted_text)
            
            # テキストを表形式に整形
            table_data = format_text_to_table(extracted_text)
            
            if table_data:
                print("\n表形式に整形されたテキスト:")
                for row in table_data:
                    print(' | '.join(row))
                
                # スプレッドシートにデータを追加
                append_to_spreadsheet(table_data, image_path)
                
                # 完了メッセージを送信
                reply_message = "画像の処理が完了しました！\nスプレッドシートにデータを保存しました。"
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_message)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="テキストの整形に失敗しました。")
                )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="テキストの抽出に失敗しました。")
            )
            
    except FileNotFoundError as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=str(e))
        )
    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"予期せぬエラーが発生しました: {str(e)}")
        )

def get_latest_image():
    """
    saved_imagesディレクトリから最新の画像ファイルを取得する関数
    
    Returns:
        str: 最新の画像ファイルのパス
    """
    # saved_imagesディレクトリ内のすべての画像ファイルを取得
    image_files = glob.glob('saved_images/*.jpg')
    
    if not image_files:
        raise FileNotFoundError("saved_imagesディレクトリに画像ファイルが見つかりません。")
    
    # 最新の画像ファイルを取得（タイムスタンプでソート）
    latest_image = max(image_files, key=os.path.getctime)
    return latest_image

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 