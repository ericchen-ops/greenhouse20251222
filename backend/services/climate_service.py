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
                    loc_id = f.split('.')[0]
                    
                    # 讀取並計算月平均 (這是修正 KeyError 的關鍵)
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
        """
        讀取 CSV 並計算 1-12 月的平均氣候數據
        確保回傳的字典包含 run_simulation 所需的所有 key:
        temps, solar, wind, humidities
        """
        # 1. 設定預設值 (萬一讀取失敗，用這些值頂著，防止 KeyError)
        default_data = {
            'months': list(range(1,13)),
            'temps': [25.0]*12, 
            'maxTemps': [30.0]*12, 
            'minTemps': [20.0]*12,
            'solar': [12.0]*12, 
            'wind': [1.0]*12,        # ★ 補上缺少的 Key
            'humidities': [75.0]*12, # ★ 補上缺少的 Key
            'rain': [100.0]*12, 
            'marketPrice': [30.0]*12
        }

        try:
            # 2. 嘗試讀取 CSV (處理編碼與標題行)
            try:
                df = pd.read_csv(path, header=1, encoding='cp950')
            except:
                df = pd.read_csv(path, header=1, encoding='utf-8')

            # 3. 智慧欄位對應 (自動抓取常見欄位名稱)
            # 氣象局格式: 氣溫(℃), 相對濕度( %), 平均風速(m/s), 全天空日射量(MJ/m2)
            col_map = {
                'Temp': next((c for c in df.columns if '氣溫' in c or 'Temp' in c), None),
                'RH': next((c for c in df.columns if '濕度' in c or 'RH' in c), None),
                'Wind': next((c for c in df.columns if '風速' in c or 'Wind' in c), None),
                'Solar': next((c for c in df.columns if '日射' in c or 'Solar' in c), None),
                'Time': next((c for c in df.columns if '時間' in c or 'Time' in c), None)
            }

            if col_map['Time']:
                df['Time'] = pd.to_datetime(df[col_map['Time']], errors='coerce')
                df = df.dropna(subset=['Time'])
                df['Month'] = df['Time'].dt.month

                # 4. 分組計算月平均
                grp = df.groupby('Month')
                
                # 填入真實數據 (如果有讀到的話)
                # 使用 reindex(range(1,13)) 確保一定有 1~12 月的資料
                if col_map['Temp']: 
                    default_data['temps'] = grp[col_map['Temp']].mean().reindex(range(1,13), fill_value=25.0).tolist()
                    default_data['maxTemps'] = grp[col_map['Temp']].max().reindex(range(1,13), fill_value=30.0).tolist()
                    default_data['minTemps'] = grp[col_map['Temp']].min().reindex(range(1,13), fill_value=20.0).tolist()
                
                if col_map['Solar']:
                    # 處理空值填 0
                    s_mean = grp[col_map['Solar']].mean().fillna(0)
                    default_data['solar'] = s_mean.reindex(range(1,13), fill_value=12.0).tolist()

                if col_map['Wind']:
                    w_mean = grp[col_map['Wind']].mean().fillna(1.0)
                    default_data['wind'] = w_mean.reindex(range(1,13), fill_value=1.0).tolist()

                if col_map['RH']:
                    h_mean = grp[col_map['RH']].mean().fillna(75.0)
                    default_data['humidities'] = h_mean.reindex(range(1,13), fill_value=75.0).tolist()

        except Exception as e:
            print(f"⚠️ Error reading summary for {path}: {e}")
            # 發生錯誤時，直接回傳 default_data，確保系統不崩潰

        return default_data

    # 2. 讀取 24 小時動態資料 (Tab 2 使用)
    def read_hourly_data(self, filename):
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            try:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='cp950')
            except:
                df = pd.read_csv(path, header=1, usecols=[1, 4, 6, 7, 13], encoding='utf-8')
            
            df.columns = ['Time', 'Temp', 'RH', 'Wind', 'Solar']
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            
            for c in ['Temp', 'RH', 'Wind', 'Solar']:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                
            return df
        except: return None

    # 3. 進階光環境分析 (Tab 1 使用) - 已修復：改為自動抓取欄位名稱
    def analyze_advanced_light(self, filename, transmittance_percent=100):
        possible_paths = [os.path.join(self.base_folder, filename), os.path.join('data', filename), filename]
        target_path = next((p for p in possible_paths if os.path.exists(p)), None)
        
        if not target_path: 
            print("找不到檔案")
            return None

        try:
            # 1. 先讀取全部欄位 (不要只讀 [1, 13])
            try:
                df = pd.read_csv(target_path, header=1, encoding='cp950')
            except:
                df = pd.read_csv(target_path, header=1, encoding='utf-8')

            # 2. 自動找「時間」和「日射量」在哪一欄
            time_col = next((c for c in df.columns if '時間' in c or 'Time' in c), None)
            solar_col = next((c for c in df.columns if '日射' in c or 'Solar' in c or 'MJ' in c), None)

            if not time_col or not solar_col:
                print(f"找不到關鍵欄位: Time={time_col}, Solar={solar_col}")
                return None

            # 3. 重新命名並整理
            df = df[[time_col, solar_col]].copy()
            df.columns = ['Time', 'Raw_MJ']
            
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
            
            # 4. 計算光環境數值
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
            print(f"分析失敗: {e}")
            return None
        
    # 4. 讀取作物參數
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

    # 5. 計算月平均矩陣
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