"""检查: 26 只基准股的粗筛 rough_yield 分布, 确定不误杀的阈值。"""
import os
os.environ['no_proxy'] = '*'
import warnings
from pathlib import Path

import akshare as ak
import pandas as pd
import requests

requests.utils.getproxies = lambda: {}
warnings.filterwarnings('ignore')

OUT = Path(r'D:\AA_Cld_test\.tmp\check_rough.txt')  # 数据根目录 (集中常量)

if __name__ == '__main__':
    base = pd.read_csv(Path(r'D:\AA_Cld_test') / '红利低波策略选股.csv', dtype={'股票代码': str})
    div = (ak.stock_history_dividend()
           .assign(code=lambda d: d['代码'].astype(str).str.strip().str.zfill(6),
                   avg_div=lambda d: pd.to_numeric(d['年均股息'], errors='coerce'),
                   n_div=lambda d: pd.to_numeric(d['分红次数'], errors='coerce'))
           .loc[:, ['code', 'avg_div', 'n_div']])
    spot = (ak.stock_zh_a_spot()
            .assign(code=lambda d: d['代码'].astype(str).str[2:].str.strip().str.zfill(6),
                    price=lambda d: pd.to_numeric(d['最新价'], errors='coerce'))
            .loc[:, ['code', 'price']])
    m = base.merge(div, left_on='股票代码', right_on='code', how='left').merge(spot, on='code', how='left')
    m['rough_yield'] = m['avg_div'] / 10 / m['price']
    lines = [f"{row['股票代码']} {row['股票名称']}: rough_yield={row['rough_yield']:.4f} (n_div={row['n_div']}) price={row['price']}"
             for _, row in m.iterrows()]
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print(f'rough_yield 最低: {m["rough_yield"].min():.4f}')
    print(f'<0.03 的基准股: {(m["rough_yield"] < 0.03).sum()} 只')
    print(f'<0.02 的基准股: {(m["rough_yield"] < 0.02).sum()} 只')
    print(f'<0.015 的基准股: {(m["rough_yield"] < 0.015).sum()} 只')
