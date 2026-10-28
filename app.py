import re
from datetime import date
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー v14", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("v14：選手データに加え、ページ本文から並び予想を抽出。自動投票は行いません。")
BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","Accept-Language":"ja,en-US;q=0.9,en;q=0.8"}
VENUES = {"hakodate":"函館","aomori":"青森","yahiko":"弥彦","maebashi":"前橋","toride":"取手","utsunomiya":"宇都宮","omiya":"大宮","seibuen":"西武園","keiokaku":"京王閣","tachikawa":"立川","matsudo":"松戸","chiba":"千葉","kawasaki":"川崎","hiratsuka":"平塚","odawara":"小田原","ito":"伊東","shizuoka":"静岡","nagoya":"名古屋","gifu":"岐阜","ogaki":"大垣","toyohashi":"豊橋","toyama":"富山","matsusaka":"松阪","yokkaichi":"四日市","fukui":"福井","nara":"奈良","mukomachi":"向日町","wakayama":"和歌山","kishiwada":"岸和田","tamano":"玉野","hiroshima":"広島","hofu":"防府","takamatsu":"高松","komatsushima":"小松島","kochi":"高知","matsuyama":"松山","kokura":"小倉","kurume":"久留米","takeo":"武雄","sasebo":"佐世保","beppu":"別府","kumamoto":"熊本"}
def norm(s): return re.sub(r"\s+"," ",str(s)).strip()
def get_html(url):
    r=requests.get(url,headers=HEADERS,timeout=30); r.raise_for_status(); r.encoding=r.apparent_encoding or "utf-8"; return r.text,r.status_code
def extract_races(html):
    soup=BeautifulSoup(html,"html.parser"); rows=[]; seen=set()
    for a in soup.find_all("a",href=True):
        href=urljoin(BASE_URL,a["href"].strip()); p=urlparse(href)
        m=re.fullmatch(r"/keirin/([^/]+)/racecard/(\d{8,})/(\d+)/(\d+)/?",p.path)
        if p.netloc.lower() not in ("www.winticket.jp","winticket.jp") or not m or href in seen: continue
        seen.add(href); slug,event,day,race=m.groups()
        rows.append({"競輪場":VENUES.get(slug,slug),"開催ID":event,"開催日番号":int(day),"レース":f"{int(race)}R","URL":href})
    return pd.DataFrame(rows,columns=["競輪場","開催ID","開催日番号","レース","URL"]).drop_duplicates("URL").reset_index(drop=True)
def extract_riders(page_text):
    text = norm(page_text)
    # 見出しの表記ゆれに依存せず、ページ本文全体から「車番→選手名→府県→級班→年齢→期別→得点」を探す。
    prefectures = ["北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉","千葉","東京","神奈川","新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重","滋賀","京都","大阪","兵庫","奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川","愛媛","高知","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄"]
    pref_pattern = "|".join(sorted(prefectures, key=len, reverse=True))
    # 通常行は「枠番 車番 選手名…」。ただし7番車は「7 越智展孝…」と
    # 1数字だけで始まる表示の場合があるため、2数字形式と1数字形式を別々に検索。
    name_chars = r"[一-龥々〆ヵヶぁ-ゖァ-ヺー・]"
    common_tail = rf"(?P<n>{name_chars}{{2,12}}?)\s+(?P<p>{pref_pattern})\s+(?P<cl>[ASL]\d)\s+(?P<age>\d{{2}})歳\s+(?P<reg>\d{{2,3}})期(?:\s+(?:本命|対抗|単穴|連下))?\s+(?P<score>\d{{2,3}}\.\d{{2}})"
    patterns = [
        re.compile(rf"(?P<w>[1-6])\s+(?P<c>[1-6])\s+" + common_tail),
        re.compile(rf"(?P<w>[7-9])\s+(?P<c>[7-9])\s+" + common_tail),
        re.compile(rf"(?P<w>[7-9])\s+" + common_tail),
    ]
    found=[]
    for pat in patterns:
        for m in pat.finditer(text):
            d=m.groupdict()
            if d.get("c") is None: d["c"] = d["w"]
            found.append((m.start(), d, m.group(0)))
    found.sort(key=lambda x: x[0])
    rows=[]; seen=set(); matches=[]
    for _, d, matched_text in found:
        car=int(d["c"])
        matches.append({"車番":car,"選手名候補":d["n"],"府県候補":d["p"],"一致文字列":matched_text})
        if car in seen: continue
        seen.add(car)
        rows.append({"枠番":int(d["w"]),"車番":car,"選手名":d["n"],"府県":d["p"],"級班":d["cl"],"年齢":int(d["age"]),"期別":int(d["reg"]),"競走得点":float(d["score"])})
    # 詳細表の並びで車番が1〜9に連番でなくても、車番をキーに重複排除する。
    rows=sorted(rows,key=lambda x:x["車番"])
    # 診断抜粋：選手名が見つからないときに本文内の該当行を確認できるようにする。
    diagnostic = "抽出候補一覧:\n" + "\n".join(f"車番{m['車番']}: {m['選手名候補']} / {m['府県候補']} — {m['一致文字列']}" for m in matches)
    diagnostic += "\n\n本文中の『越智』『愛媛』付近:\n"
    snippets=[]
    for keyword in ("越智", "愛媛", "83.25"):
        i=text.find(keyword)
        snippets.append(f"{keyword}: " + (text[max(0,i-100):i+180] if i>=0 else "見つからず"))
    diagnostic += "\n".join(snippets)
    return rows, diagnostic

