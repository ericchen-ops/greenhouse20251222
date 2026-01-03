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

# ==========================================
# 1. 頁面設定 (必須在所有程式碼的最上面)
# ==========================================
st.set_page_config(
    page_title="溫室環境決策系統 V7.5", 
    page_icon="🌿", 
    layout="wide"  # <--- 寬版模式：解決擠成一團的關鍵
)

# 加入 CSS 微調，減少頂部空白，讓畫面更滿版
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# 設定路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- 引用後端服務 ---
from backend.services.climate_service import ClimateService
from backend.services.resource_service import ResourceService
from backend.services.market_service import MarketService
from backend.services.simulation_service import SimulationService

# ==========================================
# 2. 系統初始化 (實例化服務)
# ==========================================
climate_svc = ClimateService(base_folder='data/weather_data')
resource_svc = ResourceService(data_root='data')
market_svc = MarketService(base_folder='data/market_data')
sim_svc = SimulationService()

# 透過服務載入資料
CROP_DB = resource_svc.load_crop_database()
WEATHER_DB = climate_svc.scan_and_load_weather_data()
MARKET_DB = market_svc.scan_and_load_market_prices()
COST_DB = resource_svc.load_cost_parameters()



# --- 讀取外部座標 CSV 並合併到 WEATHER_DB ---
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

if not COST_DB:
    COST_DB = {
        'Electricity_Rate': 4.0, 'Water_Rate': 12.0, 
        'Fan_Unit_Price': 15000, 'Net_Unit_Price': 50, 'Vent_Structure_Price': 3000, 'Fog_System_Price': 10,
        'Fan_Life_Year': 5, 'Net_Life_Year': 3, 'Structure_Life_Year': 10
    }

# Session State 初始化
if 'monthly_crops' not in st.session_state: st.session_state.monthly_crops = ['lettuce'] * 12
if 'planting_density' not in st.session_state: st.session_state.planting_density = 25.0
if 'annual_cycles' not in st.session_state: st.session_state.annual_cycles = 12.0
if 'production_costs' not in st.session_state: st.session_state.production_costs = [15] * 12

# 標題區
c1, c2 = st.columns([1, 4])
with c1: st.image("https://cdn-icons-png.flaticon.com/512/2942/2942544.png", width=80)
with c2: st.title("溫室模擬與環境分析系統 V7.5"); st.markdown("2026 V1 ")

# 側邊欄：地區選擇
with st.sidebar:
    st.header("氣象站設定")
    loc_options = list(WEATHER_DB.keys())
    # 設定預設選項 (若有東港則預設東港)
    default_key = next((k for k in loc_options if '東港' in k), loc_options[0] if loc_options else None)
    default_index = loc_options.index(default_key) if default_key else 0
    
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
# 3. 前端介面邏輯 (Tabs)
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["1. 外部環境", "2. 內部微氣候", "3. 產能價格", "4. 邊際效益(尚在調整中)"])

