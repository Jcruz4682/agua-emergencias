# ====================================================
# STREAMLIT: Redistribución de agua en emergencias
# Doctorado en Ciencias Ambientales - UNMSM
# Autor: Mg. Ing. Joel Cruz Machacuay
# ====================================================

import streamlit as st
import os
import pandas as pd
import geopandas as gpd
import folium
from folium import plugins
from shapely.ops import unary_union
from streamlit_folium import st_folium
import plotly.express as px

# --- LOGIN SIMPLE ---
USERS = {"jurado1": "clave123", "jurado2": "clave456"}
if "auth" not in st.session_state:
    st.session_state["auth"] = False
if not st.session_state["auth"]:
    st.title("🔐 Acceso restringido")
    user = st.text_input("Usuario")
    pw = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if user in USERS and USERS[user] == pw:
            st.session_state["auth"] = True
            st.success("Acceso permitido")
        else:
            st.error("Credenciales inválidas")
    st.stop()

# --- TITULO PRINCIPAL ---
st.markdown(
    "<h2 style='text-align:center; color:#003366;'>"
    "MODELO TÉCNICO-OPERATIVO DE REDISTRIBUCIÓN TEMPORAL DE USO DE AGUA INDUSTRIAL PARA EMERGENCIAS HÍDRICAS"
    "</h2>",
    unsafe_allow_html=True,
)

# --- RUTA LOCAL ---
data_dir = os.path.join(os.path.dirname(__file__), "Datos_qgis")

# --- CONFIG CISERNAS ---
cisternas = {"19 m³": {"capacidad": 19}, "34 m³": {"capacidad": 34}}

# ========= ESTILO DE LA SIDEBAR =========
st.markdown("""
<style>
  [data-testid="stSidebar"]{
    background-color:#f7f7f7;border-right:2px solid #d1d1d1;border-radius:0 10px 10px 0;padding:20px;
  }
  [data-testid="stSidebar"] h2, h3, h4, label{color:#333;font-family:'Segoe UI',sans-serif;}
</style>
""", unsafe_allow_html=True)

# ========= CONTROLES =========
st.sidebar.header("⚙️ Configuración del análisis")

modo = st.sidebar.radio(
    "Seleccionar nivel de análisis",
    ["Sector", "Distrito", "Combinación Distritos", "Resumen general"]
)
escenario_sel = st.sidebar.selectbox(
    "Seleccionar Escenario (% del caudal disponible por pozo)", [10, 20, 30]
)
cisterna_sel = st.sidebar.radio("Seleccionar tipo de cisterna", list(cisternas.keys()))

st.sidebar.markdown("**Consumo de combustible:** 6.0 gal/h")
consumo_gal_h = 6.0
st.sidebar.markdown("**Costo por galón:** S/ 20.00")
costo_galon = 20.0
st.sidebar.markdown("**Velocidad de referencia:** 30 km/h")
velocidad_kmh = 30.0

# ========= FUNCIONES =========
def normalizar(x):
    return str(x).strip().upper().replace("Á","A").replace("É","E").replace("Í","I").replace("Ó","O").replace("Ú","U")

def calcular_costos(aporte, dist_km, tipo_cisterna):
    cap = cisternas[tipo_cisterna]["capacidad"]
    viajes = int(aporte // cap + (aporte % cap > 0))
    horas_por_viaje = (2.0 * dist_km) / max(velocidad_kmh, 1e-6)
    consumo_por_viaje = horas_por_viaje * consumo_gal_h
    costo_por_viaje = consumo_por_viaje * costo_galon
    return viajes, viajes*costo_por_viaje, viajes*consumo_por_viaje

def asignar_pozos(geom_obj, demanda, escenario, tipo_cisterna, pozos_gdf):
    resultados, restante = [], demanda
    total_viajes, total_costo, total_consumo = 0, 0.0, 0.0
    pozos_tmp = []
    for _, pozo in pozos_gdf.iterrows():
        q_m3_dia = float(pozo.get("Q_m3_dia", 0.0))
        if q_m3_dia > 0:
            dist_km = pozo.geometry.distance(geom_obj) * 111.0
            aporte_disp = q_m3_dia * (escenario / 100.0)
            pozos_tmp.append((dist_km, pozo.get("ID","NA"), aporte_disp, pozo.geometry))
    pozos_tmp.sort(key=lambda x: x[0])
    for dist_km, pozo_id, aporte_disp, geom in pozos_tmp:
        if restante <= 0: break
        aporte_asignado = min(aporte_disp, restante)
        viajes, costo, consumo = calcular_costos(aporte_asignado, dist_km, tipo_cisterna)
        resultados.append([pozo_id, aporte_asignado, viajes, costo, consumo, round(dist_km,3), geom])
        restante -= aporte_asignado
        total_viajes += viajes; total_costo += costo; total_consumo += consumo
    return resultados, restante, total_viajes, total_costo, total_consumo

def rename_columns(df):
    mapping = {
        "Pozo_ID": "N° Pozo",
        "Aporte": "Aporte (m³/día)",
        "Viajes": "N° Viajes",
        "Costo": "Costo (Soles)",
        "Consumo": "Consumo (galones)",
        "Dist_km": "Distancia (km)",
        "Sector": "Sector",
        "Demanda": "Demanda (m³/día)",
        "Cobertura_%": "Cobertura (%)",
        "Faltante": "Faltante (m³/día)",
        "Distrito": "Distrito",
    }
    return df.rename(columns={c: mapping.get(c,c) for c in df.columns})

def plot_bar(df, x, y, title, xlabel, ylabel):
    fig = px.bar(df, x=x, y=y, title=title, color=y,
                 color_continuous_scale=px.colors.sequential.Plasma, text_auto=True,
                 hover_data={y:":.2f"})
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color="#003366")),
        xaxis_title=xlabel, yaxis_title=ylabel,
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        coloraxis_colorbar=dict(title=y, tickformat=".0f")
    )
    return fig

