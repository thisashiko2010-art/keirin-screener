import re
from datetime import date, datetime
from io import StringIO

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("個人利用向け試作版。取得できた情報だけを表示し、取れない情報は推測しません。")

TODAY = date.today()
SCHEDULE_URL = "https://www.keirin.jp/sp/raceschedule"
PC_URL = "https://www.keirin.jp/pc/raceschedule"

st.info(
    "この版はKEIRIN.JPの開催日程ページから、開催場名や開催期間らしき文字列を抽出できるか試します。"
    "出走表・ライン・オッズ・風向風速の全自動取得は、まだ実装されていません。"
)

st.subheader("1. 今日の開催日程を確認")
st.write(f"対象日：**{TODAY:%Y年%m月%d日}**")
a, b = st.columns(2)
with a:
    run = st.button("公式ページから開催情報を取得", type="primary", use_container_width=True)
with b:
    st.link_button("KEIRIN.JP公式日程を開く", PC_URL, use_container_width=True)

if run:
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"}
    try:
        with st.spinner("公式ページに接続中…"):
            r = requests.get(SCHEDULE_URL, headers=headers, timeout=20)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
        st.success(f"ページ取得成功（HTTP {r.status_code}、約{len(r.text):,}文字）")

        # Remove script/style contents; extract visible text without assuming HTML tables exist.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
        lines = [x for x in lines if x]

        # Detect schedule entries in the mobile schedule's visible text.
        date_pat = re.compile(r"(?P<start>\d{1,2}/\d{1,2})\s*[（(]?[月火水木金土日][）)]?\s*[～〜\-]\s*(?P<end>\d{1,2}/\d{1,2})")
        venue_names = [
            "函館","青森","いわき平","弥彦","前橋","取手","宇都宮","大宮","西武園","京王閣","立川",
            "松戸","川崎","平塚","小田原","伊東","静岡","名古屋","岐阜","大垣","豊橋","富山","松阪",
            "四日市","福井","奈良","向日町","和歌山","岸和田","玉野","広島","防府","高松","小松島",
            "高知","松山","小倉","久留米","武雄","佐世保","別府","熊本"
        ]
        rows = []
        current_venue = None
        for i, line in enumerate(lines):
            cleaned = line.replace("競輪場", "").strip()
            if cleaned in venue_names:
                current_venue = cleaned
            match = date_pat.search(line)
            if match and current_venue:
                title = ""
                # The event title is often in a nearby line; keep it only as source text, not a prediction.
                for candidate in lines[i+1:i+4]:
                    if candidate and not date_pat.search(candidate) and candidate not in venue_names and len(candidate) <= 80:
                        title = candidate
                        break
                rows.append({
                    "競輪場": current_venue,
                    "開催期間（ページ記載）": match.group(0),
                    "開催名（ページ記載・参考）": title
                })

        if rows:
            df = pd.DataFrame(rows).drop_duplicates()
            st.subheader("ページから抽出した開催情報（参考）")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.warning("抽出結果は自動判定の試験用です。今日開催中かどうかは日付・ページ表示を公式リンクで照合してください。")
        else:
            st.warning("ページの取得には成功しましたが、開催情報を自動抽出できませんでした。サイトのHTML構造が想定と異なる可能性があります。")
            st.write("ページ本文の先頭部分（診断用）")
            st.code("\n".join(lines[:100])[:9000])

        with st.expander("診断情報（取得ページ本文の先頭）"):
            st.code("\n".join(lines[:100])[:9000])
    except Exception as e:
        st.error("公式ページを取得できませんでした。接続制限、一時的な通信障害、サイト側の変更などが考えられます。")
        st.caption(f"診断情報：{type(e).__name__}: {e}")
        st.link_button("KEIRIN.JP公式日程を開く", PC_URL)

st.divider()
st.subheader("2. 開発状況")
st.markdown("""
- **今回の確認対象：** 公式開催日程ページの取得と、HTMLの表以外も含めた文字抽出
- **未実装：** 当日の全開催・全レースの完全な抽出、出走表、ライン、全券種オッズ、当日の風向・風速の自動取得
- **未実装：** 校正済み確率、期待値モデル、過去データでの検証
- **自動投票：** 行いません
""")

with st.expander("旧方式のCSV読み込み（予備・必要な場合のみ）"):
    files = st.file_uploader("確認用CSVを選択", type=["csv"], accept_multiple_files=True)
    if files:
        for file in files:
            st.markdown(f"**{file.name}**")
            try:
                st.dataframe(pd.read_csv(file).head(20), use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"読み込みに失敗しました: {e}")

st.caption("予想や利益を保証するものではありません。取得元サイトの利用条件に従い、出走表・ライン・オッズ・バンク特性・当日の風を確認して判断してください。")
