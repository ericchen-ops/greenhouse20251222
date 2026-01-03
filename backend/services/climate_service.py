import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # 1. 掃描資料夾 (給 Tab 1 上方摘要用)
    def scan_and_load_weather_data(self):
        weather_db = {}
        if not os.path.exists(self.base_folder):
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    loc_id = f.split('.')[0].split('_')[0] 
                    loc_name = f.split('.')[0]
                    
                    # 讀取摘要數據
                    summary_data = self._read_summary(path)
                    
                    weather_db[loc_id] = {
                        'id': loc_id,
                        'name': loc_name,
                        'data': summary_data,
                        'filename': f 
                    }
                except: continue
        return weather_db

    def _read_summary(self, path):
        # 預設值
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 'maxTemps': [30.0]*12, 'minTemps': [20.0]*12,
            'solar': [12.0]*12, 'wind': [1.0]*12, 'humidities': [75.0]*12, 'rain': [100.0]*12, 'marketPrice': [30.0]*12
        }

        try:
            # 讀取
            try: df = pd.read_csv(path, header=1, encoding='cp950')
            except: df = pd.read_csv(path, header=1, encoding='utf-8')

            # 欄位對應
            col_time = next((c for c in df.columns if '觀測時間' in c or 'Time' in c), None)
            col_temp = next((c for c in df.columns if '氣溫' in c), None)
            col_solar = next((c for c in df.columns if '日射' in c), None)
            col_wind = next((c for c in df.columns if '風速' in c), None)
            col_rh = next((c for c in df.columns if '濕度' in c), None)

            if col_time:
                df['Time'] = pd.to_datetime(df[col_time], errors='coerce')
                df = df.dropna(subset=['Time'])
                df.set_index('Time', inplace=True)
                for c in [col_temp, col_solar, col_wind, col_rh]:
                    if c: df[c] = pd.to_numeric(df[c], errors='coerce')

                # ★ 日統計 -> 月平均
                daily = df.resample('D').agg({
                    col_temp: ['mean', 'max', 'min'],
                    col_solar: 'sum',
                    col_wind: 'mean',
                    col_rh: 'mean'
                })
                daily.columns = ['Temp_Mean', 'Temp_Max', 'Temp_Min', 'Solar_Sum', 'Wind_Mean', 'RH_Mean']
                daily['Month'] = daily.index.month
                
                monthly_grp = daily.groupby('Month').mean().reindex(range(1, 13))

                if col_temp:
                    default_data['temps'] = monthly_grp['Temp_Mean'].fillna(25.0).tolist()
                    default_data['maxTemps'] = monthly_grp['Temp_Max'].fillna(30.0).tolist()
                    default_data['minTemps'] = monthly_grp['Temp_Min'].fillna(20.0).tolist()
                if col_solar: default_data['solar'] = monthly_grp['Solar_Sum'].fillna(12.0).tolist()
                if col_wind: default_data['wind'] = monthly_grp['Wind_Mean'].fillna(1.0).tolist()
                if col_rh: default_data['humidities'] = monthly_grp['RH_Mean'].fillna(75.0).tolist()

        except: pass
        return default_data

    # 2. 讀取小時資料 (Tab 2, Tab 1 熱力圖用)
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            try: df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='cp950')
            except: df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='utf-8')
            
            df.columns = ['Time', 'Temp', 'RH', 'Wind', 'Solar']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            for c in ['Temp', 'RH', 'Wind', 'Solar']: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            return df
        except: return None

    # 3. 進階光環境分析 (Tab 1 核心)
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        target_path = os.path.join(self.base_folder, os.path.basename(filename))
        if not os.path.exists(target_path): 
            target_path = os.path.join('data', os.path.basename(filename))
            if not os.path.exists(target_path): return None

        try:
            try: df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='cp950')
            except: df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='utf-8')

            df.columns = ['Time', 'Raw_MJ']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
            
            ratio = transmittance_percent / 100.0
            df['Val_MJ'] = df['Raw_MJ'] * ratio
            df['Val_Wh'] = df['Val_MJ'] * 277.78
            df['Val_PPFD'] = df['Val_MJ'] * 571.2
            df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056
            
            df['Month'] = df['Time'].dt.month
            df['Hour'] = df['Time'].dt.hour
            return df
        except: return None

    # 4. 讀取作物參數
    def get_crop_light_requirements(self):
        csv_path = os.path.join('data', 'crop_parameters.csv')
        default_crops = {'萵苣 (預設)': {'sat': 1100, 'comp': 40, 'dli': 14}}
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

    # 5. 計算矩陣
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