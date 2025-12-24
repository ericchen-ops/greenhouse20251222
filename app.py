import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import os

# --- [關鍵修改] 引用新的後端服務 ---
from backend.services.climate_service import ClimateService
from backend.services.resource_service import ResourceService
from backend.services.market_service import MarketService
from backend.services.simulation_service import SimulationService

# --- 設定頁面 ---
st.set_page_config(page_title="溫室環境決策系統 V7.0 (MVC版)", page_icon="🌿", layout="wide")

# ==========================================
# 1. 系統初始化 (實例化服務並讀取資料)
# ==========================================

# 初始化服務 (Service Instantiation)
# 這裡定義資料夾路徑，讓 Service 知道去哪裡抓資料
climate_svc = ClimateService(base_folder='data/weather_data')
resource_svc = ResourceService(data_root='data')
market_svc = MarketService(base_folder='data/market_data')

# --- [修改後的資料載入區塊] ---

# 透過服務載入資料
CROP_DB = resource_svc.load_crop_database()
WEATHER_DB = climate_svc.scan_and_load_weather_data()
MARKET_DB = market_svc.scan_and_load_market_prices()

# 載入設備庫 (呼叫 ResourceService)
FAN_DB = resource_svc.load_equipment_csv('equipment_data', 'greenhouse_fans.csv', 'fan')
CIRC_DB = resource_svc.load_equipment_csv('equipment_data', 'greenhouse_fans.csv', 'fan', 'Category', 'Circulation')
NET_DB = resource_svc.load_equipment_csv('equipment_data', 'insect_nets.csv', 'net')
FOG_DB = resource_svc.load_equipment_csv('equipment_data', 'foggingsystem.csv', 'fog')
MAT_DB = resource_svc.load_material_database(os.path.join('equipment_data', 'greenhouse_materials.csv'))

# 內建預設值 (如果讀不到天氣檔時用)
if not WEATHER_DB:
    WEATHER_DB = {'demo': {'id': 'demo', 'name': '範例氣候', 'data': {'months': list(range(1,13)), 'temps':[25]*12, 'solar':[12]*12, 'wind':[1]*12, 'humidities':[75]*12, 'marketPrice':[30]*12}}}

# Session State 初始化
if 'monthly_crops' not in st.session_state: st.session_state.monthly_crops = ['lettuce'] * 12
if 'planting_density' not in st.session_state: st.session_state.planting_density = 25.0
if 'annual_cycles' not in st.session_state: st.session_state.annual_cycles = 15.0

# 標題區
c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/2942/2942544.png", width=80)
with c2: st.title("溫室模擬與環境分析系統 V7.0"); st.markdown("模組化架構：Backend Services")

# 側邊欄：地區選擇
with st.sidebar:
    st.header("基礎設定")
    loc_id = st.selectbox("選擇模擬地區", list(WEATHER_DB.keys()), format_func=lambda x: WEATHER_DB[x]['name'])
    CURR_LOC = WEATHER_DB[loc_id]
    st.caption(CURR_LOC.get('description', ''))
    
    # 載入該地區價格
    if 'market_prices' not in st.session_state: st.session_state.market_prices = CURR_LOC['data']['marketPrice'].copy()

# ==========================================
# 2. 前端介面邏輯
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["1. 外部環境", "2. 內部微氣候", "3. 產能價格", "4. 邊際效益"])

