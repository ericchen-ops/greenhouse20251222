import math
import streamlit as st
# 引入物理模型
from backend.models.psychrometrics import PsychroModel 

class SimulationService:
    @staticmethod
    @st.cache_data
    def run_simulation(gh_specs, fan_specs, climate, crops, density, cycles, prices, crop_db, mat_db):
        """
        核心模擬器 (Black Box) - 整合 PsychroModel + 平滑化邏輯版
        """
        # 1. 初始化物理引擎
        psy = PsychroModel() 

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
            
            # 循環扇全域加成 (平滑化：移除 >30度 的硬門檻)
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
            
            # 3. 光照分數 (補回這段邏輯)
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
                'efficiency': efficiency * 100,
                'heat30_Base': h30_base * 30, 'heat35_Base': h35_base * 30,
                'heat30_In': h30_in * 30, 'heat35_In': h35_in * 30
            })
            total_revenue += rev; total_yield += yield_kg

        return {'data': data, 'totalYield': total_yield, 'totalRevenue': total_revenue, 'maxSummerTemp': max_summer_temp}