def extract_lines(page_text, riders):
    """WINTICKET本文にある並び予想を抽出する。抽出元表現と根拠を返す。"""
    text = norm(page_text)
    rider_cars = {int(r["車番"]) for r in riders}
    candidates = []
    # WINTICKETの表示例：「3 1 4 区切り 2 7 5 区切り 6」
    # 「並び予想」周辺を優先し、ライン区切り語のある範囲を探す。
    for marker in ("並び予想", "並び", "ライン"):
        pos = text.find(marker)
        if pos >= 0:
            candidates.append(text[pos:pos+500])
    candidates.append(text)
    for area in candidates:
        # 区切り表記があれば、その表記を使ってグループ分けする。
        if re.search(r"区切り|ライン", area):
            m = re.search(r"((?:[1-9](?:\s+|[-ー－])?){1,9}(?:\s*(?:区切り|ライン)\s*(?:[1-9](?:\s+|[-ー－])?){1,9}){1,8})", area)
            if m:
                raw = m.group(1)
                groups=[]
                for part in re.split(r"区切り|ライン", raw):
                    nums = [int(x) for x in re.findall(r"[1-9]", part)]
                    nums = [n for n in nums if n in rider_cars]
                    if nums and nums not in groups:
                        groups.append(nums)
                flat=[n for g in groups for n in g]
                if groups and len(flat)==len(set(flat)) and set(flat).issubset(rider_cars):
                    return groups, raw
        # KEIRIN.JPなどの「← 3先行 1追込 4追込 2押え先…」形式
        m = re.search(r"(?:←\s*)?((?:[1-9]\s*(?:先行|追込|押え先|自在|追上|マーク|捲り|追走)?\s*){2,9})", area)
        if m:
            nums = [int(x) for x in re.findall(r"([1-9])\s*(?:先行|追込|押え先|自在|追上|マーク|捲り|追走)?", m.group(1))]
            nums = [n for n in nums if n in rider_cars]
            if len(nums)>=2 and len(nums)==len(set(nums)):
                return [nums], m.group(0)
    return [], "本文から明確なライン区切りを認識できませんでした。並び予想が未掲載、または表示形式が異なる可能性があります。"

st.info("v14：選手データを抽出し、ページ本文にある並び予想も解析します。ラインはサイト掲載の予想であり、確定情報ではありません。")
c1,c2=st.columns(2)
with c1: load=st.button("出走表URL一覧を取得",type="primary",use_container_width=True)
with c2: st.link_button("WINTICKET出走表一覧を開く",BASE_URL,use_container_width=True)
if load:
    try:
        with st.spinner("一覧を取得中…"):
            html,status=get_html(BASE_URL); races=extract_races(html)
        st.session_state["races"]=races
        st.success(f"一覧取得成功（HTTP {status}）。URL {len(races)} 件。")
        if not races.empty: st.dataframe(races,use_container_width=True,hide_index=True)
    except Exception as e: st.error(f"{type(e).__name__}: {e}")
races=st.session_state.get("races")
if isinstance(races,pd.DataFrame) and not races.empty:
    st.subheader("選手データを取得")
    opts=[f'{r["競輪場"]} {r["レース"]} — {r["URL"]}' for _,r in races.iterrows()]
    choice=st.selectbox("調査するレース",opts); url=races.iloc[opts.index(choice)]["URL"]
    if st.button("選手データを抽出",use_container_width=True):
        try:
            with st.spinner("レース本文を解析中…"):
                html,status=get_html(url); soup=BeautifulSoup(html,"html.parser"); text=soup.get_text(" ",strip=True); rows,excerpt=extract_riders(text); lines,line_source=extract_lines(text,rows)
            st.write(f"レースページ HTTP {status} ／ HTML {len(html):,}文字")
            st.write(f"抽出人数：{len(rows)}人（出走表の実人数との照合は必要です）")
            if rows:
                car_numbers = [r["車番"] for r in rows]
                missing = sorted(set(range(1, max(car_numbers, default=0) + 1)) - set(car_numbers))
                if missing:
                    st.warning(f"車番 {missing} の取得漏れがあります。予想に使う前に出走表と照合してください。")
                else:
                    st.success(f"{len(rows)}人分の選手データ候補を抽出しました。車番の連番を確認しました。")
                df=pd.DataFrame(rows); st.dataframe(df,use_container_width=True,hide_index=True)
                st.download_button("選手データをCSV保存",df.to_csv(index=False).encode("utf-8-sig"),f"keirin_riders_{date.today():%Y%m%d}.csv","text/csv",use_container_width=True)
            else: st.warning("本文は取得できましたが、選手行の形式が想定と一致しませんでした。下の抜粋を使って形式を合わせます。")
            st.subheader("並び・ライン予想")
            if lines:
                st.success(f"ライン候補を {len(lines)} 組抽出しました。サイト掲載の予想なので、実際の並びと照合してください。")
                for i, group in enumerate(lines, 1):
                    names = {int(r["車番"]): r["選手名"] for r in rows}
                    st.write(f"ライン{i}: " + " - ".join(f"{n} {names.get(n, '選手名不明')}" for n in group))
                st.caption("抽出元: " + line_source)
            else:
                st.warning("並び予想を自動認識できませんでした。選手データの取得とは別に、ライン表記の確認が必要です。")
                st.code(line_source)
            with st.expander("出走表テキストの抜粋"): st.code(excerpt)
            with st.expander("並び予想の診断用テキスト"): st.code(text[max(0, text.find("並び")-100):max(0, text.find("並び")-100)+700] if "並び" in text else text[:700])
        except Exception as e: st.error(f"{type(e).__name__}: {e}")
st.divider()
st.markdown("次はオッズ、バンク特性、当日の風を追加します。1日予算上限1,000円。自動投票は行いません。")
