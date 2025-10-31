# ------------------------------------------------------------
# EQS - Painel Unificado: Clusters Regionais – Rede de Transição
# ------------------------------------------------------------
# Requisitos:
#   pip install dash==2.* dash-bootstrap-components plotly pandas
#
# Estrutura de pastas:
#   /EQS_Painel/
#     app.py
#     /data/Clusters_EQS_V2.xlsx
#     /assets/custom.css          (opcional, abaixo)
#     /assets/logo_medical_san.png (opcional)
#
# Observação:
# - O painel apenas LÊ os resultados consolidados do Clusters_EQS_V2.xlsx
# - Não recalcula distâncias nem polygons (convex hull).
# - Para posicionar a "estrela" do líder, usa o CENTROIDE dos equipamentos
#   daquele cluster (aproximação leve e estável).
# ------------------------------------------------------------

import pandas as pd
import numpy as np
from pathlib import Path
import os
import plotly.express as px
import plotly.graph_objects as go

from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

# --------------------------
# 1) Carregar dados prontos
# --------------------------
DATA_PATH = Path("data/Clusters_EQS_V2.xlsx")
RESUMO_SHEET = "Resumo_Clusters_V2"
ATAS_COORD_SHEET = "ATAs_Coordenadas"
EQUIP_SHEET = "Equipamentos_Clusterizados"

df_resumo = pd.read_excel(DATA_PATH, sheet_name=RESUMO_SHEET)
df_atas = pd.read_excel(DATA_PATH, sheet_name=ATAS_COORD_SHEET)
df_eqp = pd.read_excel(DATA_PATH, sheet_name=EQUIP_SHEET)

# Normalizações simples
for c in ["Latitude", "Longitude"]:
    if c in df_atas.columns:
        df_atas = df_atas.dropna(subset=[c])
    if c in df_eqp.columns:
        df_eqp = df_eqp.dropna(subset=[c])

leaders = sorted(df_resumo["ATA_Lider"].dropna().unique())

# Centróide (média) dos equipamentos por líder -> para posicionar a "estrela"
df_centroids = (
    df_eqp.groupby("ATA_Lider", as_index=False)[["Latitude", "Longitude"]]
    .mean()
    .rename(columns={"Latitude": "Lat_Centroide", "Longitude": "Lon_Centroide"})
)

# Palette discreta para clusters (tema claro)
palette = px.colors.qualitative.Plotly  # leve, bom contraste

# --------------------------
# 2) Construção das figuras
# --------------------------
def build_map(selected_leader: str | None) -> go.Figure:
    """
    Mapa claro com:
      - equipamentos coloridos por ATA_Lider
      - ATAs coordenadas (pontos cinza)
      - estrela no centróide do líder (se selecionado)
      - zoom: Brasil inteiro ou faixa do cluster
    """
    fig = go.Figure()

    # (A) ATAs coordenadas (pontos pequenos cinza)
    if not df_atas.empty:
        fig.add_trace(go.Scattergeo(
            lon=df_atas["Longitude"], lat=df_atas["Latitude"],
            mode="markers",
            marker=dict(size=5, color="rgba(120,120,120,0.5)"),
            name="ATAs Coordenadas (todas)"
        ))

    # (B) Equipamentos coloridos por líder
    # Para manter cores consistentes, mapeamos cada líder a uma cor da palette
    color_map = {l: palette[i % len(palette)] for i, l in enumerate(leaders)}
    for l in leaders:
        dfc = df_eqp[df_eqp["ATA_Lider"] == l]
        if dfc.empty:
            continue
        fig.add_trace(go.Scattergeo(
            lon=dfc["Longitude"], lat=dfc["Latitude"],
            text=dfc["Serial"],
            hovertemplate="<b>Serial:</b> %{text}<br>Modelo: %{customdata}<extra></extra>",
            customdata=dfc[["Modelo"]],
            mode="markers",
            marker=dict(size=6, color=color_map[l]),
            name=f"Equipamentos – {l}"
        ))

    # (C) Estrela do líder selecionado (centróide)
    lataxis_range = [-34, 6]
    lonaxis_range = [-75, -34]

    if selected_leader and selected_leader in leaders:
        row = df_centroids[df_centroids["ATA_Lider"] == selected_leader]
        if not row.empty:
            lat_c = float(row["Lat_Centroide"].values[0])
            lon_c = float(row["Lon_Centroide"].values[0])

            fig.add_trace(go.Scattergeo(
                lon=[lon_c], lat=[lat_c],
                mode="markers+text",
                text=[selected_leader],
                textposition="top center",
                marker=dict(size=12, symbol="star", line=dict(color="black", width=1),
                            color="gold"),
                name="ATA Líder (centroide)"
            ))

            # Ajusta zoom para o cluster selecionado (based on equipments of that leader)
            dfc = df_eqp[df_eqp["ATA_Lider"] == selected_leader]
            if not dfc.empty:
                lat_min, lat_max = dfc["Latitude"].min(), dfc["Latitude"].max()
                lon_min, lon_max = dfc["Longitude"].min(), dfc["Longitude"].max()
                lat_pad = max((lat_max - lat_min) * 0.20, 2)  # acolchoamento mínimo
                lon_pad = max((lon_max - lon_min) * 0.20, 2)
                lataxis_range = [lat_min - lat_pad, lat_max + lat_pad]
                lonaxis_range = [lon_min - lon_pad, lon_max + lon_pad]

    # Tema claro + estilo semelhante ao seu mapa anterior
    fig.update_layout(
        title=None,
        legend_title="Clusters (ATA Líder)",
        geo=dict(
            scope="south america",
            showland=True, landcolor="rgb(245,245,245)",
            showcountries=True, countrycolor="rgb(180,180,180)",
            coastlinecolor="rgb(160,160,160)",
            bgcolor="white",
            lataxis=dict(range=lataxis_range),
            lonaxis=dict(range=lonaxis_range)
        ),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=0, r=0, t=0, b=0)
    )
    return fig


