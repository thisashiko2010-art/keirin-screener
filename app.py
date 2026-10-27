import re
from datetime import date
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー v10", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("v10：選手表の見出しによる途中切れを避ける修正版。自動投票は行いません。")
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
    text=norm(page_text)
    pos=text.find("枠 車 選手名 AI 競走得点")
    if pos<0: pos=text.find("枠 車 選手名")
    if pos<0: return [], text[:3000]
    # ページによっては「並び予想」などの見出しが選手表の途中に現れるため、
    # 以前のように見出しで切り詰めない。選手表の開始位置以降を解析し、
    # 車番ごとに最初に見つかった候補だけを採用する。
    tail=text[pos:]
    # 都道府県名を固定候補にして、選手名と府県名の境界を曖昧にしない
    prefectures = ["北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉","千葉","東京","神奈川","新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重","滋賀","京都","大阪","兵庫","奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川","愛媛","高知","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄"]
    pref_pattern = "|".join(sorted(prefectures, key=len, reverse=True))
    pat = re.compile(
        rf"(?P<w>[1-9])\s+(?P<c>[1-9])\s+"
        rf"(?P<n>[一-龥々〆ヵヶぁ-ゖァ-ヺー・]{{2,12}}?)\s+"
        rf"(?P<p>{pref_pattern})\s+(?P<cl>[ASL]\d)\s+"
        rf"(?P<age>\d{{2}})歳\s+(?P<reg>\d{{2,3}})期\s+"
        rf"(?:(?:本命|対抗|単穴|連下)\s+)?(?P<score>\d{{2,3}}\.\d{{2}})"
    )
    rows=[]; seen=set()
    for m in pat.finditer(tail):
        d=m.groupdict(); car=int(d["c"])
        if car in seen: continue
        seen.add(car)
        rows.append({"枠番":int(d["w"]),"車番":car,"選手名":d["n"],"府県":d["p"],"級班":d["cl"],"年齢":int(d["age"]),"期別":int(d["reg"]),"競走得点":float(d["score"])})
        # 通常の競輪は最大9車。1～9番車が揃ったら後続セクションを読まない。
        if seen == set(range(1, 10)):
            break
    return sorted(rows,key=lambda x:x["車番"]),tail[:4500]

st.info("前版で7番車が抜けたため、選手表の後ろを見出しで切る処理を外しました。車番ごとに最初の候補を採用します。")
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
                html,status=get_html(url); soup=BeautifulSoup(html,"html.parser"); text=soup.get_text(" ",strip=True); rows,excerpt=extract_riders(text)
            st.write(f"レースページ HTTP {status} ／ HTML {len(html):,}文字")
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
            with st.expander("出走表テキストの抜粋"): st.code(excerpt)
        except Exception as e: st.error(f"{type(e).__name__}: {e}")
st.divider()
st.markdown("次は並び・ライン、オッズ、バンク特性、当日の風を追加します。1日予算上限1,000円。自動投票は行いません。")
