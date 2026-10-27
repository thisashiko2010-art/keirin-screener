import json
import re
from datetime import date
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("出走表URLから選手情報を取得する検証版。自動投票は行いません。")

BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
VENUE_NAMES = {
    "hakodate":"函館", "aomori":"青森", "iw平":"いわき平", "yahiko":"弥彦",
    "maebashi":"前橋", "toride":"取手", "utsunomiya":"宇都宮", "omiya":"大宮",
    "seibuen":"西武園", "keiokaku":"京王閣", "tachikawa":"立川", "matsudo":"松戸",
    "chiba":"千葉", "kawasaki":"川崎", "hiratsuka":"平塚", "odawara":"小田原",
    "ito":"伊東", "shizuoka":"静岡", "nagoya":"名古屋", "gifu":"岐阜", "ogaki":"大垣",
    "toyohashi":"豊橋", "toyama":"富山", "matsusaka":"松阪", "yokkaichi":"四日市",
    "fukui":"福井", "nara":"奈良", "mukomachi":"向日町", "wakayama":"和歌山",
    "kishiwada":"岸和田", "tamano":"玉野", "hiroshima":"広島", "hofu":"防府",
    "takamatsu":"高松", "komatsushima":"小松島", "kochi":"高知", "matsuyama":"松山",
    "kokura":"小倉", "kurume":"久留米", "takeo":"武雄", "sasebo":"佐世保",
    "beppu":"別府", "kumamoto":"熊本"
}

def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip()

def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text, r.status_code

def extract_race_urls(html):
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a["href"].strip())
        p = urlparse(href)
        if p.netloc.lower() not in ("www.winticket.jp", "winticket.jp"):
            continue
        m = re.fullmatch(r"/keirin/([^/]+)/racecard/(\d{8,})/(\d+)/(\d+)/?", p.path)
        if not m:
            continue
        slug, event_id, day_num, race_num = m.groups()
        if href in seen:
            continue
        seen.add(href)
        rows.append({
            "競輪場": VENUE_NAMES.get(slug, slug),
            "開催ID": event_id,
            "開催日番号": int(day_num),
            "レース": f"{int(race_num)}R",
            "URL": href,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates("URL").reset_index(drop=True)
    return df, soup

def find_preloaded_state(soup):
    # WINTICKET page data may be embedded in a Next.js-style JSON script or JS assignment.
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if not text:
            continue
        if "__PRELOADED_STATE__" in text:
            match = re.search(r"__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;?\s*$", text, re.S)
            if match:
                try:
                    return json.loads(match.group(1)), "window.__PRELOADED_STATE__"
                except Exception:
                    pass
        if "__NEXT_DATA__" in (script.get("id") or ""):
            try:
                return json.loads(text), "Next.js __NEXT_DATA__"
            except Exception:
                pass
    return None, "埋め込みJSONを特定できず"

def json_to_rows(obj):
    rows = []
    seen = set()
    def walk(x):
        if isinstance(x, dict):
            # Candidate competitor dictionaries, accepting common Japanese/English keys.
            keys = {str(k).lower(): k for k in x.keys()}
            name_key = next((keys[k] for k in ("name", "playername", "ridername", "選手名") if k in keys), None)
            number_key = next((keys[k] for k in ("number", "carno", "car_number", "車番") if k in keys), None)
            score_key = next((keys[k] for k in ("point", "score", "competitionpoint", "競走得点") if k in keys), None)
            if name_key is not None and (number_key is not None or score_key is not None):
                name = norm(x.get(name_key, ""))
                if name and len(name) <= 40 and name not in seen:
                    seen.add(name)
                    rows.append({
                        "車番": x.get(number_key, "") if number_key is not None else "",
                        "選手名": name,
                        "競走得点": x.get(score_key, "") if score_key is not None else "",
                        "脚質": x.get(next((keys[k] for k in ("style", "runningstyle", "脚質") if k in keys), ""), ""),
                    })
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return rows

st.info("今回は、抽出したURLのうち1レースを選び、そのページのHTMLと埋め込みデータから選手情報を読み取れるか確認します。")
left, right = st.columns(2)
with left:
    load_urls = st.button("出走表URL一覧を取得", type="primary", use_container_width=True)
with right:
    st.link_button("WINTICKET出走表一覧を開く", BASE_URL, use_container_width=True)

if load_urls:
    try:
        with st.spinner("出走表一覧を取得しています…"):
            html, status = get_html(BASE_URL)
            races, soup = extract_race_urls(html)
        st.session_state["race_urls"] = races
        st.success(f"ページ取得成功（HTTP {status}）。レースURLを {len(races)} 件検出しました。")
        if not races.empty:
            st.dataframe(races, use_container_width=True, hide_index=True)
        else:
            st.warning("レースURLを検出できませんでした。")
    except Exception as e:
        st.error("一覧ページの取得に失敗しました。")
        st.code(f"{type(e).__name__}: {e}")

races = st.session_state.get("race_urls")
if isinstance(races, pd.DataFrame) and not races.empty:
    st.subheader("出走表の内容を調べる")
    options = [f'{row["競輪場"]} {row["レース"]} — {row["URL"]}' for _, row in races.iterrows()]
    chosen = st.selectbox("調査するレース（まずは1レース）", options)
    selected_index = options.index(chosen)
    selected_url = races.iloc[selected_index]["URL"]
    st.caption(f"選択中URL：{selected_url}")
    if st.button("このレースの選手情報を取得", use_container_width=True):
        try:
            with st.spinner("レース詳細ページを読み込んでいます…"):
                race_html, race_status = get_html(selected_url)
                race_soup = BeautifulSoup(race_html, "html.parser")
                state, state_source = find_preloaded_state(race_soup)
                rows = json_to_rows(state) if state is not None else []
            st.write(f"レースページ HTTP {race_status} ／ HTML {len(race_html):,}文字")
            if rows:
                st.success(f"選手候補を {len(rows)} 人抽出しました（項目名は要確認）。")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.warning("ページは取得できましたが、埋め込みJSONから選手データを抽出できませんでした。HTML内の実データ形式を確認する必要があります。")
            with st.expander("レースページ診断情報"):
                st.write(f"埋め込みデータ検出：{state_source}")
                st.write(f"scriptタグ数：{len(race_soup.find_all('script'))}")
                st.write("本文テキスト先頭")
                st.code(norm(race_soup.get_text(" ", strip=True))[:4000])
                st.write("ページ内の選手・競走得点関連語")
                page_text = norm(race_soup.get_text(" ", strip=True))
                terms = ["競走得点", "脚質", "選手名", "車番", "並び", "ライン"]
                st.write({term: page_text.find(term) for term in terms})
        except Exception as e:
            st.error("レース詳細ページの取得に失敗しました。")
            st.code(f"{type(e).__name__}: {e}")

st.divider()
st.subheader("開発状況")
st.markdown("""
- ここまで：出走表URLを抽出
- 今回：選択した1レースから選手情報の抽出を試す
- 次：実際のデータ形式に合わせて競走得点・脚質・ラインを整理
- その後：オッズ、バンク特性、当日の風を追加
- 1日予算上限1,000円。自動投票は行いません
""")
st.caption("この版は取得方式の検証用です。抽出値を正しいものとみなす前に、画面と照合してください。")
