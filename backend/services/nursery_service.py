import pandas as pd
import os

class NurseryService:
    def __init__(self, data_path):
        """
        初始化：讀取 nursery_crops.csv
        """
        self.data_path = data_path
        self.csv_path = os.path.join(data_path, 'biological_data', 'nursery_crops.csv')
        self.nursery_df = pd.DataFrame()
        self.load_data()

    def load_data(self):
        """
        讀取 CSV 檔案，並進行基本的清理
        """
        if os.path.exists(self.csv_path):
            try:
                # 讀取 CSV
                df = pd.read_csv(self.csv_path)
                
                # 1. 清理欄位名稱：去除前後空白 (避免 ' Crop_Name' 這種情況)
                df.columns = [c.strip() for c in df.columns]
                
                # 2. 確保 Crop_Name 欄位存在
                if 'Crop_Name' in df.columns:
                    # 將作物名稱轉為字串並去除空白，方便後續比對
                    df['Crop_Name'] = df['Crop_Name'].astype(str).str.strip()
                    self.nursery_df = df
                    print(f"DEBUG: 成功載入育苗資料库，共 {len(df)} 筆作物。")
                else:
                    print("ERROR: nursery_crops.csv 缺少 'Crop_Name' 欄位")
                    
            except Exception as e:
                print(f"ERROR: 讀取育苗 CSV 失敗: {e}")
        else:
            print(f"WARNING: 找不到檔案 {self.csv_path}")

    def get_seedling_cost(self, crop_name, method=None):
        """
        根據作物名稱查詢育苗參數。
        
        Args:
            crop_name (str): 作物名稱 (如 '西瓜(嫁接)')
            method (str, optional): 繁殖方式 (Seed/Grafted/Runner)，可選。
        
        Returns:
            dict: 包含該作物 CSV 當中「所有欄位」的字典。
        """
        if self.nursery_df.empty:
            return None

        # 1. 搜尋作物 (不分大小寫)
        # 建立一個遮罩 (Mask)
        # 使用 str.lower() 增加比對成功率，並確保輸入也去除空白
        target = str(crop_name).strip().lower()
        
        # 在 DataFrame 中尋找 (比對小寫)
        # 這裡建立一個臨時欄位做比對，避免改動到原資料
        matches = self.nursery_df[self.nursery_df['Crop_Name'].str.lower() == target]

        if matches.empty:
            # 找不到時，嘗試模糊比對 (例如輸入 '草莓' 能找到 '一般草莓(走莖)')
            # 這是一個保險機制
            mask = self.nursery_df['Crop_Name'].str.lower().str.contains(target, regex=False)
            matches = self.nursery_df[mask]

        if matches.empty:
            return None

        # 2. 如果有指定 Method (例如 Seed 或 Grafted)，再過濾一次
        if method and 'Method' in matches.columns:
            method_matches = matches[matches['Method'].str.lower() == method.lower()]
            if not method_matches.empty:
                matches = method_matches

        # 3. 回傳結果
        # 取第一筆符合的資料
        row = matches.iloc[0]
        
        # ✨ 關鍵修改：直接轉成字典回傳，不做任何 Key 的重新命名 ✨
        # 這樣 SimulationService 就可以直接用 data['Market_Price_Buy_TWD'] 讀到了
        return row.to_dict()

    def get_all_crops(self):
        """
        回傳所有可用作物的清單 (用於前端下拉選單)
        """
        if not self.nursery_df.empty and 'Crop_Name' in self.nursery_df.columns:
            return self.nursery_df['Crop_Name'].unique().tolist()
        return []