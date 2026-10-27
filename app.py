import re
from datetime import date
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("個人利用向け試作版。公式ページから確認できた情報だけを表示します。")

URL = "https://www.keirin.jp/sp/raceschedule"
OFFICIAL = "https://www.keirin.jp/pc/raceschedule"
VENUES = [
    "函館","青森","いわき平","弥彦","前橋","取手","宇都宮","大宮","西武園","京王閣","立川",
    "松戸","川崎","平塚","小田原","伊東","静岡","名古屋","岐阜","大垣","豊橋","富山","松阪",
    "四日市","福井","奈良","向日町","和歌山","岸和田","玉野","広島","防府","高松","小松島",
    "高知","松山","小倉","久留米","武雄","佐世保","別府","熊本"
]
DATE_RE = re.compile(r"\d{1,2}/\d{1,2}\s*[（(]?[月火水木金土日][）)]?\s*[～〜\-－]\s*\d{1,2}/\d{1,2}\s*[（(]?[月火水木金土日][）)]?")

st.info("開催日程ページを取得し、競輪場・期間・開催名の組み合わせと関連リンクを調査します。詳細ページのURLは推測で作りません。")
st.write(f"取得日：{date.today():%Y年%m月%d日}")
c1, c2 = st.columns(2)
with c1:
    fetch = st.button("公式ページから開催情報を取得", type="primary", use_container_width=True)
with c2:
    st.link_button("KEIRIN.JP公式日程を開く", OFFICIAL, use_container_width=True)

if fetch:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}
        with st.spinner("公式ページを取得しています…"):
            response = requests.get(URL, headers=headers, timeout=25)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
        st.success(f"公式ページを取得しました（HTTP {response.status_code}）。")

        # Capture links before cleaning the HTML.
        links = []
        for a in soup.find_all("a", href=True):
            label = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
            href = urljoin(URL, a["href"].strip())
            if label:
                links.append({"リンク名": label, "URL": href})

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        rows = []
        # Use a venue heading as an anchor, then extract date/title tokens from its containing event card.
        for venue in VENUES:
            for match in soup.find_all(string=re.compile(rf"^\s*{re.escape(venue)}\s*$")):
                node = match.parent
                for _ in range(6):
                    if node is None:
                        break
                    tokens = [re.sub(r"\s+", " ", s).strip() for s in node.stripped_strings]
                    if any(DATE_RE.search(t) for t in tokens) and len(" ".join(tokens)) < 3000:
                        current_date = None
                        for token in tokens:
                            date_match = DATE_RE.search(token)
                            if date_match:
                                current_date = date_match.group(0)
                                continue
                            if current_date and token != venue and token not in VENUES and len(token) <= 120:
                                if not token.startswith(("Image", "開催がありません")):
                                    rows.append({"競輪場": venue, "開催期間": current_date, "開催名": token})
                                    current_date = None
                        if rows:
                            break
                    node = node.parent

        st.subheader("開催情報")
        if rows:
            df = pd.DataFrame(rows).drop_duplicates()
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(df)}件の候補を抽出しました。公式サイトとの照合が必要です。")
        else:
            st.warning("開催情報を表形式に抽出できませんでした。競輪場名だけを開催一覧として誤表示しないようにしています。")

        st.subheader("関連リンク候補")
        detail = []
        seen = set()
        for item in links:
            text = (item["リンク名"] + " " + item["URL"]).lower()
            if any(word in text for word in ("race", "racedetail", "racecard", "odds", "kaisai", "entry", "出走表", "レース詳細")):
                if item["URL"] not in seen:
                    seen.add(item["URL"])
                    detail.append(item)
        if detail:
            st.dataframe(pd.DataFrame(detail[:100]), use_container_width=True, hide_index=True)
        else:
            st.warning("ページ内HTMLからレース詳細への直接リンクを確認できませんでした。公式日程ページを開くリンクを利用してください。")

        with st.expander("診断情報：本文の先頭60行"):
            visible = [re.sub(r"\s+", " ", s).strip() for s in soup.stripped_strings]
            st.code("\n".join([s for s in visible if s][:60])[:7000])
        with st.expander("診断情報：取得したリンクの先頭80件"):
            st.code("\n".join(f'{x["リンク名"]} -> {x["URL"]}' for x in links[:80])[:10000])
    except Exception as exc:
        st.error("公式ページの取得に失敗しました。")
        st.caption(f"診断情報：{type(exc).__name__}: {exc}")
        st.link_button("KEIRIN.JP公式日程を開く", OFFICIAL)

st.divider()
st.subheader("開発状況")
st.markdown("""
- 開催日程ページの取得：実装
- 開催場・期間・開催名の抽出：試作段階、結果確認が必要
- 詳細ページへのリンク：HTML内で見つかったリンクだけ表示
- 出走表・ライン・オッズ・バンク特性・風向風速：未実装
- 自動投票：行いません
""")
st.caption("抽出結果は公式サイトと照合してください。予想精度や利益を保証するものではありません。")
