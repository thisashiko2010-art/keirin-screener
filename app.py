import re
from datetime import date
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("個人利用向け試作版。開催日程は公式ページから取得し、確認できた項目だけを表示します。")

SP_URL = "https://www.keirin.jp/sp/raceschedule"
PC_URL = "https://www.keirin.jp/pc/raceschedule"
VENUES = [
    "いわき平", "西武園", "京王閣", "小松島", "佐世保",
    "函館", "青森", "弥彦", "前橋", "取手", "宇都宮", "大宮", "立川",
    "松戸", "川崎", "平塚", "小田原", "伊東", "静岡", "名古屋", "岐阜",
    "大垣", "豊橋", "富山", "松阪", "四日市", "福井", "奈良", "向日町",
    "和歌山", "岸和田", "玉野", "広島", "防府", "高松", "高知", "松山",
    "小倉", "久留米", "武雄", "別府", "熊本"
]
DATE_RE = re.compile(
    r"(?P<start>\d{1,2}/\d{1,2})\s*[（(]?[月火水木金土日][）)]?\s*[～〜〜〜\-－―〜]\s*"
    r"(?P<end>\d{1,2}/\d{1,2})\s*[（(]?[月火水木金土日][）)]?"
)
DATE_SINGLE_RE = re.compile(r"\d{1,2}/\d{1,2}\s*[（(]?[月火水木金土日][）)]?")

st.info("前回の失敗を踏まえ、スマホ版だけに依存せず、PC版・スマホ版の両方を調べます。詳細URLを推測で生成することはしません。")
st.write(f"取得日：{date.today():%Y年%m月%d日}")
col1, col2 = st.columns(2)
with col1:
    fetch = st.button("公式ページから開催情報を取得", type="primary", use_container_width=True)
with col2:
    st.link_button("KEIRIN.JP公式日程を開く", PC_URL, use_container_width=True)

def clean(s):
    return re.sub(r"\s+", " ", str(s)).strip()

def extract_from_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    link_rows = []
    for a in soup.find_all("a", href=True):
        label = clean(a.get_text(" ", strip=True))
        href = urljoin(page_url, a["href"].strip())
        if label and href.startswith(("http://", "https://")):
            link_rows.append({"リンク名": label, "URL": href})

    # Strategy 1: examine table rows, which is useful when the source renders a calendar as HTML tables.
    rows = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
            joined = " | ".join(x for x in cells if x)
            if not joined:
                continue
            venue = next((v for v in sorted(VENUES, key=len, reverse=True)
                          if any(c == v or c.startswith(v + " ") for c in cells) or joined.startswith(v + " |")), None)
            dm = DATE_RE.search(joined)
            if venue and dm:
                title = joined[dm.end():].strip(" |・")
                title = re.sub(r"^(Image\s*)+", "", title).strip()
                if title and not title.startswith("開催がありません"):
                    rows.append({"競輪場": venue, "開催期間": dm.group(0), "開催名": title})

    # Strategy 2: read the page's text in order. Keep venue context and pair date ranges with the next plausible event title.
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    tokens = [clean(x) for x in soup.stripped_strings if clean(x)]
    current_venue = None
    pending_date = None
    for i, token in enumerate(tokens):
        # Venue headings are often individual text nodes in the mobile page.
        found_venue = next((v for v in sorted(VENUES, key=len, reverse=True)
                            if token == v or token.startswith(v + " ")), None)
        if found_venue:
            current_venue = found_venue
            pending_date = None
            continue
        dm = DATE_RE.search(token)
        if dm and current_venue:
            pending_date = dm.group(0)
            # Some layouts place event title in the same text token after the date.
            remainder = token[dm.end():].strip(" |・")
            if remainder and len(remainder) <= 120:
                rows.append({"競輪場": current_venue, "開催期間": pending_date, "開催名": remainder})
                pending_date = None
            continue
        if pending_date and current_venue:
            if token not in VENUES and not token.startswith(("開催がありません", "Image", "開く")) and len(token) <= 120:
                if not DATE_SINGLE_RE.fullmatch(token):
                    rows.append({"競輪場": current_venue, "開催期間": pending_date, "開催名": token})
                    pending_date = None

    # Remove navigation labels and obvious malformed rows.
    cleaned = []
    for row in rows:
        venue = row["競輪場"]
        title = clean(row["開催名"])
        period = clean(row["開催期間"])
        if title and title not in VENUES and not title.startswith(("開催日程", "グレードレース")):
            cleaned.append({"競輪場": venue, "開催期間": period, "開催名": title})
    df = pd.DataFrame(cleaned, columns=["競輪場", "開催期間", "開催名"])
    if not df.empty:
        df = df.drop_duplicates().reset_index(drop=True)
    return df, link_rows, tokens

