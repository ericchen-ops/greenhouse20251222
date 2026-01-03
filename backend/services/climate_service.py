import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # --- 1. 掃描資料夾並讀取摘要 (給 Tab 2, 4 用) ---
    def scan_and_load_weather_data(self):
        weather_db = {}
        # 確保資料夾存在
        if not os.path.exists(self.base_folder):
            print(f"⚠️ 資料夾不存在: {self.base_folder}")
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    # 假設檔名格式為 "ID_名稱.csv" 或 "ID.csv"
                    loc_id = f.split('.')[0].split('_')[0] 
                    loc_name = f.split('.')[0]
                    
                    # 讀取摘要數據
                    summary_data = self._read_summary(path)
                    
                    weather_db[loc_id] = {
                        'id': loc_id,
                        'name': loc_name,
                        'data': summary_data,
                        'filename': f # 記錄完整檔名，方便 Tab 1 尋找
                    }
                except Exception as e:
                    print(f"Skipping {f}: {e}")
                    continue
        return weather_db

    def _read_summary(self, path):
        """讀取 CSV 並計算月平均，防止 KeyError"""
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 'maxTemps': [30.0]*12, 'minTemps': [20.0]*12,
            'solar': [12.0]*12, 'wind': [1.0]*12, 'humidities': [75.0]*12, 'rain': [100.0]*12, 'marketPrice': [30.0]*12
        }

        try:
            # 讀取 CSV (處理 cp950 編碼 & header=1)
            try:
                df = pd.read_csv(path, header=1, encoding='cp950')
            except:
                df = pd.read_csv(path, header=1, encoding='utf-8')

            # 欄位對應
            col_map = {
                'Temp': next((c for c in df.columns if '氣溫' in c), None),
                'RH': next((c for c in df.columns if '濕度' in c), None),
                'Wind': next((c for c in df.columns if '風速' in c), None),
                'Solar': next((c for c in df.columns if '日射' in c), None),
                'Time': next((c for c in df.columns if '時間' in c), None)
            }

            if col_map['Time']:
                df['Time'] = pd.to_datetime(df[col_map['Time']], errors='coerce')
                df = df.dropna(subset=['Time'])
                df['Month'] = df['Time'].dt.month
                grp = df.groupby('Month')
                
                # 填入數據
                if col_map['Temp']: 
                    default_data['temps'] = grp[col_map['Temp']].mean().reindex(range(1,13), fill_value=25.0).tolist()
                    default_data['maxTemps'] = grp[col_map['Temp']].max().reindex(range(1,13), fill_value=30.0).tolist()
                    default_data['minTemps'] = grp[col_map['Temp']].min().reindex(range(1,13), fill_value=20.0).tolist()
                if col_map['Solar']: default_data['solar'] = grp[col_map['Solar']].mean().fillna(12.0).reindex(range(1,13), fill_value=12.0).tolist()
                if col_map['Wind']: default_data['wind'] = grp[col_map['Wind']].mean().fillna(1.0).reindex(range(1,13), fill_value=1.0).tolist()
                if col_map['RH']: default_data['humidities'] = grp[col_map['RH']].mean().fillna(75.0).reindex(range(1,13), fill_value=75.0).tolist()

        except: pass
        return default_data

    # --- 2. 讀取 24 小時資料 (Tab 2 用) ---
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            # 針對您的 CSV 格式：觀測時間(col 1), 氣溫(4), 濕度(6), 風速(7), 日射(13)
            # 使用 usecols 避免讀到最後的空欄位
            try:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='cp950')
            except:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='utf-8')
            
            df.columns = ['Time', 'Temp', 'RH', 'Wind', 'Solar']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            for c in ['Temp', 'RH', 'Wind', 'Solar']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            return df
        except: return None

    # --- 3. 進階光環境分析 (Tab 1 核心) ---
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        # 組合路徑 (支援只傳檔名)
        target_path = os.path.join(self.base_folder, os.path.basename(filename))
        
        if not os.path.exists(target_path): 
            # 嘗試找找看 data/ 下
            target_path = os.path.join('data', os.path.basename(filename))
            if not os.path.exists(target_path): return None

        try:
            # 讀取 CSV (只讀 時間[1] 和 日射[13])
            try:
                df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='cp950')
            except:
                df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='utf-8')

            df.columns = ['Time', 'Raw_MJ']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
            
            # 物理轉換
            ratio = transmittance_percent / 100.0
            df['Val_MJ'] = df['Raw_MJ'] * ratio
            df['Val_Wh'] = df['Val_MJ'] * 277.78
            df['Val_PPFD'] = df['Val_MJ'] * 571.2
            df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056
            
            df['Month'] = df['Time'].dt.month
            df['Hour'] = df['Time'].dt.hour
            return df
        except Exception as e:
            print(f"Error in analyze_advanced_light: {e}")
            return None

    # --- 4. 讀取作物參數 ---
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

    # --- 5. 計算月平均矩陣 (Tab 1 繪圖用) ---
    def calculate_monthly_light_matrix(self, filename, transmittance_percent=100):
        df = self.analyze_advanced_light(filename, transmittance_percent)
        if df is None or df.empty: return None, None
        
        try:
            # 矩陣運算
            matrix_ppfd = df.pivot_table(index='Month', columns='Hour', values='Val_PPFD', aggfunc='mean').fillna(0)
            # 補齊 1-12月, 0-23時
            matrix_ppfd = matrix_ppfd.reindex(index=range(1, 13), columns=range(0, 24), fill_value=0)
            
            # DLI 計算
            daily_sum_ppfd = matrix_ppfd.sum(axis=1) 
            dli_series = daily_sum_ppfd * 3600 / 1_000_000
            return matrix_ppfd, dli_series
        except: return None, None