import sys
import os

# 1. 強制將專案根目錄加入路徑 (解決 No module named 'backend' 的問題)
# 取得目前檔案位置 (.../backend/services/simulation_service.py)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 取得 backend 資料夾
parent_dir = os.path.dirname(current_dir)
# 取得 根目錄 (greenhouse20251222)
root_dir = os.path.dirname(parent_dir)

# 如果根目錄不在系統路徑中，就加進去
if root_dir not in sys.path:
    sys.path.append(root_dir)

# ==========================================
# 一般 import (現在可以正常讀取 backend 了)
# ==========================================
import math
import pandas as pd
import streamlit as st

# 2. 修正引用路徑
# 如果您的 PsychroModel 是放在 backend/services/psychro_model.py
try:
    from backend.services.psychro_model import PsychroModel
except ImportError:
    # 萬一您是放在 models 裡 (相容性備案)
    try:
        from backend.models.psychrometrics import PsychroModel
    except:
        pass # 暫時忽略，等用到再報錯

from backend.services.nursery_service import NurseryService

class SimulationService:
    # ... (原本的程式碼)
    @staticmethod
    @st.cache_data
    def run_simulation(gh_specs, fan_specs, climate, crops, density, cycles, prices, crop_db, mat_db):
        """
        核心模擬器 (Black Box) - 整合 PsychroModel + 平滑化邏輯 + ✨育苗成本分析
        """
        # 1. 初始化物理引擎
        psy = PsychroModel() 
        
        # ✨ 1. 初始化育苗服務 (動態取得路徑)
        # 假設此檔案在 backend/services/，我們要往上兩層找到 data 資料夾
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        data_path = os.path.join(base_dir, 'data')
        nursery_service = NurseryService(data_path)

        # 2. 幾何參數
        floor_area = gh_specs['width'] * gh_specs['length']
        vol_coef = gh_specs.get('_vol_coef', 1.2)
        surf_coef = gh_specs.get('_surf_coef', 1.15)
        vent_eff = gh_specs.get('_vent_eff', 1.0)
        
        volume = floor_area * gh_specs['gutterHeight'] * vol_coef
        surface_area = (floor_area * surf_coef) + (2 * (gh_specs['width'] + gh_specs['length']) * gh_specs['gutterHeight'])
        planting_area = floor_area * 0.6 
        
        # 3. 材料參數
        mat = mat_db.get(gh_specs['material'], {'uValue': 5.8, 'trans': 0.9})
        u_value = mat['uValue']
        trans = mat['trans']

        data = []
        total_revenue = 0; total_yield = 0; max_summer_temp = 0
        # ✨ 新增總成本變數
        total_seedling_cost = 0 

        # 4. 月份迴圈
        for i in range(12):
            crop = crop_db.get(crops[i], list(crop_db.values())[0])
            t_out = climate['temps'][i]; solar = climate['solar'][i]; wind = climate['wind'][i]; rh = climate['humidities'][i]

            # --- A. 熱平衡運算 ---
            t_trans = trans * (1 - gh_specs['shadingScreen']/100)
            q_solar = (solar * 1000000 / 43200) * floor_area * t_trans
            
            # 通風量計算
            vent_area = gh_specs['roofVentArea'] + gh_specs['sideVentArea']
            nat_vent = wind * vent_area * 0.4 * (gh_specs['insectNet']/100) * vent_eff
            forced_vent = (fan_specs['exhaustCount'] * fan_specs['exhaustFlow']) / 3600
            total_vent = nat_vent + forced_vent
            
            ach = (total_vent * 3600) / volume if volume > 0 else 0
            
            # 熱損失計算 (q_vent, q_cond)
            q_vent = total_vent * 1200  
            q_cond = u_value * surface_area
            
            # 溫差計算
            delta_t = q_solar / (q_vent + q_cond) if (q_vent + q_cond) > 0 else 0
            t_in = t_out + delta_t
            if i == 6: max_summer_temp = t_in
            
            # 計算 VPD
            vpd_in = psy.get_vpd(t_in, rh)

            # --- B. 高溫累積模擬 ---
            t_base = t_out + delta_t * 1.5
            h30_base = 0; h35_base = 0; h30_in = 0; h35_in = 0
            for h in range(24):
                diff = 5 * math.sin((h-9)*math.pi/12)
                if (t_base + diff) >= 30: h30_base += 1
                if (t_base + diff) >= 35: h35_base += 1
                if (t_in + diff) >= 30: h30_in += 1
                if (t_in + diff) >= 35: h35_in += 1

            # --- C. 生物產能運算 (平滑化邏輯) ---
            
            # 1. 溫度分數 (連續函數)
            t_diff = abs(t_in - crop['idealTemp'])
            score_temp = max(0, 1 - (t_diff / (crop['tempTolerance'] * 1.5)))
            
            # 循環扇全域加成
            if fan_specs['circCount'] > 0:
                score_temp *= 1.1

            # 2. VPD 分數 (梯形連續函數)
            score_vpd = 0.5 # 預設最低分
            if 0.8 <= vpd_in <= 1.2:
                score_vpd = 1.0
            elif 0.3 <= vpd_in < 0.8:
                score_vpd = 0.5 + 0.5 * ((vpd_in - 0.3) / 0.5)
            elif 1.2 < vpd_in <= 2.5:
                score_vpd = 1.0 - 0.5 * ((vpd_in - 1.2) / 1.3)
            
            # 3. 光照分數
            solar_in = solar * t_trans
            lsp = crop['lightSaturation'] 
            lcp = lsp * 0.2
            
            if solar_in >= lsp:
                score_light = 1.0
            elif solar_in <= lcp:
                score_light = 0.0
            else:
                score_light = (solar_in - lcp) / (lsp - lcp)
            
            # 4. 整合效率計算
            efficiency = score_temp * score_vpd * score_light
            
            # 產量與營收
            yield_kg = planting_area * density * crop['baseWeight'] * efficiency * (cycles / 12)
            rev = yield_kg * prices[i]

            # ✨ --- D. 育苗成本計算 (Integration) ---
            # 1. 計算本月需苗量：(種植面積 * 密度) * (年週轉率 / 12個月)
            monthly_plants_needed = planting_area * density * (cycles / 12)
                        
            # 2. 查詢單價 (取代舊的比價功能)
            # 直接去 CSV 查這個作物要多少錢
            n_data = nursery_service.get_seedling_cost(crop['name'])
            
            unit_cost = 0
            if n_data:
                # 成功找到：讀取 CSV 裡的 'Market_Price_Buy_TWD'
                unit_cost = float(n_data.get('Market_Price_Buy_TWD', 1.5))
                seedling_source = "外部採購 (CSV)"
            else:
                # 找不到：給一個預設值 (例如 1.5 元) 防止金額變 0
                unit_cost = 1.5 
                seedling_source = "預設價格"

            # 3. 計算總成本
            seedling_cost = monthly_plants_needed * unit_cost

            
            data.append({
                'month': i+1, 
                'cropName': crop['name'], 
                'tempOut': t_out, 
                'tempIn': t_in, 
                'vpd': vpd_in,
                'vIn': 0.5, 
                'ach': ach,
                'yield': yield_kg, 
                'revenue': rev, 
                # ✨ 新增輸出欄位
                'seedling_cost': seedling_cost, 
                'seedling_source': seedling_source,
                'seedling_unit_cost': unit_cost,
                # ----------------
                'efficiency': efficiency * 100,
                'heat30_Base': h30_base * 30, 'heat35_Base': h35_base * 30,
                'heat30_In': h30_in * 30, 'heat35_In': h35_in * 30
            })
            total_revenue += rev; total_yield += yield_kg
            total_seedling_cost += seedling_cost # ✨ 累加成本

        # ✨ 回傳結構新增 totalSeedlingCost 與 NetRevenue
        return {
            'data': data, 
            'totalYield': total_yield, 
            'totalRevenue': total_revenue, 
            'totalSeedlingCost': total_seedling_cost,
            'netRevenue': total_revenue - total_seedling_cost, # 粗估毛利
            'maxSummerTemp': max_summer_temp
        }
    

    def calculate_nursery_business_model(self, crop_name, gh_area_m2):
        """
        模擬【純育苗商業模式】的年獲利
        """
        # --- 1. 重新初始化 NurseryService (因為這是獨立功能) ---
        import os
        from backend.services.nursery_service import NurseryService
        
        # 動態抓取路徑 (確保能找到 CSV)
        current_file = os.path.abspath(__file__)
        services_dir = os.path.dirname(current_file)
        backend_dir = os.path.dirname(services_dir)
        root_dir = os.path.dirname(backend_dir)
        data_path = os.path.join(root_dir, 'data')
        
        # 初始化服務
        nursery_svc = NurseryService(data_path)
        # ----------------------------------------------------

        # 2. 取得單株數據 (注意這裡改用 nursery_svc，前面沒有 self)
        # 假設是種子繁殖 (Seed)
        nursery_data = nursery_svc.get_seedling_cost(crop_name, method='Seed')
        
        if not nursery_data:
            return None

        # 3. 定義育苗場的物理限制
        # 假設使用標準 128 格穴盤 (60cm x 30cm = 0.18 m2)
        effective_area = gh_area_m2 * 0.6 
        tray_area = 0.18 
        trays_capacity = int(effective_area / tray_area) 
        
        plants_per_batch = trays_capacity * 128 
        
        # 4. 計算年周轉率
        days_per_cycle = nursery_data['days_needed'] + 10
        cycles_per_year = 312 / days_per_cycle
        
        # 5. 財務試算
        price_per_plant = nursery_data['market_price'] 
        annual_revenue = plants_per_batch * cycles_per_year * price_per_plant
        
        cost_per_plant = nursery_data['cost_per_plant']
        annual_cogs = plants_per_batch * cycles_per_year * cost_per_plant
        
        gross_profit = annual_revenue - annual_cogs

        return {
            'mode': 'Pure Nursery (純育苗)',
            'annual_cycles': round(cycles_per_year, 1),
            'total_plants_year': int(plants_per_batch * cycles_per_year),
            'revenue': int(annual_revenue),
            'cost': int(annual_cogs),
            'profit': int(gross_profit),
            'profit_margin': round((gross_profit / annual_revenue)*100, 1) if annual_revenue > 0 else 0
        }
    
   

    def run_pure_nursery_simulation(self, selected_crop_names, gh_specs, cost_params_backup, 
                                  climate_data, fan_specs):
        """
        純育苗場模擬 (台一育苗場參數校正版 - Tai-Yi Calibration)
        根據實際訪談數據，大幅下修空間利用率與產能，反映真實農業現場的「淡旺季」與「實際坪效」。
        """
        import os
        import pandas as pd
        from backend.services.nursery_service import NurseryService
        
        # 1. 初始化
        current_file = os.path.abspath(__file__)
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        data_path = os.path.join(backend_dir, 'data')
        nursery_svc = NurseryService(data_path)

        # ==========================================
        # 🔧 參數調校：校正回歸 (基於台一訪談數據)
        # ==========================================
        # 空間利用率：從 0.85 下修至 0.35
        # 原因：台一 3公頃產 6600萬株 = 2200萬株/公頃/年
        # 模型原本算出來是 7200萬株/公頃/年
        # 修正係數 = 2200 / 7200 ≈ 0.30 ~ 0.35
        # 這 35% 代表實際鋪滿苗的比例，其他包含走道、工作區、或是淡季閒置區
        REALITY_FACTOR_SPACE = 0.40      
        
        # 銷售良率：128穴賣120株，良率約 93.75% (8株容錯)
        BASE_SALES_RATE = 125 / 128      
        
        # 換檔期：拉長至 7 天 (反映訂單銜接的空窗期)
        GAP_DAYS = 5                     
        
        # 雜項成本：維持 3% (B2B 模式)
        MISC_COST_RATE = 0.03            
        
        # 超溫扣分：維持溫和扣分
        STRESS_PENALTY_PER_DEGREE = 0.02
        # ==========================================

        # 2. 定義產能與規模
        width = gh_specs.get('width', 30)
        length = gh_specs.get('length', 60)
        total_area_m2 = width * length
        total_area_ping = total_area_m2 * 0.3025 

        # 這裡的 bench_area 已經乘上了 0.35 的修正係數
        bench_area = total_area_m2 * REALITY_FACTOR_SPACE 
        trays_capacity = int(bench_area / 0.18)
        
        # 這是「單批次」的極限產能 (已打折)
        max_plants_per_batch = trays_capacity * 128

        monthly_financials = []
        
        # ==========================================
        # 💰 固定成本：讀取 cost_parameters (COST_DB)
        # ==========================================
        structure_unit_price = float(cost_params_backup.get('Greenhouse_Structure_Price', 4500))
        life_years = float(cost_params_backup.get('Structure_Life_Year', 15))
        
        calculated_investment = total_area_m2 * structure_unit_price
        depreciation = calculated_investment / life_years / 12
    

        print(f"DEBUG: 台一參數校正版。利用率: {REALITY_FACTOR_SPACE*100}%, 預估年產能: {max_plants_per_batch * 10}株")

        # 4. 跑 12 個月
        for i in range(12):
            month = i + 1
            
            # --- A. 氣候運算 ---
            t_out = climate_data['temps'][i]
            solar = climate_data['solar'][i]
            
            shading_rate = gh_specs.get('shadingScreen', 0) / 100.0
            fan_count = fan_specs.get('exhaustCount', 0)
            fan_flow_per_unit = fan_specs.get('exhaustFlow', 40000)
            total_exhaust_flow = fan_count * fan_flow_per_unit
            
            g_h = gh_specs.get('gutterHeight', 4.0)
            avg_height = g_h + 1.0 
            volume = (width * length) * avg_height
            ach = total_exhaust_flow / volume if volume > 0 else 0
            
            heat_load_factor = solar * (1 - shading_rate)
            cooling_capacity = ach * 0.8 + 5.0 
            delta_t = (heat_load_factor * 100) / cooling_capacity
            t_in = t_out + delta_t
            
            min_possible_t = t_out - 0.5
            if t_in < min_possible_t: t_in = min_possible_t

            # --- B. 決定作物 ---
            target_crop = None
            if selected_crop_names:
                for name in selected_crop_names:
                    clean_name = str(name).strip()
                    info = nursery_svc.get_seedling_cost(clean_name)
                    if info:
                        prod_months_str = str(info.get('Production_Months', 'All'))
                        is_production_month = False
                        if 'All' in prod_months_str:
                            is_production_month = True
                        else:
                            try:
                                allowed_months = [int(m.strip()) for m in prod_months_str.split(',') if m.strip().isdigit()]
                                if month in allowed_months:
                                    is_production_month = True
                            except:
                                is_production_month = False
                        
                        # 特殊邏輯：如果是甘藍，且是「All」，我們手動模擬「大小月」
                        # 假設 6-9月 (夏天高山熱季) 是大月，11-1月 (平地) 也是大月
                        # 3-5月 可能稍微淡一點 (這只是假設，可根據訪談調整)
                        if is_production_month:
                            target_crop = clean_name
                            break
            
            # --- C. 填寫數據 ---
            row_data = {
                'month': month, 'season': 'N/A',
                'temp_out': round(t_out, 1), 'temp_in': round(t_in, 1),
                'crop': "休耕/非產期",
                'production': 0, 'revenue': 0, 'var_cost': 0,
                'fixed_cost': int(depreciation ),
                'net_profit': 0, 'margin': 0, 'survival_rate': 0
            }
            row_data['net_profit'] = -row_data['fixed_cost']

            if target_crop:
                data = nursery_svc.get_seedling_cost(target_crop)
                if data:
                    row_data['crop'] = target_crop
                    
                    price = float(data.get('Market_Price_Buy_TWD', 0))
                    c_seed = float(data.get('Seed_Cost_TWD', 0))
                    c_sub = float(data.get('Substrate_Cost_TWD', 0))
                    c_labor = float(data.get('Labor_Cost_TWD', 0))
                    
                    unit_var_cost = c_seed + c_sub + c_labor
                    
                    days = int(data.get('Nursery_Days', 30))
                    min_t = float(data.get('Min_Temp_C', 10))
                    max_t = float(data.get('Max_Temp_C', 30))
                    germ_rate = float(data.get('Germination_Rate', 0.9))

                    # 氣候逆境
                    weather_survival_factor = 1.0
                    stress_msg = ""
                    BUFFER_TEMP = 3.0 

                    if t_in > (max_t + BUFFER_TEMP):
                        excess_temp = t_in - (max_t + BUFFER_TEMP)
                        penalty = excess_temp * STRESS_PENALTY_PER_DEGREE
                        if penalty > 0.6: penalty = 0.6 
                        weather_survival_factor -= penalty
                        stress_msg = "🔥熱逆境"
                    
                    if t_in < (min_t - BUFFER_TEMP):
                        lack_temp = (min_t - BUFFER_TEMP) - t_in
                        penalty = lack_temp * 0.03
                        if penalty > 0.4: penalty = 0.4
                        weather_survival_factor -= penalty
                        stress_msg = "❄️寒害"

                    weather_survival_factor = max(0.2, weather_survival_factor)
                    final_success_rate = BASE_SALES_RATE * germ_rate * weather_survival_factor
                    
                    cycles = 30 / (days + GAP_DAYS) if days > 0 else 1
                    
                    # ⚠️ 這裡的 input 已經乘過 0.35 的係數了，反映了真實的產能
                    total_seeds_input = max_plants_per_batch * cycles
                    
                    # 銷售量
                    sellable_plants = total_seeds_input * final_success_rate
                    
                    # 財務計算
                    rev = sellable_plants * price
                    var = total_seeds_input * unit_var_cost
                    fix = depreciation + (rev * MISC_COST_RATE)
                    
                    row_data['production'] = int(sellable_plants)
                    row_data['revenue'] = int(rev)
                    row_data['var_cost'] = int(var)
                    row_data['fixed_cost'] = int(fix)
                    row_data['net_profit'] = int(rev - var - fix)
                    row_data['margin'] = round((row_data['net_profit']/rev)*100, 1) if rev>0 else 0
                    row_data['survival_rate'] = round(final_success_rate * 100, 1)
                    
                    if stress_msg:
                        row_data['crop'] = f"{target_crop} ({stress_msg})"
                else:
                    row_data['crop'] = f"{target_crop} (CSV缺資料)"

            monthly_financials.append(row_data)

        # 5. 彙總
        total_rev = sum(x['revenue'] for x in monthly_financials)
        total_var = sum(x['var_cost'] for x in monthly_financials)
        total_fix = sum(x['fixed_cost'] for x in monthly_financials)
        total_net = sum(x['net_profit'] for x in monthly_financials)

        return {
            'overview': {
                'total_revenue': total_rev,
                'total_var_cost': total_var,
                'total_fixed_cost': total_fix,
                'net_profit': total_net,
                'roi': round((total_net / calculated_investment) * 100, 1),
                'max_capacity_per_batch': int(max_plants_per_batch * 10) # 顯示年化產能估計
            },
            'monthly_data': monthly_financials
        }