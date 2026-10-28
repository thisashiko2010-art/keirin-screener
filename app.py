import re
from datetime import date
from urllib.parse import urljoin, urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title="競輪スクリーナー v23", page_icon="🚴", layout="wide")
st.title("🚴 競輪スクリーナー")
st.caption("v23：券種別オッズの通信先を絞り込む追加診断。候補オッズを確定値として扱わず、自動投票もしません。")
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

def diagnose_scripts(html):
    """Inspect script assets and embedded payloads to locate dynamic odds data."""
    soup = BeautifulSoup(html, "html.parser")
    script_rows = []
    keyword_rows = []
    keywords = ["odds", "Odds", "ODDS", "trifecta", "quinella", "wide", "2車単", "3連単", "ワイド", "betType", "bet_type", "raceId", "race_id", "__NEXT_DATA__", "application/json"]
    for idx, tag in enumerate(soup.find_all("script")):
        src = tag.get("src", "")
        typ = tag.get("type", "")
        body = tag.string or tag.get_text(" ", strip=False) or ""
        script_rows.append({"番号": idx, "type": typ, "src": urljoin("https://www.winticket.jp", src) if src else "(inline script)", "本文文字数": len(body)})
        if body.strip():
            for kw in keywords:
                pos = body.lower().find(kw.lower())
                if pos >= 0:
                    excerpt = re.sub(r"\s+", " ", body[max(0, pos-180):min(len(body), pos+420)]).strip()
                    keyword_rows.append({"script番号": idx, "キーワード": kw, "抜粋": excerpt})
    # Capture page-level preload JSON and resource hints as well.
    json_blocks = []
    for idx, tag in enumerate(soup.find_all("script", attrs={"type": re.compile("json", re.I)})):
        body = tag.string or tag.get_text(" ", strip=False) or ""
        if body.strip():
            json_blocks.append({"script番号": idx, "type": tag.get("type", ""), "文字数": len(body), "先頭": re.sub(r"\s+", " ", body[:1600]).strip()})
    return script_rows, keyword_rows[:100], json_blocks

def diagnose_external_js(html):
    """Prioritize odds-related bundles and collect more useful endpoint/state excerpts."""
    soup = BeautifulSoup(html, "html.parser")
    script_urls = []
    for tag in soup.find_all("script", src=True):
        u = urljoin("https://www.winticket.jp", tag.get("src", ""))
        if urlparse(u).netloc.lower() in ("www.winticket.jp", "winticket.jp") and u not in script_urls:
            script_urls.append(u)
    # Odds table implementation chunks are more informative than generic vendor bundles.
    priority_terms = ("chunk.92a6d36b954bd55e", "chunk.f5dd43f5e7ea94e5", "chunk.e5df37209196866a", "chunk.7189593c233b9f07", "bootstrap.")
    script_urls.sort(key=lambda u: (min([priority_terms.index(t) for t in priority_terms if t in u] or [len(priority_terms)]), u))
    keywords = ["/v1/", "/keirin/odds", "oddsForTable", "oddsId", "oddsSelectionByType", "raceId", "baseURL", "baseUrl", "axios.create", "fetch(", "method:\"GET\"", "application/json", "trifecta", "quinella_place", "bracket_quinella"]
    rows = []
    for u in script_urls[:80]:
        try:
            r = requests.get(u, headers=HEADERS, timeout=15)
            if r.status_code != 200 or not r.text:
                rows.append({"scriptURL":u,"HTTP":r.status_code,"文字数":len(r.text or ""),"キーワード":"取得失敗/空","抜粋":""})
                continue
            body = r.text
            local_rows = []
            for kw in keywords:
                start = 0; hits = 0
                while hits < 5:
                    pos = body.lower().find(kw.lower(), start)
                    if pos < 0: break
                    excerpt = re.sub(r"\s+", " ", body[max(0,pos-500):min(len(body),pos+1000)]).strip()
                    local_rows.append({"scriptURL":u,"HTTP":r.status_code,"文字数":len(body),"キーワード":kw,"抜粋":excerpt})
                    start = pos + len(kw); hits += 1
            # Avoid letting one 1MB vendor bundle crowd out route-specific chunks.
            rows.extend(local_rows[:35])
            if len(rows) >= 500: break
        except Exception as e:
            rows.append({"scriptURL":u,"HTTP":"ERR","文字数":0,"キーワード":type(e).__name__,"抜粋":str(e)[:250]})
    return rows[:500]

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

