import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # 1. 基礎讀取 (Tab 2, 4 使用)
    def scan_and_load_weather_data(self):
        weather_db = {}
        if not os.path.exists(self.base_folder):
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    # 嘗試讀取基本資訊 (假設有特定格式，若無則略過)
                    # 這裡簡化處理，只抓檔名當 ID
                    loc_id = f.split('.')[0]
                    weather_db[loc_id] = {
                        'id': loc_id,
                        'name': loc_id,
                        'data': self._read_summary(path) # 讀取摘要
                    }
                except: continue
        return weather_db

    def _read_summary(self, path):
        # 這是舊有的簡易讀取，若您的系統沒用到可忽略
        # 為了相容性保留回傳假資料或做簡單統計
        return {
            'months': list(range(1,13)),
            'temps': [25]*12, 'maxTemps': [30]*12, 'minTemps': [20]*12,
            'solar': [12]*12, 'rain': [100]*12, 'marketPrice': [30]*12
        }

    # 2. 讀取 24 小時動態資料 (Tab 2 使用)
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            # 嘗試處理氣象局格式
            try:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='cp950')
            except:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='utf-8')
            
            df.columns = ['Time', 'Temp', 'RH', 'Wind', 'Solar']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            
            # 填補空值
            for c in ['Temp', 'RH', 'Wind', 'Solar']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                
            return df
        except: return None

    # 3. 進階光環境分析 (Tab 1 使用)
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        # 組合路徑
        possible_paths = [
            os.path.join(self.base_folder, filename),
            os.path.join('data', filename),
            filename
        ]
        target_path = None
        for p in possible_paths:
            if os.path.exists(p): target_path = p; break
        
        if not target_path: return None

        try:
            # 嘗試讀取
            try:
                df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='cp950')
            except:
                df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='utf-8')

            df.columns = ['Time', 'Raw_MJ']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
            
            # 運算
            ratio = transmittance_percent / 100.0
            df['Val_MJ'] = df['Raw_MJ'] * ratio
            df['Val_Wh'] = df['Val_MJ'] * 277.78
            df['Val_PPFD'] = df['Val_MJ'] * 571.2
            df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056
            
            df['Month'] = df['Time'].dt.month
            df['Date'] = df['Time'].dt.date.astype(str)
            df['Hour'] = df['Time'].dt.hour
            
            return df
        except Exception as e:
            print(f"Error in analyze_advanced_light: {e}")
            return None

    # 4. [NEW] 讀取作物參數 (優先讀 CSV)
    def get_crop_light_requirements(self):
        csv_path = os.path.join('data', 'crop_parameters.csv')
        
        default_crops = {
            '萵苣 (預設)': {'sat': 1100, 'comp': 40, 'dli': 14},
            '小白菜 (預設)': {'sat': 1200, 'comp': 40, 'dli': 16}
        }

        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, encoding='utf-8')
                crop_dict = {}
                for _, row in df.iterrows():
                    name = str(row.get('Crop_Name', row.get('Crop_ID', 'Unknown')))
                    crop_dict[name] = {
                        'sat': float(row.get('Light_Sat_Point', 1200)),
                        'comp': float(row.get('Light_Comp_Point', 40)),
                        'dli': float(row.get('DLI_Target', 15))
                    }
                return crop_dict
            except: return default_crops
        return default_crops

    # 5. [NEW] 計算月平均矩陣 (修復 AttributeError 的關鍵)
    def calculate_monthly_light_matrix(self, filename, transmittance_percent=100):
        # 1. 取得乾淨數據
        df = self.analyze_advanced_light(filename, transmittance_percent)
        if df is None or df.empty: return None, None
        
        try:
            # 2. 矩陣運算: Month x Hour 平均值
            matrix_ppfd = df.pivot_table(
                index='Month', 
                columns='Hour', 
                values='Val_PPFD', 
                aggfunc='mean'
            ).fillna(0)
            
            # 補齊 1-12 月, 0-23 時
            matrix_ppfd = matrix_ppfd.reindex(
                index=pd.Index(range(1, 13), name='Month'), 
                columns=pd.Index(range(0, 24), name='Hour'), 
                fill_value=0
            )
            
            # 3. 計算 DLI
            # 先算每個月不同小時的 PPFD 總和 (每日平均變化曲線的積分)
            # 公式: sum(avg_PPFD_per_hour) * 3600 / 1,000,000
            daily_sum_ppfd = matrix_ppfd.sum(axis=1) 
            dli_series = daily_sum_ppfd * 3600 / 1_000_000
            
            return matrix_ppfd, dli_series
            
        except Exception as e:
            print(f"Matrix calculation error: {e}")
            return None, None