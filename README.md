# LINE画像保存プログラム

このプログラムは、LINEで送信された画像を自動的に保存するプログラムです。

## セットアップ方法

1. 必要なパッケージをインストール
```bash
pip install -r requirements.txt
```

2. LINE Developersでチャネルを作成し、以下の情報を取得
- Channel Access Token
- Channel Secret

3. `.env`ファイルを作成し、以下の情報を設定
```
LINE_CHANNEL_ACCESS_TOKEN=あなたのChannel Access Token
LINE_CHANNEL_SECRET=あなたのChannel Secret
```

4. プログラムを実行
```bash
python line_image_saver.py
```

5. ngrokなどのツールを使用して、ローカルサーバーをインターネットに公開
```bash
ngrok http 5000
```

6. LINE DevelopersのWebhook URLに、ngrokで生成されたURL + /callbackを設定
   （例：https://xxxx-xx-xx-xx-xx.ngrok.io/callback）

## 使用方法

1. LINEでボットに画像を送信すると、自動的に`saved_images`ディレクトリに保存されます
2. 保存された画像は、タイムスタンプ付きのファイル名で保存されます
3. 保存が完了すると、LINEで通知メッセージが送信されます

## 注意事項

- 画像はJPEG形式で保存されます
- 保存先のディレクトリは自動的に作成されます
- エラーが発生した場合は、LINEでエラーメッセージが送信されます 