# --- Tab 1: 外部環境 ---
with tab1:
    st.subheader(f"📍 {CURR_LOC['name']} - 氣候數據")
    
    # 1. 準備資料
    c_data = CURR_LOC['data']
    df_clim = pd.DataFrame({
        'Month': c_data['months'], 
        'Temp': c_data['temps'], 
        'MaxTemp': c_data['maxTemps'], 
        'MinTemp': c_data['minTemps'],
        'Solar': c_data['solar']
    })
    # 單位轉換
    df_clim['Solar_W'] = df_clim['Solar'] * 11.574 

    # 2. 版面配置
    col1, col2 = st.columns([1, 1.5]) 
    
    # --- 左側：全年氣候趨勢 ---
    with col1:
        st.markdown("##### 全年氣候趨勢圖")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df_clim['Month'], y=df_clim['Temp'], name="平均氣溫", marker_color='orange', opacity=0.6), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['MaxTemp'], name="最高溫", line=dict(color='#ef4444', dash='dot', width=1)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['MinTemp'], name="最低溫", line=dict(color='#3b82f6', dash='dot', width=1)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['Solar_W'], name="日射量 (W/m²)", line=dict(color='#f59e0b', width=3)), secondary_y=True)
        
        fig.update_layout(
            height=450, 
            template="plotly_dark", 
            hovermode="x unified", 
            legend=dict(orientation="h", y=1.15, x=0), 
            margin=dict(l=10, r=10, t=50, b=10),
        
            xaxis=dict(
                tickmode='linear',  # 設定刻度模式為線性
                dtick=1,            # 強制每一個單位顯示一個刻度
                range=[0.5, 12.5]   # (選用) 稍微留邊，讓 1月和 12月的 Bar 不會貼齊邊緣
            )
            # -----------------
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- 右側：氣溫與輻射量分布 ---
    with col2:
        st.markdown("##### 氣溫與日射量分布 ")
        scatter_points = []
        np.random.seed(42)
        for i, m in enumerate(df_clim['Month']):
            base_temp = df_clim.loc[i, 'Temp']; base_solar = df_clim.loc[i, 'Solar_W']
            sim_temps = np.random.normal(loc=base_temp, scale=2.5, size=30)
            sim_solars = np.random.normal(loc=base_solar, scale=40, size=30)
            for t, s in zip(sim_temps, sim_solars): scatter_points.append({'Temp': t, 'Solar_W': max(0, s)})
        
        df_scatter = pd.DataFrame(scatter_points)
        first_row = df_clim.iloc[[0]]
        df_loop = pd.concat([df_clim, first_row], ignore_index=True)
        text_labels = [f"{int(m)}月" for m in df_loop['Month']]; text_labels[-1] = "" 

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_scatter['Temp'], y=df_scatter['Solar_W'], mode='markers', name='日分佈模擬', marker=dict(color='rgba(100, 180, 255, 0.3)', size=6), hoverinfo='none'))
        fig2.add_trace(go.Scatter(x=df_loop['Temp'], y=df_loop['Solar_W'], mode='lines+markers+text', name='月均值', text=text_labels, textposition="top center", textfont=dict(size=12, color='white'), line=dict(color='#ff7f0e', width=4), marker=dict(color='#ff7f0e', size=10)))

        fig2.update_layout(height=450, template="plotly_dark", xaxis_title="氣溫 (°C)", yaxis_title="日射強度 (W/m²)", legend=dict(orientation="v", y=1, x=1.02), margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig2, use_container_width=True)

