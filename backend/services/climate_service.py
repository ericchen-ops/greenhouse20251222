import os
import pandas as pd
import numpy as np

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder

    # --- 1. 掃描資料夾並讀取摘要 (給 Tab 1 上半部圖表用) ---
    def scan_and_load_weather_data(self):
        weather_db = {}
        if not os.path.exists(self.base_folder):
            # 嘗試建立資料夾，避免報錯
            try: os.makedirs(self.base_folder)
            except: pass
            return weather_db
        
        for f in os.listdir(self.base_folder):
            if f.endswith('.csv'):
                try:
                    path = os.path.join(self.base_folder, f)
                    # 檔名處理：保留原始檔名作為 ID (如 12Q970_東港)
                    loc_id = f.split('.')[0]
                    
                    # 讀取摘要數據 (這裡會進行運算)
                    summary_data = self._read_summary(path)
                    
                    weather_db[loc_id] = {
                        'id': loc_id,
                        'name': loc_id, # 暫用檔名當顯示名稱
                        'data': summary_data,
                        'filename': f   # 關鍵：記住檔名
                    }
                except Exception as e:
                    print(f"Skipping {f}: {e}")
                    continue
        return weather_db

    def _read_summary(self, path):
        """
        [核心修復] 讀取 CWA 原始 CSV 並計算正確的「月統計值」
        融合 V5.9 的讀取邏輯 (on_bad_lines='skip')
        """
        # 1. 預設值 (防止崩潰)
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 'maxTemps': [30.0]*12, 'minTemps': [20.0]*12,
            'solar': [12.0]*12, 'wind': [1.0]*12, 'humidities': [75.0]*12, 
            'rain': [100.0]*12, 'marketPrice': [30.0]*12
        }

        try:
            # 2. 強壯讀取 (仿照 V5.9)
            # 先試 header=1 (氣象局標準)，失敗試 header=0
            try:
                df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='cp950')
            except:
                try:
                    df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='utf-8')
                except:
                    # 最後一搏：試試看 header=0
                    df = pd.read_csv(path, header=0, on_bad_lines='skip', encoding='cp950')

            # 清除欄位名稱的空白
            df.columns = [c.strip() for c in df.columns]

            # 3. 智慧欄位對應
            col_map = {}
            for c in df.columns:
                if '觀測時間' in c or 'Time' in c: col_map['Time'] = c
                elif '氣溫' in c or 'Temp' in c: col_map['Temp'] = c
                elif '日射' in c or 'Solar' in c: col_map['Solar'] = c
                elif '風速' in c or 'Wind' in c: col_map['Wind'] = c
                elif '濕度' in c or 'RH' in c: col_map['RH'] = c

            if 'Time' in col_map:
                # 轉換時間
                df['Time'] = pd.to_datetime(df[col_map['Time']], errors='coerce')
                df = df.dropna(subset=['Time'])
                df.set_index('Time', inplace=True)
                
                # 轉數值 (強制轉換，非數值變 NaN)
                for k, v in col_map.items():
                    if k != 'Time':
                        df[v] = pd.to_numeric(df[v], errors='coerce')

                # ==========================================
                # ★ 關鍵運算：小時 -> 日 -> 月
                # ==========================================
                # 氣溫/風速/濕度：取每日「平均」
                # 日射量 (MJ/m2)：取每日「總和」(因為 CSV 是每小時累積量)
                
                agg_rules = {}
                if 'Temp' in col_map: agg_rules[col_map['Temp']] = ['mean', 'max', 'min']
                if 'Solar' in col_map: agg_rules[col_map['Solar']] = 'sum'
                if 'Wind' in col_map: agg_rules[col_map['Wind']] = 'mean'
                if 'RH' in col_map: agg_rules[col_map['RH']] = 'mean'

                daily = df.resample('D').agg(agg_rules)
                
                # 欄位攤平 (處理 MultiIndex)
                # 例如: (氣溫, mean) -> Temp_Mean
                new_cols = []
                for col in daily.columns:
                    # col 是一個 tuple ('原始欄位名', '統計法')
                    base_name = ""
                    if 'Temp' in col_map and col[0] == col_map['Temp']: base_name = "Temp"
                    elif 'Solar' in col_map and col[0] == col_map['Solar']: base_name = "Solar"
                    elif 'Wind' in col_map and col[0] == col_map['Wind']: base_name = "Wind"
                    elif 'RH' in col_map and col[0] == col_map['RH']: base_name = "RH"
                    
                    suffix = col[1].capitalize() # mean -> Mean
                    new_cols.append(f"{base_name}_{suffix}")
                
                daily.columns = new_cols
                daily['Month'] = daily.index.month
                
                # 取月平均
                monthly_grp = daily.groupby('Month').mean().reindex(range(1, 13))

                # 4. 填回資料 (fillna 補預設值)
                if 'Temp_Mean' in monthly_grp:
                    default_data['temps'] = monthly_grp['Temp_Mean'].fillna(25.0).tolist()
                    default_data['maxTemps'] = monthly_grp['Temp_Max'].fillna(30.0).tolist()
                    default_data['minTemps'] = monthly_grp['Temp_Min'].fillna(20.0).tolist()
                
                if 'Solar_Sum' in monthly_grp:
                    # 這裡得到的是「每日平均總日射量 (MJ/m2/day)」
                    default_data['solar'] = monthly_grp['Solar_Sum'].fillna(12.0).tolist()
                    
                if 'Wind_Mean' in monthly_grp:
                    default_data['wind'] = monthly_grp['Wind_Mean'].fillna(1.0).tolist()
                    
                if 'RH_Mean' in monthly_grp:
                    default_data['humidities'] = monthly_grp['RH_Mean'].fillna(75.0).tolist()

        except Exception as e: 
            print(f"Error reading summary for {path}: {e}")
            pass
            
        return default_data

    # --- 2. 讀取 24 小時資料 (Tab 2, Tab 1 熱力圖用) ---
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            # 強壯讀取
            try: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='cp950')
            except: df = pd.read_csv(path, header=1, on_bad_lines='skip', encoding='utf-8')
            
            df.columns = [c.strip() for c in df.columns]
            
            # 欄位對應
            col_map = {}
            for c in df.columns:
                if '觀測時間' in c or 'Time' in c: col_map['Time'] = c
                elif '氣溫' in c or 'Temp' in c: col_map['Temp'] = c
                elif '日射' in c or 'Solar' in c: col_map['Solar'] = c
                elif '風速' in c or 'Wind' in c: col_map['Wind'] = c
                elif '濕度' in c or 'RH' in c: col_map['RH'] = c

            if 'Time' in col_map:
                df = df.rename(columns={col_map['Time']: 'Time'})
                if 'Temp' in col_map: df = df.rename(columns={col_map['Temp']: 'Temp'})
                if 'Solar' in col_map: df = df.rename(columns={col_map['Solar']: 'Solar'})
                if 'Wind' in col_map: df = df.rename(columns={col_map['Wind']: 'Wind'})
                if 'RH' in col_map: df = df.rename(columns={col_map['RH']: 'RH'})

                df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
                df = df.dropna(subset=['Time'])
                
                for c in ['Temp', 'RH', 'Wind', 'Solar']: 
                    if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                return df
            return None
        except: return None

    # --- 3. 進階光環境分析 (Tab 1 核心) ---
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        # 支援純檔名或路徑
        target_path = os.path.join(self.base_folder, os.path.basename(filename))
        if not os.path.exists(target_path): 
            target_path = os.path.join('data', os.path.basename(filename))
            if not os.path.exists(target_path): return None

        try:
            try: df = pd.read_csv(target_path, header=1, on_bad_lines='skip', encoding='cp950')
            except: df = pd.read_csv(target_path, header=1, on_bad_lines='skip', encoding='utf-8')

            df.columns = [c.strip() for c in df.columns]
            col_time = next((c for c in df.columns if '觀測時間' in c), None)
            col_solar = next((c for c in df.columns if '日射' in c), None)

            if col_time and col_solar:
                df = df.rename(columns={col_time: 'Time', col_solar: 'Raw_MJ'})
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
            return None
        except: return None

    # --- 4. 讀取作物參數 ---
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

    # --- 5. 計算矩陣 ---
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