# --- Tab 1: 外部環境 ---
with tab1:
    # --- 地圖區塊 ---
    st.markdown("---")
    st.subheader("🗺️ 氣象站位置")
    with st.expander("點擊查看氣象站位置", expanded=False):
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
            
        st_folium(m, width=1000, height=500, use_container_width=True, returned_objects=[])

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

    
    # --- 光環境適性分析 (Tab 1 下半部) ---
    st.markdown("---")
    st.subheader(f"☀️ {CURR_LOC['name']} - 光環境適性分析")
    
    # 1. 取得檔案路徑 
    target_filename = CURR_LOC.get('filename') 
    
    if not target_filename:
        current_id = str(CURR_LOC['id'])
        weather_folder = 'data/weather_data'
        if os.path.exists(weather_folder):
            for f in os.listdir(weather_folder):
                if current_id in f and f.endswith('.csv'):
                    target_filename = f; break
    
    if target_filename:
        c_set1, c_set2 = st.columns([1, 2.5])
        
        crop_data = climate_svc.get_crop_light_requirements()
        
        with c_set1:
            st.markdown("#### ⚙️ 栽培與環境設定")
            
            # 1. 作物選擇
            sel_crop = st.selectbox("目標作物", list(crop_data.keys()))
            crop_req = crop_data[sel_crop]
            sat_point = crop_req['sat']
            comp_point = crop_req['comp']
            target_dli = crop_req.get('dli', 17)
            min_dli_limit = crop_req.get('min_dli', 8)
            
            m1, m2 = st.columns(2)
            m1.metric("補償點", f"{int(comp_point)}", "μmol")
            m2.metric("飽和點", f"{int(sat_point)}", "μmol")
            
            st.markdown("---")
            
            # 2. 環境設定 (透光率)
            env_mode = st.radio("觀測情境", ["室外 (Outdoor)", "室內 (Indoor)"], horizontal=True)
            trans_rate = 100
            if env_mode == "室內 (Indoor)":
                trans_rate = st.slider("溫室透光率 (%)", 5, 100, 51, step=1, help="考慮遮陰網與覆蓋材的總透光率，請先計算(1-遮陰率)*材質透光率")#預設值為40%模組遮蔽率*85%透光率=51%
            
            # 3. 進階校正 (解決數值過高問題)
            with st.expander("🛠️ 進階參數校正", expanded=False):
                st.caption("若數值與現場差異過大，請調整轉換係數。")
                ppfd_coef = st.slider("MJ -> PPFD 轉換係數", 300.0, 600.0, 571.0, step=1.0, help="每 1 MJ/m² 對應多少 μmol/m²/s。室外約 550，室內通常較低 (約 450-500)。")
                #每小時MJ / m²換算 μmol / m² / s ，PPFD = MJ / m² * 1000000(MJ換算成J) * 45 % (有效光波長) * 4.57(太陽光，能量單位焦耳轉光子單位微莫耳的常數) / 3600 (秒) = 571


        # 呼叫後端運算
        matrix, dli_monthly = climate_svc.calculate_monthly_light_matrix(target_filename, transmittance_percent=trans_rate)
        
        if matrix is not None:
            # [關鍵修正] 在前端進行係數校正
            # 原本後端是用 571.2 算的，我們把它還原再乘上新的係數
            correction_factor = ppfd_coef / 571.2
            matrix = matrix * correction_factor
            dli_monthly = dli_monthly * correction_factor
            
            with c_set2:
                # -----------------------------------------------------------
                # [圖表 1] DLI 分析
                # -----------------------------------------------------------
                st.markdown("#### 📊  DLI (日累積光量，單位：mol / m² / day)")
                dli_colors = ['#10b981' if v >= target_dli else '#f59e0b' for v in dli_monthly.values]
                
                fig_dli = go.Figure(go.Bar(
                    x=dli_monthly.index, y=dli_monthly.values,
                    marker_color=dli_colors,
                    text=[f"{v:.1f}" for v in dli_monthly.values], textposition='auto',
                    name='DLI'
                ))
                fig_dli.add_hline(y=target_dli, line_dash="dash", line_color="white", annotation_text=f"上限值: {target_dli}")
                fig_dli.add_hline(y=min_dli_limit, line_dash="dash", line_color="white", annotation_text=f"下限值: {min_dli_limit}")
                fig_dli.update_layout(height=220, template="plotly_dark", margin=dict(l=20,r=20,t=30,b=10), xaxis=dict(title="月份", dtick=1), yaxis=dict(title="mol/m²/day"), showlegend=False)
                st.plotly_chart(fig_dli, use_container_width=True)

                # -----------------------------------------------------------
            # [圖表 2] 光照熱圖 (終極解法：Python 預先組好文字)
            # -----------------------------------------------------------
            st.markdown("#### 🔥 全年光照分布圖 (單位：μmol / m² / s)")
            
            # 1. 準備數據 (四捨五入取整數)
            z_values = matrix.values.round(0)
            
            # 2. 建立顏色分類矩陣 (0, 1, 2)
            z_category = np.zeros_like(z_values)
            z_category[(z_values >= comp_point) & (z_values <= sat_point)] = 1
            z_category[z_values > sat_point] = 2
            
            # 3. ★★★ 關鍵修改：在 Python 裡先把每一格的 Hover 文字組好 ★★★
            # 這樣 Plotly 只要負責顯示就好，不用處理變數，保證能顯示數字
            hover_text_matrix = []
            for y_idx, month in enumerate(matrix.index):
                row_txt = []
                for x_idx, hour in enumerate(matrix.columns):
                    val = z_values[y_idx][x_idx]
                    # 直接組合成 HTML 字串
                    txt = (f"<b>{int(month)}月 {int(hour)}:00</b><br>"
                           f"平均 PPFD: <b>{int(val)}</b> μmol<br>")
                    row_txt.append(txt)
                hover_text_matrix.append(row_txt)

            # 4. 定義 Excel 風格色票
            excel_colors = [
                [0.0, "#c7cacf"],   # 0: 灰
                [0.33, "#5E6063"],
                [0.33, "#dcca43"],  # 1: 米黃
                [0.66, "#a4920a"],
                [0.66, "#bf1919"],  # 2: 紅
                [1.0, "#d51414"]
            ]
            
            # 5. 繪製熱力圖
            fig_heat = go.Figure(data=go.Heatmap(
                z=z_category, 
                x=matrix.columns, y=matrix.index,
                colorscale=excel_colors, 
                showscale=False, 
                xgap=2, ygap=2, 
                zmin=0, zmax=2, 
                
                # ★★★ 關鍵：改用 hovertext 傳入我們組好的文字矩陣 ★★★
                hovertext=hover_text_matrix,
                
                # ★★★ 模板只要讀取 hovertext 就好，不用再寫 %{text} ★★★
                hovertemplate="%{hovertext}<extra></extra>"
            ))
            
            fig_heat.update_layout(
                height=450, 
                template="plotly_dark", 
                margin=dict(l=50, r=50, t=10, b=50),
                # 強制開啟互動
                hovermode="closest", 
                xaxis=dict(title="時間", tickmode='array', tickvals=list(range(0,24,2)), ticktext=[f"{h:02d}:00" for h in range(0,24,2)]),
                yaxis=dict(title="月份", tickmode='linear', dtick=1, autorange='reversed')
            )
            st.plotly_chart(fig_heat, use_container_width=True)
            
            cl1, cl2, cl3 = st.columns(3)
            cl1.markdown(f"⬜ **低於光補償點** (<{int(comp_point)})")
            cl2.markdown(f"🟨 **適當範圍** ({int(comp_point)}~{int(sat_point)})")
            cl3.markdown(f"🟥 **超過光飽和點** (>{int(sat_point)})")
            
        else:
            st.warning(f"⚠️ 讀取數據失敗：請確認 `{target_filename}` 格式是否正確。")
    else:
        st.warning(f"⚠️ 尚未上傳 **{CURR_LOC['name']}** 的原始氣象 CSV 檔。")