# --- Tab 2: 室內氣候 ---
with tab2:
    st.subheader("🏠 溫室結構與模擬")
    ci, cr = st.columns([1, 2])
    
    # --- 左側：參數輸入區 ---
    with ci:
        with st.expander("1. 結構尺寸 (Geometry)", expanded=True):
            w = st.number_input("寬度 (m)", value=25.0, step=1.0)
            l = st.number_input("長度 (m)", value=40.0, step=1.0)
            h = st.number_input("簷高 (m)", value=4.5, step=0.5)
            r_type = st.selectbox("屋頂形式", ["Venlo", "Tunnel", "SingleSlope"])
            r_angle = st.slider("屋頂角度 (°)", 0, 45, 22)
            m_key = st.selectbox("覆蓋材料", list(MAT_DB.keys()), format_func=lambda x: MAT_DB[x]['label']) if MAT_DB else 'glass'

        with st.expander("2. 通風設備 (Ventilation)", expanded=True):
            p_rate = st.number_input("電費 ($/度)", value=4.0, step=0.1)
            st.session_state['elec_rate'] = p_rate
            st.markdown("---")
            if not FAN_DB.empty:
                f_idx = st.selectbox("排風扇型號", FAN_DB.index, format_func=lambda x: f"{FAN_DB.loc[x, 'Model']} ({FAN_DB.loc[x, 'Airflow_CMH']:.0f} CMH | {FAN_DB.loc[x, 'Power_W']:.0f}W)")
                f_flow = float(FAN_DB.loc[f_idx, 'Airflow_CMH']); f_power = float(FAN_DB.loc[f_idx, 'Power_W'])
                st.session_state['sel_fan_power'] = f_power
            else: 
                f_flow = 40000; f_power = 1000; st.session_state['sel_fan_power'] = 1000
            f_count = st.number_input("排風扇數量 (台)", value=8, step=1)

            st.markdown("---")
            if not CIRC_DB.empty:
                c_idx = st.selectbox("循環扇型號", CIRC_DB.index, format_func=lambda x: f"{CIRC_DB.loc[x, 'Model']} ({CIRC_DB.loc[x, 'Airflow_CMH']:.0f} CMH)")
            c_count = st.number_input("循環扇數量 (台)", value=10, step=1)

        with st.expander("3. 環控與內裝 (Controls)", expanded=True):
            shading = st.slider("遮蔭率 (%)", 0, 90, 30)
            if not NET_DB.empty:
                n_idx = st.selectbox("防蟲網規格", NET_DB.index, format_func=lambda x: NET_DB['Label'][x])
                try: i_net = float(NET_DB.loc[n_idx, 'Openness_Percent'])
                except: i_net = 70.0
            else: i_net = st.slider("網通風率 (%)", 0, 100, 70)
            c_type = st.selectbox("栽培系統", ["NFT", "DFT", "Soil", "Pot"])
            r_vent = st.number_input("天窗面積 (m²)", value=0.0)
            s_vent = st.number_input("側窗面積 (m²)", value=0.0)

        with st.expander("4. 噴霧系統 (Fogging)", expanded=True):
            if not FOG_DB.empty:
                fog_idx = st.selectbox("噴霧規格", FOG_DB.index, format_func=lambda x: FOG_DB['Label'][x])
                try: fog_cap = float(FOG_DB.loc[fog_idx, 'Spray_Capacity_g_m2_hr'])
                except: fog_cap = 0
            else: fog_cap = 0
            fog_trig = st.slider("啟動溫度 (°C)", 25, 35, 28)
            fog_rh = st.slider("停止濕度 (%RH)", 70, 95, 85)

    # --- 資料打包 ---
    rad = math.radians(r_angle)
    vol_map = {"NFT": 1.1, "Pot": 1.2, "Soil": 1.4, "DFT": 1.6}
    avg_h = 0.5 * w * math.tan(rad) if r_type != 'Tunnel' else 0
    gh_specs = {
        'width': w, 'length': l, 'gutterHeight': h, 'material': m_key,
        'roofVentArea': r_vent, 'sideVentArea': s_vent, 'shadingScreen': shading, 'insectNet': i_net,
        '_vol_coef': (1 + avg_h/h) * vol_map.get(c_type, 1.2), '_surf_coef': 1 / math.cos(rad), 
        '_vent_eff': (1.0 + math.sin(rad)*0.5) * (i_net/100)*0.8
    }
    fan_specs = {'exhaustCount': f_count, 'exhaustFlow': f_flow, 'circCount': c_count, 'circDistance': 15}
    st.session_state.gh_specs = gh_specs; st.session_state.fan_specs = fan_specs

    # ★ 呼叫 SimulationService
    res = SimulationService.run_simulation(
        gh_specs, fan_specs, CURR_LOC['data'], 
        st.session_state.monthly_crops, st.session_state.planting_density, 
        st.session_state.annual_cycles, st.session_state.market_prices,
        CROP_DB, MAT_DB
    )

    
    # --- 右側：模擬結果展示 ---
    with cr:
        # 顯示物理參數 (保持不變)
        st.markdown(f"""<div style="background-color:#1e293b; padding:15px; border-radius:10px; border:1px solid #334155; margin-bottom:20px;"><strong style="color:#38bdf8">📊 物理模型參數</strong><br>• 溫室體積: {w*l*h*gh_specs['_vol_coef']:.0f} m³ (熱緩衝係數 {gh_specs['_vol_coef']:.2f})<br>• 總換氣率: {(f_count*f_flow)/3600*3600 / (w*l*h*gh_specs['_vol_coef']) if (w*l*h)>0 else 0:.1f} 次/小時 (ACH)<br>• 通風效率: {gh_specs['_vent_eff']*100:.0f}% (受結構與防蟲網影響)</div>""", unsafe_allow_html=True)

        df_sim = pd.DataFrame(res['data'])
        
        # === 圖表 1: 微氣候 (溫度 + ACH) ===
        fig_sim = make_subplots(specs=[[{"secondary_y": True}]])
        fig_sim.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['tempOut'], name="外部氣溫", line=dict(color='#94a3b8', dash='dot')), secondary_y=False)
        fig_sim.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['tempIn'], name="內部氣溫", line=dict(color='#ef4444', width=3), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.1)'), secondary_y=False)
        fig_sim.add_trace(go.Bar(x=df_sim['month'], y=df_sim['ach'], name="換氣率 (ACH)", marker_color='#0ea5e9', opacity=0.3), secondary_y=True)
        
        fig_sim.update_layout(
            title="微氣候模擬 (月均值)", 
            height=300,  
            template="plotly_dark", 
            hovermode="x unified",
            xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]) # 強制顯示 1-12月
        )
        st.plotly_chart(fig_sim, use_container_width=True)

        # === ★ 新增: VPD 趨勢圖 (植物適合水汽壓差分析) ===
        if 'vpd' in df_sim.columns:
            st.markdown("##### 🌱 植物生理指標 水汽壓差(VPD)")
            fig_vpd = go.Figure()

            # 1. 繪製綠色範圍區 (0.8 - 1.2 kPa)
            fig_vpd.add_hrect(
                y0=0.8, y1=1.2, 
                fillcolor="#22c55e", opacity=0.15, 
                line_width=0,
                annotation_text="舒適區 (0.8-1.2)", annotation_position="top left", annotation_font_color="#22c55e"
            )

            # 2. 繪製 VPD 線
            fig_vpd.add_trace(go.Scatter(
                x=df_sim['month'], 
                y=df_sim['vpd'], 
                name="VPD (kPa)", 
                mode='lines+markers',
                line=dict(color='#d946ef', width=3), # 紫色
                marker=dict(size=6)
            ))

            fig_vpd.update_layout(
                height=250, # 扁一點的圖
                template="plotly_dark",
                hovermode="x unified",
                xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]),
                yaxis=dict(title="kPa", range=[0, 3]), # 固定範圍方便觀察
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig_vpd, use_container_width=True)
        
        # === 圖表 3: 高溫累積時數 (原本的圖) ===
        fig_heat = go.Figure()
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat30_Base'], name="原況 >30°C", marker_color='#94a3b8'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat30_In'], name="改善 >30°C", marker_color='#fbbf24'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat35_Base'], name="原況 >35°C", marker_color='#475569'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat35_In'], name="改善 >35°C", marker_color='#ea580c'))
        
        fig_heat.update_layout(
            title="高溫累積時數", 
            height=300, 
            template="plotly_dark", 
            barmode='group', 
            legend=dict(orientation="h", y=-0.2),
            xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5])
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    # --- 底部：24小時詳細模擬 ---
    st.markdown("---"); st.subheader("⏱️ 24小時一日動態模擬 (依據 CWA 時報表)")
    
    # 這裡直接列出檔案清單 (不需 full path，傳給 service 時再組)
    weather_files = [f for f in os.listdir('data/weather_data') if f.endswith('.csv')]
    
    c_h1, c_h2 = st.columns([1, 3])
    df_day = None
    
    with c_h1:
        if weather_files:
            st.success(f"✅ 已鎖定測站：{CURR_LOC['name']}")
            default_idx = 0
            current_id = str(CURR_LOC.get('id', ''))
            for i, fname in enumerate(weather_files):
                if current_id in fname: default_idx = i; break
            
            sel_f = st.selectbox("選擇氣候檔", weather_files, index=default_idx)
            
            # 呼叫 ClimateService
            df_hourly = climate_svc.read_hourly_data(sel_f)
            
            if df_hourly is not None:
                d_strs = sorted(df_hourly['Time'].dt.strftime('%Y-%m-%d').unique(), reverse=True)
                sel_date = st.selectbox("選擇日期", d_strs)
                df_day = df_hourly[df_hourly['Time'].dt.strftime('%Y-%m-%d') == sel_date].copy().sort_values('Time')
                df_day = df_day[df_day['Time'].dt.hour != 0]

                if not df_day.empty:
                    st.info(f"📊 {sel_date} 氣候摘要：\n\n• 均溫: {df_day['Temp'].mean():.1f}°C\n• 總日射: {df_day['Solar'].sum():.1f} MJ/m²")
                else: st.warning("該日期無有效資料")
            else: st.error("讀取失敗")
        else: st.warning("無資料")

    with c_h2:
        if df_day is not None and not df_day.empty:
            for col in ['Temp', 'Solar', 'Wind']:
                if col in df_day.columns: df_day[col] = pd.to_numeric(df_day[col], errors='coerce')
                else: df_day[col] = np.nan
            df_day['Temp'].fillna(25.0, inplace=True); df_day['Solar'].fillna(0.0, inplace=True); df_day['Wind'].fillna(0.5, inplace=True)
            df_day['Solar_W'] = df_day['Solar'] * 277.78

            # 2. 執行物理模擬 (與 Tab 2 邏輯一致)
            res_24h = []
            mat_info = MAT_DB.get(m_key, {'uValue':5.8, 'trans':0.9})
            u_val = mat_info['uValue']; trans = mat_info['trans'] * (1 - shading/100)
            surf_ratio = gh_specs.get('_surf_coef', 1.05)
            total_roof_area = (w * l) * surf_ratio 
            
            for _, row in df_day.iterrows():
                t_out_h = row['Temp']; solar_h = row['Solar']; wind_h = row['Wind']
                q_solar = (solar_h * 1000000 / 3600) * (w*l) * trans 
                tot_vent = (wind_h * (r_vent + s_vent) * 0.4 * (i_net/100) * gh_specs['_vent_eff']) + ((f_count * f_flow) / 3600)
                q_fog = (fog_cap * (w*l) * 2450 / 3600) * 0.8 if (fog_cap > 0 and t_out_h > fog_trig) else 0
                surface_area = total_roof_area + 2*(w+l)*h
                q_remove = (tot_vent * 1200) + (u_val * surface_area)
                delta_t = (q_solar - q_fog) / q_remove if q_remove > 0 else 0
                t_in_h = t_out_h + delta_t
                if t_in_h < t_out_h - 2: t_in_h = t_out_h - 2
                res_24h.append(t_in_h)
            
            df_day['TempIn'] = res_24h
            fig_24 = make_subplots(specs=[[{"secondary_y": True}]])
            fig_24.add_trace(go.Scatter(x=df_day['Time'].dt.hour, y=df_day['Solar_W'], name="日射強度 (W/m²)", mode='lines', line=dict(width=0), fill='tozeroy', fillcolor='rgba(245, 158, 11, 0.4)', marker=dict(color='#f59e0b')), secondary_y=True)
            fig_24.add_trace(go.Scatter(x=df_day['Time'].dt.hour, y=df_day['Temp'], name="外氣溫", mode='lines+markers', line=dict(color='#e2e8f0', width=2, dash='dot'), marker=dict(size=4)), secondary_y=False)
            fig_24.add_trace(go.Scatter(x=df_day['Time'].dt.hour, y=df_day['TempIn'], name="室內溫", mode='lines+markers', line=dict(color='#ef4444', width=3), marker=dict(size=5)), secondary_y=False)
            fig_24.update_layout(title=f"{sel_date} 24小時模擬 ({sel_f.split('.')[0]})", template="plotly_dark", height=400, hovermode="x unified", xaxis=dict(title="時間 (小時)", tickmode='linear', dtick=1, range=[0.5, 24.5]), legend=dict(orientation="h", y=1.1, x=0), margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig_24, use_container_width=True)
            m1, m2 = st.columns(2)
            m1.metric("最高室溫", f"{df_day['TempIn'].max():.1f}°C"); m2.metric("日夜溫差", f"{(df_day['TempIn'].max() - df_day['TempIn'].min()):.1f}°C")

