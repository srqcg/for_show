"""把 for_show/data/stock_picks.csv 转为 for_show/data/data.js (script 引入, 兼容 file:// 与 GitHub Pages)。

用法: 用 refresh_26.py 更新选股 CSV 后, 复制为 data/stock_picks.csv, 再运行本脚本。
"""
import json
from pathlib import Path

import pandas as pd

SHOW = Path(__file__).resolve().parent.parent  # for_show/
SRC = SHOW / 'data' / 'stock_picks.csv'
DST = SHOW / 'data' / 'data.js'

if __name__ == '__main__':
    df = pd.read_csv(SRC, dtype={'股票代码': str})
    df['股票代码'] = df['股票代码'].str.strip().str.zfill(6)
    rows = df.where(df.notna(), None).to_dict(orient='records')
    payload = json.dumps(rows, ensure_ascii=False, indent=2)
    DST.write_text(f'window.STOCK_DATA = {payload};\n', encoding='utf-8')
    print(f'{len(rows)} 条 -> {DST}')