def build_bars_pie(selected_leader: str | None) -> go.Figure:
    """
    Gera figura com barras (Top 5 modelos) + pizza (mix).
    Se nada selecionado, mostra um 'overview' com os Top5 globais.
    """
    if selected_leader and selected_leader in leaders:
        dfc = df_eqp[df_eqp["ATA_Lider"] == selected_leader]
        title = f"Cluster {selected_leader}: Top 5 Modelos e Mix"
    else:
        dfc = df_eqp.copy()
        title = "Brasil inteiro: Top 5 Modelos e Mix"

    cont = dfc["Modelo"].value_counts().sort_values(ascending=False)
    top5 = cont.head(5)

    # Pizza com até 8 fatias + 'Outros'
    parts = cont.copy()
    if len(parts) > 8:
        outros = parts[8:].sum()
        parts = parts.head(8)
        parts.loc["Outros"] = outros

    fig = go.Figure()

    # Barras (lado esquerdo)
    fig.add_trace(go.Bar(
        x=top5.index.astype(str),
        y=top5.values,
        name="Top 5 Modelos",
        marker_color="#004B8D"
    ))

    # Layout de duas áreas (barras e pizza)
    fig.update_layout(
        title=title,
        xaxis=dict(domain=[0.0, 0.48], title="Modelos (Top 5)"),
        yaxis=dict(domain=[0.0, 1.0], title="Qtd"),
        xaxis2=dict(domain=[0.52, 1.0]),
        yaxis2=dict(domain=[0.0, 1.0]),
        paper_bgcolor="white",
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=60, b=20)
    )

    # Pizza (lado direito)
    fig.add_trace(go.Pie(
        labels=parts.index.astype(str),
        values=parts.values,
        name="Mix de Modelos"
    ))
    # posiciona a pizza no domínio do segundo eixo
    fig.data[1].domain = {"x": [0.52, 1.0], "y": [0.0, 1.0]}
    return fig


# --------------------------
# 3) App Dash (layout + UX)
# --------------------------
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    title="Clusters Regionais – Rede de Transição EQS",
)

app.layout = dbc.Container(
    fluid=True,
    children=[

        # Barra superior com logo + título
        dbc.Row([
            dbc.Col(
                html.Img(src="/assets/logo_medical_san.png", height="46"),
                width="auto", className="d-flex align-items-center"
            ),
            dbc.Col(
                html.H3("Clusters Regionais – Rede de Transição EQS",
                        className="mb-0 text-brand"),
                className="d-flex align-items-center"
            )
        ], className="topbar py-2 px-3 mb-2"),

        # Controles
        dbc.Row([
            dbc.Col([
                html.Label("Selecione o cluster (ATA líder):", className="label"),
                dcc.Dropdown(
                    id="ddl-leader",
                    options=[{"label": "Brasil inteiro", "value": ""}]
                            + [{"label": l, "value": l} for l in leaders],
                    value="",  # Brasil inteiro
                    clearable=False
                )
            ], md=4)
        ], className="px-3 pb-2"),

        # Mapa
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="map-geo", config={"displayModeBar": True}, style={"height": "65vh"})
            ], md=12)
        ], className="px-3"),

        # Gráficos
        dbc.Row([
            dbc.Col([
                dcc.Graph(id="fig-bars-pie", config={"displayModeBar": True})
            ], md=12)
        ], className="px-3 pb-4")
    ]
)

# --------------------------
# 4) Callbacks
# --------------------------
@app.callback(
    Output("map-geo", "figure"),
    Output("fig-bars-pie", "figure"),
    Input("ddl-leader", "value")
)
def update_dashboard(selected_leader):
    leader = selected_leader if selected_leader else None
    return build_map(leader), build_bars_pie(leader)

port = int(os.environ.get("PORT", 8050)) 
if __name__ == "__main__":
    app.run_server(debug=False, host='0.0.0.0', port=port)