def mostrar_kpis(nombre, demanda, restante, viajes, costo, consumo, resultados):
    st.markdown(f"<h3 style='color:#003366;'>{nombre}</h3>", unsafe_allow_html=True)
    fila1 = st.columns(3); fila2 = st.columns(3); fila3 = st.columns(1)
    cobertura = (1-restante/demanda)*100 if demanda > 0 else 0
    eficiencia = ((demanda - restante)/costo) if costo > 0 else 0
    fila1[0].metric("🚰 Demanda (m³/día)", f"{demanda:,.1f}")
    fila1[1].metric("🎯 Cobertura (%)", f"{cobertura:.1f}%")
    fila1[2].metric("🏭 Pozos usados", f"{len(resultados)}")
    fila2[0].metric("🚛 Viajes", f"{viajes}")
    fila2[1].metric("💵 Costo (S/)", f"{costo:,.2f}")
    fila2[2].metric("⛽ Consumo (gal)", f"{consumo:,.1f}")
    fila3[0].metric("⚙️ Eficiencia hídrico-económica", f"{eficiencia:,.2f} m³/S/")
    st.caption("⚠️ Los costos corresponden únicamente al consumo de combustible.")

def agregar_conclusion(contexto, nombre, demanda, restante, viajes, costo, consumo, pozos):
    cobertura = (1 - restante / demanda) * 100 if demanda > 0 else 0
    cobertura_texto = f"{cobertura:.1f}%"
    base_texto = (
        f"En escenario de <b>emergencia hídrica</b> en el <b>{contexto.lower()} {nombre}</b>, "
        f"la demanda diaria (<b>{demanda:.2f} m³</b>) "
    )
    if restante <= 0 or cobertura >= 99.9:
        texto = (base_texto +
            f"fue <b>totalmente satisfecha ({cobertura_texto})</b> con el aporte de "
            f"<b>{len(pozos)} pozos industriales</b>, requiriendo <b>{viajes} viajes</b> "
            f"con <b>cisternas de {cisterna_sel}</b>.<br>"
            f"El traslado implicó un <b>consumo de {consumo:.1f} gal</b> de combustible, "
            f"equivalente a <b>S/ {costo:,.2f}</b> en costos operativos.")
        color, borde, icono = "#e8f5e9", "#2e7d32", "✅"
    else:
        texto = (base_texto +
            f"<b>no fue satisfecha en su totalidad ({cobertura_texto})</b>, "
            f"a pesar del aporte de <b>{len(pozos)} pozos industriales</b>, que requirieron "
            f"<b>{viajes} viajes</b> con <b>cisternas de {cisterna_sel}</b>.<br>"
            f"El traslado implicó un <b>consumo de {consumo:.1f} gal</b> de combustible, "
            f"equivalente a <b>S/ {costo:,.2f}</b> en costos operativos.")
        color, borde, icono = "#fff3e0", "#ef6c00", "⚠️"
    st.markdown(f"""
    <div style='text-align:center; margin-top:25px;'>
        <h4 style='color:#003366; font-family:"Segoe UI", sans-serif;'>📋 Conclusión Operativa</h4>
    </div>
    <div style='background-color:{color};
                border-left:6px solid {borde};
                padding:15px 22px; margin-top:8px; border-radius:6px;
                color:#222; font-size:16px; line-height:1.6; font-family:"Segoe UI", sans-serif;'>
        <b>{icono} Conclusión:</b><br>{texto}
    </div>
    """, unsafe_allow_html=True)

