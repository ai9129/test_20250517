import os
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
import glob
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import re
import json
import base64

# .envファイルから環境変数を読み込む
load_dotenv()

# Gemini APIの設定
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEYが設定されていません。.envファイルを確認してください。")

genai.configure(api_key=GOOGLE_API_KEY)

# 環境変数からcredentials.jsonの内容を取得
credentials_json_str = os.environ.get('CREDENTIALS_JSON')
if credentials_json_str:
    credentials_info = json.loads(credentials_json_str)
else:
    # ローカル環境では従来通りファイルから読み込む
    with open('credentials.json', 'r') as f:
        credentials_info = json.load(f)

# Google Sheets APIのスコープ
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def format_text_to_table(text):
    """
    テキストを表形式に整形する関数
    
    Args:
        text (str): 整形前のテキスト
    
    Returns:
        list: 表形式のデータ（2次元リスト）
    """
    try:
        # Geminiモデルの初期化
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # テキストを表形式に整形するプロンプト
        prompt = f"""
        以下のテキストを表形式に整形してください。
        各行は「|」で区切られ、最初の行はヘッダーとしてください。
        可能な限り情報を整理し、見やすい表にしてください。
        
        テキスト:
        {text}
        """
        
        # テキストを整形
        response = model.generate_content(prompt)
        formatted_text = response.text
        
        # 表形式のデータを2次元リストに変換
        table_data = []
        for line in formatted_text.strip().split('\n'):
            if '|' in line:
                # 行を「|」で分割し、空白を削除
                row = [cell.strip() for cell in line.split('|') if cell.strip()]
                if row:  # 空の行を除外
                    table_data.append(row)
        
        return table_data
    
    except Exception as e:
        print(f"テキストの整形中にエラーが発生しました: {str(e)}")
        return None

def get_google_sheets_service():
    """
    Google Sheets APIのサービスを取得する関数
    
    Returns:
        googleapiclient.discovery.Resource: Google Sheets APIのサービス
    """
    creds = None
    # token.pickleファイルが存在する場合は、そこから認証情報を読み込む
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # 認証情報が無効な場合は更新
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(credentials_info, SCOPES)
            creds = flow.run_local_server(port=0)
        # 認証情報を保存
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return build('sheets', 'v4', credentials=creds)

def clear_sheet(service, spreadsheet_id, sheet_name):
    """
    スプレッドシートの内容をクリアする関数
    
    Args:
        service: Google Sheets APIのサービス
        spreadsheet_id (str): スプレッドシートID
        sheet_name (str): シート名
    """
    try:
        # シートの内容をクリア
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f'{sheet_name}!A:Z'
        ).execute()
        print("スプレッドシートの内容をクリアしました。")
    except Exception as e:
        print(f"スプレッドシートのクリア中にエラーが発生しました: {str(e)}")

def append_to_spreadsheet(table_data, image_path):
    """
    スプレッドシートにデータを追加する関数
    
    Args:
        table_data (list): 表形式のデータ（2次元リスト）
        image_path (str): 画像ファイルのパス
    """
    try:
        # スプレッドシートIDを環境変数から取得
        SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
        if not SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_IDが設定されていません。.envファイルを確認してください。")
        
        # シート名を環境変数から取得（デフォルトは'Sheet1'）
        SHEET_NAME = os.getenv('SHEET_NAME', 'Sheet1')
        
        # 現在の日時を取得
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 画像情報を追加
        image_info = [current_time, image_path]
        
        # スプレッドシートにデータを追加
        service = get_google_sheets_service()
        
        # シートの内容をクリア
        clear_sheet(service, SPREADSHEET_ID, SHEET_NAME)
        
        # ヘッダー行を追加
        header = ['日時', '画像パス'] + table_data[0]
        body = {'values': [header]}
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f'{SHEET_NAME}!A:Z',
            valueInputOption='RAW',
            body=body
        ).execute()
        
        # データ行を追加
        for row in table_data[1:]:  # ヘッダー行をスキップ
            values = image_info + row
            body = {'values': [values]}
            result = service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f'{SHEET_NAME}!A:Z',
                valueInputOption='RAW',
                body=body
            ).execute()
            print(f"スプレッドシートにデータを追加しました: {result.get('updates').get('updatedCells')} セル")
        
    except Exception as e:
        print(f"スプレッドシートへの追加中にエラーが発生しました: {str(e)}")
        print("スプレッドシートの設定を確認してください。")
        print(f"スプレッドシートID: {SPREADSHEET_ID}")
        print(f"シート名: {SHEET_NAME}")

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

def extract_text_from_image(image_path):
    """
    画像から文字を抽出する関数
    
    Args:
        image_path (str): 画像ファイルのパス
    
    Returns:
        str: 抽出されたテキスト
    """
    try:
        # 画像を開く
        image = Image.open(image_path)
        
        # Geminiモデルの初期化（新しいモデルを使用）
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 画像からテキストを抽出
        response = model.generate_content(["この画像から文字を抽出してください。", image])
        
        return response.text
    
    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")
        return None

if __name__ == "__main__":
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
            else:
                print("テキストの整形に失敗しました。")
        else:
            print("テキストの抽出に失敗しました。")
            
    except FileNotFoundError as e:
        print(f"エラー: {str(e)}")
        print("LINEで画像を送信してから再度実行してください。")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {str(e)}") 