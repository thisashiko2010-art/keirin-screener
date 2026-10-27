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
st.caption("出走表URLとページ内データの調査版。自動投票は行いません。")

BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
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
        if not m or href in seen:
            continue
        seen.add(href)
        slug, event_id, day_num, race_num = m.groups()
        rows.append({"競輪場": slug, "開催ID": event_id, "開催日番号": int(day_num),
                     "レース": f"{int(race_num)}R", "URL": href})
    return pd.DataFrame(rows).drop_duplicates("URL") if rows else pd.DataFrame(columns=["競輪場","開催ID","開催日番号","レース","URL"])

def inspect_scripts(soup):
    found = []
    for i, script in enumerate(soup.find_all("script")):
        src = script.get("src", "")
        body = script.string or script.get_text() or ""
        # Avoid dumping large/minified scripts; report only data-like markers and small snippets.
        markers = ["競走得点", "選手名", "脚質", "rider", "player", "racecard", "__NEXT_DATA__", "__INITIAL_STATE__", "apollo", "graphql", "application/json"]
        hits = [m for m in markers if m.lower() in body.lower()]
        if src or hits:
            found.append({
                "script番号": i + 1,
                "種類": "srcあり" if src else "inline",
                "src": urljoin("https://www.winticket.jp", src) if src else "",
                "文字数": len(body),
                "データ関連語": ", ".join(hits) if hits else "目立つ語なし",
                "冒頭": norm(body[:180]) if not src else "",
            })
    return found

st.info("ページの診断結果から、想定していたJSON名が見つからないことが分かりました。この版では、ページ内の全script要素を調べ、選手データらしい語や外部JavaScriptの参照先を確認します。")
c1, c2 = st.columns(2)
with c1:
    load_urls = st.button("出走表URL一覧を取得", type="primary", use_container_width=True)
with c2:
    st.link_button("WINTICKET出走表一覧を開く", BASE_URL, use_container_width=True)

if load_urls:
    try:
        with st.spinner("出走表一覧を取得しています…"):
            html, status = get_html(BASE_URL)
            races = extract_race_urls(html)
        st.session_state["race_urls"] = races
        st.success(f"一覧ページ取得成功（HTTP {status}）。レースURLを {len(races)} 件検出しました。")
        if not races.empty:
            st.dataframe(races, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error("一覧ページの取得に失敗しました。")
        st.code(f"{type(e).__name__}: {e}")

races = st.session_state.get("race_urls")
if isinstance(races, pd.DataFrame) and not races.empty:
    st.subheader("出走表ページを調査")
    options = [f'{r["競輪場"]} {r["レース"]} — {r["URL"]}' for _, r in races.iterrows()]
    chosen = st.selectbox("調査するレース", options)
    url = races.iloc[options.index(chosen)]["URL"]
    st.caption(f"選択URL：{url}")
    if st.button("ページ内のデータ構造を調査", use_container_width=True):
        try:
            with st.spinner("レースページとscriptタグを調べています…"):
                html, status = get_html(url)
                soup = BeautifulSoup(html, "html.parser")
                scripts = inspect_scripts(soup)
                text_body = norm(soup.get_text(" ", strip=True))
            st.success(f"レースページ取得成功（HTTP {status}、HTML {len(html):,}文字）。scriptタグ {len(soup.find_all('script'))} 個。")
            st.subheader("ページ本文の先頭")
            st.code(text_body[:3500] or "(本文テキストなし)")
            st.subheader("scriptタグの診断")
            if scripts:
                st.dataframe(pd.DataFrame(scripts), use_container_width=True, hide_index=True)
            else:
                st.warning("データらしい語を含むscriptタグは見つかりませんでした。")
            with st.expander("HTML内のデータ候補（安全な範囲の抜粋）"):
                candidates = []
                for i, script in enumerate(soup.find_all("script")):
                    body = script.string or script.get_text() or ""
                    if any(k in body.lower() for k in ["競走得点", "rider", "player", "racecard", "graphql", "__next_data__"]):
                        candidates.append(f"--- script {i+1} ---\n{norm(body[:500])}")
                st.code("\n\n".join(candidates[:15]) if candidates else "該当するinline scriptなし")
        except Exception as e:
            st.error("レースページの調査に失敗しました。")
            st.code(f"{type(e).__name__}: {e}")

st.divider()
st.subheader("開発状況")
st.markdown("""
- 成功済み：公開一覧からレースURLを抽出
- 今回：ページ本文とscriptタグを調べ、選手データの格納場所を特定
- 次：実際の格納形式に合わせて選手名・車番・競走得点・脚質・ラインを抽出
- その後：オッズ、バンク特性、当日の風を追加
- 1日予算上限1,000円。自動投票は行いません
""")
st.caption("診断用の版です。取得データの正確性を確認してから予想ロジックを追加します。")
