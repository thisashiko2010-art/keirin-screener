# 競輪スクリーナー v0.2

## この版でできること
- KEIRIN.JPの開催日程ページへの接続テスト（公開環境から取得できるかを確認）
- レース基本情報・出走選手・オッズ・結果のCSV取り込み
- レースの暫定的な堅さ参考スコア
- 順位情報とオッズからの買い目候補表示（未校正の試作値）
- 購入額・払戻額・回収率の計算
- CSVテンプレートのダウンロード

## まだできないこと
- 当日の全開催を正確に自動抽出
- 出走表・ライン・全券種オッズの自動取得
- 校正済み確率モデルと検証済み期待値
- 自動投票

## ローカル起動（PC向け）
```bash
pip install -r requirements.txt
streamlit run app.py
```

## iPhoneで使う場合
クラウドへの公開が必要です。Streamlit Community CloudはGitHubリポジトリと連携します。iPhoneだけでセットアップする場合もGitHubアカウント作成とリポジトリへのファイル追加が必要です。

## CSV形式
- `races`: date, venue, race_no, start_time, grade, race_title, line_count, largest_line_size, top_score, second_score, wind_speed_mps, wind_direction, straight_m, bank_lap_m, banking_deg
- `entrants`: date, venue, race_no, car_no, rider_name, score, recent_form_0_100, escape_count, back_count, line_id, line_position, comment
- `odds`: date, venue, race_no, bet_type, combination, odds
- `results`: date, venue, race_no, bet_type, combination, stake_yen, hit, payout_yen

## 注意
予想ロジックは未校正の試作で、勝率・利益を保証しません。オッズから期待値を正しく推定するには、組み合わせ別確率の校正と過去データによるバックテストが必要です。データ取得は各サイトの利用条件に従ってください。
