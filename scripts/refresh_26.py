"""更新 红利低波策略选股.csv 中 26 只股票的当期数据, 输出 红利低波策略选股_更新.csv。

字段: 最新价(新浪spot) / PE·ROE·3年ROE·市值(新浪财务摘要, 2025年报) /
当期股息率(巨潮2025年度派息合计/10/股价) / 120日均价·买卖点(腾讯日线不复权)。
"""
import os
os.environ['no_proxy'] = '*'
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import akshare as ak
import pandas as pd
import requests
from tqdm import tqdm

requests.utils.getproxies = lambda: {}
warnings.filterwarnings('ignore')

DATA_ROOT = Path(r'D:\AA_Cld_test')        # 源CSV与输出CSV所在目录 (集中常量)
BASE_CSV = DATA_ROOT / '红利低波策略选股.csv'
OUT_CSV = DATA_ROOT / '红利低波策略选股_更新.csv'
PROG = DATA_ROOT / '.tmp' / 'refresh_progress.log'

YEARS = ['20251231', '20241231', '20231231']  # 近三个年报期
DIV_YEAR = '2025'    # 当期股息率用最新年度分红
TODAY = '20260804'   # 日线截止日
WORKERS = 8          # 新浪/腾讯并发
WORKERS_DIV = 1      # 巨潮接口并发必崩(实测8/2线程均触发原生崩溃), 全串行
LOCK = threading.Lock()


def log(msg: str) -> None:
    print(msg)
    try:
        with PROG.open('a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except OSError:
        pass


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


def tx_symbol(code: str) -> str:
    if code.startswith('6'):
        return f'sh{code}'
    if code.startswith(('0', '3')):
        return f'sz{code}'
    return f'bj{code}'


def fetch_spot() -> pd.DataFrame:
    return (ak.stock_zh_a_spot()
            .assign(code=lambda d: d['代码'].astype(str).str[2:].str.strip().str.zfill(6),
                    price=lambda d: pd.to_numeric(d['最新价'], errors='coerce'))
            .loc[:, ['code', 'price']])


def fundamentals(code: str) -> dict | None:
    fa = retry(lambda: ak.stock_financial_abstract(symbol=code))
    if fa is None or fa.empty:
        return None
    cols = [c for c in YEARS if c in fa.columns]
    if not cols:
        return None

    def pick(name: str) -> pd.Series | None:
        hit = fa['指标'].eq(name)
        return pd.to_numeric(fa.loc[hit, cols].iloc[0], errors='coerce') if hit.any() else None

    eps, roe, bps, equity = (pick('基本每股收益'), pick('净资产收益率(ROE)'),
                             pick('每股净资产'), pick('股东权益合计(净资产)'))
    if any(x is None for x in (eps, roe, bps, equity)):
        return None
    return {'eps': eps.iloc[0], 'roe': roe.iloc[0], 'roe_3y': roe.mean(),
            'bps': bps.iloc[0], 'equity': equity.iloc[0]}


def div_yield(code: str, price: float) -> float:
    """当期股息率 = 2025 年度各次派息比例合计 / 10 / 股价。"""
    dv = retry(lambda: ak.stock_dividend_cninfo(symbol=code))
    if dv is None or dv.empty:
        return float('nan')
    total = (dv.assign(派息比例=lambda d: pd.to_numeric(d['派息比例'], errors='coerce'),
                       year=lambda d: d['报告时间'].astype(str).str.extract(r'(\d{4})')[0])
             .query('year == @DIV_YEAR')['派息比例'].sum())
    return total / 10 / price


def ma120(code: str) -> float:
    hist = retry(lambda: ak.stock_zh_a_hist_tx(symbol=tx_symbol(code),
                                               start_date='20250101', end_date=TODAY))
    if hist is None or hist.empty:
        return float('nan')
    return pd.to_numeric(hist['close'], errors='coerce').dropna().tail(120).mean()


def run_threaded(items, work, desc: str, workers: int) -> list[dict]:
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(work, it) for it in items]
        for fut in tqdm(as_completed(futures), total=len(futures), desc=desc, file=sys.stderr):
            results.append(fut.result())
    return results


