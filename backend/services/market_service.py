import os
import pandas as pd

class MarketService:
    def __init__(self, base_folder='data/market_data'):
        self.base_folder = base_folder

    def scan_and_load_market_prices(self):
        price_db = {}
        if not os.path.exists(self.base_folder): return {}
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    try: df = pd.read_csv(path, header=2)
                    except: df = pd.read_csv(path, header=0)
                    
                    if '交易日期' in df.columns and '平均價' in df.columns:
                        df['M'] = df['交易日期'].astype(str).apply(lambda x: int(x.split('年')[1].replace('月','')) if '年' in x else None)
                        avg = df.groupby('M')['平均價'].mean()
                        price_db[os.path.splitext(f)[0]] = [round(avg.get(m, 30.0), 1) for m in range(1, 13)]
                except: continue
        return price_db