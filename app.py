import re
from datetime import date
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー v17", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("v17：当日・日付指定、選手7人・ライン抽出、券種選択付きオッズ診断。自動投票は行いません。")
BASE_URL = "https://www.winticket.jp/keirin/racecard"
HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","Accept-Language":"ja,en-US;q=0.9,en;q=0.8"}
VENUES = {"hakodate":"函館","aomori":"青森","yahiko":"弥彦","maebashi":"前橋","toride":"取手","utsunomiya":"宇都宮","omiya":"大宮","seibuen":"西武園","keiokaku":"京王閣","tachikawa":"立川","matsudo":"松戸","chiba":"千葉","kawasaki":"川崎","hiratsuka":"平塚","odawara":"小田原","ito":"伊東","shizuoka":"静岡","nagoya":"名古屋","gifu":"岐阜","ogaki":"大垣","toyohashi":"豊橋","toyama":"富山","matsusaka":"松阪","yokkaichi":"四日市","fukui":"福井","nara":"奈良","mukomachi":"向日町","wakayama":"和歌山","kishiwada":"岸和田","tamano":"玉野","hiroshima":"広島","hofu":"防府","takamatsu":"高松","komatsushima":"小松島","kochi":"高知","matsuyama":"松山","kokura":"小倉","kurume":"久留米","takeo":"武雄","sasebo":"佐世保","beppu":"別府","kumamoto":"熊本"}

def norm(s): return re.sub(r"\s+", " ", str(s)).strip()
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
    prefectures=["北海道","青森","岩手","宮城","秋田","山形","福島","茨城","栃木","群馬","埼玉","千葉","東京","神奈川","新潟","富山","石川","福井","山梨","長野","岐阜","静岡","愛知","三重","滋賀","京都","大阪","兵庫","奈良","和歌山","鳥取","島根","岡山","広島","山口","徳島","香川","愛媛","高知","福岡","佐賀","長崎","熊本","大分","宮崎","鹿児島","沖縄"]
    pref_pattern="|".join(sorted(prefectures,key=len,reverse=True)); name_chars=r"[一-龥々〆ヵヶぁ-ゖァ-ヺー・]"
    tail=rf"(?P<n>{name_chars}{{2,12}}?)\s+(?P<p>{pref_pattern})\s+(?P<cl>[ASL]\d)\s+(?P<age>\d{{2}})歳\s+(?P<reg>\d{{2,3}})期(?:\s+(?:本命|対抗|単穴|連下))?\s+(?P<score>\d{{2,3}}\.\d{{2}})"
    patterns=[re.compile(rf"(?P<w>[1-6])\s+(?P<c>[1-6])\s+"+tail),re.compile(rf"(?P<w>[7-9])\s+(?P<c>[7-9])\s+"+tail),re.compile(rf"(?P<w>[7-9])\s+"+tail)]
    found=[]
    for pat in patterns:
        for m in pat.finditer(text):
            d=m.groupdict()
            if not d.get("c"): d["c"]=d["w"]
            found.append((m.start(),d,m.group(0)))
    found.sort(key=lambda x:x[0]); rows=[]; seen=set(); matches=[]
    for _,d,matched in found:
        car=int(d["c"]); matches.append({"車番":car,"選手名候補":d["n"],"府県候補":d["p"],"一致文字列":matched})
        if car in seen: continue
        seen.add(car); rows.append({"枠番":int(d["w"]),"車番":car,"選手名":d["n"],"府県":d["p"],"級班":d["cl"],"年齢":int(d["age"]),"期別":int(d["reg"]),"競走得点":float(d["score"])})
    rows.sort(key=lambda x:x["車番"])
    diagnostic="抽出候補一覧:\n"+"\n".join(f"車番{m['車番']}: {m['選手名候補']} / {m['府県候補']} — {m['一致文字列']}" for m in matches)
    return rows,diagnostic

