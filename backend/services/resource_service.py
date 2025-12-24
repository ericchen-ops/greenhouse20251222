import os
import pandas as pd

class ResourceService:
    def __init__(self, data_root='data'):
        self.data_root = data_root

    def load_crop_database(self, filename='crops.csv'):
        path = os.path.join(self.data_root, filename)
        # 預設作物資料
        default = {'lettuce': {'id': 'lettuce', 'name': '萵苣', 'idealTemp': 20, 'tempTolerance': 6, 'baseWeight': 0.35, 'cycleDays': 45, 'lightSaturation': 11, 'lightSlope': 1.2, 'price': 45}}
        
        if not os.path.exists(path): return default
        try:
            df = pd.read_csv(path)
            # 將 ID 當作 Key 轉成字典
            return {row['id']: row.to_dict() for _, row in df.iterrows()}
        except: return default

    # ★★★ 修正重點 1: 專門讀取材料並回傳 Dictionary ★★★
    def load_material_database(self, filename='greenhouse_materials.csv'):
        # 組合路徑: data/equipment_data/greenhouse_materials.csv
        path = os.path.join(self.data_root, filename)
        
        # 預設值 (字典格式)
        default = {'glass': {'label': '散射玻璃 (Glass) - 預設', 'trans': 0.9, 'uValue': 5.8}}
        
        if not os.path.exists(path): 
            print(f"⚠️ 找不到材料檔: {path}") # 印出警告方便除錯
            return default
            
        try:
            df = pd.read_csv(path)
            
            # 建立字典
            mat_dict = {}
            for _, row in df.iterrows():
                code = str(row['Material_Code'])
                mat_type = str(row['Material_Type'])
                
                # U值簡易判斷
                if 'Glass' in mat_type: u_val = 5.8
                elif str(row.get('Thermic','No')) == 'Yes': u_val = 4.5
                else: u_val = 6.0
                
                # 取得穿透率，若無欄位給預設值
                trans_val = float(row.get('Light_Transmittance_Rate', 0.85))

                mat_dict[code] = {
                    'label': f"{mat_type}", 
                    'trans': trans_val, 
                    'uValue': u_val
                }
            
            # ★ 絕對回傳字典
            return mat_dict 
            
        except Exception as e: 
            print(f"❌ 讀取材料檔失敗: {e}")
            return default

    # ★★★ 修正重點 2: 通用設備讀取 (回傳 DataFrame) ★★★
    def load_equipment_csv(self, folder_name, filename, eq_type='fan', filter_col=None, filter_val=None):
        path = os.path.join(self.data_root, folder_name, filename)
        
        if not os.path.exists(path): 
            return pd.DataFrame() # 找不到檔案回傳空表格
            
        try:
            df = pd.read_csv(path)
            df.columns = [c.strip() for c in df.columns] # 清除欄位空白
            
            # 過濾功能 (例如只抓 排風扇)
            if filter_col and filter_val:
                if filter_col in df.columns:
                    # 使用 str.contains 做模糊比對，避免大小寫或空白導致過濾失敗
                    df = df[df[filter_col].astype(str).str.contains(filter_val, case=False, na=False)]
            
            # 建立顯示用的 Label
            if eq_type == 'fan':
                # 確保欄位存在才合併
                if 'Model' in df.columns and 'Airflow_CMH' in df.columns:
                    df['Label'] = df['Model'].astype(str) + " (" + df['Airflow_CMH'].astype(str) + " CMH)"
            elif eq_type == 'net':
                if 'Mesh' in df.columns:
                    df['Label'] = df['Mesh'].astype(str) + "目"
            elif eq_type == 'fog':
                if 'Spray_Capacity_g_m2_hr' in df.columns:
                    df['Label'] = df['Spray_Capacity_g_m2_hr'].astype(str) + " g/m²/hr"
                
            return df
        except: return pd.DataFrame()