import pandas as pd
import os
import sys

# --- 路徑導航 (確保找得到 backend) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# 引用物理模型
from backend.models.psychrometrics import PsychroModel

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        self.base_folder = base_folder
        self.psy_model = PsychroModel(p_atm_kpa=101.325)

    # ... (在 ClimateService 類別中) ...

    def analyze_advanced_light(self, filename, transmittance_percent=100):
        """
        讀取氣象局原始 CSV，計算進階光環境指標 (PPFD, DLI, Wh)
        :param filename: 原始 CSV 檔名
        :param transmittance_percent: 透光率 (100=室外, <100=室內)
        :return: 處理好、包含所有指標的 DataFrame
        """
        # 1. 組合路徑 (支援多種位置搜尋)
        possible_paths = [
            os.path.join(self.base_folder, filename), # data/weather_data/xxx.csv
            os.path.join('data', filename),           # data/xxx.csv
            filename                                  # xxx.csv
        ]
        
        target_path = None
        for p in possible_paths:
            if os.path.exists(p):
                target_path = p
                break
        
        if not target_path:
            return None # 找不到檔案

        try:
            # 2. 讀取原始數據 (封裝髒活：處理 header=1 和結尾逗號)
            # 氣象局格式：第2行才是標題，只取時間(col 1)和日射量(col 13)
            df = pd.read_csv(target_path, header=1, usecols=[1, 13], encoding='utf-8')
            df.columns = ['Time', 'Raw_MJ'] # 重新命名
            
            # 3. 數據清洗
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            df['Raw_MJ'] = pd.to_numeric(df['Raw_MJ'], errors='coerce').fillna(0)
            
            # 4. 核心運算 (Backend 負責物理轉換)
            ratio = transmittance_percent / 100.0
            
            # 基礎值 (MJ/m²)
            df['Val_MJ'] = df['Raw_MJ'] * ratio
            
            # 轉換值
            # 1 MJ = 277.78 Wh
            df['Val_Wh'] = df['Val_MJ'] * 277.78
            
            # 1 MJ (Solar) ≈ 571.2 umol (PPFD) (寬頻光譜估算值)
            df['Val_PPFD'] = df['Val_MJ'] * 571.2
            
            # DLI 貢獻量 (每小時) = PPFD * 3600秒 / 1,000,000 (轉mol)
            # 簡化公式: 1 MJ ≈ 2.056 mol (PAR)
            df['Val_DLI_Hr'] = df['Val_MJ'] * 2.056

            # 補上時間特徵 (方便前端繪圖)
            df['Date'] = df['Time'].dt.date.astype(str)
            df['Hour'] = df['Time'].dt.hour
            
            return df
            
        except Exception as e:
            print(f"光環境分析錯誤: {e}")
            return None

    def scan_and_load_weather_data(self):
        """
        [完整邏輯補完] 讀取氣象資料並計算月統計數據 (Tab 1 專用)
        """
        loaded_locations = {}
        if not os.path.exists(self.base_folder): return {}

        files = [f for f in os.listdir(self.base_folder) if f.endswith('.csv')]
        for f in files:
            path = os.path.join(self.base_folder, f)
            try:
                # 1. 抓取測站名稱
                station_name = f.split('.')[0]
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                        if '測站' in file.readline():
                            parts = file.readline().split(',')
                            if len(parts) > 1: station_name = parts[1].strip()
                except: pass

                # 2. 讀取 CSV
                try: df = pd.read_csv(path, header=1, encoding='utf-8', on_bad_lines='skip')
                except: 
                    try: df = pd.read_csv(path, header=1, encoding='big5', on_bad_lines='skip')
                    except: df = pd.read_csv(path, header=0, encoding='utf-8', on_bad_lines='skip')

                df.columns = [c.strip() for c in df.columns]
                
                # 3. 欄位對照
                col_map = {}
                for c in df.columns:
                    if '時間' in c or 'Time' in c: col_map['time'] = c
                    elif '氣溫' in c or 'Temp' in c: col_map['temp'] = c
                    elif '濕度' in c or 'RH' in c: col_map['rh'] = c
                    elif '風速' in c or 'Wind' in c: col_map['wind'] = c
                    elif '日射' in c or 'Solar' in c: col_map['solar'] = c

                if 'time' not in col_map: continue 

                df['Date'] = pd.to_datetime(df[col_map['time']], errors='coerce')
                df = df.dropna(subset=['Date'])
                df['Month'] = df['Date'].dt.month
                
                for k, col in col_map.items():
                    if k != 'time': df[col] = pd.to_numeric(df[col], errors='coerce')

                # 4. [關鍵] 統計運算 (這裡一定要產生 maxTemps 等欄位)
                data_dict = {'months': list(range(1, 13)), 'temps': [], 'maxTemps': [], 'minTemps': [], 'humidities': [], 'solar': [], 'wind': [], 'marketPrice': [30]*12}

                # 判斷資料量 (月資料 vs 時資料)
                if len(df) <= 24: 
                    monthly_grp = df.groupby('Month')
                    for m in range(1, 13):
                        if m in monthly_grp.groups:
                            g = monthly_grp.get_group(m)
                            data_dict['temps'].append(float(g[col_map['temp']].mean()))
                            
                            # 抓取最高/最低溫
                            max_c = next((c for c in df.columns if '最高' in c and '溫' in c), col_map['temp'])
                            min_c = next((c for c in df.columns if '最低' in c and '溫' in c), col_map['temp'])
                            data_dict['maxTemps'].append(float(g[max_c].max()))
                            data_dict['minTemps'].append(float(g[min_c].min()))
                            
                            data_dict['humidities'].append(float(g[col_map.get('rh', col_map['temp'])].mean()))
                            data_dict['wind'].append(float(g[col_map.get('wind', col_map['temp'])].mean()))
                            
                            if 'solar' in col_map:
                                val = g[col_map['solar']].mean()
                                if val > 50: val /= 30 
                                data_dict['solar'].append(float(val))
                            else: data_dict['solar'].append(12.0)
                        else:
                            for k in ['temps','maxTemps','minTemps','humidities','solar','wind']: data_dict[k].append(0)
                else: 
                     for m in range(1, 13):
                        g = df[df['Month'] == m]
                        if not g.empty:
                            data_dict['temps'].append(float(g[col_map['temp']].mean()))
                            # 時資料統計 Max/Min
                            data_dict['maxTemps'].append(float(g[col_map['temp']].max()))
                            data_dict['minTemps'].append(float(g[col_map['temp']].min()))
                            
                            data_dict['humidities'].append(float(g[col_map.get('rh', col_map['temp'])].mean()))
                            data_dict['wind'].append(float(g[col_map.get('wind', col_map['temp'])].mean()))
                            
                            if 'solar' in col_map:
                                daily_s = g.groupby(g['Date'].dt.date)[col_map['solar']].sum()
                                data_dict['solar'].append(float(daily_s.mean()))
                            else: data_dict['solar'].append(12.0)
                        else:
                            for k in ['temps','maxTemps','minTemps','humidities','solar','wind']: data_dict[k].append(0)

                loaded_locations[station_name] = {'id': station_name, 'name': station_name, 'description': f'File: {f}', 'data': data_dict}
            except: continue
        return loaded_locations

    def read_hourly_data(self, filename):
        """
        讀取詳細時報表 (並呼叫 PsychroModel 進行運算)
        """
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            # 1. 讀取 CSV
            try: df = pd.read_csv(path, header=1, encoding='utf-8', on_bad_lines='skip')
            except: df = pd.read_csv(path, header=1, encoding='big5', on_bad_lines='skip')
            
            # 2. 欄位處理
            df.columns = [c.strip() for c in df.columns]
            rm = {}
            for c in df.columns:
                if '時間' in c or 'Time' in c: rm['Time'] = c
                elif '氣溫' in c or 'Temp' in c: rm['Temp'] = c
                elif '日射' in c or 'Solar' in c: rm['Solar'] = c
                elif '濕度' in c or 'RH' in c: rm['RH'] = c
                elif '平均風速' in c or 'Wind' in c: rm['Wind'] = c
                elif '氣壓' in c or 'Press' in c: rm['Press'] = c
                elif '露點' in c or 'Dew' in c: rm['DewRaw'] = c
            
            cols = list(rm.values())
            df = df[cols].rename(columns={v:k for k,v in rm.items()})
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            df = df.dropna(subset=['Time'])
            
            # 3. 物理運算 (使用 ASAE 方法)
            results = []
            for index, row in df.iterrows():
                try:
                    t = float(row.get('Temp', 25))
                    rh = float(row.get('RH', 80))
                    
                    # 更新大氣壓
                    p_atm_hpa = float(row.get('Press', 1013.25))
                    self.psy_model.P_atm = p_atm_hpa / 10.0 
                    
                    # 呼叫 ASAE 方法
                    pw = self.psy_model.get_partial_vapor_pressure(t, rh)
                    vpd = self.psy_model.get_vpd(t, rh)
                    w = self.psy_model.get_humidity_ratio(pw)
                    enthalpy = self.psy_model.get_enthalpy(t, w)
                    
                    # 露點 (優先用實測)
                    if 'DewRaw' in row and not pd.isna(row['DewRaw']):
                        dew_point = float(row['DewRaw'])
                    else:
                        dew_point = self.psy_model.get_dew_point(pw)
                    
                    results.append({
                        "Time": row['Time'],
                        "Temp": t,
                        "RH": rh,
                        "Solar": float(row.get('Solar', 0)),
                        "Wind": float(row.get('Wind', 0)),
                        "VPD": round(vpd, 2),
                        "DewPoint": round(dew_point, 1),
                        "Enthalpy": round(enthalpy, 1),
                        "HumidityRatio": round(w * 1000, 2)
                    })
                except: continue
            
            return pd.DataFrame(results)

        except Exception as e: 
            print(f"Error reading hourly data: {e}")
            return None