def extract_lines(page_text,riders):
    text=norm(page_text); rider_cars={int(r["車番"]) for r in riders}; candidates=[]
    for marker in ("並び予想","並び","ライン"):
        pos=text.find(marker)
        if pos>=0: candidates.append(text[pos:pos+500])
    candidates.append(text)
    for area in candidates:
        if re.search(r"区切り|ライン",area):
            m=re.search(r"((?:[1-9](?:\s+|[-ー－])?){1,9}(?:\s*(?:区切り|ライン)\s*(?:[1-9](?:\s+|[-ー－])?){1,9}){1,8})",area)
            if m:
                raw=m.group(1); groups=[]
                for part in re.split(r"区切り|ライン",raw):
                    nums=[int(x) for x in re.findall(r"[1-9]",part)]; nums=[n for n in nums if n in rider_cars]
                    if nums and nums not in groups: groups.append(nums)
                flat=[n for g in groups for n in g]
                if groups and len(flat)==len(set(flat)) and set(flat).issubset(rider_cars): return groups,raw
        m=re.search(r"(?:←\s*)?((?:[1-9]\s*(?:先行|追込|押え先|自在|追上|マーク|捲り|追走)?\s*){2,9})",area)
        if m:
            nums=[int(x) for x in re.findall(r"([1-9])\s*(?:先行|追込|押え先|自在|追上|マーク|捲り|追走)?",m.group(1))]; nums=[n for n in nums if n in rider_cars]
            if len(nums)>=2 and len(nums)==len(set(nums)): return [nums],m.group(0)
    return [],"本文から明確なライン区切りを認識できませんでした。"

def odds_url_from_racecard(url):
    # WINTICKETの同一レースパスの odds 版を試す。実際のURL形式は取得時に検証する。
    return url.replace("/racecard/","/odds/")

def extract_odds(html):
    soup=BeautifulSoup(html,"html.parser")
    text=norm(soup.get_text(" ",strip=True))
    # 初期診断用。券種見出しと、車番組み合わせ＋小数オッズが同一テキストにある場合だけ候補化。
    bet_types=["ワイド","2車複","2車単","3連複","3連単","枠複","枠単"]
    present=[b for b in bet_types if b in text]
    candidates=[]
    # 汎用的な組番表記: 1-2 12.3 / 1=2 12.3 等。ページ本文の無関係な数値を誤採用しないため、候補としてのみ表示。
    for m in re.finditer(r"(?<!\d)([1-9])\s*[-=＞>]\s*([1-9])(?:\s*[-=＞>]\s*([1-9]))?\s+([1-9]\d{0,3}(?:\.\d)?)",text):
        combo="-".join(x for x in m.groups()[:3] if x)
        odds=float(m.group(4))
        if odds>0: candidates.append({"組番候補":combo,"オッズ候補":odds,"一致テキスト":m.group(0)})
    # 重複を除くが、券種の確定は行わない。
    dedup=[]; seen=set()
    for row in candidates:
        key=(row["組番候補"],row["オッズ候補"])
        if key not in seen: seen.add(key); dedup.append(row)
    return present,dedup,text

st.info("初期値は今日。開催一覧から対象日を選び、出走表・ラインを取得できます。オッズはページ構造を検証中で、確実に読めた値だけを候補表示します。")
date_col,btn_col,link_col=st.columns([1.2,1,1])
with date_col: target_date=st.date_input("開催日",value=date.today())
with btn_col: load=st.button("開催一覧を更新",type="primary",use_container_width=True)
with link_col: st.link_button("WINTICKET出走表一覧",BASE_URL,use_container_width=True)
if load:
    try:
        with st.spinner("一覧を取得中…"):
            html,status=get_html(BASE_URL); races=extract_races(html)
        st.session_state["races_all"]=races
        st.success(f"一覧取得成功（HTTP {status}）。サイトからURL {len(races)} 件を検出。")
    except Exception as e: st.error(f"開催一覧取得失敗：{type(e).__name__}: {e}")
