import re
from datetime import date
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("WINTICKETの実際のレースURL構造に合わせた修正版。自動投票は行いません。")

BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
VENUE_SLUGS = {
    "hakodate":"函館", "aomori":"青森", "iw平":"いわき平", "iw平":"いわき平",
    "yahiko":"弥彦", "maebashi":"前橋", "toride":"取手", "utsunomiya":"宇都宮",
    "omiya":"大宮", "seibuen":"西武園", "keiokaku":"京王閣", "tachikawa":"立川",
    "matsudo":"松戸", "kawasaki":"川崎", "hiratsuka":"平塚", "odawara":"小田原",
    "ito":"伊東", "shizuoka":"静岡", "nagoya":"名古屋", "gifu":"岐阜",
    "ogaki":"大垣", "toyohashi":"豊橋", "toyama":"富山", "matsusaka":"松阪",
    "yokkaichi":"四日市", "fukui":"福井", "nara":"奈良", "mukomachi":"向日町",
    "wakayama":"和歌山", "kishiwada":"岸和田", "tamano":"玉野", "hiroshima":"広島",
    "hofu":"防府", "takamatsu":"高松", "komatsushima":"小松島", "kochi":"高知",
    "matsuyama":"松山", "kokura":"小倉", "kurume":"久留米", "takeo":"武雄",
    "sasebo":"佐世保", "beppu":"別府", "kumamoto":"熊本", "chiba":"千葉",
}

def norm(s):
    return re.sub(r"\s+", " ", str(s)).strip()

def get_html(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text, response.status_code

def venue_from_path(path):
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "keirin":
        return VENUE_SLUGS.get(parts[1], parts[1])
    return ""

def extract_races(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    races, venues, seen = [], [], set()
    for a in soup.find_all("a", href=True):
        label = norm(a.get_text(" ", strip=True))
        href = urljoin(base_url, a["href"].strip())
        p = urlparse(href)
        if p.netloc.lower() not in ("www.winticket.jp", "winticket.jp"):
            continue
        path = p.path.rstrip("/")
        # Observed actual pattern: /keirin/{venue}/racecard/{event_id}/{day}/{race_number}
        m = re.fullmatch(r"/keirin/([^/]+)/racecard/(\d{8,})/(\d+)/(\d+)", path)
        if m:
            slug, event_id, day_no, race_no = m.groups()
            key = (href, label)
            if key not in seen:
                seen.add(key)
                races.append({
                    "競輪場": VENUE_SLUGS.get(slug, slug),
                    "開催ID": event_id,
                    "開催日番号": int(day_no),
                    "レース": f"{int(race_no)}R",
                    "URL": href,
                })
        # venue's racecard landing page, used to identify venues and links
        vm = re.fullmatch(r"/keirin/([^/]+)/racecard", path)
        if vm:
            slug = vm.group(1)
            venue = VENUE_SLUGS.get(slug, slug)
            if venue not in venues:
                venues.append(venue)
    df = pd.DataFrame(races, columns=["競輪場", "開催ID", "開催日番号", "レース", "URL"])
    if not df.empty:
        df = df.drop_duplicates(subset=["URL"]).sort_values(["競輪場", "開催日番号", "レース"]).reset_index(drop=True)
    return df, venues, soup

st.info("診断情報で確認できた実際のURL（例：/keirin/keiokaku/racecard/2026102627/2/1）に合わせ、開催ブロックの文章解析ではなくURLの形からレース番号を判定します。")
st.write(f"取得日：{date.today():%Y年%m月%d日}")
c1, c2 = st.columns(2)
with c1:
    run = st.button("本日の出走表リンクを取得", type="primary", use_container_width=True)
with c2:
    st.link_button("WINTICKET出走表一覧を開く", BASE_URL, use_container_width=True)

if run:
    try:
        with st.spinner("出走表一覧を取得しています…"):
            html, status = get_html(BASE_URL)
            df, venues, soup = extract_races(html, BASE_URL)
        st.success(f"一覧ページ取得成功（HTTP {status}）。")
        st.subheader("開催場")
        if venues:
            st.write("、".join(venues))
        else:
            st.caption("開催場の個別ページリンクは見つかりませんでした。")
        st.subheader("レース詳細URL")
        if not df.empty:
            st.write(f"実際のURLを {len(df)} 件検出しました。")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "レースURL一覧をCSV保存",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"keirin_race_links_{date.today():%Y%m%d}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.warning("実際のURL形式に一致するレースリンクを見つけられませんでした。下の診断情報を確認できます。")
        with st.expander("診断情報"):
            st.write(f"HTML文字数：{len(html):,}")
            st.write(f"HTML内リンク数：{len(soup.find_all('a', href=True))}")
            st.write("検出したracecard関連URL（先頭100件）")
            urls = []
            for a in soup.find_all("a", href=True):
                href = urljoin(BASE_URL, a.get("href", ""))
                if "winticket.jp/keirin/" in href and "racecard" in href:
                    urls.append(f"{norm(a.get_text(' ', strip=True)) or '(文字なし)'} -> {href}")
            unique_urls = list(dict.fromkeys(urls))
            st.code("\n".join(unique_urls[:100]) if unique_urls else "該当URLなし")
    except Exception as e:
        st.error("一覧ページの取得に失敗しました。")
        st.code(f"{type(e).__name__}: {e}")

st.divider()
st.subheader("次の開発段階")
st.markdown("""
- 今回：実際のURL構造から開催場・開催日番号・レース番号を抽出
- 次：個別レースページから選手・競走得点・脚質・ラインを取得
- その後：オッズ、バンク特性、当日の風を加えて分析
- 1日予算上限は1,000円。自動投票は行いません
""")
st.caption("URL構造に基づく抽出版です。開催名・正式な開催日付は次の段階で追加します。")