def agregar_leyenda(m):
    legend_html = """
    <div style="position: fixed; bottom: 20px; left: 20px; width: 220px;
                background-color: white; border:2px solid grey; z-index:9999;
                font-size:14px; padding: 10px; color:black;">
    <b>Leyenda</b><br>
    <span style="color:blue;">●</span> Pozos<br>
    <span style="color:red;">●</span> Sectores<br>
    <span style="color:green;">●</span> Distritos<br>
    <span style="color:purple;">●</span> Distritos combinados
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    return m

def dibujar_pozos(resultados, m):
    df = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"])
    for _, row in df.iterrows():
        geom = row["geom"]
        if geom is not None:
            folium.CircleMarker(
                location=[geom.y, geom.x], radius=6, color="blue", fill=True, fill_opacity=0.7,
                popup=(f"Pozo {row['Pozo_ID']}<br>"
                       f"Aporte: {row['Aporte']:.2f} m³/día<br>"
                       f"Viajes: {row['Viajes']}<br>"
                       f"Costo: S/ {row['Costo']:.2f}<br>"
                       f"Consumo: {row['Consumo']:.1f} gal<br>"
                       f"Distancia: {row['Dist_km']} km")
            ).add_to(m)
    return m

# ========= CARGA DE DATOS =========
sectores_gdf  = gpd.read_file(os.path.join(data_dir, "Sectores.geojson")).to_crs(epsg=4326)
distritos_gdf = gpd.read_file(os.path.join(data_dir, "DISTRITOS_Final.geojson")).to_crs(epsg=4326)
pozos_gdf     = gpd.read_file(os.path.join(data_dir, "Pozos.geojson")).to_crs(epsg=4326)
demandas_sectores  = pd.read_csv(os.path.join(data_dir, "Demandas_Sectores_30lhd.csv"))
demandas_distritos = pd.read_csv(os.path.join(data_dir, "Demandas_Distritos_30lhd.csv"))

sectores_gdf["ZONENAME"] = sectores_gdf["ZONENAME"].apply(normalizar)
demandas_sectores["ZONENAME"] = demandas_sectores["ZONENAME"].apply(normalizar)
distritos_gdf["NOMBDIST"] = distritos_gdf["NOMBDIST"].apply(normalizar)
demandas_distritos["Distrito"] = demandas_distritos["Distrito"].apply(normalizar)

sectores_gdf = sectores_gdf.merge(demandas_sectores[["ZONENAME","Demanda_m3_dia"]], on="ZONENAME", how="left")
distritos_gdf = distritos_gdf.merge(
    demandas_distritos[["Distrito","Demanda_Distrito_m3_30_lhd"]],
    left_on="NOMBDIST", right_on="Distrito", how="left"
)

# ========= SECTOR =========
if modo == "Sector":
    sector_sel = st.sidebar.selectbox("Seleccionar sector", sorted(sectores_gdf["ZONENAME"].dropna().unique()))
    row = sectores_gdf[sectores_gdf["ZONENAME"] == sector_sel].iloc[0]
    demanda = float(row.get("Demanda_m3_dia",0))
    resultados, restante, viajes, costo, consumo = asignar_pozos(row.geometry.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)

    # --- Contexto descriptivo adaptado ---
if modo == "Sector":
    nivel_texto = "Por sector"
elif modo == "Distrito":
    nivel_texto = "Por distrito"
elif modo == "Combinación Distritos":
    nivel_texto = "Por combinación de distritos"
else:
    nivel_texto = "Resumen general"

st.markdown(
    f"### 🧩 Contexto: Escenario {escenario_sel}% – Cisterna {cisterna_sel} – Nivel: {nivel_texto}"
)
    mostrar_kpis(f"📍 Sector {sector_sel}", demanda, restante, viajes, costo, consumo, resultados)

    # Tabla
    st.markdown("### 📘 Resultados por pozo")
    st.caption("Pozos industriales asignados al sector, con aporte, viajes, consumo y costo.")
    df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
    df_res = rename_columns(df_res)
    styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
    "Aporte (m³/día)": "{:,.2f}",
    "Costo (Soles)": "{:,.2f}",
    "Consumo (galones)": "{:,.1f}",
    "Distancia (km)": "{:,.2f}"
})
    st.dataframe(styled_df, use_container_width=True)

    # Gráfico
    st.markdown("### 📊 Distribución del aporte por pozo")
    st.caption("Aporte diario de cada pozo industrial en el escenario seleccionado.")
    st.plotly_chart(
        plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                 title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
        use_container_width=True
    )

        # --- 🗺️ MAPA CON OPCIÓN DE ZONA DE CALOR ---
    st.markdown("### 🗺️ Ubicación espacial")
    show_heat = st.checkbox("Mostrar mapa de calor por costo (S/)", value=False, key=f"heat_{modo.lower()}")

    m = folium.Map(location=[row.geometry.centroid.y, row.geometry.centroid.x],
                   zoom_start=12 if modo == "Distrito" else 13,
                   tiles="cartodbpositron")

    # Capa base del área analizada
    color_mapa = "green" if modo == "Distrito" else "red"
    folium.GeoJson(row.geometry, style_function=lambda x: {"color": color_mapa, "fillOpacity": 0.3}).add_to(m)

    # Capa de pozos seleccionados
    m = dibujar_pozos(resultados, m)

    # --- ZONA DE CALOR (si se activa la casilla) ---
    if show_heat and len(resultados) > 0:
        heat_data = [[r[6].y, r[6].x, r[3]] for r in resultados if r[6] is not None]
        plugins.HeatMap(heat_data, radius=18, blur=25, max_zoom=10).add_to(m)

        # Leyenda específica para el mapa de calor
        legend_heat = """
        <div style="position: fixed; bottom: 20px; right: 20px; width: 210px;
                    background-color: white; border:2px solid #666; z-index:9999;
                    font-size:14px; padding:10px; border-radius:8px;">
            <b>Mapa de calor – Costo operativo (S/)</b><br>
            <span style="color:#ff0000;">●</span> Mayor costo<br>
            <span style="color:#ffcc00;">●</span> Costo medio<br>
            <span style="color:#00cc00;">●</span> Menor costo
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_heat))

    # Leyenda general del mapa (pozos, sectores o distritos)
    m = agregar_leyenda(m)

    st_folium(m, width=900, height=500)

    # =====================================================
    # 🔍 ANÁLISIS COMPARATIVO POST-CONCLUSIÓN
    # =====================================================
    st.markdown("## 📈 Análisis comparativo de eficiencia hídrico-económica")
    st.caption("Evaluación del desempeño del modelo frente a distintos escenarios de redistribución y tipos de cisterna.")

    # --- Comparativa entre escenarios y tipos de cisterna ---
    escenarios = [10, 20, 30]
    tipos_cisterna = ["19 m³", "34 m³"]
    comparacion_total = []

    for tipo in tipos_cisterna:
        for esc in escenarios:
            _, restante_esc, _, costo_esc, _ = asignar_pozos(row.geometry.centroid, demanda, esc, tipo, pozos_gdf)
            eficiencia_esc = ((demanda - restante_esc) / costo_esc) if costo_esc > 0 else 0
            comparacion_total.append({
                "Escenario (%)": esc,
                "Cisterna": tipo,
                "Eficiencia (m³/S/)": eficiencia_esc
            })

    df_comp = pd.DataFrame(comparacion_total)

    # --- Gráfico 1: eficiencia por escenario y tipo de cisterna ---
    df_comp["Eficiencia_label"] = df_comp["Eficiencia (m³/S/)"].apply(lambda x: f"{x:.3f}")

    fig_eff = px.line(
        df_comp,
        x="Escenario (%)",
        y="Eficiencia (m³/S/)",
        color="Cisterna",
        markers=True,
        text="Eficiencia_label",
        title="Comparación de eficiencia hídrico-económica por escenario y tipo de cisterna",
        color_discrete_map={"19 m³": "#0077b6", "34 m³": "#009e73"}
    )

    fig_eff.update_traces(textposition="top center", textfont_size=12)
    fig_eff.update_layout(
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        title=dict(font=dict(size=16, color="#003366")),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis_title="Eficiencia (m³ por S/)",
        xaxis_title="Escenario de redistribución (%)",
        legend_title="Tipo de cisterna"
    )
    st.plotly_chart(fig_eff, use_container_width=True)

    # --- Gráfico 2: eficiencia promedio por tipo de cisterna ---
    df_prom = df_comp.groupby("Cisterna")["Eficiencia (m³/S/)"].mean().reset_index()

    fig_bar = px.bar(
        df_prom,
        x="Cisterna",
        y="Eficiencia (m³/S/)",
        color="Cisterna",
        color_discrete_sequence=["#0077b6", "#009e73"],
        text_auto=".3f",
        title="Eficiencia promedio por tipo de cisterna (promedio de los tres escenarios)"
    )

    fig_bar.update_layout(
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        title=dict(font=dict(size=16, color="#003366")),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis_title="Eficiencia (m³ por S/)"
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Resumen interpretativo automático ---
    cisterna_ganadora = df_prom.loc[df_prom["Eficiencia (m³/S/)"].idxmax(), "Cisterna"]
    eff_max = df_prom["Eficiencia (m³/S/)"].max()

    st.markdown(f"""
    <div style='background-color:#f0f9ff; border-left:6px solid #0066cc;
                padding:12px 20px; margin-top:15px; border-radius:6px;
                font-size:16px; color:#222; font-family:"Segoe UI", sans-serif;'>
        <b>📊 Síntesis comparativa:</b><br>
        En este escenario, la <b>cisterna de {cisterna_ganadora}</b> mostró el mejor desempeño,
        con una eficiencia promedio de <b>{eff_max:.3f} m³/S/</b> considerando los tres niveles de redistribución (10 %, 20 % y 30 %).<br>
        Esto indica que, bajo condiciones similares, el uso de dicha flota optimiza la relación entre
        <b>volumen redistribuido y costo operativo</b>, reforzando la capacidad técnica del modelo en este contexto.
    </div>
    """, unsafe_allow_html=True)

# ========= DISTRITO =========
elif modo == "Distrito":
    dist_sel = st.sidebar.selectbox("Seleccionar distrito", sorted(distritos_gdf["NOMBDIST"].dropna().unique()))
    row = distritos_gdf[distritos_gdf["NOMBDIST"] == dist_sel].iloc[0]
    demanda = float(row.get("Demanda_Distrito_m3_30_lhd",0))
    resultados, restante, viajes, costo, consumo = asignar_pozos(row.geometry.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)

    # --- Contexto descriptivo adaptado ---
if modo == "Sector":
    nivel_texto = "Por sector"
elif modo == "Distrito":
    nivel_texto = "Por distrito"
elif modo == "Combinación Distritos":
    nivel_texto = "Por combinación de distritos"
else:
    nivel_texto = "Resumen general"

st.markdown(
    f"### 🧩 Contexto: Escenario {escenario_sel}% – Cisterna {cisterna_sel} – Nivel: {nivel_texto}"
)
    mostrar_kpis(f"🏙️ Distrito {dist_sel}", demanda, restante, viajes, costo, consumo, resultados)

    st.markdown("### 📘 Resultados por pozo")
    st.caption("Pozos industriales asignados al distrito, con aporte, viajes, consumo y costo.")
    df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
    df_res = rename_columns(df_res)
    styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
    "Aporte (m³/día)": "{:,.2f}",
    "Costo (Soles)": "{:,.2f}",
    "Consumo (galones)": "{:,.1f}",
    "Distancia (km)": "{:,.2f}"
})
    st.dataframe(styled_df, use_container_width=True)

    st.markdown("### 📊 Distribución del aporte por pozo")
    st.caption("Aporte diario de cada pozo industrial al distrito seleccionado.")
    st.plotly_chart(
        plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                 title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
        use_container_width=True
    )

    st.markdown("### 🗺️ Ubicación espacial")
    show_heat = st.checkbox("Mostrar mapa de calor por costo (S/)", value=False, key="heat_dist")
    m = folium.Map(location=[row.geometry.centroid.y, row.geometry.centroid.x], zoom_start=11, tiles="cartodbpositron")
    folium.GeoJson(row.geometry, style_function=lambda x: {"color":"green","fillOpacity":0.2}).add_to(m)
    m = dibujar_pozos(resultados, m)
    if show_heat and len(resultados) > 0:
        heat_data = [[r[6].y, r[6].x, r[3]] for r in resultados if r[6] is not None]
        plugins.HeatMap(heat_data, radius=18).add_to(m)
    m = agregar_leyenda(m)
    st_folium(m, width=900, height=500)

    agregar_conclusion("distrito", dist_sel, demanda, restante, viajes, costo, consumo, resultados)

    # =====================================================
    # 🔍 ANÁLISIS COMPARATIVO POST-CONCLUSIÓN
    # =====================================================
    st.markdown("## 📈 Análisis comparativo de eficiencia hídrico-económica")
    st.caption("Evaluación del desempeño del modelo frente a distintos escenarios de redistribución y tipos de cisterna.")

    # --- Comparativa entre escenarios y tipos de cisterna ---
    escenarios = [10, 20, 30]
    tipos_cisterna = ["19 m³", "34 m³"]
    comparacion_total = []

    for tipo in tipos_cisterna:
        for esc in escenarios:
            _, restante_esc, _, costo_esc, _ = asignar_pozos(row.geometry.centroid, demanda, esc, tipo, pozos_gdf)
            eficiencia_esc = ((demanda - restante_esc) / costo_esc) if costo_esc > 0 else 0
            comparacion_total.append({
                "Escenario (%)": esc,
                "Cisterna": tipo,
                "Eficiencia (m³/S/)": eficiencia_esc
            })

    df_comp = pd.DataFrame(comparacion_total)

    # --- Gráfico 1: eficiencia por escenario y tipo de cisterna ---
    df_comp["Eficiencia_label"] = df_comp["Eficiencia (m³/S/)"].apply(lambda x: f"{x:.3f}")

    fig_eff = px.line(
        df_comp,
        x="Escenario (%)",
        y="Eficiencia (m³/S/)",
        color="Cisterna",
        markers=True,
        text="Eficiencia_label",
        title="Comparación de eficiencia hídrico-económica por escenario y tipo de cisterna",
        color_discrete_map={"19 m³": "#0077b6", "34 m³": "#009e73"}
    )

    fig_eff.update_traces(textposition="top center", textfont_size=12)
    fig_eff.update_layout(
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        title=dict(font=dict(size=16, color="#003366")),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis_title="Eficiencia (m³ por S/)",
        xaxis_title="Escenario de redistribución (%)",
        legend_title="Tipo de cisterna"
    )
    st.plotly_chart(fig_eff, use_container_width=True)

    # --- Gráfico 2: eficiencia promedio por tipo de cisterna ---
    df_prom = df_comp.groupby("Cisterna")["Eficiencia (m³/S/)"].mean().reset_index()

    fig_bar = px.bar(
        df_prom,
        x="Cisterna",
        y="Eficiencia (m³/S/)",
        color="Cisterna",
        color_discrete_sequence=["#0077b6", "#009e73"],
        text_auto=".3f",
        title="Eficiencia promedio por tipo de cisterna (promedio de los tres escenarios)"
    )

    fig_bar.update_layout(
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        title=dict(font=dict(size=16, color="#003366")),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis_title="Eficiencia (m³ por S/)"
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Resumen interpretativo automático ---
    cisterna_ganadora = df_prom.loc[df_prom["Eficiencia (m³/S/)"].idxmax(), "Cisterna"]
    eff_max = df_prom["Eficiencia (m³/S/)"].max()

    st.markdown(f"""
    <div style='background-color:#f0f9ff; border-left:6px solid #0066cc;
                padding:12px 20px; margin-top:15px; border-radius:6px;
                font-size:16px; color:#222; font-family:"Segoe UI", sans-serif;'>
        <b>📊 Síntesis comparativa:</b><br>
        En este escenario, la <b>cisterna de {cisterna_ganadora}</b> mostró el mejor desempeño,
        con una eficiencia promedio de <b>{eff_max:.3f} m³/S/</b> considerando los tres niveles de redistribución (10 %, 20 % y 30 %).<br>
        Esto indica que, bajo condiciones similares, el uso de dicha flota optimiza la relación entre
        <b>volumen redistribuido y costo operativo</b>, reforzando la capacidad técnica del modelo en este contexto.
    </div>
    """, unsafe_allow_html=True)

# ========= COMBINACIÓN DE DISTRITOS =========
elif modo == "Combinación Distritos":
    criticos = ["ATE","LURIGANCHO","SAN_JUAN_DE_LURIGANCHO","EL_AGUSTINO","SANTA_ANITA"]
    seleccion = st.sidebar.multiselect("Seleccionar combinación de distritos", criticos, default=criticos)
    if seleccion:
        rows = distritos_gdf[distritos_gdf["NOMBDIST"].isin(seleccion)]
        demanda = rows["Demanda_Distrito_m3_30_lhd"].sum()
        geom_union = unary_union(rows.geometry)
        resultados, restante, viajes, costo, consumo = asignar_pozos(geom_union.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)

        # --- Contexto descriptivo adaptado ---
if modo == "Sector":
    nivel_texto = "Por sector"
elif modo == "Distrito":
    nivel_texto = "Por distrito"
elif modo == "Combinación Distritos":
    nivel_texto = "Por combinación de distritos"
else:
    nivel_texto = "Resumen general"

st.markdown(
    f"### 🧩 Contexto: Escenario {escenario_sel}% – Cisterna {cisterna_sel} – Nivel: {nivel_texto}"
)
        mostrar_kpis(f"🌀 Combinación: {', '.join(seleccion)}", demanda, restante, viajes, costo, consumo, resultados)

        st.markdown("### 📘 Resultados por pozo")
        st.caption("Pozos industriales utilizados para la combinación crítica de distritos.")
        df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
        df_res = rename_columns(df_res)
        styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
    "Aporte (m³/día)": "{:,.2f}",
    "Costo (Soles)": "{:,.2f}",
    "Consumo (galones)": "{:,.1f}",
    "Distancia (km)": "{:,.2f}"
})
        st.dataframe(styled_df, use_container_width=True)

        st.markdown("### 📊 Distribución del aporte por pozo")
        st.caption("Aporte total por pozo a la combinación crítica.")
        st.plotly_chart(
            plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                     title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
            use_container_width=True
        )

        st.markdown("### 🗺️ Distribución espacial")
        show_heat = st.checkbox("Mostrar mapa de calor por costo (S/)", value=False, key="heat_comb")
        m = folium.Map(location=[geom_union.centroid.y, geom_union.centroid.x], zoom_start=10, tiles="cartodbpositron")
        folium.GeoJson(geom_union, style_function=lambda x: {"color":"purple","fillOpacity":0.2}).add_to(m)
        m = dibujar_pozos(resultados, m)
        if show_heat and len(resultados) > 0:
            heat_data = [[r[6].y, r[6].x, r[3]] for r in resultados if r[6] is not None]
            plugins.HeatMap(heat_data, radius=18).add_to(m)
        m = agregar_leyenda(m)
        st_folium(m, width=900, height=500)

        agregar_conclusion("combinación crítica de distritos", ", ".join(seleccion), demanda, restante, viajes, costo, consumo, resultados)

