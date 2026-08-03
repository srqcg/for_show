"""验证: 对 CSV 26 只基准股跑财务+股息提取, 对比 CSV 数值, 排查通过率异常。"""
import os
os.environ['no_proxy'] = '*'
import time
import warnings
from pathlib import Path

import akshare as ak
import pandas as pd
import requests

requests.utils.getproxies = lambda: {}
warnings.filterwarnings('ignore')

OUT = Path(r'D:\AA_Cld_test\.tmp\verify_out.txt')  # 数据根目录 (集中常量)
YEARS = ['20251231', '20241231', '20231231']


def log(msg: str) -> None:
    print(msg)
    with OUT.open('a', encoding='utf-8') as f:
        f.write(msg + '\n')


def retry(fn, tries: int = 2, pause: float = 0.4):
    for i in range(tries):
        try:
            time.sleep(pause)
            return fn()
        except Exception as exc:
            if i == tries - 1:
                log(f'  fail: {type(exc).__name__} {exc}')
                return None
    return None


def pick(fa: pd.DataFrame, name: str) -> pd.Series | None:
    hit = fa['指标'].eq(name)
    cols = [c for c in YEARS if c in fa.columns]
    if not cols or not hit.any():
        return None
    return pd.to_numeric(fa.loc[hit, cols].iloc[0], errors='coerce')


if __name__ == '__main__':
    OUT.write_text('', encoding='utf-8')
    base = pd.read_csv(Path(r'D:\AA_Cld_test') / '红利低波策略选股.csv', dtype={'股票代码': str})
    for code, name in base[['股票代码', '股票名称']].itertuples(index=False):
        fa = retry(lambda: ak.stock_financial_abstract(symbol=code))
        if fa is None or fa.empty:
            log(f'{code} {name}: 财务摘要取不到')
            continue
        eps, roe, bps, equity = (pick(fa, '基本每股收益'), pick(fa, '净资产收益率(ROE)'),
                                 pick(fa, '每股净资产'), pick(fa, '股东权益合计(净资产)'))
        if any(x is None for x in (eps, roe, bps, equity)):
            log(f'{code} {name}: 缺指标')
            continue
        log(f'{code} {name}: EPS={eps.iloc[0]:.2f} ROE={roe.iloc[0]:.2f} '
            f'ROE_3y={roe.mean():.2f} BPS={bps.iloc[0]:.2f} 净资产={equity.iloc[0]/1e8:.0f}亿')
        # 当期股息率 (2025年度)
        dv = retry(lambda: ak.stock_dividend_cninfo(symbol=code))
        if dv is not None and not dv.empty:
            total = (dv.assign(派息比例=lambda d: pd.to_numeric(d['派息比例'], errors='coerce'),
                               year=lambda d: d['报告时间'].astype(str).str.extract(r'(\d{4})')[0])
                     .query('year == "2025"')['派息比例'].sum())
            log(f'  2025年度派息合计={total}')
            log(f'  2025年报告期: {dv[dv["报告时间"].astype(str).str.contains("2025")]["报告时间"].tolist()}')
        log('')