# --- Tab 2: 室內氣候 ---
with tab2:
    st.subheader("🏠 溫室內部環境模擬")
    ci, cr = st.columns([1, 2])
    
    with ci:
        with st.expander("1. 結構尺寸 (Geometry)", expanded=True):
            w = st.number_input("寬度 (m)", value=50.0, step=1.0)
            l = st.number_input("長度 (m)", value=200.0, step=1.0)
            h = st.number_input("簷高 (m)", value=6.0, step=0.5)
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
            f_count = st.number_input("排風扇數量 (台)", value=50, step=1)

            st.markdown("---")
            if not CIRC_DB.empty:
                c_idx = st.selectbox("循環扇型號", CIRC_DB.index, format_func=lambda x: f"{CIRC_DB.loc[x, 'Model']} ({CIRC_DB.loc[x, 'Airflow_CMH']:.0f} CMH)")
            c_count = st.number_input("循環扇數量 (台)", value=40, step=1)

        with st.expander("3. 環控與內裝 (Controls)", expanded=True):
            shading = st.slider("遮蔭率 (%)", 0, 90, 40)
            if not NET_DB.empty:
                n_idx = st.selectbox("防蟲網規格", NET_DB.index, format_func=lambda x: NET_DB['Label'][x])
                try: i_net = float(NET_DB.loc[n_idx, 'Openness_Percent'])
                except: i_net = 70.0
            else: i_net = st.slider("網通風率 (%)", 0, 100, 70)
            c_type = st.selectbox("栽培系統", ["NFT", "DFT", "Soil", "Pot"])
            r_vent = st.number_input("天窗面積 (m²)", value=3000.0)
            s_vent = st.number_input("側窗面積 (m²)", value=1000.0)

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

