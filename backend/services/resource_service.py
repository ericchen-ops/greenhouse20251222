import os
import pandas as pd

class ResourceService:
    def __init__(self, data_path):
        # ✅ 修改前：
        # self.cost_df = pd.read_csv(f"{data_path}/cost_parameters.csv", encoding='utf-8-sig')

        # ✅ 修改後：使用 os.path.join 自動處理斜線
        csv_path = os.path.join(data_path, 'cost_parameters.csv')
        
        # 加入檢查機制，告訴您程式到底在找哪裡
        if not os.path.exists(csv_path):
            print(f"❌ 嚴重錯誤：找不到檔案！程式預期路徑為：{csv_path}")
            # 這裡可以選擇拋出錯誤或建立空 DataFrame
            self.cost_df = pd.DataFrame() 
        else:
            self.cost_df = pd.read_csv(csv_path, encoding='utf-8-sig')

    def load_crop_database(self, filename='crops.csv'):
        path = os.path.join(self.data_path, filename)
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
        path = os.path.join(self.data_path, filename)
        
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
        path = os.path.join(self.data_path, folder_name, filename)
        
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

    # --- [新增] 讀取成本參數設定 ---
    def load_cost_parameters(self, filename='cost_parameters.csv'):
        """
        讀取成本參數 CSV 並轉為字典，方便用 Key 查詢數值
        """
        path = os.path.join(self.data_path, filename)
        default_costs = {}
        
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                # 轉成字典格式: {'Electricity_Rate': 4.0, 'Fan_Unit_Price': 15000, ...}
                # 確保 Value 欄位是數字
                df['Value'] = pd.to_numeric(df['Value'], errors='coerce').fillna(0)
                default_costs = dict(zip(df['Item'], df['Value']))
            except Exception as e:
                print(f"Error reading cost parameters: {e}")
                
        return default_costs


    def __init__(self, data_path):
        self.cost_df = pd.read_csv(f"{data_path}/cost_parameters.csv", encoding='utf-8-sig')
        
        self.data_path = data_path 
        
        # 接著才是原本的讀取邏輯
        self.csv_path = os.path.join(data_path, 'cost_parameters.csv')

    def calculate_costs(self, crop_type, gh_area_m2):
        """
        根據作物類型 (crop_type) 過濾適用設備，並計算總部與加盟主的拆帳
        """
        # 1. 標籤過濾：只選取 "All" 或者 "符合當前作物" 的項目
        # 例如：如果 crop_type 是 'Strawberry' (草莓)，會抓到 'All', 'Soil', 'Berry' 標籤
        # 這裡做簡單字串比對，實際可寫更複雜
        def is_applicable(tags):
            tags_list = tags.split(',')
            return 'All' in tags_list or crop_type in tags_list

        # 篩選出適用的成本項目
        df_filtered = self.cost_df[self.cost_df['Applicable_Tags'].apply(is_applicable)].copy()

        # 2. 計算總金額 (Value * 數量)
        # 注意：這裡只是簡化範例，實際計算需依 Item 判斷 (有些是單價/m2，有些是/unit)
        # 您原本的程式應該有處理這段 "Unit" 的邏輯，這裡假設我們已算出 'Total_Amount'
        
        # --- 模擬計算邏輯 (請替換回您原本的詳細運算) ---
        df_filtered['Calculated_Cost'] = 0
        for index, row in df_filtered.iterrows():
            if row['Unit'] == 'NTD/m2':
                df_filtered.at[index, 'Calculated_Cost'] = row['Value'] * gh_area_m2
            elif row['Unit'] == 'NTD/unit': 
                # 假設每 200m2 需要一台
                count = max(1, gh_area_m2 / 200) 
                df_filtered.at[index, 'Calculated_Cost'] = row['Value'] * count
            # ... 其他單位邏輯 ...

        # 3. 核心修改：依 Payer (支付者) 進行 GroupBy 分組加總
        summary = df_filtered.groupby(['Type', 'Payer'])['Calculated_Cost'].sum().unstack(fill_value=0)
        
        # 轉換成容易讀取的字典
        return {
            'Headquarters': {
                'CAPEX': summary.get('Headquarters', {}).get('CAPEX', 0),
                'OPEX': summary.get('Headquarters', {}).get('OPEX', 0),
                'Depreciation': summary.get('Headquarters', {}).get('Depreciation', 0)
            },
            'Franchisee': {
                'CAPEX': summary.get('Franchisee', {}).get('CAPEX', 0), # 加盟主通常 CAPEX 少
                'OPEX': summary.get('Franchisee', {}).get('OPEX', 0),   # 加盟主負責營運
                'Depreciation': summary.get('Franchisee', {}).get('Depreciation', 0)
            }
        }