st.info("初期値は今日。WINTICKETの開催IDは複数日開催をまとめた日付範囲なので、開催日＝開催IDの先頭日付とは限りません。開催日を開催ID＋日目から計算します。オッズ候補は券種と組番数が一致するものだけ表示します。")
date_col,btn_col,link_col=st.columns([1.2,1,1])
with date_col: target_date=st.date_input("開催日",value=date.today())
with btn_col: load=st.button("開催一覧を更新",type="primary",use_container_width=True)
with link_col: st.link_button("WINTICKET出走表一覧",BASE_URL,use_container_width=True)

if "races_all" not in st.session_state:
    st.session_state["races_all"] = pd.DataFrame(columns=["競輪場","開催ID","開催日番号","レース","URL"])
if load:
    try:
        with st.spinner("一覧を取得中…"):
            html,status=get_html(BASE_URL); fresh=extract_races(html)
        old=st.session_state["races_all"]
        if isinstance(old,pd.DataFrame) and not old.empty:
            combined=pd.concat([old,fresh],ignore_index=True).drop_duplicates("URL",keep="last")
        else:
            combined=fresh
        st.session_state["races_all"]=combined.reset_index(drop=True)
        st.session_state["races_last_fetch_count"]=len(fresh)
        st.session_state["races_last_http"]=status
        if len(fresh) < len(old) and len(old)>0:
            st.warning(f"今回の再取得は {len(fresh)} 件で、前回保持分 {len(old)} 件より少ないため、既存URLを保持して統合しました。現在の重複除去後は {len(combined)} 件です。")
        else:
            st.success(f"一覧取得成功（HTTP {status}）。今回 {len(fresh)} 件、保持・統合後 {len(combined)} 件。")
    except Exception as e:
        st.error(f"開催一覧取得失敗：{type(e).__name__}: {e}")