if fetch:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    }
    successes = []
    failures = []
    with st.spinner("公式ページ2種類を確認しています…"):
        for page_url in (SP_URL, PC_URL):
            try:
                response = requests.get(page_url, headers=headers, timeout=25)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                df, links, tokens = extract_from_html(response.text, page_url)
                successes.append((page_url, response.status_code, df, links, tokens, len(response.text)))
            except Exception as exc:
                failures.append(f"{page_url}: {type(exc).__name__}: {exc}")

    if successes:
        st.success("公式ページへの接続に成功しました。")
        # Prefer the source that actually yielded more event rows.
        successes.sort(key=lambda item: len(item[2]), reverse=True)
        page_url, status, df, links, tokens, html_size = successes[0]
        st.caption(f"主に使用したページ：{page_url} ／ HTTP {status} ／ HTML {html_size:,}文字")
        st.subheader("開催情報")
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.success(f"{len(df)}件の開催候補を抽出しました。日程・開催名は公式ページで照合してください。")
        else:
            st.warning("接続はできましたが、HTMLから開催情報を確実に組み合わせられませんでした。誤った開催一覧は表示しません。")

        # Show only links that are plausibly event/race details, not the two schedule navigation links.
        detail_links = []
        seen = set()
        for item in links:
            text = (item["リンク名"] + " " + item["URL"]).lower()
            if any(w in text for w in ("racecard", "racedetail", "race_detail", "odds", "出走表", "レース詳細", "kaisai")):
                if item["URL"] not in seen:
                    seen.add(item["URL"])
                    detail_links.append(item)
        st.subheader("レース関連リンク")
        if detail_links:
            st.dataframe(pd.DataFrame(detail_links[:100]), use_container_width=True, hide_index=True)
        else:
            st.caption("開催日程ページのHTMLには、出走表への直接リンクが見つかりませんでした。URLは推測で作成していません。")

        with st.expander("診断情報（必要な場合だけ開く）"):
            st.write("各ページの抽出件数")
            st.dataframe(pd.DataFrame([
                {"ページ": x[0], "HTTP": x[1], "抽出件数": len(x[2]), "HTML文字数": x[5]}
                for x in successes
            ]), use_container_width=True, hide_index=True)
            st.write("本文テキストの先頭100項目")
            st.code("\n".join(tokens[:100])[:10000])
            st.write("取得リンクの先頭60件")
            st.code("\n".join(f'{x["リンク名"]} -> {x["URL"]}' for x in links[:60])[:10000])
    else:
        st.error("公式ページの取得に失敗しました。")
    if failures:
        with st.expander("取得エラーの詳細"):
            st.code("\n".join(failures))

st.divider()
st.subheader("開発状況")
st.markdown("""
- 開催日程：公式PC版・スマホ版を取得して抽出を試行
- 開催場・期間・開催名：抽出できた候補のみ表示。確実に取れない場合は空欄のままにする
- 出走表・ライン・オッズ・バンク特性・当日の風：まだ未実装
- 自動投票：行いません
""")
st.caption("この版は開催日程の抽出改善を検証するものです。予想精度や利益を保証するものではありません。")