if __name__ == '__main__':
    PROG.write_text('', encoding='utf-8')
    base = pd.read_csv(BASE_CSV, dtype={'股票代码': str})
    base['股票代码'] = base['股票代码'].str.strip().str.zfill(6)
    log(f'读取 {len(base)} 只基准股')

    # 最新价 (新浪spot, 一次批量)
    spot = fetch_spot()
    base = base.merge(spot, left_on='股票代码', right_on='code', how='left')

    # 财务: EPS/ROE/3年ROE/市值
    def work_fin(row) -> dict:
        code, name, price = row
        f = fundamentals(code)
        if f is None or not f['eps'] or not f['bps'] or f['eps'] <= 0:
            rec = {'code': code, 'name': name, 'price': price,
                   'pe': float('nan'), 'roe': float('nan'), 'roe_3y': float('nan'), 'cap_yi': float('nan')}
        else:
            shares = f['equity'] / f['bps']
            rec = {'code': code, 'name': name, 'price': price,
                   'pe': price / f['eps'], 'roe': f['roe'], 'roe_3y': f['roe_3y'],
                   'cap_yi': shares * price / 1e8}
        with LOCK:
            log(f'  财务 {code} {name} PE={rec["pe"]:.1f} ROE={rec["roe"]:.1f} 市值={rec["cap_yi"]:.0f}亿')
        return rec

    fin = pd.DataFrame(run_threaded(
        base[['股票代码', '股票名称', 'price']].itertuples(index=False), work_fin, '财务摘要', WORKERS))
    log(f'财务完成: {len(fin)} 只')

    # 当期股息率 (巨潮, 低并发)
    def work_div(row) -> dict:
        code, name, price = row
        y = div_yield(code, price)
        with LOCK:
            log(f'  股息 {code} {name} 2025股息率={y:.4f}')
        return {'code': code, 'div_yield': y}

    div = pd.DataFrame(run_threaded(
        fin[['code', 'name', 'price']].itertuples(index=False), work_div, '当期股息率', WORKERS_DIV))
    log(f'股息完成: {len(div)} 只')

    # 120日均价 + 买卖点 (腾讯)
    def work_ma(code: str) -> dict:
        m = ma120(code)
        with LOCK:
            log(f'  均线 {code} 120日均价={m:.2f}')
        return {'code': code, 'ma120': m}

    ma = pd.DataFrame(run_threaded(fin['code'], work_ma, '120日均价', WORKERS))
    log(f'均线完成: {len(ma)} 只')

    # 合并输出, 列与原始 CSV 同构
    out = (base[['股票代码', '股票名称']]
           .merge(fin, left_on='股票代码', right_on='code', how='left')
           .merge(div, on='code', how='left')
           .merge(ma, on='code', how='left')
           .assign(买入点=lambda d: d['ma120'] * 0.88,
                   卖出点=lambda d: d['ma120'] * 1.12)
           .drop(columns=['code'])
           .rename(columns={'price': '最新价(元)', 'pe': '市盈率(PE)', 'roe': 'ROE(%)',
                            'roe_3y': '3年平均ROE(%)', 'div_yield': '股息率(%)',
                            'cap_yi': '总市值(亿元)', 'ma120': '120日均价(元)',
                            '买入点': '买入点(元)', '卖出点': '卖出点(元)'}))
    out = out[['股票代码', '股票名称', '最新价(元)', '市盈率(PE)', 'ROE(%)', '3年平均ROE(%)',
               '股息率(%)', '总市值(亿元)', '120日均价(元)', '买入点(元)', '卖出点(元)']]
    out.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    log(f'\n完成: {len(out)} 只, 已写入 {OUT_CSV}')
