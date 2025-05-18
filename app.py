from flask import Flask, request, jsonify
import os
from image_to_text import extract_text_from_image, format_text_to_table, append_to_spreadsheet
import glob
from datetime import datetime

app = Flask(__name__)

@app.route('/callback', methods=['POST'])
def callback():
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
                return jsonify({"status": "success"}), 200
            else:
                return jsonify({"status": "error", "message": "テキストの整形に失敗しました。"}), 500
        else:
            return jsonify({"status": "error", "message": "テキストの抽出に失敗しました。"}), 500
            
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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