# --- Tab 3: 產能價格 ---
with tab3:
    st.subheader("💰 經濟分析與價格管理")
    if MARKET_DB: st.success(f"✅ 已連結 {len(MARKET_DB)} 檔市場價格資料庫")
    else: st.warning("⚠️ 未偵測到市場價格檔 (market_data資料夾為空)")

    c1, c2 = st.columns([1, 2])
    with c1:
        with st.form("econ_form"):
            st.markdown("#### 生產參數")
            den = st.number_input("種植密度 (株/m²)", value=st.session_state.planting_density, step=1.0)
            cyc = st.number_input("年周轉率 (次/年)", value=st.session_state.annual_cycles, step=1.0)
            st.markdown("#### 月生產計畫")
            id_to_name = {k: v['name'] for k, v in CROP_DB.items()}; name_to_id = {v['name']: k for k, v in CROP_DB.items()}
            crop_options = list(name_to_id.keys())
            current_names = [id_to_name.get(c_id, c_id) for c_id in st.session_state.monthly_crops]
            df_plan = pd.DataFrame({'月': range(1, 13), '作物': current_names, '批發價 ($)': st.session_state.market_prices})
            
            edited_df = st.data_editor(df_plan, column_config={"月": st.column_config.NumberColumn(disabled=True), "作物": st.column_config.SelectboxColumn(options=crop_options, required=True), "批發價 ($)": st.column_config.NumberColumn(min_value=0, step=1)}, hide_index=True, use_container_width=True, height=300)
            auto_fill = st.checkbox("🔄 自動帶入 CSV 價格 (若有)", value=True)
            submit_btn = st.form_submit_button("🚀 計算", type="primary")

            if submit_btn:
                st.session_state.planting_density = den; st.session_state.annual_cycles = cyc
                new_crops = []; new_prices = []
                for idx, row in edited_df.iterrows():
                    c_name = row['作物']; c_id = name_to_id.get(c_name, 'lettuce')
                    new_crops.append(c_id)
                    final_price = row['批發價 ($)']
                    if auto_fill and MARKET_DB:
                        for db_name, price_list in MARKET_DB.items():
                            if c_name in db_name: final_price = price_list[idx]; break
                    new_prices.append(final_price)
                st.session_state.monthly_crops = new_crops; st.session_state.market_prices = new_prices
                st.rerun()

    with c2:
        # ★ [關鍵修改] 呼叫 SimulationService
        res_eco = SimulationService.run_simulation(
            st.session_state.gh_specs, st.session_state.fan_specs, CURR_LOC['data'], 
            st.session_state.monthly_crops, st.session_state.planting_density, 
            st.session_state.annual_cycles, st.session_state.market_prices, 
            CROP_DB, MAT_DB
        )
        
        k1, k2, k3 = st.columns(3)
        k1.metric("預估年營收", f"${int(res_eco['totalRevenue']):,}")
        k2.metric("預估年產量", f"{res_eco['totalYield']/1000:.1f} 噸")
        df_res = pd.DataFrame(res_eco['data'])
        k3.metric("平均環境效率", f"{df_res['efficiency'].mean():.1f}%")
        
        st.markdown("##### 營收產量趨勢")
        fig_eco = make_subplots(specs=[[{"secondary_y": True}]])
        fig_eco.add_trace(go.Bar(x=df_res['month'], y=df_res['revenue'], name="營收 ($)", marker_color='#10b981', opacity=0.8), secondary_y=False)
        fig_eco.add_trace(go.Scatter(x=df_res['month'], y=df_res['yield'], name="產量 (kg)", mode='lines+markers', line=dict(color='#3b82f6', width=3), marker=dict(size=6)), secondary_y=True)
        fig_eco.update_layout(
            height=400, 
            template="plotly_dark", 
            hovermode="x unified", 
            legend=dict(orientation="h", y=1.1), 
            margin=dict(t=50),
            # ★ 關鍵修改：強制顯示 1-12 月刻度
            xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5])
        )
        st.plotly_chart(fig_eco, use_container_width=True)

