import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # ==========================================
    # ★ 新增：核心讀取函式 (所有功能都用它)
    # ==========================================
    def _smart_read_csv(self, path, required_cols=None):
        """
        聰明讀取 CSV：
        1. 自動嘗試 utf-8, cp950, big5 編碼
        2. 自動尋找標題行 (不只是 header=1)
        3. 回傳標準化的 DataFrame (Time, Temp, Solar...)
        """
        if not os.path.exists(path):
            return None

        # 1. 嘗試不同編碼讀取
        df = None
        encodings = ['utf-8', 'cp950', 'big5', 'utf-8-sig']
        
        for enc in encodings:
            try:
                # 先讀 header=1 (最常見)
                df = pd.read_csv(path, header=1, encoding=enc)
                # 簡單檢查：如果欄位太少，可能是 header 設錯，改試 header=0
                if len(df.columns) < 2:
                    df = pd.read_csv(path, header=0, encoding=enc)
                break
            except:
                continue
        
        if df is None:
            print(f"❌ 無法讀取檔案: {path}")
            return None

        # 2. 欄位關鍵字對應表
        # 格式：'標準名稱': ['關鍵字1', '關鍵字2', ...]
        keywords = {
            'Time': ['時間', 'Time', 'Date', 'ObsTime'],
            'Temp': ['氣溫', 'Temp', 'Temperature'],
            'RH': ['濕度', 'RH', 'Humidity'],
            'Wind': ['風速', 'Wind', 'Speed'],
            'Solar': ['日射', 'Solar', 'MJ', 'Radiation']
        }

        # 3. 建立欄位對應 map
        col_map = {}
        for key, kw_list in keywords.items():
            # 找到第一個符合的欄位
            found_col = next((c for c in df.columns if any(k in str(c) for k in kw_list)), None)
            if found_col:
                col_map[key] = found_col

        # 4. 檢查必要欄位是否存在 (如果有指定)
        if required_cols:
            for req in required_cols:
                if req not in col_map:
                    print(f"⚠️ 檔案 {path} 缺少必要欄位: {req} (找到: {list(col_map.keys())})")
                    return None

        # 5. 重新命名並回傳乾淨的 DF
        # 為了避免 SettingWithCopyWarning，我們建立一個新的 DF
        clean_df = pd.DataFrame()
        
        if 'Time' in col_map:
            clean_df['Time'] = pd.to_datetime(df[col_map['Time']], errors='coerce')
            clean_df = clean_df.dropna(subset=['Time']) # 去除時間無效的列
        
        # 填入數值資料 (轉成數字，非數字變 NaN 再補 0)
        for key in ['Temp', 'RH', 'Wind', 'Solar']:
            if key in col_map:
                clean_df[key] = pd.to_numeric(df[col_map[key]], errors='coerce').fillna(0)
            else:
                clean_df[key] = 0.0 # 缺少的欄位補 0

        return clean_df

    # 1. 基礎讀取 (修正後)
    def scan_and_load_weather_data(self):
        weather_db = {}
        if not os.path.exists(self.base_folder):
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    loc_id = f.split('.')[0]
                    summary_data = self._read_summary(path)
                    
                    weather_db[loc_id] = {
                        'id': loc_id,
                        'name': loc_id,
                        'data': summary_data
                    }
                except Exception as e:
                    print(f"Skipping {f}: {e}")
                    continue
        return weather_db

    def _read_summary(self, path):
        # 預設資料 (保命用)
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 'maxTemps': [30.0]*12, 'minTemps': [20.0]*12,
            'solar': [12.0]*12, 'wind': [1.0]*12, 'humidities': [75.0]*12,
            'rain': [100.0]*12, 'marketPrice': [30.0]*12
        }

        # ★ 改用 _smart_read_csv
        df = self._smart_read_csv(path, required_cols=['Time'])
        
        if df is None or df.empty:
            return default_data

        try:
            df['Month'] = df['Time'].dt.month
            grp = df.groupby('Month')

            # 只要有讀到，就覆蓋預設值
            default_data['temps'] = grp['Temp'].mean().reindex(range(1,13), fill_value=25.0).tolist()
            default_data['maxTemps'] = grp['Temp'].max().reindex(range(1,13), fill_value=30.0).tolist()
            default_data['minTemps'] = grp['Temp'].min().reindex(range(1,13), fill_value=20.0).tolist()
            default_data['solar'] = grp['Solar'].mean().reindex(range(1,13), fill_value=12.0).tolist()
            default_data['wind'] = grp['Wind'].mean().reindex(range(1,13), fill_value=1.0).tolist()
            default_data['humidities'] = grp['RH'].mean().reindex(range(1,13), fill_value=75.0).tolist()
            
            return default_data
        except Exception as e:
            print(f"Summary calculation failed: {e}")
            return default_data

    # 2. 讀取 24 小時動態資料 (Tab 2)
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        # ★ 改用 _smart_read_csv
        df = self._smart_read_csv(path, required_cols=['Time'])
        return df # 已經包含 Temp, RH, Wind, Solar

    # 3. 進階光環境分析 (Tab 1) - 原本壞掉的地方
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        # 處理檔名可能沒有 .csv 的問題
        if not filename.endswith('.csv'):
            filename += '.csv'
            
        possible_paths = [os.path.join(self.base_folder, filename), os.path.join('data', filename), filename]
        target_path = next((p for p in possible_paths if os.path.exists(p)), None)
        
        # ★ 改用 _smart_read_csv，並指定需要 Solar
        df = self._smart_read_csv(target_path, required_cols=['Time', 'Solar'])
        
        if df is None: return None

        # 進行光環境計算
        ratio = transmittance_percent / 100.0
        # 注意: _smart_read_csv 已經把日射量統一命名為 'Solar'
        df['Val_MJ'] = df['Solar'] * ratio 
        df['Val_Wh'] = df['Val_MJ'] * 277.78
        df['Val_PPFD'] = df['Val_MJ'] * 571.2
        df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056
        
        df['Month'] = df['Time'].dt.month
        df['Date'] = df['Time'].dt.date.astype(str)
        df['Hour'] = df['Time'].dt.hour
        
        return df

    # 4. 讀取作物參數 (不用改)
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

    # 5. 計算月平均矩陣 (不用改邏輯，只需確認 analyze_advanced_light 回傳正確)
    def calculate_monthly_light_matrix(self, filename, transmittance_percent=100):
        df = self.analyze_advanced_light(filename, transmittance_percent)
        if df is None or df.empty: return None, None
        
        try:
            matrix_ppfd = df.pivot_table(index='Month', columns='Hour', values='Val_PPFD', aggfunc='mean').fillna(0)
            matrix_ppfd = matrix_ppfd.reindex(index=range(1, 13), columns=range(0, 24), fill_value=0)
            daily_sum_ppfd = matrix_ppfd.sum(axis=1) 
            dli_series = daily_sum_ppfd * 3600 / 1_000_000
            return matrix_ppfd, dli_series
        except: return None, None