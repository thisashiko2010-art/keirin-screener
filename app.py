import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
from io import StringIO

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")

st.title("🚴 競輪スクリーナー v0.2")
st.caption("個人利用向けプロトタイプ｜自動投票なし｜予想補助ツール")

st.warning(
    "この版は『開催日程の取得テスト＋CSV取込＋評価の試作』です。"
    "出走表・ライン・オッズの完全自動取得は未実装です。表示される評価は実績検証前の暫定ロジックで、的中や利益を保証しません。"
)

SCHEDULE_URL = "https://www.keirin.jp/pc/raceschedule"
SCHEDULE_MOBILE_URL = "https://www.keirin.jp/sp/raceschedule"

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_schedule():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; personal-keirin-screening/0.2)",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    }
    errors = []
    for url in (SCHEDULE_URL, SCHEDULE_MOBILE_URL):
        try:
            r = requests.get(url, headers=headers, timeout=12)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text("\n", strip=True)
            # A lightweight availability check; schedule page content can change.
            if "開催日程" in text and ("北日本" in text or "函館" in text):
                links = []
                for a in soup.find_all("a", href=True):
                    label = " ".join(a.get_text(" ", strip=True).split())
                    href = a["href"]
                    if label and any(x in label for x in [
                        "函館","青森","いわき平","弥彦","前橋","取手","宇都宮","大宮",
                        "西武園","京王閣","立川","松戸","千葉","川崎","平塚","小田原",
                        "伊東","静岡","名古屋","岐阜","大垣","豊橋","富山","松阪",
                        "四日市","福井","奈良","向日町","和歌山","岸和田","玉野",
                        "広島","防府","高松","小松島","高知","松山","小倉","久留米",
                        "武雄","佐世保","別府","熊本"
                    ]):
                        links.append({"表示名": label, "リンク": requests.compat.urljoin(url, href)})
                unique = {}
                for x in links:
                    unique[(x["表示名"], x["リンク"])] = x
                return {
                    "ok": True,
                    "url": url,
                    "title": soup.title.get_text(" ", strip=True) if soup.title else "開催日程",
                    "text": text[:12000],
                    "links": list(unique.values()),
                    "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            errors.append(f"{url}: ページ構造を認識できません")
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    return {"ok": False, "errors": errors}

def make_template(kind):
    templates = {
        "races": pd.DataFrame(columns=[
            "date","venue","race_no","start_time","grade","race_title",
            "line_count","largest_line_size","top_score","second_score",
            "wind_speed_mps","wind_direction","straight_m","bank_lap_m","banking_deg"
        ]),
        "entrants": pd.DataFrame(columns=[
            "date","venue","race_no","car_no","rider_name","score",
            "recent_form_0_100","escape_count","back_count","line_id","line_position","comment"
        ]),
        "odds": pd.DataFrame(columns=[
            "date","venue","race_no","bet_type","combination","odds"
        ]),
        "results": pd.DataFrame(columns=[
            "date","venue","race_no","bet_type","combination","stake_yen","hit","payout_yen"
        ]),
    }
    return templates[kind]

def read_csv(upload):
    if upload is None:
        return None
    try:
        return pd.read_csv(upload)
    except Exception:
        try:
            upload.seek(0)
            return pd.read_csv(upload, encoding="cp932")
        except Exception as e:
            st.error(f"CSVを読み込めませんでした: {e}")
            return None

def num(v, default=0.0):
    try:
        if pd.isna(v) or str(v).strip() == "":
            return default
        return float(v)
    except Exception:
        return default

def solidity(row):
    # Transparent provisional heuristic, not a trained model.
    top = num(row.get("top_score"))
    second = num(row.get("second_score"))
    gap = max(0, top - second)
    line_count = max(1, num(row.get("line_count"), 3))
    largest = max(1, num(row.get("largest_line_size"), 2))
    wind = max(0, num(row.get("wind_speed_mps")))
    score = 45 + min(gap * 2.5, 18) + min((largest / line_count) * 15, 15) - min(wind * 1.8, 12)
    if num(row.get("straight_m")) >= 60:
        score += 2
    if num(row.get("bank_lap_m")) >= 400:
        score += 1
    return max(0, min(100, round(score)))

def recommend_candidates(entrants, odds, budget):
    if entrants is None or odds is None or entrants.empty or odds.empty:
        return pd.DataFrame()
    output = []
    key_cols = ["date", "venue", "race_no"]
    for _, o in odds.iterrows():
        mask = pd.Series(True, index=entrants.index)
        for c in key_cols:
            if c in entrants.columns and c in o.index:
                mask &= entrants[c].astype(str) == str(o[c])
        e = entrants[mask].copy()
        if e.empty:
            continue
        e["score"] = pd.to_numeric(e.get("score", 0), errors="coerce").fillna(0)
        if e["score"].nunique() < 2:
            continue
        # Softmax-like normalized scores are only a rough ranking proxy.
        scores = e.set_index(e["car_no"].astype(str))["score"].to_dict()
        combo = str(o.get("combination", "")).replace(" ", "")
        nums = [x for x in combo.replace("-", ",").replace("=", ",").split(",") if x.isdigit()]
        if not nums:
            continue
        odds_val = num(o.get("odds"), 0)
        if odds_val <= 1:
            continue
        # Approximate probability from score ranks, deliberately conservative.
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ranks = {car: i+1 for i, (car, _) in enumerate(ranked)}
        # Probability proxy is NOT calibrated; display as a candidate signal only.
        rank_sum = sum(ranks.get(n, len(ranks)+1) for n in nums)
        prob_proxy = max(0.005, min(0.55, 0.36 / (rank_sum ** 0.85)))
        ev_proxy = prob_proxy * odds_val
        output.append({
            "date": o.get("date", ""),
            "venue": o.get("venue", ""),
            "race_no": o.get("race_no", ""),
            "券種": o.get("bet_type", ""),
            "組み合わせ": combo,
            "オッズ": odds_val,
            "順位ベース参考値": round(prob_proxy, 3),
            "参考値×オッズ": round(ev_proxy, 3),
            "注意": "未校正の参考値。購入判断に直結させない"
        })
    if not output:
        return pd.DataFrame()
    return pd.DataFrame(output).sort_values("参考値×オッズ", ascending=False).head(100)

tab1, tab2, tab3, tab4 = st.tabs(["開催日程の取得テスト", "データ取込", "レース評価・買い目候補", "結果・回収率"])

with tab1:
    st.subheader("公式開催日程ページへの接続テスト")
    st.write("接続ボタンを押すと、KEIRIN.JPの開催日程ページを取得できるか確認します。")
    if st.button("開催日程ページを取得", type="primary"):
        with st.spinner("公式ページに接続中…"):
            result = fetch_schedule()
        if result["ok"]:
            st.success(f"ページ取得成功：{result['title']}（{result['retrieved_at']}）")
            st.caption(f"取得元: {result['url']}")
            st.write(f"競輪場らしきリンク候補: {len(result['links'])} 件。これは開催中の場を確定する数ではありません。")
            if result["links"]:
                st.dataframe(pd.DataFrame(result["links"]), use_container_width=True, hide_index=True)
            with st.expander("取得テキスト（確認用）"):
                st.text(result["text"])
            st.info("現状は接続確認とページ内容の調査用です。日付ごとの開催抽出・レースカードへのリンク解析は次の実装工程です。")
        else:
            st.error("この実行環境からページを取得できませんでした。アプリの公開環境や接続制限の可能性があります。")
            st.write(result.get("errors", []))
    st.markdown(f"公式開催日程: [{SCHEDULE_URL}]({SCHEDULE_URL})")

with tab2:
    st.subheader("CSVデータの取込")
    st.write("現段階では、出走表・ライン・オッズはCSVで補う方式です。")
    c1, c2 = st.columns(2)
    with c1:
        races_file = st.file_uploader("レース基本情報 CSV", type=["csv"], key="races")
        entrants_file = st.file_uploader("出走選手 CSV", type=["csv"], key="entrants")
    with c2:
        odds_file = st.file_uploader("オッズ CSV", type=["csv"], key="odds")
        results_file = st.file_uploader("結果 CSV", type=["csv"], key="results")
    races_df = read_csv(races_file)
    entrants_df = read_csv(entrants_file)
    odds_df = read_csv(odds_file)
    results_df = read_csv(results_file)

    for label, df in [("レース基本情報", races_df), ("出走選手", entrants_df), ("オッズ", odds_df), ("結果", results_df)]:
        if df is not None:
            st.write(f"**{label}**：{len(df)} 行")
            st.dataframe(df.head(10), use_container_width=True, hide_index=True)

    st.markdown("#### CSVテンプレート")
    cols = st.columns(4)
    for col, kind, label in zip(cols, ["races","entrants","odds","results"], ["レース基本情報","出走選手","オッズ","結果"]):
        col.download_button(f"{label}テンプレート", make_template(kind).to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"{kind}_template.csv", mime="text/csv")

with tab3:
    st.subheader("レース評価・買い目候補")
    st.caption("CSVを読み込んだ場合に表示します。順位ベース参考値は統計モデルで校正されておらず、期待値の断定には使えません。")
    budget = st.number_input("1日の購入予算（円）", min_value=0, max_value=10000, value=1000, step=100)
    if races_df is not None and not races_df.empty:
        df = races_df.copy()
        if "top_score" in df.columns and "second_score" in df.columns:
            df["堅さ参考スコア"] = df.apply(solidity, axis=1)
            df["判定"] = df["堅さ参考スコア"].apply(lambda x: "候補" if x >= 65 else ("要検討" if x >= 50 else "見送り寄り"))
            st.dataframe(df.sort_values("堅さ参考スコア", ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("レースCSVに top_score と second_score の列が必要です。")
    else:
        st.info("まずレース基本情報CSVを読み込んでください。")

    if entrants_df is not None and odds_df is not None:
        cand = recommend_candidates(entrants_df, odds_df, budget)
        if not cand.empty:
            st.markdown("#### オッズ付き買い目候補（試作）")
            st.dataframe(cand, use_container_width=True, hide_index=True)
            st.warning("この候補表は未校正の順位ヒューリスティックです。実際の購入推奨として使う前に、確率モデルの学習・バックテストが必要です。")
        else:
            st.info("組み合わせ候補を作れません。車番・選手得点・オッズCSVの列と値を確認してください。")

with tab4:
    st.subheader("結果・回収率")
    if results_df is not None and not results_df.empty:
        needed = {"stake_yen", "payout_yen"}
        if needed.issubset(results_df.columns):
            stake = pd.to_numeric(results_df["stake_yen"], errors="coerce").fillna(0).sum()
            payout = pd.to_numeric(results_df["payout_yen"], errors="coerce").fillna(0).sum()
            roi = payout / stake * 100 if stake else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("購入額", f"¥{stake:,.0f}")
            c2.metric("払戻額", f"¥{payout:,.0f}")
            c3.metric("回収率", f"{roi:.1f}%")
            st.dataframe(results_df, use_container_width=True, hide_index=True)
        else:
            st.error("結果CSVには stake_yen と payout_yen が必要です。")
    else:
        st.info("結果CSVを読み込むと、購入額・払戻額・回収率を計算します。")

st.divider()
st.caption("データ出典・取得時刻・欠損を残すこと。サイトの利用条件に従い、過度なアクセスを行わないこと。")
