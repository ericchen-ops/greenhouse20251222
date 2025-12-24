import os
import pandas as pd

class ClimateService:
    def __init__(self, base_folder='data/weather_data'):
        
        self.base_folder = base_folder

    def scan_and_load_weather_data(self):
        """讀取氣象資料 (包含月報表與時報表處理)"""
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

                # 2. 讀取 CSV (嘗試多種編碼)
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

                # 4. 統計運算
                data_dict = {'months': list(range(1, 13)), 'temps': [], 'maxTemps': [], 'minTemps': [], 'humidities': [], 'solar': [], 'wind': [], 'marketPrice': [30]*12}

                # 判斷資料量 (月資料 vs 時資料)
                if len(df) <= 24: 
                    monthly_grp = df.groupby('Month')
                    for m in range(1, 13):
                        if m in monthly_grp.groups:
                            g = monthly_grp.get_group(m)
                            data_dict['temps'].append(float(g[col_map['temp']].mean()))
                            
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
        """讀取詳細時報表"""
        path = os.path.join(self.base_folder, filename)
        if not os.path.exists(path): return None
        try:
            try: df = pd.read_csv(path, header=1, encoding='utf-8', on_bad_lines='skip')
            except: df = pd.read_csv(path, header=1, encoding='big5', on_bad_lines='skip')
            
            df.columns = [c.strip() for c in df.columns]
            rm = {}
            for c in df.columns:
                if '時間' in c or 'Time' in c: rm['Time'] = c
                elif '氣溫' in c or 'Temp' in c: rm['Temp'] = c
                elif '日射' in c or 'Solar' in c: rm['Solar'] = c
                elif '濕度' in c or 'RH' in c: rm['RH'] = c
                elif '平均風速' in c: rm['Wind'] = c
            
            cols = list(rm.values())
            df = df[cols].rename(columns={v:k for k,v in rm.items()})
            df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
            return df.dropna(subset=['Time'])
        except: return None