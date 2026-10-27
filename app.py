import re
from datetime import date
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("出走表リンクを先に拾う診断版。自動投票は行いません。")

BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

def norm(s):
    return re.sub(r"\\s+", " ", str(s)).strip()

def get_page(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text, r.status_code

def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        label = norm(a.get_text(" ", strip=True))
        href = urljoin(base_url, a.get("href", "").strip())
        parsed = urlparse(href)
        if parsed.netloc.lower() not in ("www.winticket.jp", "winticket.jp"):
            continue
        path = parsed.path.lower()
        is_race = bool(re.search(r"/racecard/[^/]+/races", path))
        is_racecard = "/racecard/" in path
        if not (is_race or is_racecard):
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)
        parent, context = a, ""
        for _ in range(4):
            if parent.parent is None:
                break
            parent = parent.parent
            txt = norm(parent.get_text(" ", strip=True))
            if txt and len(txt) <= 350:
                context = txt
            if len(txt) > 350:
                break
        out.append({"表示名": label or "(リンク文字なし)", "URL": href,
                    "レース詳細URL": is_race, "周辺テキスト": context[:250]})
    return out, soup

def venue_guess(text):
    venues = ["函館","青森","いわき平","弥彦","前橋","取手","宇都宮","大宮","西武園","京王閣",
              "立川","松戸","川崎","平塚","小田原","伊東","静岡","名古屋","岐阜","大垣",
              "豊橋","富山","松阪","四日市","福井","奈良","向日町","和歌山","岸和田","玉野",
              "広島","防府","高松","小松島","高知","松山","小倉","久留米","武雄","佐世保",
              "別府","熊本","千葉"]
    return next((v for v in venues if v in text), "")

st.info("前回は開催ブロックの検出条件が厳しすぎた可能性があります。この版では開催場ブロックの特定を必須にせず、HTML内の実際の出走表URLを直接集めます。")
st.write(f"取得日：{date.today():%Y年%m月%d日}")
c1, c2 = st.columns(2)
with c1:
    run = st.button("出走表リンクを取得・診断", type="primary", use_container_width=True)
with c2:
    st.link_button("WINTICKET出走表一覧を開く", BASE_URL, use_container_width=True)

if run:
    try:
        with st.spinner("公開ページを取得して、実際のリンクを調べています…"):
            html, status = get_page(BASE_URL)
            links, soup = extract_links(html, BASE_URL)
        st.success(f"ページ取得成功（HTTP {status}、HTML {len(html):,}文字）")
        if links:
            df = pd.DataFrame(links)
            df.insert(0, "競輪場候補", df["周辺テキスト"].apply(venue_guess))
            st.subheader("検出した出走表・レース関連リンク")
            st.write(f"リンクを {len(df)} 件検出しました。")
            st.dataframe(df, use_container_width=True, hide_index=True)
            race_details = df[df["レース詳細URL"] == True].copy()
            st.subheader("レース詳細ページ候補")
            if not race_details.empty:
                st.write(f"レース詳細URLを {len(race_details)} 件検出しました。")
                st.dataframe(race_details[["競輪場候補","表示名","URL","周辺テキスト"]], use_container_width=True, hide_index=True)
                st.download_button("検出したレース詳細URLをCSV保存",
                    data=race_details[["競輪場候補","表示名","URL","周辺テキスト"]].to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"keirin_race_links_{date.today():%Y%m%d}.csv",
                    mime="text/csv", use_container_width=True)
            else:
                st.warning("HTML内に /racecard/.../races 形式のリンクは見つかりませんでした。診断情報でHTML構造を確認できます。")
        else:
            st.warning("ページは取得できましたが、HTML内に出走表リンクを見つけられませんでした。JavaScriptで後から表示される可能性があります。")
        with st.expander("診断情報（必要な場合だけ開く）"):
            st.write("HTML内のリンク数:", len(soup.find_all("a", href=True)))
            st.write("HTMLに含まれる racecard / races 関連URL")
            raw = []
            for a in soup.find_all("a", href=True):
                href = urljoin(BASE_URL, a["href"])
                if "racecard" in href.lower() or "/races" in href.lower():
                    raw.append(f'{norm(a.get_text(" ", strip=True)) or "(文字なし)"} -> {href}')
            unique_raw = list(dict.fromkeys(raw))
            st.code("\\n".join(unique_raw[:150]) if unique_raw else "該当URLなし")
            st.write("ページ本文の先頭")
            st.code(norm(soup.get_text(" ", strip=True))[:5000])
    except Exception as e:
        st.error("公開ページの取得に失敗しました。")
        st.code(f"{type(e).__name__}: {e}")

st.divider()
st.subheader("現在の到達点")
st.markdown("""
- この版：開催ブロックの推測をやめ、実際の出走表URLを直接抽出
- 次段階：レース詳細ページから選手・競走得点・脚質・ラインを抽出
- その後：オッズ、バンク特性、当日の風を追加
- 1日予算の上限は1,000円。自動投票は行わない
""")
st.caption("ページ構造が変わると抽出に失敗する場合があります。取得結果を確認してから次の段階へ進みます。")
