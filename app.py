import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import os
import folium
from streamlit_folium import st_folium
import sys 

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
import os
import folium
from streamlit_folium import st_folium
import sys 

# 設定寬版模式 (解決擠成一團的問題)

st.set_page_config(
    page_title="溫室環境決策系統 V7.1", 
    page_icon="🌿", 
    layout="wide" 
)

st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 2rem;}
</style>
""", unsafe_allow_html=True)


current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- 引用後端服務 ---
from backend.services.climate_service import ClimateService
from backend.services.resource_service import ResourceService
from backend.services.market_service import MarketService
from backend.services.simulation_service import SimulationService

# ==========================================
# 1. 系統初始化 (實例化服務)
# ==========================================
climate_svc = ClimateService(base_folder='data/weather_data')
resource_svc = ResourceService(data_root='data')
market_svc = MarketService(base_folder='data/market_data')

# [新增] 實例化模擬服務
sim_svc = SimulationService()
# 透過服務載入資料
CROP_DB = resource_svc.load_crop_database()
WEATHER_DB = climate_svc.scan_and_load_weather_data()
MARKET_DB = market_svc.scan_and_load_market_prices()

# --- [新增] 讀取外部座標 CSV 並合併到 WEATHER_DB ---
gps_file_path = 'data/station_coords.csv'
if os.path.exists(gps_file_path):
    try:
        df_gps = pd.read_csv(gps_file_path)
        gps_dict = df_gps.set_index('StationName').to_dict('index')
        for key in WEATHER_DB.keys():
            for gps_name, coords in gps_dict.items():
                if gps_name in key: 
                    WEATHER_DB[key]['lat'] = coords['Lat']
                    WEATHER_DB[key]['lon'] = coords['Lon']
                    break
    except Exception as e:
        st.error(f"⚠️ 座標檔讀取錯誤: {e}")

# 載入設備庫
FAN_DB = resource_svc.load_equipment_csv('equipment_data', 'greenhouse_fans.csv', 'fan')
CIRC_DB = resource_svc.load_equipment_csv('equipment_data', 'greenhouse_fans.csv', 'fan', 'Category', 'Circulation')
NET_DB = resource_svc.load_equipment_csv('equipment_data', 'insect_nets.csv', 'net')
FOG_DB = resource_svc.load_equipment_csv('equipment_data', 'foggingsystem.csv', 'fog')
MAT_DB = resource_svc.load_material_database(os.path.join('equipment_data', 'greenhouse_materials.csv'))

# 內建預設值
if not WEATHER_DB:
    WEATHER_DB = {'demo': {'id': 'demo', 'name': '範例氣候', 'data': {'months': list(range(1,13)), 'temps':[25]*12, 'solar':[12]*12, 'wind':[1]*12, 'humidities':[75]*12, 'marketPrice':[30]*12}}}

# Session State 初始化
if 'monthly_crops' not in st.session_state: st.session_state.monthly_crops = ['lettuce'] * 12
if 'planting_density' not in st.session_state: st.session_state.planting_density = 25.0
if 'annual_cycles' not in st.session_state: st.session_state.annual_cycles = 15.0
if 'production_costs' not in st.session_state: st.session_state.production_costs = [15] * 12 # [新增] 成本預設值

# 標題區
c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/2942/2942544.png", width=80)
with c2: st.title("溫室模擬與環境分析系統 V7.1"); st.markdown("20251222 完整版")

# 側邊欄：地區選擇
with st.sidebar:
    st.header("基礎設定")
    loc_options = list(WEATHER_DB.keys())
    default_key = '12Q970_東港工作站' 
    default_index = loc_options.index(default_key) if default_key in loc_options else 0
    
    loc_id = st.selectbox(
        "選擇模擬地區", 
        loc_options, 
        format_func=lambda x: WEATHER_DB[x]['name'],
        index=default_index  
    )
    CURR_LOC = WEATHER_DB[loc_id]
    st.caption(CURR_LOC.get('description', ''))
    if 'market_prices' not in st.session_state: st.session_state.market_prices = CURR_LOC['data']['marketPrice'].copy()

# ==========================================
# 2. 前端介面邏輯
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["1. 外部環境", "2. 內部微氣候", "3. 產能價格", "4. 邊際效益"])

# --- Tab 1: 外部環境 ---
with tab1:
    st.subheader(f"📍 {CURR_LOC['name']} - 氣候數據")
    c_data = CURR_LOC['data']
    df_clim = pd.DataFrame({
        'Month': c_data['months'], 
        'Temp': c_data['temps'], 
        'MaxTemp': c_data['maxTemps'], 
        'MinTemp': c_data['minTemps'],
        'Solar': c_data['solar']
    })
    df_clim['Solar_W'] = df_clim['Solar'] * 11.574 

    col1, col2 = st.columns([1, 1.5]) 
    with col1:
        st.markdown("##### 全年氣候趨勢圖")
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=df_clim['Month'], y=df_clim['Solar_W'], name="日射量 (W/m²)", marker_color='orange', opacity=0.5), secondary_y=False)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['MaxTemp'], name="最高溫", line=dict(color='#ef4444', dash='dot', width=2)), secondary_y=True)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['MinTemp'], name="最低溫", line=dict(color='#3b82f6', dash='dot', width=2)), secondary_y=True)
        fig.add_trace(go.Scatter(x=df_clim['Month'], y=df_clim['Temp'], name="平均氣溫", line=dict(color='#f59e0b', width=3)), secondary_y=True)
        
        fig.update_layout(
            height=450, template="plotly_dark", hovermode="x unified",
            legend=dict(orientation="h", y=1.1, x=0.5, xanchor='center'),
            margin=dict(l=10, r=10, t=50, b=10),
            xaxis=dict(title="月份", tickmode='linear', dtick=1, range=[0.5, 12.5]),
            yaxis=dict(title="日射量 (W/m²)", showgrid=True),
            yaxis2=dict(title="溫度 (°C)", showgrid=False, overlaying='y', side='right')
        )
        st.plotly_chart(fig, use_container_width=True)
            
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

    # --- [修正] 地圖區塊 (已加入 returned_objects=[]) ---
    st.markdown("---")
    st.subheader("🗺️ 氣象站地理位置分佈")
    with st.expander("點擊展開地圖", expanded=True):
        map_data = []
        for key, value in WEATHER_DB.items():
            lat = value.get('lat') or value.get('latitude')
            lon = value.get('lon') or value.get('longitude')
            if lat is None: lat = 23.973875
            if lon is None: lon = 120.982024
            
            map_data.append({
                "name": value.get('name', key),
                "lat": float(lat), "lon": float(lon),
                "desc": value.get('description', '無描述')
            })
        df_map = pd.DataFrame(map_data)
        m = folium.Map(location=[23.7, 121.0], zoom_start=7)
        for _, row in df_map.iterrows():
            is_current = (row['name'] == CURR_LOC['name'])
            icon_color = 'red' if is_current else 'green'
            icon_type = 'star' if is_current else 'leaf'
            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=f"<b>{row['name']}</b><br>{row['desc']}",
                tooltip=row['name'],
                icon=folium.Icon(color=icon_color, icon=icon_type)
            ).add_to(m)
            
        # 關鍵修正：防止地圖縮放時重跑
        st_folium(m, width=1000, height=500, use_container_width=True, returned_objects=[])


    # ... (Tab 1 前半部不變) ...

    st.markdown("---")
    st.subheader(f"☀️ {CURR_LOC['name']} - 光環境適性分析 (月均值版)")
    
    # 1. 尋找檔案邏輯 (保持不變)
    current_id = str(CURR_LOC['id'])
    target_filename = None
    weather_folder = 'data/weather_data'
    if os.path.exists(weather_folder):
        for f in os.listdir(weather_folder):
            if current_id in f and f.endswith('.csv'):
                target_filename = f; break
    
    if target_filename:
        # 2. 設定面板
        c_set1, c_set2 = st.columns([1, 2])
        
        # --- 讀取作物資料 ---.

        # --- 讀取作物資料 ---
        
        crop_data = climate_svc.get_crop_light_requirements()
        
        with c_set1:
            st.markdown("#### ⚙️ 栽培設定")
            
            # 選單會自動列出 CSV 裡所有的 Crop_Name
            sel_crop = st.selectbox("目標作物", list(crop_data.keys()))
            
            # 取得該作物的參數
            crop_req = crop_data[sel_crop]
            sat_point = crop_req['sat']
            comp_point = crop_req['comp']
            target_dli = crop_req.get('dli', 15) # 預留欄位，若沒有則預設15
            
            st.info(f"📋 **{sel_crop}** 參數：\n"
                    f"• 光補償點: `{comp_point}` μmol\n"
                    f"• 光飽和點: `{sat_point}` μmol\n"
                    f"• 目標 DLI: `{target_dli}` mol")
            
            st.markdown("---")
            env_mode = st.radio("環境設定", ["室外 (Outdoor)", "室內 (Indoor)"], horizontal=True)
            trans_rate = 100
            if env_mode == "室內 (Indoor)":
                trans_rate = st.slider("透光率 (%)", 10, 100, 50, step=5)

        # 3. 呼叫後端運算 (取得 12x24 矩陣)
        matrix, dli_monthly = climate_svc.calculate_monthly_light_matrix(target_filename, transmittance_percent=trans_rate)
        
        if matrix is not None:
            with c_set2:
                # --- [圖表 1] 月平均 DLI (Bar Chart) ---
                st.markdown("#### 📊 平均 DLI (日累積光量)")
                fig_dli = go.Figure(go.Bar(
                    x=dli_monthly.index, # 1-12月
                    y=dli_monthly.values,
                    marker_color='#10b981',
                    text=[f"{v:.1f}" for v in dli_monthly.values],
                    textposition='auto',
                    name='DLI'
                ))
                fig_dli.update_layout(
                    height=200, 
                    template="plotly_dark", 
                    margin=dict(l=20, r=20, t=20, b=10),
                    xaxis=dict(tickmode='linear', title="月份"),
                    yaxis=dict(title="mol/m²/day")
                )
                st.plotly_chart(fig_dli, use_container_width=True)

            # --- [圖表 2] 三色警示熱力圖 (Custom Heatmap) ---
            st.markdown("#### 🔥 全年光照適性指紋圖 (Month x Hour)")
            st.caption(f"🎨 顏色說明：⬜ 灰色 < {comp_point} (無效) | 🟨 米黃色 (適當生長) | 🟥 紅色 > {sat_point} (過量/飽和)")
            
            # 準備熱力圖數據
            # 為了實現「三色」，我們需要建立一個「類別矩陣」(0, 1, 2) 來控制顏色
            # 但同時又要顯示「真實數值」在滑鼠提示上
            
            z_values = matrix.values # 真實數值 (PPFD)
            
            # 建立顏色分類矩陣
            # 0: < Comp (灰)
            # 1: Comp ~ Sat (米黃)
            # 2: > Sat (紅)
            z_category = np.zeros_like(z_values)
            z_category[(z_values >= comp_point) & (z_values <= sat_point)] = 1
            z_category[z_values > sat_point] = 2
            
            # 定義三色盤 (Discrete Colorscale)
            # 0->0.33: Grey, 0.33->0.66: Beige, 0.66->1: Red
            custom_colors = [
                [0.0, '#d1d5db'],   # Grey (Light)
                [0.33, '#d1d5db'],
                [0.33, '#fef3c7'],  # Beige (Warm Yellow)
                [0.66, '#fef3c7'],
                [0.66, '#ef4444'],  # Red
                [1.0, '#ef4444']
            ]
            
            # 使用 heatmap 繪圖
            # Trick: 我們用 z_category 來決定顏色，但用 customdata 來存真實數值顯示在 tooltip
            fig_heat = go.Figure(data=go.Heatmap(
                z=z_category,
                x=matrix.columns, # 0-23 Hour
                y=matrix.index,   # 1-12 Month
                colorscale=custom_colors,
                showscale=False,  # 不顯示色條，因為是離散的
                customdata=z_values,
                hovertemplate='<b>%{y}月 %{x}點</b><br>平均 PPFD: %{customdata:.0f} μmol<br>狀態: %{z}<extra></extra>'
            ))
            
            fig_heat.update_layout(
                height=400,
                template="plotly_dark",
                xaxis=dict(title="時間 (Hour)", tickmode='linear', dtick=2),
                yaxis=dict(title="月份", tickmode='linear', dtick=1, autorange='reversed'), # 1月在最上
                margin=dict(l=50, r=50, t=20, b=20)
            )
            st.plotly_chart(fig_heat, use_container_width=True)
            
        else:
            st.warning("數據運算失敗，請檢查檔案格式。")
            
    else:
        st.warning(f"⚠️ 尚未上傳 **{CURR_LOC['name']}** 的原始氣象 CSV。")

# --- Tab 2: 室內氣候 ---
with tab2:
    st.subheader("🏠 溫室內部環境模擬")
    ci, cr = st.columns([1, 2])
    
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

    # --- 資料打包與模擬 ---
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


    res = sim_svc.run_simulation(
        gh_specs, fan_specs, CURR_LOC['data'], 
        st.session_state.monthly_crops, st.session_state.planting_density, 
        st.session_state.annual_cycles, st.session_state.market_prices,
        CROP_DB, MAT_DB
    )
    
    with cr:
        st.markdown(f"""<div style="background-color:#1e293b; padding:15px; border-radius:10px; border:1px solid #334155; margin-bottom:20px;"><strong style="color:#38bdf8">📊 物理模型參數</strong><br>• 溫室體積: {w*l*h*gh_specs['_vol_coef']:.0f} m³ (熱緩衝係數 {gh_specs['_vol_coef']:.2f})<br>• 總換氣率: {(f_count*f_flow)/3600*3600 / (w*l*h*gh_specs['_vol_coef']) if (w*l*h)>0 else 0:.1f} 次/小時 (ACH)<br>• 通風效率: {gh_specs['_vent_eff']*100:.0f}% (受結構與防蟲網影響)</div>""", unsafe_allow_html=True)
        df_sim = pd.DataFrame(res['data'])
        
        fig_sim = make_subplots(specs=[[{"secondary_y": True}]])
        fig_sim.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['tempOut'], name="外部氣溫", line=dict(color='#94a3b8', dash='dot')), secondary_y=False)
        fig_sim.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['tempIn'], name="內部氣溫", line=dict(color='#ef4444', width=3), fill='tonexty', fillcolor='rgba(239, 68, 68, 0.1)'), secondary_y=False)
        fig_sim.add_trace(go.Bar(x=df_sim['month'], y=df_sim['ach'], name="換氣率 (ACH)", marker_color='#0ea5e9', opacity=0.3), secondary_y=True)
        fig_sim.update_layout(title="微氣候模擬 (月均值)", height=300, template="plotly_dark", hovermode="x unified", xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]))
        st.plotly_chart(fig_sim, use_container_width=True)

        if 'vpd' in df_sim.columns:
            st.markdown("##### 水汽壓差(VPD)")
            fig_vpd = go.Figure()
            fig_vpd.add_hrect(y0=0.8, y1=1.2, fillcolor="#22c55e", opacity=0.15, line_width=0, annotation_text="舒適區 (0.8-1.2)", annotation_position="top left", annotation_font_color="#22c55e")
            fig_vpd.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['vpd'], name="VPD (kPa)", mode='lines+markers', line=dict(color='#d946ef', width=3), marker=dict(size=6)))
            fig_vpd.update_layout(height=250, template="plotly_dark", hovermode="x unified", xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]), yaxis=dict(title="kPa", range=[0, 3]), margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_vpd, use_container_width=True)
        
        fig_heat = go.Figure()
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat30_Base'], name="原況 >30°C", marker_color='#94a3b8'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat30_In'], name="改善 >30°C", marker_color='#fbbf24'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat35_Base'], name="原況 >35°C", marker_color='#475569'))
        fig_heat.add_trace(go.Bar(x=df_sim['month'], y=df_sim['heat35_In'], name="改善 >35°C", marker_color='#ea580c'))
        fig_heat.update_layout(title="高溫累積時數", height=300, template="plotly_dark", barmode='group', legend=dict(orientation="h", y=-0.2), xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]))
        st.plotly_chart(fig_heat, use_container_width=True)

    # --- 24小時模擬 ---
    st.markdown("---"); st.subheader("⏱️ 24小時一日動態模擬")
    weather_files = [f for f in os.listdir('data/weather_data') if f.endswith('.csv')]
    c_h1, c_h2 = st.columns([1, 3])
    df_day = None
    with c_h1:
        if weather_files:
            default_idx = 0
            current_id = str(CURR_LOC.get('id', ''))
            for i, fname in enumerate(weather_files):
                if current_id in fname: default_idx = i; break
            sel_f = st.selectbox("選擇氣候檔", weather_files, index=default_idx)
            df_hourly = climate_svc.read_hourly_data(sel_f)
            if df_hourly is not None:
                d_strs = sorted(df_hourly['Time'].dt.strftime('%Y-%m-%d').unique(), reverse=True)
                sel_date = st.selectbox("選擇日期", d_strs)
                df_day = df_hourly[df_hourly['Time'].dt.strftime('%Y-%m-%d') == sel_date].copy().sort_values('Time')
                df_day = df_day[df_day['Time'].dt.hour != 0]
                if not df_day.empty: st.info(f"📊 {sel_date} 氣候摘要：\n\n• 均溫: {df_day['Temp'].mean():.1f}°C\n• 總日射: {df_day['Solar'].sum():.1f} MJ/m²")
                else: st.warning("該日期無有效資料")
            else: st.error("讀取失敗")
    with c_h2:
        if df_day is not None and not df_day.empty:
            for col in ['Temp', 'Solar', 'Wind']:
                if col in df_day.columns: df_day[col] = pd.to_numeric(df_day[col], errors='coerce')
                else: df_day[col] = np.nan
            df_day['Temp'].fillna(25.0, inplace=True); df_day['Solar'].fillna(0.0, inplace=True); df_day['Wind'].fillna(0.5, inplace=True)
            df_day['Solar_W'] = df_day['Solar'] * 277.78
            
            res_24h = []
            mat_info = MAT_DB.get(m_key, {'uValue':5.8, 'trans':0.9})
            u_val = mat_info['uValue']; trans = mat_info['trans'] * (1 - shading/100)
            surf_ratio = gh_specs.get('_surf_coef', 1.05); total_roof_area = (w * l) * surf_ratio 
            
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
            fig_24.update_layout(title=f"{sel_date} 24小時模擬", template="plotly_dark", height=400, hovermode="x unified", xaxis=dict(title="時間 (小時)", tickmode='linear', dtick=1, range=[0.5, 24.5]), legend=dict(orientation="h", y=1.1, x=0), margin=dict(l=20, r=20, t=50, b=20))
            st.plotly_chart(fig_24, use_container_width=True)
            m1, m2 = st.columns(2)
            m1.metric("最高室溫", f"{df_day['TempIn'].max():.1f}°C"); m2.metric("日夜溫差", f"{(df_day['TempIn'].max() - df_day['TempIn'].min()):.1f}°C")

# --- Tab 3: 產能價格 (含淨利分析) ---
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
            st.markdown("#### 月生產計畫 (含成本)")
            id_to_name = {k: v['name'] for k, v in CROP_DB.items()}; name_to_id = {v['name']: k for k, v in CROP_DB.items()}
            crop_options = list(name_to_id.keys())
            current_names = [id_to_name.get(c_id, c_id) for c_id in st.session_state.monthly_crops]
            
            df_plan = pd.DataFrame({
                '月': range(1, 13), '作物': current_names, 
                '批發價 ($)': st.session_state.market_prices,
                '成本 ($/kg)': st.session_state.production_costs
            })
            
            edited_df = st.data_editor(
                df_plan, 
                column_config={
                    "月": st.column_config.NumberColumn(disabled=True), 
                    "作物": st.column_config.SelectboxColumn(options=crop_options, required=True), 
                    "批發價 ($)": st.column_config.NumberColumn(min_value=0, step=1, format="$%d"),
                    "成本 ($/kg)": st.column_config.NumberColumn(min_value=0, step=1, format="$%d", help="預估每公斤成本")
                }, 
                hide_index=True, use_container_width=True, height=300
            )
            auto_fill = st.checkbox("🔄 自動帶入 CSV 價格", value=True)
            submit_btn = st.form_submit_button("🚀 計算淨利", type="primary")

            if submit_btn:
                st.session_state.planting_density = den; st.session_state.annual_cycles = cyc
                new_crops = []; new_prices = []; new_costs = []
                for idx, row in edited_df.iterrows():
                    c_name = row['作物']; c_id = name_to_id.get(c_name, 'lettuce')
                    new_crops.append(c_id)
                    final_price = row['批發價 ($)']
                    if auto_fill and MARKET_DB:
                        for db_name, price_list in MARKET_DB.items():
                            if c_name in db_name: final_price = price_list[idx]; break
                    new_prices.append(final_price)
                    new_costs.append(row['成本 ($/kg)'])
                st.session_state.monthly_crops = new_crops
                st.session_state.market_prices = new_prices
                st.session_state.production_costs = new_costs
                st.rerun()

    with c2:
        res_eco = sim_svc.run_simulation(
            st.session_state.gh_specs, st.session_state.fan_specs, CURR_LOC['data'], 
            st.session_state.monthly_crops, st.session_state.planting_density, 
            st.session_state.annual_cycles, st.session_state.market_prices, CROP_DB, MAT_DB
        )
        df_res = pd.DataFrame(res_eco['data'])
        df_res['cost_unit'] = st.session_state.production_costs
        df_res['total_cost'] = df_res['yield'] * df_res['cost_unit']
        df_res['net_profit'] = df_res['revenue'] - df_res['total_cost']
        
        total_revenue = res_eco['totalRevenue']
        total_profit = df_res['net_profit'].sum()
        profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("預估年營收", f"${int(total_revenue):,}")
        k2.metric("預估年產量", f"{res_eco['totalYield']/1000:.1f} 噸")
        k3.metric("平均環境效率", f"{df_res['efficiency'].mean():.1f}%")
        k4.metric("預估年淨利", f"${int(total_profit):,}", delta=f"{profit_margin:.1f}%")
        
        fig_eco = make_subplots(specs=[[{"secondary_y": True}]])
        fig_eco.add_trace(go.Bar(x=df_res['month'], y=df_res['revenue'], name="營收 ($)", marker_color='#10b981', opacity=0.4), secondary_y=False)
        fig_eco.add_trace(go.Scatter(x=df_res['month'], y=df_res['net_profit'], name="淨利 ($)", mode='lines+markers', line=dict(color='#f59e0b', width=3), fill='tozeroy', fillcolor='rgba(245, 158, 11, 0.1)'), secondary_y=False)
        fig_eco.add_trace(go.Scatter(x=df_res['month'], y=df_res['total_cost'], name="總成本 ($)", mode='lines', line=dict(color='#ef4444', width=2, dash='dot')), secondary_y=False)
        fig_eco.add_trace(go.Scatter(x=df_res['month'], y=df_res['yield'], name="產量 (kg)", mode='lines', line=dict(color='#3b82f6', width=2)), secondary_y=True)
        fig_eco.update_layout(height=400, template="plotly_dark", hovermode="x unified", legend=dict(orientation="h", y=1.1), margin=dict(t=50), xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]), yaxis=dict(title="金額 ($)"), yaxis2=dict(title="產量 (kg)", showgrid=False))
        st.plotly_chart(fig_eco, use_container_width=True)

# --- Tab 4: 設備最佳化 ---
with tab4:
    st.subheader("⚖️ 設備最佳化：邊際效益分析")
    
    # 0. 防呆檢查
    if 'gh_specs' not in st.session_state:
        st.warning("⚠️ 請先至「Tab 2: 內部微氣候」完成規格設定。")
        st.stop()
        
    gh_specs = st.session_state.gh_specs
    fan_specs = st.session_state.fan_specs
    
    # 1. 分析目標選擇
    st.markdown("#### 🎯 選擇要最佳化的系統 (變動因子)")
    target_sys = st.radio(
        "請選擇分析對象:建議順序，確定天窗面積->噴霧系統->負壓扇數量，每個項目數值確定後，到tab2調整數值，再接著選下一項目", 
        ["負壓風扇 (Fans)", "內遮蔭 (Shading)", "天窗面積 (Vents)", "噴霧系統 (Fogging)"], 
        horizontal=True
    )
    st.markdown("---")
    
    col_opt1, col_opt2 = st.columns([1, 2.5])
    
    # --- 左側：參數設定與固定條件顯示 ---
    with col_opt1:
        st.markdown("### ⚙️ 成本與運轉參數")
        run_hours = st.number_input("年運轉時數 (hr)", value=3000, step=100)
        elec_rate = st.number_input("電費費率 ($/度)", value=4.0, step=0.5)
        
        sim_range = range(0, 1)
        x_label = ""
        capex_per_unit = 0; opex_per_unit = 0
        
        # 根據選擇設定變動參數
        if "Fans" in target_sys:
            fan_power = st.session_state.get('sel_fan_power', 1000.0)
            unit_price = st.number_input("風扇單價 ($/台)", value=15000, step=1000)
            life_year = st.number_input("折舊年限 (年)", value=5, step=1)
            capex_per_unit = unit_price / life_year
            opex_per_unit = (fan_power / 1000) * run_hours * elec_rate
            sim_range = range(0, 51, 2); x_label = "風扇數量 (台)"
            
        elif "Shading" in target_sys:
            net_price = st.number_input("遮蔭網成本 ($/m²)", value=50, step=10)
            life_year = st.number_input("使用年限 (年)", value=3, step=1)
            capex_per_unit = net_price / life_year
            sim_range = range(0, 95, 10); x_label = "遮蔭率 (%)"
            
        elif "Vents" in target_sys:
            vent_price = st.number_input("天窗造價 ($/m²)", value=3000, step=500)
            life_year = st.number_input("結構折舊 (年)", value=10, step=1)
            capex_per_unit = vent_price / life_year
            max_area = int(gh_specs['width'] * gh_specs['length'] * gh_specs.get('_surf_coef', 1.05))
            step = max(1, int(max_area / 10))
            sim_range = range(0, max_area, step); x_label = "天窗面積 (m²)"

        elif "Fogging" in target_sys:
            water_price = st.number_input("水費 ($/度)", value=12.0)
            sys_price = st.number_input("系統造價攤提 ($/單位流量/年)", value=10.0)
            sim_range = range(0, 600, 20); x_label = "噴霧流量 (g/m²/hr)"

        # ==========================================
        # ★ [新增] 顯示目前固定條件 (Context)
        # ==========================================
        st.markdown("---")
        st.markdown("#### 🔒 模擬背景 (其餘固定條件)")
        st.caption("以下參數將維持不變，僅變動上方選擇的系統：")
        
        with st.container(border=True):
            # 1. 顯示排風扇 (如果不是正在分析它)
            if "Fans" not in target_sys:
                st.markdown(f"**排風扇數量:** `{fan_specs['exhaustCount']} 台`")
            
            # 2. 顯示遮蔭 (如果不是正在分析它)
            if "Shading" not in target_sys:
                st.markdown(f"**內遮蔭率:** `{gh_specs['shadingScreen']}%`")
            
            # 3. 顯示天窗 (如果不是正在分析它)
            if "Vents" not in target_sys:
                st.markdown(f"**天窗面積:** `{gh_specs['roofVentArea']} m²`")
            
            # 4. 顯示噴霧 (如果不是正在分析它)
            if "Fogging" not in target_sys:
                # 這裡要小心 key 可能不存在
                curr_fog = gh_specs.get('_fog_capacity', 0)
                st.markdown(f"**噴霧系統:** `{curr_fog} g/m²/hr`")
                
            # 5. 顯示結構基本資訊
            st.markdown("---")
            st.markdown(f"**🏠 溫室尺寸:** `{gh_specs['width']}x{gh_specs['length']}x{gh_specs['gutterHeight']}m`")

    # --- 右側：執行運算與繪圖 (保持不變) ---
    with col_opt2:
        if st.button("🚀 開始最佳化運算", type="primary", use_container_width=True):
            results = []
            floor_area = gh_specs['width'] * gh_specs['length']
            with st.spinner(f"正在模擬各種 {target_sys} 配置..."):
                for val in sim_range:
                    tmp_gh = gh_specs.copy(); tmp_fan = fan_specs.copy()
                    cost_total = 0
                    
                    if "Fans" in target_sys:
                        tmp_fan['exhaustCount'] = val
                        cost_total = val * (capex_per_unit + opex_per_unit)
                    elif "Shading" in target_sys:
                        tmp_gh['shadingScreen'] = val
                        cost_total = (floor_area * val/100) * (capex_per_unit) 
                    elif "Vents" in target_sys:
                        tmp_gh['roofVentArea'] = val
                        cost_total = val * capex_per_unit
                    elif "Fogging" in target_sys:
                        tmp_gh['_fog_capacity'] = val 
                        water_ton = (val * floor_area * run_hours) / 1_000_000
                        cost_water = water_ton * water_price
                        cost_elec = (val * floor_area * 0.005) * run_hours * elec_rate / 1000 
                        cost_total = cost_water + cost_elec + (val * sys_price)

                    
                    sim_res = sim_svc.run_simulation(
                        tmp_gh, tmp_fan, CURR_LOC['data'], 
                        st.session_state.monthly_crops, st.session_state.planting_density, 
                        st.session_state.annual_cycles, st.session_state.market_prices, CROP_DB, MAT_DB
                    )
                    revenue = sim_res['totalRevenue']
                    net_profit = revenue - cost_total
                    results.append({"Value": val, "Revenue": revenue, "Cost": cost_total, "Profit": net_profit, "Yield": sim_res['totalYield']})
            
            df_opt = pd.DataFrame(results)
            best_row = df_opt.loc[df_opt['Profit'].idxmax()]
            best_val = best_row['Value']; best_profit = best_row['Profit']
            st.success(f"🏆 建議最佳配置： **{int(best_val)}** (單位: {x_label.split('(')[1][:-1]})，預估年淨利 **${int(best_profit):,}**")

            fig_opt = make_subplots(specs=[[{"secondary_y": True}]])
            fig_opt.add_trace(go.Scatter(x=df_opt['Value'], y=df_opt['Profit'], name="淨利 (Profit)", mode='lines', line=dict(color='#22c55e', width=3), fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)'), secondary_y=False)
            fig_opt.add_trace(go.Scatter(x=df_opt['Value'], y=df_opt['Revenue'], name="總營收 (Revenue)", mode='lines', line=dict(color='#3b82f6', width=2, dash='dash')), secondary_y=False)
            fig_opt.add_trace(go.Scatter(x=df_opt['Value'], y=df_opt['Cost'], name="總成本 (Cost)", mode='lines', line=dict(color='#ef4444', width=2, dash='dot')), secondary_y=False)
            fig_opt.add_trace(go.Scatter(x=df_opt['Value'], y=df_opt['Yield'], name="作物產量 (kg)", mode='lines+markers', marker=dict(color='#f59e0b', size=6)), secondary_y=True)
            fig_opt.update_layout(title=f"{target_sys} 效益最佳化分析", template="plotly_dark", hovermode="x unified", xaxis_title=x_label, legend=dict(orientation="h", y=1.1), height=500)
            fig_opt.update_yaxes(title_text="金額 ($)", secondary_y=False); fig_opt.update_yaxes(title_text="產量 (kg)", secondary_y=True, showgrid=False)
            st.plotly_chart(fig_opt, use_container_width=True)
            with st.expander("查看詳細數據表"): st.dataframe(df_opt.style.format("{:,.0f}"))



