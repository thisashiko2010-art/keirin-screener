import re
from datetime import date
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("開催日程から実際の出走表リンクを探す試作版。自動投票は行いません。")

RACECARD_URL = "https://www.winticket.jp/keirin/racecard/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
VENUES = [
    "函館", "青森", "いわき平", "弥彦", "前橋", "取手", "宇都宮", "大宮",
    "西武園", "京王閣", "立川", "松戸", "千葉", "川崎", "平塚", "小田原",
    "伊東", "静岡", "名古屋", "岐阜", "大垣", "豊橋", "富山", "松阪",
    "四日市", "福井", "奈良", "向日町", "和歌山", "岸和田", "玉野",
    "広島", "防府", "高松", "小松島", "高知", "松山", "小倉", "久留米",
    "武雄", "佐世保", "別府", "熊本"
]

def clean(value):
    return re.sub(r"\s+", " ", str(value)).strip()

def get_html(url):
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text, response.status_code

def parse_race_list(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    # Identify event blocks by searching upward from each venue link, then collect 1R/2R links inside that block.
    events = []
    used_races = set()
    for venue in VENUES:
        venue_anchors = [
            a for a in soup.find_all("a", href=True)
            if venue in clean(a.get_text(" ", strip=True)) and "競輪" in clean(a.get_text(" ", strip=True))
        ]
        for va in venue_anchors:
            node = va
            chosen = None
            # Find the nearest ancestor with a date range and several race-number links.
            for _ in range(7):
                if node is None:
                    break
                text = clean(node.get_text(" ", strip=True))
                race_anchors = [
                    a for a in node.find_all("a", href=True)
                    if re.fullmatch(r"\d{1,2}R", clean(a.get_text(" ", strip=True)))
                ]
                if len(race_anchors) >= 3 and re.search(r"\d{1,2}/\d{1,2}", text):
                    chosen = node
                    break
                node = node.parent
            if chosen is None:
                continue
            block_text = clean(chosen.get_text(" ", strip=True))
            dates = re.findall(r"\d{1,2}/\d{1,2}", block_text)
            title = ""
            for line in chosen.stripped_strings:
                line = clean(line)
                if line and venue not in line and not re.fullmatch(r"\d{1,2}R", line) and not re.fullmatch(r"\d{1,2}/\d{1,2}", line):
                    if len(line) < 100 and not any(x in line for x in ("前日", "翌日", "出走表一覧", "WINTICKET")):
                        title = line
            event_key = (venue, tuple(dates[:2]), title)
            if any(e["開催キー"] == event_key for e in events):
                continue
            races = []
            for a in race_anchors:
                race_name = clean(a.get_text(" ", strip=True))
                race_url = urljoin(base_url, a["href"])
                key = (venue, race_name, race_url)
                if key in used_races:
                    continue
                used_races.add(key)
                races.append({"競輪場": venue, "レース": race_name, "出走表URL": race_url})
            if races:
                events.append({
                    "開催キー": event_key,
                    "競輪場": venue,
                    "開催期間": "〜".join(dates[:2]) if dates else "日付未抽出",
                    "開催名": title or "開催名未抽出",
                    "レース数": len(races),
                    "レース": races,
                })
    return events, soup

st.info("前の版では公式日程ページから出走表への直接リンクを見つけられませんでした。今回は、当日の出走表リンクが一覧化されている公開ページを入口として使い、実在するリンクを抽出します。")
st.write(f"取得日：{date.today():%Y年%m月%d日}")
left, right = st.columns(2)
with left:
    fetch = st.button("本日の出走表一覧を取得", type="primary", use_container_width=True)
with right:
    st.link_button("出走表一覧をブラウザで開く", RACECARD_URL, use_container_width=True)

if fetch:
    try:
        with st.spinner("出走表一覧を取得して、実際のレースリンクを調べています…"):
            html, status = get_html(RACECARD_URL)
            events, soup = parse_race_list(html, RACECARD_URL)
        st.success(f"一覧ページを取得しました（HTTP {status}）。")
        if events:
            st.subheader("開催一覧")
            summary = pd.DataFrame([{
                "競輪場": e["競輪場"],
                "開催期間": e["開催期間"],
                "開催名": e["開催名"],
                "抽出レース数": e["レース数"],
            } for e in events])
            st.dataframe(summary, use_container_width=True, hide_index=True)
            all_races = [race for event in events for race in event["レース"]]
            st.subheader("出走表リンク")
            st.write(f"実在するリンクを {len(all_races)} 件抽出しました。")
            st.dataframe(pd.DataFrame(all_races), use_container_width=True, hide_index=True)
            st.download_button(
                "出走表リンク一覧をCSV保存",
                data=pd.DataFrame(all_races).to_csv(index=False).encode("utf-8-sig"),
                file_name=f"keirin_race_links_{date.today():%Y%m%d}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.session_state["keirin_events"] = events
        else:
            st.warning("ページへの接続は成功しましたが、開催ブロックとレースリンクの組み合わせを特定できませんでした。推測したURLは表示しません。")
        with st.expander("診断情報"):
            st.write(f"HTML文字数：{len(html):,}")
            st.write("ページ内の競輪場リンク")
            venue_links = []
            for a in soup.find_all("a", href=True):
                label = clean(a.get_text(" ", strip=True))
                if any(v in label for v in VENUES) and "競輪" in label:
                    venue_links.append({"表示名": label, "URL": urljoin(RACECARD_URL, a["href"])})
            if venue_links:
                st.dataframe(pd.DataFrame(venue_links).drop_duplicates(), use_container_width=True, hide_index=True)
            st.write("1R〜12Rのリンク先（先頭100件）")
            race_links = []
            for a in soup.find_all("a", href=True):
                label = clean(a.get_text(" ", strip=True))
                if re.fullmatch(r"\d{1,2}R", label):
                    race_links.append({"レース": label, "URL": urljoin(RACECARD_URL, a["href"])})
            st.dataframe(pd.DataFrame(race_links).drop_duplicates().head(100), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error("出走表一覧を取得できませんでした。")
        st.code(f"{type(exc).__name__}: {exc}")

st.divider()
st.subheader("次の開発段階")
st.markdown("""
- 現在：開催一覧から実際の出走表URLを抽出する
- 次：選択したレースの選手・脚質・競走得点・ライン情報を読み取る
- その次：オッズ取得、期待値計算、バンク特性と当日の風の反映
- 買い目候補は1日最大1,000円以内で提示し、投票操作は行わない
""")
st.caption("情報提供元：WINTICKET公開出走表一覧。表示内容は公式情報等と照合してください。利用規約・アクセス制限に従って使用してください。")