races_all=st.session_state.get("races_all")
if isinstance(races_all,pd.DataFrame) and not races_all.empty:
    # WINTICKETの開催IDは YYYYMMDDYYYYMMDD 等の開催期間を表すことがあり、
    # URLの第2セグメントは「何日目」なので、開催日を開始日＋(日目-1)で計算する。
    def actual_race_date(row):
        try:
            event_id = str(row["開催ID"])
            start = pd.to_datetime(event_id[:8], format="%Y%m%d", errors="raise").date()
            day_number = int(row["開催日番号"])
            from datetime import timedelta
            return start + timedelta(days=max(0, day_number - 1))
        except Exception:
            return None
    races = races_all.copy()
    races["実開催日"] = races.apply(actual_race_date, axis=1)
    races = races[races["実開催日"] == target_date].copy()
    st.subheader(f"{target_date:%Y年%m月%d日} の開催")
    st.caption(f"保持中URL総数：{len(races_all)}件（開催日を開催期間＋日目から判定）")
    if races.empty:
        st.warning("指定日のURLが保持一覧にありません。開催一覧を更新してください。")
    else:
        st.success(f"指定日のレースURL：{len(races)}件")
        opts=[f'{r["競輪場"]} {r["レース"]}（{r["実開催日"]}） — {r["URL"]}' for _,r in races.iterrows()]
        previous=st.session_state.get("selected_race_option")
        default_index=opts.index(previous) if previous in opts else 0
        choice=st.selectbox("調査するレース",opts,index=default_index,key="race_choice")
        st.session_state["selected_race_option"]=choice
        selected=races.iloc[opts.index(choice)]
        race_url=selected["URL"]
        selected_bet_type=st.selectbox(
            "表示・照合したい券種",
            ["3連単", "3連複", "2車単", "2車複", "ワイド", "枠単", "枠複"],
            key="selected_bet_type",
            help="券種の選択は保持されます。ただし、現状の取得処理はページ全体から数値候補を拾う診断段階で、券種別のオッズに絞り込めているとは限りません。"
        )
        if st.button("選手・ライン・オッズ情報を取得",use_container_width=True):
            try:
                with st.spinner("出走表を解析中…"):
                    html,status=get_html(race_url)
                    soup=BeautifulSoup(html,"html.parser")
                    page_text=soup.get_text(" ",strip=True)
                    riders,diag=extract_riders(page_text)
                    lines,line_source=extract_lines(page_text,riders)
                odds_url=odds_url_from_racecard(race_url)
                odds_result={"url":odds_url,"status":None,"html_len":0,"bet_types":[],"rows":[],"text":"","error":None,"scripts":[],"script_keywords":[],"json_blocks":[],"external_js_diag":[]}
                try:
                    with st.spinner("オッズページを取得中…"):
                        odds_html,odds_status=get_html(odds_url)
                    bet_types,odds_rows,odds_text=extract_odds(odds_html)
                    script_rows, keyword_rows, json_blocks = diagnose_scripts(odds_html)
                    external_js_diag = diagnose_external_js(odds_html)
                    odds_result.update({"status":odds_status,"html_len":len(odds_html),"bet_types":bet_types,"rows":odds_rows,"text":odds_text,"scripts":script_rows,"script_keywords":keyword_rows,"json_blocks":json_blocks,"external_js_diag":external_js_diag})
                except Exception as oe:
                    odds_result["error"]=f"{type(oe).__name__}: {oe}"
                st.session_state["last_result"]={"race_url":race_url,"race_label":choice,"rider_status":status,"html_len":len(html),"riders":riders,"rider_diag":diag,"lines":lines,"line_source":line_source,"odds":odds_result,"fetched_at":pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")}
            except Exception as e:
                st.error(f"出走表処理失敗：{type(e).__name__}: {e}")

result=st.session_state.get("last_result")
if result:
    st.divider()
    st.caption(f"最後の取得：{result['fetched_at']} ／ {result['race_label']}")
    if result["race_url"] != st.session_state.get("selected_race_option", "") and False:
        pass
    st.subheader("選手データ")
    st.write(f"出走表HTTP {result['rider_status']}／HTML {result['html_len']:,}文字／抽出人数 {len(result['riders'])}人")
    if result["riders"]:
        df=pd.DataFrame(result["riders"])
        st.dataframe(df,use_container_width=True,hide_index=True)
        missing=sorted(set(range(1,max(r["車番"] for r in result["riders"])+1))-set(r["車番"] for r in result["riders"]))
        if missing: st.warning(f"車番 {missing} の取得漏れ候補。予想に使う前に照合してください。")
        st.download_button("選手データCSV保存",df.to_csv(index=False).encode("utf-8-sig"),f"keirin_riders_{date.today():%Y%m%d}.csv","text/csv",key="download_riders")
    else: st.warning("選手データを認識できませんでした。")
    st.subheader("並び・ライン予想")
    if result["lines"]:
        names={r["車番"]:r["選手名"] for r in result["riders"]}
        for i,g in enumerate(result["lines"],1): st.write(f"ライン{i}: "+" - ".join(f"{n} {names.get(n,'選手名不明')}" for n in g))
        st.caption("抽出元: "+result["line_source"])
    else: st.warning(result["line_source"])
    st.subheader("オッズ取得・券種照合")
    odds=result["odds"]
    st.write(f"推定オッズURL：{odds['url']}")
    st.link_button("オッズページをブラウザで確認",odds["url"],use_container_width=True)
    if odds["error"]:
        st.error(f"オッズURL取得に失敗：{odds['error']}")
    else:
        st.write(f"オッズURL HTTP {odds['status']}／HTML {odds['html_len']:,}文字")
        st.write("ページ内で見つかった券種見出し："+("、".join(odds["bet_types"]) if odds["bet_types"] else "未検出"))
        st.info(f"選択中：{selected_bet_type}。券種選択は画面に保持されますが、現在の候補データは券種別に確定できていません。下表は選択した券種の確定オッズではありません。")
        if odds["rows"]:
            # 券種に必要な車番数で候補を絞る。元ページの券種そのものを特定できていないため、
            # 組番の車番数が一致しない候補を混ぜて表示しない。
            needed = 3 if selected_bet_type in ("3連単", "3連複") else 2
            filtered_rows = [row for row in odds["rows"] if len(str(row.get("組番候補", "")).split("-")) == needed]
            if filtered_rows:
                odds_df=pd.DataFrame(filtered_rows)
                st.caption(f"表示形式：{selected_bet_type}向けの{needed}車番候補。券種・組番・数値の正確な対応は未検証です。")
                st.dataframe(odds_df,use_container_width=True,hide_index=True)
                st.download_button("オッズ候補CSV保存",odds_df.to_csv(index=False).encode("utf-8-sig"),f"keirin_odds_candidates_{date.today():%Y%m%d}.csv","text/csv",key="download_odds")
            else:
                st.warning(f"ページ本文から{selected_bet_type}に合う{needed}車番の候補を確認できませんでした。誤った券種の数値を表示しないため、候補を隠しています。")
        else:
            st.warning("HTTP取得はできましたが、組番・オッズ候補を認識できませんでした。")
        with st.expander("オッズページ本文の診断抜粋"):
            st.code(odds["text"][:5000] if odds["text"] else "本文テキストなし")
        with st.expander("券種切替の調査：JavaScript一覧"):
            st.caption("券種ごとのオッズが初期HTMLに含まれるか、JavaScript側で後から読み込まれるかを調べるための診断です。ここでは通信を実行したり投票したりしません。")
            if odds.get("scripts"):
                st.dataframe(pd.DataFrame(odds["scripts"]), use_container_width=True, hide_index=True)
                st.download_button("JavaScript一覧CSV保存", pd.DataFrame(odds["scripts"]).to_csv(index=False).encode("utf-8-sig"), f"winticket_scripts_{date.today():%Y%m%d}.csv", "text/csv", key="download_scripts")
            else:
                st.warning("scriptタグが見つかりませんでした。")
        with st.expander("券種切替の調査：スクリプト内キーワード"):
            if odds.get("script_keywords"):
                st.dataframe(pd.DataFrame(odds["script_keywords"]), use_container_width=True, hide_index=True)
                st.download_button("キーワード抜粋CSV保存", pd.DataFrame(odds["script_keywords"]).to_csv(index=False).encode("utf-8-sig"), f"winticket_script_keywords_{date.today():%Y%m%d}.csv", "text/csv", key="download_script_keywords")
            else:
                st.warning("オッズ関連キーワードを含むインラインスクリプトは見つかりませんでした。外部JavaScript一覧を確認してください。")
        with st.expander("券種切替の調査：外部JavaScript本体（v23・通信先重点調査）"):
            st.caption("オッズ表実装に近いJavaScriptを優先し、APIパス・oddsId・オッズ状態管理の前後文脈を広めに採取します。結果は診断用で、直接投票や購入は行いません。")
            js_diag = odds.get("external_js_diag", [])
            if js_diag:
                js_df = pd.DataFrame(js_diag)
                st.write(f"診断行数：{len(js_df)}")
                st.dataframe(js_df, use_container_width=True, hide_index=True)
                st.download_button("外部JavaScript診断CSV保存", js_df.to_csv(index=False).encode("utf-8-sig"), f"winticket_external_js_diag_{date.today():%Y%m%d}.csv", "text/csv", key="download_external_js_diag")
            else:
                st.info("診断結果がありません。オッズ取得を実行し直してください。")
        with st.expander("券種切替の調査：埋め込みJSON"):
            if odds.get("json_blocks"):
                st.dataframe(pd.DataFrame(odds["json_blocks"]), use_container_width=True, hide_index=True)
            else:
                st.info("JSON形式のscriptブロックは見つかりませんでした。")
    with st.expander("出走表の抽出診断"):
        st.code(result["rider_diag"])
st.divider()
st.markdown("注意：券種別のオッズ取得はまだ未完成です。組番と券種の対応を検証できるまで期待値計算には使用しません。1日予算上限1,000円、購入は手動です。")