# --- Tab 3: 精細化財務分析 (自動化排程版) ---
with tab3:
    st.subheader("💰 財務損益預測 (P&L)")
    
    if not COST_DB:
        st.error("⚠️ 未讀取到成本參數檔 (data/cost_parameters.csv)，無法進行精細計算。")
        st.stop()

    # ==========================================
    # 1. 策略設定面板 (簡潔版)
    # ==========================================
    with st.container(border=True):
        st.markdown("### 🗓️ 年度生產排程與定價")
        
        with st.form("financial_form"):
            # 1. 篩選作物清單：只列出「有市場行情 CSV」的作物
            # 邏輯：檢查 CROP_DB 的名稱是否出現在 MARKET_DB 的檔名中
            valid_crop_options = []
            crop_name_to_id = {}
            
            if MARKET_DB and CROP_DB:
                mkt_keys = list(MARKET_DB.keys()) # 例如 ['lettuce.csv', 'spinach.csv']
                for cid, cdata in CROP_DB.items():
                    cname = cdata['name'] # 例如 'Lettuce'
                    # 簡單模糊比對：若 CSV 檔名包含作物名稱 (忽略大小寫)
                    # 例如 'lettuce' in 'Lettuce.csv'.lower()
                    matched_file = next((f for f in mkt_keys if cname.lower() in f.lower()), None)
                    
                    if matched_file:
                        display_name = f"{cname} (有行情檔)"
                        valid_crop_options.append(display_name)
                        crop_name_to_id[display_name] = {'id': cid, 'file': matched_file}
            
            if not valid_crop_options:
                st.warning("⚠️ 找不到與作物名稱對應的市場 CSV 檔，將顯示所有作物。")
                valid_crop_options = [v['name'] for v in CROP_DB.values()]
                crop_name_to_id = {v['name']: {'id': k, 'file': None} for k, v in CROP_DB.items()}

            # 2. 設定區塊 (兩欄)
            c_strat1, c_strat2 = st.columns(2)
            
            with c_strat1:
                st.markdown("#### 🌱 種植策略")
                crop_mode = st.radio("排程模式", ["單一作物 (全年)", "季節性輪作(先按計算損益按鈕後再繼續選擇月份)"], horizontal=True)
                
                # 變數初始化
                sel_winter = None
                sel_summer = None
                summer_months = []
                
                if crop_mode == "單一作物 (全年)":
                    sel_winter = st.selectbox("選擇全年作物", valid_crop_options)
                    sel_summer = sel_winter # 夏天跟冬天一樣
                    summer_months = [] 
                else:
                    # 季節輪作
                    col_w, col_s = st.columns(2)
                    with col_w:
                        sel_winter = st.selectbox("❄️ 冷涼月份作物", valid_crop_options, index=0)
                    with col_s:
                        # 預設選第二個，如果有的話
                        idx_sum = 1 if len(valid_crop_options) > 1 else 0
                        sel_summer = st.selectbox("☀️ 炎熱月份作物", valid_crop_options, index=idx_sum)
                    
                    summer_months = st.multiselect("選擇夏季月份", range(1, 13), default=[6, 7, 8, 9])
            
            with c_strat2:
                st.markdown("#### 💵 定價策略")
                price_mode = st.radio("價格來源", ["引用市場資料庫 (自動對應)", "自訂固定均價"], horizontal=True)
                
                base_price = 0
                use_season_fluc = False
                
                if "引用市場資料庫" in price_mode:
                    st.info("💡 系統將根據左側選定的作物，自動抓取對應月份的歷史價格 CSV。")
                else:
                    base_price = st.number_input("設定平均批發價 ($/kg)", value=45.0, step=5.0)
                    use_season_fluc = st.checkbox("啟用季節波動 (夏季 +40%)", value=True)

            st.markdown("---")
            
            # 生產參數
            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                area_m2 = st.session_state.gh_specs['width'] * st.session_state.gh_specs['length']
                st.write(f"📐 面積: **{area_m2:,.0f}** m²")
            with c_p2:
                den = st.number_input("種植密度 (株/m²)", value=st.session_state.planting_density)
            with c_p3:
                cyc = st.number_input("年周轉率 (次/年)", value=st.session_state.annual_cycles)
            
            # 送出按鈕
            submit_btn = st.form_submit_button("🚀 計算損益", type="primary", use_container_width=True)

            if submit_btn:
                # === 後端運算邏輯 ===
                final_monthly_crops = []
                final_monthly_prices = []
                
                # 1. 準備作物 ID 與 檔名
                winter_id = crop_name_to_id[sel_winter]['id']
                winter_file = crop_name_to_id[sel_winter]['file']
                
                summer_id = crop_name_to_id[sel_summer]['id']
                summer_file = crop_name_to_id[sel_summer]['file']
                
                # 2. 逐月生成數據
                for m in range(1, 13):
                    # A. 決定當月作物
                    is_summer = m in summer_months
                    curr_crop_id = summer_id if is_summer else winter_id
                    curr_file = summer_file if is_summer else winter_file
                    
                    final_monthly_crops.append(curr_crop_id)
                    
                    # B. 決定當月價格
                    p = 0
                    if "引用市場資料庫" in price_mode and curr_file and MARKET_DB:
                        # 從資料庫抓價格 (注意：MARKET_DB[file] 是一個 12 個月的陣列，索引是 m-1)
                        p = MARKET_DB[curr_file][m-1]
                    else:
                        # 手動價格
                        p = base_price
                        if use_season_fluc and is_summer:
                            p = base_price * 1.4
                    
                    final_monthly_prices.append(p)
                
                # 3. 存入 Session
                st.session_state.monthly_crops = final_monthly_crops
                st.session_state.market_prices = final_monthly_prices
                st.session_state.planting_density = den
                st.session_state.annual_cycles = cyc
                
                st.rerun()

    # ==========================================
    # 2. 運算結果呈現 (保持原樣)
    # ==========================================
    
    # 執行物理模擬
    res_sim = SimulationService.run_simulation(
        st.session_state.gh_specs, st.session_state.fan_specs, CURR_LOC['data'], 
        st.session_state.monthly_crops, st.session_state.planting_density, 
        st.session_state.annual_cycles, st.session_state.market_prices, 
        CROP_DB, MAT_DB
    )
    df_sim = pd.DataFrame(res_sim['data'])
    if 'price' not in df_sim.columns: df_sim['price'] = st.session_state.market_prices

    # 財務運算
    wage_worker = float(COST_DB.get('Hourly_Wage_Worker', 200))
    workers_per_ha = float(COST_DB.get('Workers_Per_Ha', 12))
    seed_cost = float(COST_DB.get('Seed_Cost', 0.8))
    subst_cost = float(COST_DB.get('Substrate_Cost', 2.5))
    pack_cost = float(COST_DB.get('Packaging_Cost', 2.0))
    elec_rate = float(COST_DB.get('Electricity_Rate', 3.5))
    
    area_ha = area_m2 / 10000.0
    total_revenue = res_sim['totalRevenue']
    total_yield_kg = res_sim['totalYield']
    total_plants = area_m2 * den * cyc 
    
    req_workers = max(1, workers_per_ha * area_ha) 
    cost_labor = req_workers * wage_worker * 8 * 25 * 12
    cost_material = (seed_cost + subst_cost) * total_plants
    cost_packaging = (total_yield_kg / 0.25) * pack_cost 
    fan_kw = st.session_state.fan_specs['exhaustCount'] * st.session_state.get('sel_fan_power', 1000) / 1000
    cost_energy = fan_kw * 10 * 365 * elec_rate
    total_opex = cost_labor + cost_material + cost_packaging + cost_energy
    
    capex_struct = area_m2 * float(COST_DB.get('Greenhouse_Structure_Price', 5500))
    life_struct = float(COST_DB.get('Structure_Life_Year', 20))
    capex_fans = st.session_state.fan_specs['exhaustCount'] * float(COST_DB.get('Fan_Unit_Price', 16000))
    life_fans = float(COST_DB.get('Fan_Life_Year', 5))
    depr_annual = (capex_struct / life_struct) + (capex_fans / life_fans)
    
    net_profit = total_revenue - total_opex - depr_annual
    roi = (net_profit / (capex_struct + capex_fans)) * 100 if (capex_struct > 0) else 0
    
    st.markdown("---")
    st.markdown("### 📊 年度財務指標")
    
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("預估年營收", f"${int(total_revenue/10000):,} 萬")
    k2.metric("總營運成本 (OPEX)", f"${int(total_opex/10000):,} 萬", delta="-支出", delta_color="inverse")
    k3.metric("預估稅前淨利", f"${int(net_profit/10000):,} 萬", delta=f"ROI {roi:.1f}%")
    k4.metric("損益平衡點", f"${int((total_opex+depr_annual)/total_yield_kg):.1f} /kg" if total_yield_kg>0 else "N/A")
    
    st.markdown("---")
    
    chart_c1, chart_c2 = st.columns(2)
    with chart_c1:
        st.markdown("##### 🍰 成本結構分析")
        cost_data = pd.DataFrame([
            {'Item': '人力成本', 'Value': cost_labor},
            {'Item': '資材費用', 'Value': cost_material + cost_packaging},
            {'Item': '能源電費', 'Value': cost_energy},
            {'Item': '設備折舊', 'Value': depr_annual}
        ])
        fig_pie = go.Figure(data=[go.Pie(labels=cost_data['Item'], values=cost_data['Value'], hole=.4)])
        fig_pie.update_layout(height=350, showlegend=True, legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig_pie, use_container_width=True)
            
    with chart_c2:
        st.markdown("##### 📈 累計現金流 (20 Year ROI)")
        monthly_net_cash = (total_revenue - total_opex) / 12
        initial_investment = -(capex_struct + capex_fans)
        months_proj = list(range(0, 240))
        cash_flow = [initial_investment + (monthly_net_cash * m) for m in months_proj]
        
        fig_cf = go.Figure()
        fig_cf.add_hline(y=0, line_dash="dash", line_color="white")
        fig_cf.add_trace(go.Scatter(x=months_proj, y=cash_flow, mode='lines', fill='tozeroy', name='累計現金流', line=dict(color='#3b82f6', width=3), fillcolor='rgba(59, 130, 246, 0.1)'))
        if next((i for i, v in enumerate(cash_flow) if v >= 0), None):
            fig_cf.add_vline(x=next((i for i, v in enumerate(cash_flow) if v >= 0), None), line_dash="dot", line_color="#22c55e", annotation_text="回本")
        fig_cf.update_layout(height=350, xaxis=dict(title="營運月份", tickmode='linear', dtick=6), yaxis=dict(title="累計金額 ($)"), hovermode="x unified")
        st.plotly_chart(fig_cf, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🗓️ 月份產能與營收詳情")
    
    # 圖表：月份產量與營收
    fig_monthly = make_subplots(specs=[[{"secondary_y": True}]])
    # 根據不同作物顯示不同顏色 (進階視覺化)
    # 我們可以根據 df_sim['cropName'] 來分組，這裡簡單統一顏色
    fig_monthly.add_trace(go.Bar(x=df_sim['month'], y=df_sim['yield'], name="月產量 (kg)", marker_color='#3b82f6', opacity=0.6), secondary_y=False)
    fig_monthly.add_trace(go.Scatter(x=df_sim['month'], y=df_sim['revenue'], name="月營收 ($)", mode='lines+markers', line=dict(color='#10b981', width=3), marker=dict(size=6)), secondary_y=True)
    
    fig_monthly.update_layout(height=400, hovermode="x unified", xaxis=dict(title="月份", tickmode='linear', dtick=1), legend=dict(orientation="h", y=1.1))
    fig_monthly.update_yaxes(title_text="產量 (kg)", secondary_y=False)
    fig_monthly.update_yaxes(title_text="營收 ($)", secondary_y=True, showgrid=False)
    st.plotly_chart(fig_monthly, use_container_width=True)

    with st.expander("查看詳細數據表"):
        st.dataframe(
            df_sim[['month', 'cropName', 'yield', 'revenue', 'price', 'efficiency', 'tempIn']],
            column_config={
                "month": "月份", "cropName": "作物", 
                "yield": st.column_config.NumberColumn("產量 (kg)", format="%.0f"),
                "revenue": st.column_config.NumberColumn("營收 ($)", format="$%.0f"),
                "price": st.column_config.NumberColumn("單價 ($)", format="$%.1f"),
                "efficiency": st.column_config.NumberColumn("環境效率 (%)", format="%.1f"),
                "tempIn": st.column_config.NumberColumn("均溫 (°C)", format="%.1f")
            }, hide_index=True, use_container_width=True
        )

# --- Tab 4: 設備最佳化分析 (整合 COST_DB) ---
with tab4:
    st.subheader("⚖️ 設備最佳化：ROI 邊際效益分析")
    
    if 'gh_specs' not in st.session_state:
        st.warning("⚠️ 請先至「Tab 2: 內部微氣候」完成規格設定。")
        st.stop()
        
    gh_specs = st.session_state.gh_specs
    fan_specs = st.session_state.fan_specs
    
    # 1. 分析目標
    st.markdown("#### 🎯 選擇要最佳化的系統")
    target_sys = st.radio(
        "請選擇分析對象", 
        ["負壓風扇 (Fans)", "內遮蔭 (Shading)", "天窗面積 (Vents)", "噴霧系統 (Fogging)"], 
        horizontal=True
    )
    st.markdown("---")
    
    col_opt1, col_opt2 = st.columns([1, 2.5])
    
    # --- 左側：自動讀取 CSV 成本 ---
    with col_opt1:
        st.markdown("### ⚙️ 成本參數 (Auto-Load)")
        
        # 讀取共用參數
        elec_rate = st.number_input("電費費率 ($/度)", value=float(COST_DB.get('Electricity_Rate', 3.5)), step=0.5)
        run_hours = st.number_input("年運轉時數 (hr)", value=3000, step=100)
        
        # 依據選擇，從 CSV 撈取特定參數
        capex_unit = 0
        life_year = 5
        opex_unit = 0
        x_label = ""
        sim_range = range(0, 1)
        
        if "Fans" in target_sys:
            fan_price = float(COST_DB.get('Fan_Unit_Price', 16000))
            fan_life = float(COST_DB.get('Fan_Life_Year', 5))
            fan_power = st.session_state.get('sel_fan_power', 1000.0)
            
            st.info(f"📋 參數來源：\n• 單價: ${fan_price:,.0f} (Fan_Unit_Price)\n• 年限: {fan_life} 年")
            
            unit_price = st.number_input("設備單價 ($/台)", value=fan_price)
            life_year = st.number_input("折舊年限 (年)", value=fan_life)
            
            capex_unit = unit_price / life_year # 年攤提
            opex_unit = (fan_power / 1000) * run_hours * elec_rate # 年電費
            
            sim_range = range(0, 50, 2) # 0~50台
            x_label = "風扇數量 (台)"
            
        elif "Shading" in target_sys:
            net_price = float(COST_DB.get('Net_Unit_Price', 60))
            net_life = float(COST_DB.get('Net_Life_Year', 3))
            
            st.info(f"📋 參數來源：\n• 單價: ${net_price:,.0f}/m² (Net_Unit_Price)\n• 年限: {net_life} 年")
            
            unit_price = st.number_input("每 m² 成本 ($)", value=net_price)
            life_year = st.number_input("折舊年限 (年)", value=net_life)
            
            # 遮蔭網總價 = 面積 * 遮蔭率 * 單價
            # 這裡計算「每 1% 遮蔭率」的年成本係數
            floor_area = gh_specs['width'] * gh_specs['length']
            capex_unit = (floor_area * unit_price / 100) / life_year
            opex_unit = 0 # 遮蔭網無運轉電費
            
            sim_range = range(0, 100, 10)
            x_label = "遮蔭率 (%)"
            
        elif "Vents" in target_sys:
            vent_price = float(COST_DB.get('Vent_Structure_Price', 4500))
            vent_life = float(COST_DB.get('Structure_Life_Year', 15))
            
            st.info(f"📋 參數來源：\n• 結構單價: ${vent_price:,.0f}/m²\n• 年限: {vent_life} 年")
            
            unit_price = st.number_input("結構造價 ($/m²)", value=vent_price)
            life_year = st.number_input("折舊年限 (年)", value=vent_life)
            
            capex_unit = unit_price / life_year
            opex_unit = 0 # 自然通風無電費
            
            max_area = int(gh_specs['width'] * gh_specs['length'])
            step = max(1, int(max_area/10))
            sim_range = range(0, max_area, step)
            x_label = "天窗面積 (m²)"

        elif "Fogging" in target_sys:
            fog_sys_price = float(COST_DB.get('Fog_System_Price', 15))
            pump_life = float(COST_DB.get('Pump_Life_Year', 7))
            water_rate = float(COST_DB.get('Water_Rate', 12.0))
            
            st.info(f"📋 參數來源：\n• 系統單價: ${fog_sys_price}/(g/m²)\n• 水費: ${water_rate}/度")
            
            unit_price = st.number_input("系統造價 ($/單位流量)", value=fog_sys_price)
            life_year = st.number_input("設備年限 (年)", value=pump_life)
            
            # 這裡比較複雜，隨流量變動
            sim_range = range(0, 600, 20)
            x_label = "噴霧流量 (g/m²/hr)"

    # --- 右側：執行運算 ---
    with col_opt2:
        if st.button("🚀 開始 ROI 分析", type="primary", use_container_width=True):
            results = []
            floor_area = gh_specs['width'] * gh_specs['length']
            
            with st.spinner("正在進行邊際效益模擬..."):
                for val in sim_range:
                    tmp_gh = gh_specs.copy()
                    tmp_fan = fan_specs.copy()
                    cost_annual = 0
                    
                    # 套用變數
                    if "Fans" in target_sys:
                        tmp_fan['exhaustCount'] = val
                        cost_annual = val * (capex_unit + opex_unit)
                    elif "Shading" in target_sys:
                        tmp_gh['shadingScreen'] = val
                        cost_annual = val * capex_unit
                    elif "Vents" in target_sys:
                        tmp_gh['roofVentArea'] = val
                        cost_annual = val * capex_unit
                    elif "Fogging" in target_sys:
                        tmp_gh['_fog_capacity'] = val
                        # 噴霧成本 = 設備折舊 + 水費 + 電費
                        total_flow_g = val * floor_area
                        capex = (total_flow_g * unit_price) / life_year
                        
                        water_ton = (total_flow_g * run_hours) / 1_000_000
                        water_cost = water_ton * water_rate
                        elec_cost = (total_flow_g * 0.005) * run_hours * elec_rate / 1000 # 假設泵浦能耗
                        cost_annual = capex + water_cost + elec_cost

                    # 模擬營收
                    res = SimulationService.run_simulation(
                        tmp_gh, tmp_fan, CURR_LOC['data'], 
                        st.session_state.monthly_crops, st.session_state.planting_density, 
                        st.session_state.annual_cycles, st.session_state.market_prices, 
                        CROP_DB, MAT_DB
                    )
                    
                    revenue = res['totalRevenue']
                    # 淨利 = 營收 - (變動成本 + 此設備的額外成本)
                    # 為了簡化比較，我們假設其他成本不變，只看邊際變化
                    # 所以這裡的 "Net Benefit" 是 (總營收 - 此項設備總年費)
                    marginal_profit = revenue - cost_annual
                    
                    results.append({
                        "Value": val, "Revenue": revenue, "Cost": cost_annual, "Profit": marginal_profit
                    })
            
            # 繪圖
            df_opt = pd.DataFrame(results)
            best_row = df_opt.loc[df_opt['Profit'].idxmax()]
            
            st.success(f"🏆 最佳配置點：**{int(best_row['Value'])}** {x_label.split('(')[0]}，預估淨效益 **${int(best_row['Profit']):,}**")
            
            fig_opt = make_subplots(specs=[[{"secondary_y": True}]])
            
            # 淨利曲線 (最重要的指標)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Profit'], name="淨效益 (Revenue-Cost)",
                mode='lines', line=dict(color='#22c55e', width=4), fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.15)'
            ), secondary_y=False)
            
            # 成本曲線 (紅色)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Cost'], name="投入成本 (Cost)",
                mode='lines', line=dict(color='#ef4444', width=2, dash='dot')
            ), secondary_y=False)
            
            # 營收曲線 (藍色)
            fig_opt.add_trace(go.Scatter(
                x=df_opt['Value'], y=df_opt['Revenue'], name="總營收 (Revenue)",
                mode='lines', line=dict(color='#3b82f6', width=2, dash='dash')
            ), secondary_y=True) # 放右軸，避免數值差異太大擠壓圖形

            fig_opt.update_layout(
                title=f"{target_sys} 投資效益分析",
                template="plotly_dark", hovermode="x unified", height=450,
                xaxis_title=x_label,
                legend=dict(orientation="h", y=1.1)
            )
            fig_opt.update_yaxes(title_text="效益/成本 ($)", secondary_y=False)
            fig_opt.update_yaxes(title_text="總營收 ($)", secondary_y=True, showgrid=False)
            
            st.plotly_chart(fig_opt, use_container_width=True)
            
            with st.expander("詳細數據"):
                st.dataframe(df_opt.style.format("{:,.0f}"))