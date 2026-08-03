"""阶段0: 探测五类数据接口的可用性与列名。每查到一条立即追加落盘, 避免超时丢结果。"""
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

OUT = Path(r'D:\AA_Cld_test\.tmp\probe_out.txt')  # 数据根目录 (集中常量)


def log(msg: str) -> None:
    """立即追加写入, 失败不中断探测。"""
    print(msg)
    try:
        with OUT.open('a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except OSError as exc:
        print(f'  写盘失败: {exc}')


def probe(name: str, fn) -> None:
    t0 = time.time()
    try:
        df = fn()
        assert isinstance(df, pd.DataFrame)
        log(f'[OK] {name}: {len(df)} 行 x {len(df.columns)} 列, 耗时 {time.time()-t0:.1f}s')
        log(f'  列名: {list(df.columns)}')
        if not df.empty:
            log(f'  首行: {df.iloc[0].to_dict()}')
    except Exception as exc:
        log(f'[FAIL] {name}: {type(exc).__name__} {exc}')
    log('')


if __name__ == '__main__':
    OUT.write_text('', encoding='utf-8')  # 清空旧结果
    # 1. 新浪全A实时价 (批量)
    probe('stock_zh_a_spot', lambda: ak.stock_zh_a_spot())

    # 2. 新浪历史分红 (批量)
    probe('stock_history_dividend', lambda: ak.stock_history_dividend())

    # 3. 新浪财务摘要 (单股)
    probe('stock_financial_abstract(600066)', lambda: ak.stock_financial_abstract(symbol='600066'))

    # 4. 巨潮分红明细 (单股)
    probe('stock_dividend_cninfo(600066)', lambda: ak.stock_dividend_cninfo(symbol='600066'))

    # 5. 腾讯历史日线 (单股)
    probe('stock_zh_a_hist_tx(sh600066)',
          lambda: ak.stock_zh_a_hist_tx(symbol='sh600066', start_date='20250101', end_date='20260804'))
