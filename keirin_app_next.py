import re
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("個人利用向け試作版。取得できた情報だけを表示し、取れない情報は推測しません。")

SCHEDULE_URL = "https://www.keirin.jp/sp/raceschedule"
OFFICIAL_URL = "https://www.keirin.jp/pc/raceschedule"
VENUES = [
    "函館", "青森", "いわき平", "弥彦", "前橋", "取手", "宇都宮", "大宮", "西武園", "京王閣",
    "立川", "松戸", "川崎", "平塚", "小田原", "伊東", "静岡", "名古屋", "岐阜", "大垣",
    "豊橋", "富山", "松阪", "四日市", "福井", "奈良", "向日町", "和歌山", "岸和田", "玉野",
    "広島", "防府", "高松", "小松島", "高知", "松山", "小倉", "久留米", "武雄", "佐世保",
    "別府", "熊本"
]

st.info(
    "この版では、公式開催日程を取得し、開催情報に関連するリンク候補を一覧表示します。"
    "リンクがレース詳細ページであることを確認するための調査版です。"
)

st.subheader("1. 公式開催情報と関連リンク")
c1, c2 = st.columns(2)
with c1:
    fetch = st.button("公式ページから情報・リンクを取得", type="primary", use_container_width=True)
with c2:
    st.link_button("KEIRIN.JP公式日程を開く", OFFICIAL_URL, use_container_width=True)

if fetch:
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    }
    try:
        with st.spinner("KEIRIN.JPに接続しています…"):
            response = requests.get(SCHEDULE_URL, headers=headers, timeout=25)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")

        st.success(f"公式ページの取得に成功しました（HTTP {response.status_code}）。")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        lines = [re.sub(r"\s+", " ", x).strip() for x in soup.stripped_strings]
        lines = [x for x in lines if x]

        venue_lines = []
        for i, line in enumerate(lines):
            for venue in VENUES:
                if venue in line:
                    venue_lines.append({"ページ内の表示": line[:180], "本文内の位置": i})
                    break
        if venue_lines:
            st.write("ページ本文に見つかった競輪場名を含む行（重複を含む場合があります）")
            st.dataframe(pd.DataFrame(venue_lines).drop_duplicates(), use_container_width=True, hide_index=True)
        else:
            st.warning("競輪場名を含む行を本文から抽出できませんでした。")

        link_rows = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            if not href:
                continue
            full_url = urljoin(SCHEDULE_URL, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            combined = (label + " " + href).lower()
            if any(k in combined for k in (
                "race", "schedule", "kaisai", "entry", "card", "odds", "detail", "開催", "出走表", "レース"
            )):
                category = "レース・開催関連候補"
            elif any(v in label for v in VENUES):
                category = "競輪場名を含むリンク"
            else:
                category = "その他"
            link_rows.append({"分類": category, "リンク名": label[:120] or "（リンク文字なし）", "リンク先": full_url})

        st.subheader("2. 関連リンク候補")
        likely = [x for x in link_rows if x["分類"] != "その他"]
        if likely:
            st.write(f"関連候補：{len(likely)}件")
            st.dataframe(pd.DataFrame(likely[:150]), use_container_width=True, hide_index=True)
        else:
            st.warning("関連リンク候補を判別できませんでした。下の全リンク診断を確認します。")

        with st.expander("診断用：ページ本文の先頭100行"):
            st.code("\n".join(lines[:100])[:10000])
        with st.expander("診断用：ページ内リンクの先頭150件（全分類）"):
            all_link_text = [
                f'{x["分類"]} | {x["リンク名"]} | {x["リンク先"]}'
                for x in link_rows[:150]
            ]
            st.code("\n".join(all_link_text)[:16000])
        st.caption(
            "注意：この画面のリンク候補には、開催日程以外のリンクが混ざることがあります。"
            "まだ出走表・ライン・オッズの自動取得は実装していません。"
        )
    except Exception as e:
        st.error("公式ページを取得できませんでした。時間をおいて再試行してください。")
        st.caption(f"診断情報：{type(e).__name__}: {e}")
        st.link_button("公式日程をブラウザで開く", OFFICIAL_URL)

st.divider()
st.subheader("開発状況")
st.markdown("""
- **完了：** 開催場・開催期間・開催名の抽出（前の版で確認済み）
- **今回：** 公式ページのリンク候補を一覧表示し、詳細ページへの道筋を調べる
- **未実装：** 各開催の全レース、出走表、ライン、オッズ、バンク特性、当日の風向・風速の自動取得
- **未実装：** 的中確率の校正、期待値評価、過去データによる検証
- **自動投票：** 行いません
""")
st.caption("予想や利益を保証するものではありません。取得元サイトの利用条件に従って利用してください。")
