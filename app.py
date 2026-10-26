import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
from io import StringIO

st.set_page_config(page_title="競輪スクリーナー", page_icon="🚴", layout="wide")

st.title("🚴 競輪スクリーナー")
st.caption("個人利用向け試作版 — まず公式開催日程の取得を試し、取得できない情報は推測しません。")

TODAY = date.today()
SCHEDULE_URL = "https://www.keirin.jp/pc/raceschedule"
SP_SCHEDULE_URL = "https://www.keirin.jp/sp/raceschedule"

st.info(
    "この版では、KEIRIN.JPの公開開催日程ページへの接続を試します。"
    "出走表・ライン・オッズ・当日の風をすべて自動取得する機能は、まだ完成していません。"
    "取得できた情報と、未取得の情報を分けて表示します。"
)

st.subheader("1. 今日の開催日程を取得")
st.write(f"対象日：**{TODAY.strftime('%Y年%m月%d日')}**")

col1, col2 = st.columns(2)
with col1:
    fetch_button = st.button("公式開催日程への接続を試す", type="primary", use_container_width=True)
with col2:
    st.link_button("KEIRIN.JPの開催日程を開く", SCHEDULE_URL, use_container_width=True)

if fetch_button:
    with st.spinner("KEIRIN.JPに接続しています…"):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; personal-keirin-screener/0.3)"
            }
            response = requests.get(SP_SCHEDULE_URL, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            soup = BeautifulSoup(response.text, "html.parser")
            page_text = " ".join(soup.stripped_strings)

            st.success(f"公式ページへの接続に成功しました（HTTP {response.status_code}）。")
            st.caption("これはページに接続できたことを示すもので、今日の全開催を正しく抽出できた保証ではありません。")

            # Display a small excerpt for diagnostics rather than pretending to have parsed all races.
            keywords = ["開催日程", "開催がありません", "北日本", "関東", "南関東"]
            found = [word for word in keywords if word in page_text]
            if found:
                st.write("ページ内で確認できた見出し・語句：", "、".join(found))

            # Try to extract tables, but clearly label the result as raw source tables.
            try:
                tables = pd.read_html(StringIO(response.text))
                if tables:
                    st.write(f"ページ内の表を {len(tables)} 個検出しました。内容は公式ページの表をそのまま表示したものです。")
                    for i, table in enumerate(tables[:8], start=1):
                        with st.expander(f"取得した表 {i}", expanded=(i == 1)):
                            st.dataframe(table, use_container_width=True, hide_index=True)
                else:
                    st.warning("ページ内の表を自動抽出できませんでした。上の公式リンクから開催日程を確認してください。")
            except Exception:
                st.warning("ページのHTMLから表を自動抽出できませんでした。上の公式リンクから開催日程を確認してください。")

            st.markdown(f"[公式開催日程を別画面で確認する]({SCHEDULE_URL})")
        except Exception as exc:
            st.error("KEIRIN.JPへの自動接続に失敗しました。サイト側の仕様・接続制限・一時的な通信障害などが考えられます。")
            st.caption(f"診断情報：{type(exc).__name__}: {exc}")
            st.link_button("公式開催日程を開く", SCHEDULE_URL)
            st.write("自動取得に失敗したため、開催情報を推測して表示することはしません。")

st.divider()
st.subheader("2. 次の開発段階")
st.markdown(
    """
    - **この版で試すこと：** 公式開催日程ページへの接続と、ページ内の表を抽出できるかの確認
    - **まだ未実装：** 当日の全開催・全レースの正確な抽出、出走表、ライン、全券種オッズ、風向・風速の自動取得
    - **まだ未実装：** 校正済みの勝率・期待値モデル、バックテスト、結果の自動照合
    - **自動投票：** 行いません
    """
)

st.subheader("3. CSVを使った旧方式（予備）")
st.caption("自動取得の検証中に、必要な場合だけ使う予備機能です。CSVを手作業で用意することを前提にしたくないため、ここは折りたたんであります。")

with st.expander("CSVを読み込む（必要な場合のみ）"):
    uploaded = st.file_uploader(
        "確認用CSVを選択（races / entrants / odds / results）",
        type=["csv"],
        accept_multiple_files=True
    )
    if uploaded:
        for file in uploaded:
            st.markdown(f"**{file.name}**")
            try:
                df = pd.read_csv(file)
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"読み込みに失敗しました: {exc}")

st.divider()
st.caption(
    "注意：取得元サイトの利用条件に従ってください。表示されたデータだけで購入判断をせず、"
    "オッズ・出走表・ライン・バンク特性・当日の風を確認してください。予測や利益を保証するものではありません。"
)