# ========= RESUMEN GENERAL (TABS + TOP5) =========
elif modo == "Resumen general":
    st.subheader("📊 Resumen general")
    tabs = st.tabs(["📍 Sectores", "🏙️ Distritos", "🌀 Combinación crítica", "🏆 Top 5"])

    # ============== SECTORES ==============
    with tabs[0]:
        resumen_sectores = []
        for _, r in sectores_gdf.iterrows():
            dem = float(r.get("Demanda_m3_dia",0))
            if dem > 0:
                _, rest, via, cos, con = asignar_pozos(r.geometry.centroid, dem, escenario_sel, cisterna_sel, pozos_gdf)
                cobertura = (1-rest/dem)*100 if dem>0 else 0
                resumen_sectores.append([r["ZONENAME"], dem, via, cos, con, rest, cobertura])
        df_sec = pd.DataFrame(resumen_sectores, columns=["Sector","Demanda","Viajes","Costo","Consumo","Faltante","Cobertura_%"])
        df_sec = rename_columns(df_sec)

        st.markdown("### 📍 Sectores")
        st.caption("Resumen por sector del costo y cobertura en el escenario seleccionado.")
        st.dataframe(df_sec.style.background_gradient(subset=["Costo (Soles)"], cmap="Purples").format({
            "Demanda (m³/día)":"{:,.2f}", "Costo (Soles)":"{:,.2f}", "Consumo (galones)":"{:,.1f}", "Faltante (m³/día)":"{:,.2f}"
        }), use_container_width=True)
        st.plotly_chart(
            plot_bar(df_sec, x="Sector", y="Costo (Soles)",
                     title="Costo por sector", xlabel="Sector", ylabel="Costo (S/)"),
            use_container_width=True
        )
        st.caption(f"➡️ Costo promedio por sector: S/ {df_sec['Costo (Soles)'].mean():,.2f}")

    # ============== DISTRITOS ==============
    with tabs[1]:
        resumen_distritos = []
        for _, r in distritos_gdf.iterrows():
            dem = float(r.get("Demanda_Distrito_m3_30_lhd",0))
            if dem > 0:
                _, rest, via, cos, con = asignar_pozos(r.geometry.centroid, dem, escenario_sel, cisterna_sel, pozos_gdf)
                cobertura = (1-rest/dem)*100 if dem>0 else 0
                resumen_distritos.append([r["NOMBDIST"], dem, via, cos, con, rest, cobertura])
        df_dis = pd.DataFrame(resumen_distritos, columns=["Distrito","Demanda","Viajes","Costo","Consumo","Faltante","Cobertura_%"])
        df_dis = rename_columns(df_dis)

        st.markdown("### 🏙️ Distritos")
        st.caption("Resumen por distrito del costo y cobertura en el escenario seleccionado.")
        st.dataframe(df_dis.style.background_gradient(subset=["Costo (Soles)"], cmap="Purples").format({
            "Demanda (m³/día)":"{:,.2f}", "Costo (Soles)":"{:,.2f}", "Consumo (galones)":"{:,.1f}", "Faltante (m³/día)":"{:,.2f}"
        }), use_container_width=True)
        st.plotly_chart(
            plot_bar(df_dis, x="Distrito", y="Costo (Soles)",
                     title="Costo por distrito", xlabel="Distrito", ylabel="Costo (S/)"),
            use_container_width=True
        )
        st.caption(f"➡️ Cobertura promedio general: {df_dis['Cobertura (%)'].mean():.1f}%")

    # ============== COMBINACIÓN CRÍTICA ==============
    with tabs[2]:
        criticos = ["ATE","LURIGANCHO","SAN_JUAN_DE_LURIGANCHO","EL_AGUSTINO","SANTA_ANITA"]
        filas = distritos_gdf[distritos_gdf["NOMBDIST"].isin(criticos)]
        demanda = filas["Demanda_Distrito_m3_30_lhd"].sum()
        _, restante, viajes, costo, consumo = asignar_pozos(unary_union(filas.geometry).centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)
        st.markdown("### 🌀 Combinación crítica de distritos")
        df_comb = pd.DataFrame({
            "Distrito": criticos,
            "Demanda (m³/día)": [
                filas.loc[filas["NOMBDIST"]==d,"Demanda_Distrito_m3_30_lhd"].values[0]
                for d in criticos if d in filas["NOMBDIST"].values
            ]
        })
        st.dataframe(df_comb.style.background_gradient(subset=["Demanda (m³/día)"], cmap="YlGnBu"),
                     use_container_width=True)
        st.plotly_chart(
            plot_bar(df_comb, x="Distrito", y="Demanda (m³/día)",
                     title="Demanda total en distritos críticos",
                     xlabel="Distrito", ylabel="Demanda (m³/día)"),
            use_container_width=True
        )
        agregar_conclusion("combinación crítica de distritos", ", ".join(criticos), demanda, restante, viajes, costo, consumo, [])

    # ============== TOP 5 ==============
    with tabs[3]:
        st.markdown("### 🏆 Rankings operativos (costos)")
        colA, colB = st.columns(2)

        # Asegurar que df_sec y df_dis existan si el usuario no entró a las otras tabs antes
        if 'df_sec' not in locals():
            resumen_sectores = []
            for _, r in sectores_gdf.iterrows():
                dem = float(r.get("Demanda_m3_dia",0))
                if dem>0:
                    _, rest, via, cos, con = asignar_pozos(r.geometry.centroid, dem, escenario_sel, cisterna_sel, pozos_gdf)
                    cobertura = (1-rest/dem)*100 if dem>0 else 0
                    resumen_sectores.append([r["ZONENAME"], dem, via, cos, con, rest, cobertura])
            df_sec = rename_columns(pd.DataFrame(resumen_sectores, columns=["Sector","Demanda","Viajes","Costo","Consumo","Faltante","Cobertura_%"]))
        if 'df_dis' not in locals():
            resumen_distritos = []
            for _, r in distritos_gdf.iterrows():
                dem = float(r.get("Demanda_Distrito_m3_30_lhd",0))
                if dem>0:
                    _, rest, via, cos, con = asignar_pozos(r.geometry.centroid, dem, escenario_sel, cisterna_sel, pozos_gdf)
                    cobertura = (1-rest/dem)*100 if dem>0 else 0
                    resumen_distritos.append([r["NOMBDIST"], dem, via, cos, con, rest, cobertura])
            df_dis = rename_columns(pd.DataFrame(resumen_distritos, columns=["Distrito","Demanda","Viajes","Costo","Consumo","Faltante","Cobertura_%"]))

        # Top 5 Sectores (costosos y económicos)
        with colA:
            st.markdown("#### 💰 Sectores más costosos (Top 5)")
            top5_cost_sect = df_sec.nlargest(5, "Costo (Soles)")
            st.dataframe(top5_cost_sect.style.background_gradient(subset=["Costo (Soles)"], cmap="Reds").format({
                "Demanda (m³/día)":"{:,.2f}","Costo (Soles)":"{:,.2f}","Consumo (galones)":"{:,.1f}"
            }), use_container_width=True)
            st.plotly_chart(
                px.bar(top5_cost_sect, x="Sector", y="Costo (Soles)", color="Costo (Soles)",
                       color_continuous_scale="Reds", text_auto=True,
                       title="Top 5 sectores con mayor costo").update_layout(
                           xaxis_title="Sector", yaxis_title="Costo (S/)", plot_bgcolor="white",
                           font=dict(family="Segoe UI", size=13, color="#222"),
                           title=dict(font=dict(size=16, color="#003366")),
                           xaxis=dict(showgrid=True, gridcolor="lightgray"),
                           yaxis=dict(showgrid=True, gridcolor="lightgray")
                       ),
                use_container_width=True
            )
            st.markdown("#### 💧 Sectores más económicos (Top 5)")
            top5_cheap_sect = df_sec.nsmallest(5, "Costo (Soles)")
            st.dataframe(top5_cheap_sect.style.background_gradient(subset=["Costo (Soles)"], cmap="Blues").format({
                "Demanda (m³/día)":"{:,.2f}","Costo (Soles)":"{:,.2f}","Consumo (galones)":"{:,.1f}"
            }), use_container_width=True)
            st.plotly_chart(
                px.bar(top5_cheap_sect, x="Sector", y="Costo (Soles)", color="Costo (Soles)",
                       color_continuous_scale="Blues", text_auto=True,
                       title="Top 5 sectores con menor costo").update_layout(
                           xaxis_title="Sector", yaxis_title="Costo (S/)", plot_bgcolor="white",
                           font=dict(family="Segoe UI", size=13, color="#222"),
                           title=dict(font=dict(size=16, color="#003366")),
                           xaxis=dict(showgrid=True, gridcolor="lightgray"),
                           yaxis=dict(showgrid=True, gridcolor="lightgray")
                       ),
                use_container_width=True
            )

        # Top 5 Distritos (costosos y económicos)
        with colB:
            st.markdown("#### 🏙️ Distritos más costosos (Top 5)")
            top5_cost_dis = df_dis.nlargest(5, "Costo (Soles)")
            st.dataframe(top5_cost_dis.style.background_gradient(subset=["Costo (Soles)"], cmap="Reds").format({
                "Demanda (m³/día)":"{:,.2f}","Costo (Soles)":"{:,.2f}","Consumo (galones)":"{:,.1f}"
            }), use_container_width=True)
            st.plotly_chart(
                px.bar(top5_cost_dis, x="Distrito", y="Costo (Soles)", color="Costo (Soles)",
                       color_continuous_scale="Reds", text_auto=True,
                       title="Top 5 distritos con mayor costo").update_layout(
                           xaxis_title="Distrito", yaxis_title="Costo (S/)", plot_bgcolor="white",
                           font=dict(family="Segoe UI", size=13, color="#222"),
                           title=dict(font=dict(size=16, color="#003366")),
                           xaxis=dict(showgrid=True, gridcolor="lightgray"),
                           yaxis=dict(showgrid=True, gridcolor="lightgray")
                       ),
                use_container_width=True
            )
            st.markdown("#### 🌿 Distritos más económicos (Top 5)")
            top5_cheap_dis = df_dis.nsmallest(5, "Costo (Soles)")
            st.dataframe(top5_cheap_dis.style.background_gradient(subset=["Costo (Soles)"], cmap="Blues").format({
                "Demanda (m³/día)":"{:,.2f}","Costo (Soles)":"{:,.2f}","Consumo (galones)":"{:,.1f}"
            }), use_container_width=True)
            st.plotly_chart(
                px.bar(top5_cheap_dis, x="Distrito", y="Costo (Soles)", color="Costo (Soles)",
                       color_continuous_scale="Blues", text_auto=True,
                       title="Top 5 distritos con menor costo").update_layout(
                           xaxis_title="Distrito", yaxis_title="Costo (S/)", plot_bgcolor="white",
                           font=dict(family="Segoe UI", size=13, color="#222"),
                           title=dict(font=dict(size=16, color="#003366")),
                           xaxis=dict(showgrid=True, gridcolor="lightgray"),
                           yaxis=dict(showgrid=True, gridcolor="lightgray")
                       ),
                use_container_width=True
            )