races_all=st.session_state.get("races_all")
if isinstance(races_all,pd.DataFrame) and not races_all.empty:
    day_key=target_date.strftime("%Y%m%d"); races=races_all[races_all["開催ID"].astype(str).str.startswith(day_key)].copy()
    st.subheader(f"{target_date:%Y年%m月%d日} の開催")
    if races.empty: st.warning("指定日のURLが一覧にありません。日付を変更するか、開催一覧を更新してください。")
    else:
        st.success(f"指定日のレースURL：{len(races)}件")
        opts=[f'{r["競輪場"]} {r["レース"]} — {r["URL"]}' for _,r in races.iterrows()]
        choice=st.selectbox("調査するレース",opts); selected=races.iloc[opts.index(choice)]; race_url=selected["URL"]
        if st.button("選手・ライン・オッズ情報を取得",use_container_width=True):
            try:
                with st.spinner("出走表を解析中…"):
                    html,status=get_html(race_url); soup=BeautifulSoup(html,"html.parser"); page_text=soup.get_text(" ",strip=True); riders,diag=extract_riders(page_text); lines,line_source=extract_lines(page_text,riders)
                st.subheader("選手データ")
                st.write(f"出走表HTTP {status}／HTML {len(html):,}文字／抽出人数 {len(riders)}人")
                if riders:
                    df=pd.DataFrame(riders); st.dataframe(df,use_container_width=True,hide_index=True)
                    missing=sorted(set(range(1,max(r["車番"] for r in riders)+1))-set(r["車番"] for r in riders))
                    if missing: st.warning(f"車番 {missing} の取得漏れ候補。予想に使う前に照合してください。")
                    st.download_button("選手データCSV保存",df.to_csv(index=False).encode("utf-8-sig"),f"keirin_riders_{date.today():%Y%m%d}.csv","text/csv")
                else: st.warning("選手データを認識できませんでした。")
                st.subheader("並び・ライン予想")
                if lines:
                    names={r["車番"]:r["選手名"] for r in riders}
                    for i,g in enumerate(lines,1): st.write(f"ライン{i}: "+" - ".join(f"{n} {names.get(n,'選手名不明')}" for n in g))
                    st.caption("抽出元: "+line_source)
                else: st.warning(line_source)
                st.subheader("オッズ取得・券種選択")
                selected_bet_type = st.selectbox(
                    "確認したい券種",
                    ["3連単", "3連複", "2車単", "2車複", "ワイド", "枠単", "枠複"],
                    key="selected_bet_type",
                    help="ここで選ぶのは表示・整理用の指定です。取得元ページの券種見出しと一致することを確認するまでは、確定オッズとして扱いません。"
                )
                st.info(f"選択中の券種：{selected_bet_type}。取得した数値がこの券種のものか、ページ上の券種見出しと必ず照合してください。")
                odds_url=odds_url_from_racecard(race_url)
                st.write("推定した同一レースのオッズURL：")
                st.code(odds_url)
                st.link_button("オッズページをブラウザで確認",odds_url,use_container_width=True)
                try:
                    with st.spinner("オッズページを取得中…"):
                        odds_html,odds_status=get_html(odds_url)
                    st.write(f"オッズURL HTTP {odds_status}／HTML {len(odds_html):,}文字")
                    bet_types,odds_rows,odds_text=extract_odds(odds_html)
                    st.write("ページ内で見つかった券種見出し："+("、".join(bet_types) if bet_types else "未検出"))
                    if odds_rows:
                        odds_df = pd.DataFrame(odds_rows)
                        odds_df.insert(0, "選択券種（未検証）", selected_bet_type)
                        st.warning("以下は組番・数値の機械的な候補です。選択券種は手動ラベルであり、サイト上の券種を自動判定したものではありません。券種の見出しと組番の意味を照合するまで、予想や期待値計算には使わないでください。")
                        st.dataframe(odds_df,use_container_width=True,hide_index=True)
                        st.download_button("オッズ候補CSV保存",odds_df.to_csv(index=False).encode("utf-8-sig"),f"keirin_odds_candidates_{date.today():%Y%m%d}.csv","text/csv")
                    else:
                        st.warning("HTTP取得はできましたが、組番・オッズ候補を認識できませんでした。券種ごとの画面構造を診断します。")
                    with st.expander("オッズページ本文の診断抜粋"):
                        st.code(odds_text[:5000] if odds_text else "本文テキストなし")
                except Exception as e:
                    st.error(f"オッズURL取得に失敗：{type(e).__name__}: {e}")
                    st.info("オッズページのURL形式が違うか、サイト側が直接取得を制限している可能性があります。下のリンクからブラウザで開けるか確認してください。")
                with st.expander("出走表の抽出診断"): st.code(diag)
            except Exception as e: st.error(f"出走表処理失敗：{type(e).__name__}: {e}")
st.divider()
st.markdown("注意：オッズの抽出はまだ実証段階です。券種と組番を正しく識別できるまで期待値計算には使用しません。1日予算上限1,000円、購入は手動です。")
