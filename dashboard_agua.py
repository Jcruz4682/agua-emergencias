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
sidebar_style = """
<style>
    [data-testid="stSidebar"] {
        background-color: #f7f7f7;
        border-right: 2px solid #d1d1d1;
        border-radius: 0px 10px 10px 0px;
        padding: 20px;
    }
    [data-testid="stSidebar"] h2, h3, h4, label {
        color: #333333;
        font-family: 'Segoe UI', sans-serif;
    }
</style>
"""
st.markdown(sidebar_style, unsafe_allow_html=True)

# ========= CONTROLES =========
st.sidebar.header("⚙️ Configuración del análisis")

# Nivel de análisis
modo = st.sidebar.radio(
    "Seleccionar nivel de análisis",
    ["Sector", "Distrito", "Combinación Distritos", "Resumen general"]
)

# Escenario (texto mejorado)
escenario_sel = st.sidebar.selectbox(
    "Seleccionar Escenario (% del caudal disponible por pozo)",
    [10, 20, 30]
)

# Tipo de cisterna
cisterna_sel = st.sidebar.radio("Seleccionar tipo de cisterna", list(cisternas.keys()))

# Valores fijos
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
        "Dist_km": "Distancia (km)"
    }
    return df.rename(columns={c: mapping.get(c,c) for c in df.columns})

def plot_bar(df, x, y, title, xlabel, ylabel):
    fig = px.bar(df, x=x, y=y, title=title, color=y,
                 color_continuous_scale=px.colors.sequential.Plasma, text_auto=True)
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color="#003366")),
        xaxis_title=xlabel,
        yaxis_title=ylabel,
        plot_bgcolor="white",
        font=dict(family="Segoe UI", size=13, color="#222"),
        xaxis=dict(showgrid=True, gridcolor="lightgray"),
        yaxis=dict(showgrid=True, gridcolor="lightgray"),
        coloraxis_colorbar=dict(title=y, tickformat=".0f")
    )
    return fig

def mostrar_kpis(nombre, demanda, restante, viajes, costo, consumo, resultados):
    st.markdown(f"<h3 style='color:#003366;'>{nombre}</h3>", unsafe_allow_html=True)
    fila1 = st.columns(3)
    fila2 = st.columns(3)
    cobertura = (1-restante/demanda)*100 if demanda > 0 else 0
    fila1[0].metric("🚰 Demanda (m³/día)", f"{demanda:,.1f}")
    fila1[1].metric("🎯 Cobertura (%)", f"{cobertura:.1f}%")
    fila1[2].metric("🏭 Pozos usados", f"{len(resultados)}")
    fila2[0].metric("🚛 Viajes", f"{viajes}")
    fila2[1].metric("💵 Costo (S/)", f"{costo:,.2f}")
    fila2[2].metric("⛽ Consumo (gal)", f"{consumo:,.1f}")
    st.caption("⚠️ Los costos corresponden únicamente al consumo de combustible.")

# --- CONCLUSIÓN OPERATIVA ---
def agregar_conclusion(contexto, nombre, demanda, restante, viajes, costo, consumo, pozos):
    cobertura = (1 - restante / demanda) * 100 if demanda > 0 else 0
    cobertura_texto = f"{cobertura:.1f}%"
    base_texto = (
        f"En escenario de <b>emergencia hídrica</b> en el <b>{contexto.lower()} {nombre}</b>, "
        f"la demanda diaria (<b>{demanda:.2f} m³</b>) "
    )
    if restante <= 0 or cobertura >= 99.9:
        texto = (
            base_texto +
            f"fue <b>totalmente satisfecha ({cobertura_texto})</b> con el aporte de "
            f"<b>{len(pozos)} pozos industriales</b>, requiriendo <b>{viajes} viajes</b> "
            f"con <b>cisternas de {cisterna_sel}</b>.<br>"
            f"El traslado implicó un <b>consumo de {consumo:.1f} gal</b> de combustible, "
            f"equivalente a <b>S/ {costo:,.2f}</b> en costos operativos."
        )
        color, borde, icono = "#e8f5e9", "#2e7d32", "✅"
    else:
        texto = (
            base_texto +
            f"<b>no fue satisfecha en su totalidad ({cobertura_texto})</b>, "
            f"a pesar del aporte de <b>{len(pozos)} pozos industriales</b>, que requirieron "
            f"<b>{viajes} viajes</b> con <b>cisternas de {cisterna_sel}</b>.<br>"
            f"El traslado implicó un <b>consumo de {consumo:.1f} gal</b> de combustible, "
            f"equivalente a <b>S/ {costo:,.2f}</b> en costos operativos."
        )
        color, borde, icono = "#fff3e0", "#ef6c00", "⚠️"
    st.markdown(f"""
    <div style='text-align:center; margin-top:25px;'>
        <h4 style='color:#003366; font-family:"Segoe UI", sans-serif;'>📋 Conclusión Operativa</h4>
    </div>
    <div style='background-color:{color};
                border-left:6px solid {borde};
                padding:15px 22px;
                margin-top:8px;
                border-radius:6px;
                color:#222;
                font-size:16px;
                line-height:1.6;
                font-family:"Segoe UI", sans-serif;'>
        <b>{icono} Conclusión:</b><br>
        {texto}
    </div>
    """, unsafe_allow_html=True)
