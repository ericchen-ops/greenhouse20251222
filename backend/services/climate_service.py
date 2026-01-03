import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # 1. 掃描與摘要
    def scan_and_load_weather_data(self):
        weather_db = {}
        if not os.path.exists(self.base_folder):
            try: os.makedirs(self.base_folder)
            except: pass
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    loc_id = f.split('.')[0]
                    summary_data = self._read_summary(path)
                    weather_db[loc_id] = {
                        'id': loc_id, 'name': loc_id, 'data': summary_data, 'filename': f
                    }
                except: continue
        return weather_db

    def _read_summary(self, path):
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 'maxTemps': [30.0]*12, 'minTemps': [20.0]*12,
            'solar': [12.0]*12, 'wind': [1.0]*12, 'humidities': [75.0]*12, 
            'rain': [100.0]*12, 'marketPrice': [30.0]*12
        }
        try:
            try: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='cp950')
            except: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]

            col_map = {}
            for c in df.columns:
                if '觀測時間' in c or 'Time' in c: col_map['Time'] = c
                elif '氣溫' in c or 'Temp' in c: col_map['Temp'] = c
                elif '日射' in c or 'Solar' in c: col_map['Solar'] = c
                elif '風速' in c or 'Wind' in c: col_map['Wind'] = c
                elif '濕度' in c or 'RH' in c: col_map['RH'] = c

            if 'Time' in col_map:
                df['Time'] = pd.to_datetime(df[col_map['Time']], errors='coerce')
                df = df.dropna(subset=['Time'])
                df.set_index('Time', inplace=True)
                for k, v in col_map.items(): 
                    if k!='Time': df[v] = pd.to_numeric(df[v], errors='coerce')

                agg_rules = {}
                if 'Temp' in col_map: agg_rules[col_map['Temp']] = ['mean', 'max', 'min']
                if 'Solar' in col_map: agg_rules[col_map['Solar']] = 'sum'
                if 'Wind' in col_map: agg_rules[col_map['Wind']] = 'mean'
                if 'RH' in col_map: agg_rules[col_map['RH']] = 'mean'

                daily = df.resample('D').agg(agg_rules)
                
                # Flatten columns
                new_cols = []
                for col in daily.columns:
                    base = "Temp" if col[0]==col_map.get('Temp') else "Solar" if col[0]==col_map.get('Solar') else "Wind" if col[0]==col_map.get('Wind') else "RH"
                    new_cols.append(f"{base}_{col[1].capitalize()}")
                daily.columns = new_cols
                
                monthly_grp = daily.groupby(daily.index.month).mean().reindex(range(1, 13))

                if 'Temp_Mean' in monthly_grp:
                    default_data['temps'] = monthly_grp['Temp_Mean'].fillna(25.0).tolist()
                    default_data['maxTemps'] = monthly_grp['Temp_Max'].fillna(30.0).tolist()
                    default_data['minTemps'] = monthly_grp['Temp_Min'].fillna(20.0).tolist()
                if 'Solar_Sum' in monthly_grp: default_data['solar'] = monthly_grp['Solar_Sum'].fillna(12.0).tolist()
                if 'Wind_Mean' in monthly_grp: default_data['wind'] = monthly_grp['Wind_Mean'].fillna(1.0).tolist()
                if 'RH_Mean' in monthly_grp: default_data['humidities'] = monthly_grp['RH_Mean'].fillna(75.0).tolist()
        except: pass
        return default_data

    # 2. 讀取小時 (Tab 2 用)
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            try: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='cp950')
            except: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            
            # Smart Mapping
            col_map = {}
            for c in df.columns:
                if '觀測時間' in c or 'Time' in c: col_map['Time'] = c
                elif '氣溫' in c or 'Temp' in c: col_map['Temp'] = c
                elif '日射' in c or 'Solar' in c: col_map['Solar'] = c
                elif '風速' in c or 'Wind' in c: col_map['Wind'] = c
                elif '濕度' in c or 'RH' in c: col_map['RH'] = c

            if 'Time' in col_map:
                rename_dict = {col_map['Time']: 'Time'}
                if 'Temp' in col_map: rename_dict[col_map['Temp']] = 'Temp'
                if 'Solar' in col_map: rename_dict[col_map['Solar']] = 'Solar'
                if 'Wind' in col_map: rename_dict[col_map['Wind']] = 'Wind'
                if 'RH' in col_map: rename_dict[col_map['RH']] = 'RH'
                
                df = df.rename(columns=rename_dict)
                df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
                df = df.dropna(subset=['Time'])
                for c in ['Temp', 'Solar', 'Wind', 'RH']:
                    if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                return df
            return None
        except: return None

    # 3. [關鍵修正] 進階光環境分析
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        # 尋找檔案
        target_path = os.path.join(self.base_folder, os.path.basename(filename))
        if not os.path.exists(target_path):
            target_path = os.path.join('data', os.path.basename(filename))
            if not os.path.exists(target_path): return None

        try:
            # 讀取檔案
            try: df = pd.read_csv(target_path, header=1, on_bad_lines='skip', encoding='cp950')
            except: df = pd.read_csv(target_path, header=1, on_bad_lines='skip', encoding='utf-8')
            
            df.columns = [c.strip() for c in df.columns]

            # [重點] 智慧尋找「日射量」欄位，而不是只抓第 13 欄
            col_time = next((c for c in df.columns if '觀測時間' in c or 'Time' in c), None)
            col_solar = next((c for c in df.columns if '全天空日射量' in c or '日射' in c or 'Solar' in c), None)

            if col_time and col_solar:
                df = df.rename(columns={col_time: 'Time', col_solar: 'Raw_MJ'})
                df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
                df = df.dropna(subset=['Time'])
                
                # 轉數值 (確保真的是數字，不是 "X" 或 "--")
                df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
                
                # 核心運算
                ratio = transmittance_percent / 100.0
                df['Val_MJ'] = df['Raw_MJ'] * ratio
                df['Val_Wh'] = df['Val_MJ'] * 277.78
                df['Val_PPFD'] = df['Val_MJ'] * 571.2 # 1 MJ solar ~ 571 umol PAR
                df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056
                
                df['Month'] = df['Time'].dt.month
                df['Hour'] = df['Time'].dt.hour
                return df
            
            print(f"⚠️ {filename} 缺少必要欄位 (需要: 觀測時間, 全天空日射量)")
            return None
        except Exception as e:
            print(f"Error analyzing light: {e}")
            return None

    # 4. 作物參數
    def get_crop_light_requirements(self):
        csv_path = os.path.join('data', 'crop_parameters.csv')
        default_crops = {'萵苣 (預設)': {'sat': 1100, 'comp': 40, 'dli': 17}}
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path, encoding='utf-8')
                crop_dict = {}
                for _, row in df.iterrows():
                    name = str(row.get('Crop_Name', row.get('Crop_ID', 'Unknown')))
                    crop_dict[name] = {
                        'sat': float(row.get('Light_Sat_Point', 1200)),
                        'comp': float(row.get('Light_Comp_Point', 40)),
                        'dli': float(row.get('DLI_Target', 17))
                    }
                return crop_dict
            except: return default_crops
        return default_crops

    # 5. 計算矩陣
    def calculate_monthly_light_matrix(self, filename, transmittance_percent=100):
        df = self.analyze_advanced_light(filename, transmittance_percent)
        if df is None or df.empty: return None, None
        try:
            # 算出平均
            matrix_ppfd = df.pivot_table(index='Month', columns='Hour', values='Val_PPFD', aggfunc='mean').fillna(0)
            matrix_ppfd = matrix_ppfd.reindex(index=range(1, 13), columns=range(0, 24), fill_value=0)
            # DLI (日總量)
            daily_sum_ppfd = matrix_ppfd.sum(axis=1) 
            dli_series = daily_sum_ppfd * 3600 / 1_000_000
            return matrix_ppfd, dli_series
        except: return None, None