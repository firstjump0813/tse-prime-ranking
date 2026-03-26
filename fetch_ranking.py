"""
東京証券取引所 プライム市場 値下がり率ランキング取得スクリプト
Yahoo!ファイナンスから全市場データを取得し、東証プライム(東証PRM)に絞って
ranking_yyyymmdd.csv として保存する
"""

import requests
import pandas as pd
from datetime import datetime
import time
import sys
import os
import json
import re

SAVE_DIR = os.path.dirname(os.path.abspath(__file__))  # スクリプトと同じディレクトリに保存
BASE_URL = "https://finance.yahoo.co.jp/stocks/ranking/down"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
PRIME_MARKET_NAME = "東証PRM"


def fetch_page(page: int) -> tuple[list[dict], bool]:
    """
    指定ページの値下がり率ランキングを取得する
    戻り値: (行データリスト, 次ページがあるか)
    """
    params = {"market": "all", "term": "daily", "page": page}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] ページ {page} の取得に失敗しました: {e}", file=sys.stderr)
        return [], False

    match = re.search(
        r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*(?:</script>|YAHOO)',
        resp.text, re.DOTALL
    )
    if not match:
        match = re.search(r'__PRELOADED_STATE__\s*=\s*(\{.*\})', resp.text, re.DOTALL)
    if not match:
        print(f"[WARN] ページ {page}: データが見つかりません", file=sys.stderr)
        return [], False

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"[ERROR] ページ {page}: JSON解析失敗: {e}", file=sys.stderr)
        return [], False

    main_ranking = data.get("mainRankingList", {})
    ranking_list = main_ranking.get("results", [])
    paging = main_ranking.get("paging", {})
    has_next = paging.get("hasNext", False)

    rows = []
    for item in ranking_list:
        # プライム市場のみ抽出
        if item.get("marketName", "") != PRIME_MARKET_NAME:
            continue

        # 騰落率・前日比は rankingResult.changePriceRate の下にある
        ranking_result = item.get("rankingResult", {}) or {}
        cpr = ranking_result.get("changePriceRate", {}) or {}

        row = {
            "順位": item.get("rank", ""),
            "コード": item.get("stockCode", ""),
            "銘柄名": item.get("stockName", ""),
            "市場": item.get("marketName", ""),
            "現在値": item.get("savePrice", ""),
            "前日比": cpr.get("changePrice", ""),
            "騰落率(%)": cpr.get("changePriceRate", ""),
            "出来高": cpr.get("volume", ""),
            "時刻": item.get("date", ""),
        }
        rows.append(row)

    return rows, has_next


def fetch_all_rankings() -> pd.DataFrame:
    """全ページを取得してプライム市場の値下がり率ランキングをDataFrameにまとめる"""
    all_rows = []
    page = 1
    while True:
        print(f"  ページ {page} を取得中...", flush=True)
        rows, has_next = fetch_page(page)

        if rows:
            all_rows.extend(rows)
            print(f"  → プライム: {len(rows)} 件（累計: {len(all_rows)} 件）", flush=True)

        if not has_next:
            print("  全ページ取得完了。")
            break
        page += 1
        time.sleep(1.5)

    return pd.DataFrame(all_rows) if all_rows else pd.DataFrame()


def main():
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    output_path = os.path.join(SAVE_DIR, f"ranking_{date_str}.csv")

    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 東証プライム 値下がり率ランキング取得開始")
    print(f"保存先: {output_path}", flush=True)

    df = fetch_all_rankings()

    if df.empty:
        print("[ERROR] データを取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    # 騰落率で昇順に並び替え（最も下がっているものが上位）
    df["騰落率(%)"] = pd.to_numeric(df["騰落率(%)"], errors="coerce")
    df = df.sort_values("騰落率(%)", ascending=True).reset_index(drop=True)
    df.index += 1
    df.index.name = "順位(プライム内)"

    df.to_csv(output_path, encoding="utf-8-sig")
    print(f"[完了] プライム市場 {len(df)} 件を保存しました → {output_path}")


if __name__ == "__main__":
    main()