def agregar_leyenda(m):
    legend_html = """
    <div style="position: fixed; bottom: 20px; left: 20px; width: 200px;
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
                location=[geom.y, geom.x],
                radius=6,
                color="blue",
                fill=True,
                fill_opacity=0.7,
                popup=(
                    f"Pozo {row['Pozo_ID']}<br>"
                    f"Aporte: {row['Aporte']:.2f} m³/día<br>"
                    f"Viajes: {row['Viajes']}<br>"
                    f"Costo: S/ {row['Costo']:.2f}<br>"
                    f"Consumo: {row['Consumo']:.1f} gal<br>"
                    f"Distancia: {row['Dist_km']} km"
                )
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

    mostrar_kpis(f"📍 Sector {sector_sel}", demanda, restante, viajes, costo, consumo, resultados)

    # --- Tabla ---
    st.markdown("### 📘 Resultados por pozo")
    st.caption("Pozos industriales asignados al sector, con su aporte, viajes, consumo y costo asociado.")
    df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
    df_res = rename_columns(df_res)
    styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
        "Costo (Soles)": "{:,.2f}", "Consumo (galones)": "{:,.1f}", "Distancia (km)": "{:,.2f}"
    })
    st.dataframe(styled_df, use_container_width=True)

    # --- Gráfico ---
    st.markdown("### 📊 Distribución del aporte por pozo")
    st.caption("Visualización del aporte diario de cada pozo industrial en el escenario seleccionado.")
    st.plotly_chart(plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                             title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
                    use_container_width=True)

    # --- Mapa ---
    st.markdown("### 🗺️ Ubicación espacial de pozos y sector")
    st.caption("Visualización geoespacial del sector analizado y los pozos industriales más cercanos.")
    m = folium.Map(location=[row.geometry.centroid.y, row.geometry.centroid.x], zoom_start=13, tiles="cartodbpositron")
    folium.GeoJson(row.geometry, style_function=lambda x: {"color":"red","fillOpacity":0.3}).add_to(m)
    m = dibujar_pozos(resultados, m)
    m = agregar_leyenda(m)
    st_folium(m, width=900, height=500)

    agregar_conclusion("sector", sector_sel, demanda, restante, viajes, costo, consumo, resultados)

# ========= DISTRITO =========
elif modo == "Distrito":
    dist_sel = st.sidebar.selectbox("Seleccionar distrito", sorted(distritos_gdf["NOMBDIST"].dropna().unique()))
    row = distritos_gdf[distritos_gdf["NOMBDIST"] == dist_sel].iloc[0]
    demanda = float(row.get("Demanda_Distrito_m3_30_lhd",0))
    resultados, restante, viajes, costo, consumo = asignar_pozos(row.geometry.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)

    mostrar_kpis(f"🏙️ Distrito {dist_sel}", demanda, restante, viajes, costo, consumo, resultados)

    st.markdown("### 📘 Resultados por pozo")
    st.caption("Pozos industriales asignados al distrito, con su aporte, viajes, consumo y costo asociado.")
    df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
    df_res = rename_columns(df_res)
    styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
        "Costo (Soles)": "{:,.2f}", "Consumo (galones)": "{:,.1f}", "Distancia (km)": "{:,.2f}"
    })
    st.dataframe(styled_df, use_container_width=True)

    st.markdown("### 📊 Distribución del aporte por pozo")
    st.caption("Visualización del aporte diario de cada pozo industrial al distrito seleccionado.")
    st.plotly_chart(plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                             title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
                    use_container_width=True)

    st.markdown("### 🗺️ Ubicación espacial de pozos y distrito")
    st.caption("Mapa del distrito y de los pozos industriales más cercanos.")
    m = folium.Map(location=[row.geometry.centroid.y, row.geometry.centroid.x], zoom_start=11, tiles="cartodbpositron")
    folium.GeoJson(row.geometry, style_function=lambda x: {"color":"green","fillOpacity":0.2}).add_to(m)
    m = dibujar_pozos(resultados, m)
    m = agregar_leyenda(m)
    st_folium(m, width=900, height=500)

    agregar_conclusion("distrito", dist_sel, demanda, restante, viajes, costo, consumo, resultados)

# ========= COMBINACIÓN DE DISTRITOS =========
elif modo == "Combinación Distritos":
    criticos = ["ATE","LURIGANCHO","SAN_JUAN_DE_LURIGANCHO","EL_AGUSTINO","SANTA_ANITA"]
    seleccion = st.sidebar.multiselect("Seleccionar combinación de distritos", criticos, default=criticos)
    if seleccion:
        rows = distritos_gdf[distritos_gdf["NOMBDIST"].isin(seleccion)]
        demanda = rows["Demanda_Distrito_m3_30_lhd"].sum()
        geom_union = unary_union(rows.geometry)
        resultados, restante, viajes, costo, consumo = asignar_pozos(geom_union.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)

        mostrar_kpis(f"🌀 Combinación: {', '.join(seleccion)}", demanda, restante, viajes, costo, consumo, resultados)

        st.markdown("### 📘 Resultados por pozo")
        st.caption("Pozos industriales utilizados para abastecer la combinación crítica de distritos seleccionada.")
        df_res = pd.DataFrame(resultados, columns=["Pozo_ID","Aporte","Viajes","Costo","Consumo","Dist_km","geom"]).drop(columns="geom")
        df_res = rename_columns(df_res)
        styled_df = df_res.style.background_gradient(subset=["Aporte (m³/día)"], cmap="YlGnBu").format({
            "Costo (Soles)": "{:,.2f}", "Consumo (galones)": "{:,.1f}", "Distancia (km)": "{:,.2f}"
        })
        st.dataframe(styled_df, use_container_width=True)

        st.markdown("### 📊 Distribución del aporte por pozo")
        st.caption("Aporte total por pozo industrial a la combinación crítica de distritos.")
        st.plotly_chart(plot_bar(df_res, x="N° Pozo", y="Aporte (m³/día)",
                                 title="Aporte por pozo industrial", xlabel="N° Pozo", ylabel="Aporte (m³/día)"),
                        use_container_width=True)

        st.markdown("### 🗺️ Distribución espacial de los pozos y distritos combinados")
        m = folium.Map(location=[geom_union.centroid.y, geom_union.centroid.x], zoom_start=10, tiles="cartodbpositron")
        folium.GeoJson(geom_union, style_function=lambda x: {"color":"purple","fillOpacity":0.2}).add_to(m)
        m = dibujar_pozos(resultados, m)
        m = agregar_leyenda(m)
        st_folium(m, width=900, height=500)

        agregar_conclusion("combinación crítica de distritos", ", ".join(seleccion), demanda, restante, viajes, costo, consumo, resultados)

# ========= RESUMEN GENERAL =========
elif modo == "Resumen general":
    st.subheader("📊 Resumen general")

    resumen_sectores = []
    for _, row in sectores_gdf.iterrows():
        demanda = float(row.get("Demanda_m3_dia",0))
        if demanda > 0:
            _, restante, viajes, costo, consumo = asignar_pozos(row.geometry.centroid, demanda, escenario_sel, cisterna_sel, pozos_gdf)
            cobertura = (1-restante/demanda)*100 if demanda>0 else 0
            resumen_sectores.append([row["ZONENAME"], demanda, viajes, costo, consumo, restante, cobertura])
    df_sec = pd.DataFrame(resumen_sectores, columns=["Sector","Demanda","Viajes","Costo","Consumo","Faltante","Cobertura_%"])
    df_sec = rename_columns(df_sec)
    st.markdown("### 📍 Sectores")
    st.dataframe(df_sec)
    st.plotly_chart(plot_bar(df_sec, x="Sector", y="Costo (Soles)",
                             title="Costo por sector", xlabel="Sector", ylabel="Costo (S/)"),
                    use_container_width=True)