# --- Tab 4: 設備最佳化分析 (全新改版) ---
with tab4:
    st.subheader("⚖️ 設備最佳化：邊際效益分析")
    
    # 0. 防呆檢查
    if 'gh_specs' not in st.session_state:
        st.warning("⚠️ 請先至「Tab 2: 內部微氣候」完成規格設定。")
        st.stop()
        
    gh_specs = st.session_state.gh_specs
    fan_specs = st.session_state.fan_specs
    
    # 1. 分析目標選擇
    st.markdown("#### 🎯 選擇要最佳化的系統")
    target_sys = st.radio(
        "請選擇分析對象", 
        ["負壓風扇 (Fans)", "內遮蔭 (Shading)", "天窗面積 (Vents)", "噴霧系統 (Fogging)"], 
        horizontal=True
    )
    
    st.markdown("---")
    
    col_opt1, col_opt2 = st.columns([1, 2.5])
    
    # --- 左側：成本參數設定 ---
    with col_opt1:
        st.markdown("### ⚙️ 成本與運轉參數")
        
        # 通用參數
        run_hours = st.number_input("年運轉時數 (hr)", value=3000, step=100, help="設備一年大約開多久")
        elec_rate = st.number_input("電費費率 ($/度)", value=4.0, step=0.5)
        
        # 依據選擇顯示不同參數
        cost_capex = 0  # 建置成本 (攤提後)
        cost_opex = 0   # 運轉成本 (每單位)
        
        if "Fans" in target_sys:
            st.info("分析：隨著風扇數量增加，降溫效果提升，但電費與設備費也線性增加。尋找淨利最高點。")
            fan_power = st.session_state.get('sel_fan_power', 1000.0)
            unit_price = st.number_input("風扇單價 ($/台)", value=15000, step=1000)
            life_year = st.number_input("折舊年限 (年)", value=5, step=1)
            # 計算參數
            capex_per_unit = unit_price / life_year
            opex_per_unit = (fan_power / 1000) * run_hours * elec_rate
            
            # 設定模擬範圍
            sim_range = range(0, 1000, 1) # 0 到 1000 台，每 1 台算一次
            x_label = "風扇數量 (台)"
            
        elif "Shading" in target_sys:
            st.info("分析：遮蔭越高，溫度越低(利於生長)，但光照越少(不利產量)。尋找光照與氣溫平衡點。")
            # 遮蔭通常算一次性耗材或設施
            net_price = st.number_input("遮蔭網成本 ($/m²)", value=50, step=10)
            life_year = st.number_input("使用年限 (年)", value=3, step=1)
            capex_per_unit = net_price / life_year # 這裡 unit 是 % 還是 m2? 簡化為總成本係數
            
            sim_range = range(0, 95, 10) # 0% 到 90%
            x_label = "遮蔭率 (%)"
            
        elif "Vents" in target_sys:
            st.info("分析：天窗面積越大，自然通風越好，但建置成本越高。")
            vent_price = st.number_input("天窗造價 ($/m²)", value=3000, step=500)
            life_year = st.number_input("結構折舊 (年)", value=10, step=1)
            capex_per_unit = vent_price / life_year
            
            # 最大天窗面積不能超過屋頂
            max_area = int(gh_specs['width'] * gh_specs['length'] * gh_specs.get('_surf_coef', 1.05))
            step = max(1, int(max_area / 10))
            sim_range = range(0, max_area, step)
            x_label = "天窗面積 (m²)"

        elif "Fogging" in target_sys:
            st.info("分析：噴霧量增加可大幅降溫增濕，但需考量水電成本與病害風險(高濕)。")
            water_price = st.number_input("水費 ($/度)", value=12.0)
            # 假設噴霧每 g/m2/hr 的建置攤提
            sys_price = st.number_input("系統造價攤提 ($/單位流量/年)", value=10.0, help="每增加 1 g/m²/hr 流量的設備年攤提")
            
            sim_range = range(0, 600, 10) # 流量 0 ~ 600 g/m2/hr
            x_label = "噴霧流量 (g/m²/hr)"

    # --- 右側：執行運算與繪圖 ---
    with col_opt2:
        if st.button("🚀 開始最佳化運算", type="primary", use_container_width=True):
            
            results = []
            floor_area = gh_specs['width'] * gh_specs['length']
            
            with st.spinner(f"正在模擬各種 {target_sys} 配置..."):
                for val in sim_range:
                    # 1. 複製規格以免汙染原始設定
                    tmp_gh = gh_specs.copy()
                    tmp_fan = fan_specs.copy()
                    
                    # 2. 根據選擇修改參數
                    cost_total = 0
                    
                    if "Fans" in target_sys:
                        tmp_fan['exhaustCount'] = val
                        cost_total = val * (capex_per_unit + opex_per_unit)
                        
                    elif "Shading" in target_sys:
                        tmp_gh['shadingScreen'] = val
                        # 遮蔭成本 = 面積 * 單價 / 年限 * (遮蔭率/100 假設用量)
                        cost_total = (floor_area * val/100) * (capex_per_unit) 
                        
                    elif "Vents" in target_sys:
                        tmp_gh['roofVentArea'] = val
                        cost_total = val * capex_per_unit
                        
                    elif "Fogging" in target_sys:
                        # 這裡假設 SimulationService 有能力處理 fog_capacity 
                        # 如果後端還沒支援，我們可以透過 gh_specs 偷渡進去
                        tmp_gh['_fog_capacity'] = val 
                        
                        # 成本估算: 水費 + 電費 + 設備
                        # 總用水噸數 = (流量 g * 面積 * 時數) / 1,000,000
                        water_ton = (val * floor_area * run_hours) / 1_000_000
                        cost_water = water_ton * water_price
                        cost_elec = (val * floor_area * 0.005) * run_hours * elec_rate / 1000 # 假設泵浦耗電
                        cost_total = cost_water + cost_elec + (val * sys_price)

                    # 3. 呼叫後端模擬
                    sim_res = SimulationService.run_simulation(
                        tmp_gh, tmp_fan, CURR_LOC['data'], 
                        st.session_state.monthly_crops, st.session_state.planting_density, 
                        st.session_state.annual_cycles, st.session_state.market_prices, 
                        CROP_DB, MAT_DB
                    )
                    
                    # 4. 記錄結果
                    revenue = sim_res['totalRevenue']
                    net_profit = revenue - cost_total
                    yield_kg = sim_res['totalYield']
                    
                    results.append({
                        "Value": val,
                        "Revenue": revenue,
                        "Cost": cost_total,
                        "Profit": net_profit,
                        "Yield": yield_kg
                    })
            
            # --- 繪製結果圖 ---
            df_opt = pd.DataFrame(results)
            
            # 找出最佳點
            best_row = df_opt.loc[df_opt['Profit'].idxmax()]
            best_val = best_row['Value']
            best_profit = best_row['Profit']

            st.success(f"🏆 建議最佳配置： **{int(best_val)}** (單位: {x_label.split('(')[1][:-1]})，預估年淨利 **${int(best_profit):,}**")

            # 建立雙軸圖表
            fig_opt = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 區域圖：淨利 (綠色陰影)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Profit'], 
                name="淨利 (Revenue - Cost)",
                mode='lines', line=dict(color='#22c55e', width=3),
                fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)'
            ), secondary_y=False)
            
            # 線圖：總營收 (藍色)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Revenue'], 
                name="總營收 (Revenue)",
                mode='lines', line=dict(color='#3b82f6', width=2, dash='dash')
            ), secondary_y=False)

            # 線圖：總成本 (紅色)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Cost'], 
                name="總成本 (Cost)",
                mode='lines', line=dict(color='#ef4444', width=2, dash='dot')
            ), secondary_y=False)
            
            # 右軸：產量 (黃色)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Yield'], 
                name="作物產量 (kg)",
                mode='lines+markers', marker=dict(color='#f59e0b', size=6)
            ), secondary_y=True)

            # 標記最佳點
            fig_opt.add_annotation(
                x=best_val, y=best_profit,
                text=f"最佳點: {int(best_val)}",
                showarrow=True, arrowhead=1, ax=0, ay=-40
            )

            fig_opt.update_layout(
                title=f"{target_sys} 效益最佳化分析",
                template="plotly_dark",
                hovermode="x unified",
                xaxis_title=x_label,
                legend=dict(orientation="h", y=1.1),
                height=500
            )
            fig_opt.update_yaxes(title_text="金額 ($)", secondary_y=False)
            fig_opt.update_yaxes(title_text="產量 (kg)", secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_opt, use_container_width=True)
            
            # 顯示數據表
            with st.expander("查看詳細數據表"):
                st.dataframe(df_opt.style.format("{:,.0f}"))
        else:
            st.info("👈 請調整左側成本參數，並點擊按鈕開始分析。")
