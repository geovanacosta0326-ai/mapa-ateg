import pandas as pd
import folium
import folium.plugins
import hashlib
import requests
from folium import DivIcon
from sqlalchemy import create_engine, text
import warnings

warnings.filterwarnings("ignore")

# =========================================================
# 1. CONEXÃO COM O BANCO
# =========================================================
engine_pg = create_engine(
    "postgresql+psycopg2://postgres:faecsenar2022@localhost:5432/api_sisateg"
)

# =========================================================
# 2. QUERY
# =========================================================
query_sql = """
SELECT 
    supervisor_atual, 
    tecnico, 
    atividade,
    municipios,
    regiao_faec,
    tempo_projeto_meses, 
    codigos_ibge,
    data_ultima_visita
FROM public.vw_tecnicos_atuantes_vs_vinculos
WHERE 
    TO_DATE(data_ultima_visita, 'DD/MM/YYYY') >= (
        CURRENT_DATE - INTERVAL '2 months'
    ) and tempo_projeto_meses <= 24 and total_propriedades_ativas >0 
ORDER BY 
    supervisor_atual ASC, 
    tecnico ASC
"""

CORES_HEX = ["#E63946", "#457B9D", "#2D6A4F", "#7B2D8B", "#E76F51", "#8B0000", "#2A9D8F", "#1D3557"]

# =========================================================
# 3. FUNÇÕES AUXILIARES
# =========================================================

def criar_marcador_div(nome_tecnico, cor_hex, tempo_meses):
    """Cria o círculo colorido com a inicial do técnico."""
    tamanho = min(28 + int(float(tempo_meses) / 3), 44)
    inicial = nome_tecnico.strip()[0].upper() if nome_tecnico else "?"
    font_size = max(tamanho // 3, 9)
    html = f"""
    <div style="width:{tamanho}px; height:{tamanho}px; border-radius:50%; background:{cor_hex};
        border:2px solid white; box-shadow:0 1px 5px rgba(0,0,0,0.45); display:flex; 
        align-items:center; justify-content:center; font-family:Arial; font-size:{font_size}px;
        font-weight:bold; color:white; cursor:pointer;">{inicial}</div>
    """
    return DivIcon(html=html, icon_size=(tamanho, tamanho), icon_anchor=(tamanho // 2, tamanho // 2))

def formatar_subtotais(df_base, col_agrupadora, valor_agrupador):
    """Gera a linha de texto com subtotais por atividade para o menu lateral."""
    sub = df_base[df_base[col_agrupadora] == valor_agrupador].drop_duplicates(subset=['tecnico', 'atividade'])
    contagem = sub.groupby('atividade')['tecnico'].nunique().to_dict()
    partes = [f"{k.upper()}: {v}" for k, v in contagem.items()]
    texto = " | ".join(partes)
    return f"<br><span style='font-size:10px; color:#777; font-weight:normal;'>({texto})</span>"

# =========================================================
# 4. FUNÇÃO PRINCIPAL
# =========================================================
def gerar_mapa_ateg_consolidado():
    try:
        print("⏳ Iniciando processamento...")
        with engine_pg.connect() as conn:
            df = pd.read_sql(text(query_sql), conn)

        if df.empty:
            print("⚠️ Sem dados para o período.")
            return

        # Explodir municípios por código IBGE
        df = df.assign(cod_ibge=df['codigos_ibge'].str.split(', ')).explode('cod_ibge')
        df['cod_ibge'] = df['cod_ibge'].astype(str).str.strip()
        
        # Carregar coordenadas
        df_coords = pd.read_csv("https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv")
        df_coords['codigo_ibge'] = df_coords['codigo_ibge'].astype(str)
        df_final = df.merge(df_coords, left_on='cod_ibge', right_on='codigo_ibge', how='inner')

        # Totais para os labels
        contagem_sup = df_final.groupby('supervisor_atual')['tecnico'].nunique().to_dict()
        contagem_reg = df_final.groupby('regiao_faec')['tecnico'].nunique().to_dict()
        contagem_atv = df_final.groupby('atividade')['tecnico'].nunique().to_dict()

        # Criar Mapa
        m = folium.Map(location=[-5.2, -39.5], zoom_start=7, tiles='cartodbpositron')
        
        # GeoJSON Ceará
        geojson_ce = requests.get("https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-23-mun.json").json()
        folium.GeoJson(geojson_ce, name="Divisórias municipais", 
                       style_function=lambda _: {"color": "#888888", "weight": 0.6, "fillOpacity": 0.04}).add_to(m)

        # Paleta de Cores
        supervisores = sorted(df_final['supervisor_atual'].dropna().unique())
        cor_hex_map = {sup: CORES_HEX[i % len(CORES_HEX)] for i, sup in enumerate(supervisores)}

        # Dicionários de Grupos
        grupos_dict = {"S": {}, "R": {}, "A": {}}

        for _, row in df_final.iterrows():
            cor_hex = cor_hex_map.get(row['supervisor_atual'], '#457B9D')
            
            # Cálculo de jitter para evitar sobreposição exata
            seed = int(hashlib.md5(row['tecnico'].encode()).hexdigest(), 16)
            lat_f = row['latitude'] + (((seed % 100) - 50) / 2000.0)
            lon_f = row['longitude'] + ((((seed // 100) % 100) - 50) / 2000.0)

            # --- POPUP FORMATADO (ESTILO IMAGEM) ---
            html_popup = f"""
            <div style="font-family: 'Segoe UI', Tahoma, sans-serif; width: 280px; padding: 10px; background: white; border-radius: 12px;">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                    <div style="width: 45px; height: 45px; border-radius: 50%; background: {cor_hex}; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 18px;">
                        {row['tecnico'].strip()[0].upper()}
                    </div>
                    <div>
                        <div style="font-size: 15px; font-weight: 800; color: #333; line-height: 1.1;">{row['tecnico'].upper()}</div>
                        <div style="font-size: 12px; color: #777;">Técnico(a)</div>
                    </div>
                </div>
                <div style="height: 3px; background-color: {cor_hex}; opacity: 0.3; border-radius: 2px; margin-bottom: 10px;"></div>
                <div style="margin-bottom: 12px;">
                    <span style="background-color: {cor_hex}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 10px; font-weight: bold; text-transform: uppercase;">
                        {row['supervisor_atual']}
                    </span>
                </div>
                <table style="width: 100%; font-size: 13px; color: #444; border-collapse: collapse;">
                    <tr style="height: 26px;"><td>🌎 Região</td><td style="text-align: right; font-weight: 500;">{row['regiao_faec']}</td></tr>
                    <tr style="height: 26px;"><td>🏙️ Município</td><td style="text-align: right; font-weight: 500;">{row['nome']}</td></tr>
                    <tr style="height: 26px;"><td>🌱 Atividade</td><td style="text-align: right; font-weight: 500; text-transform: uppercase;">{row['atividade']}</td></tr>
                    <tr style="height: 26px;"><td>⏱️ Projeto</td><td style="text-align: right; font-weight: bold; color: #e67e22;">{int(row['tempo_projeto_meses'])} meses</td></tr>
                </table>
            </div>
            """

            # --- TOOLTIP (HOVER) ---
            texto_tooltip = f"<b>Técnico:</b> {row['tecnico']}<br><b>Município:</b> {row['nome']}<br><b>Supervisor:</b> {row['supervisor_atual']}"

            # --- LABELS DO MENU ---
            label_s = f"S: {row['supervisor_atual']} ({contagem_sup[row['supervisor_atual']]}){formatar_subtotais(df_final, 'supervisor_atual', row['supervisor_atual'])}"
            label_r = f"R: {row['regiao_faec']} ({contagem_reg[row['regiao_faec']]}){formatar_subtotais(df_final, 'regiao_faec', row['regiao_faec'])}"
            label_a = f"A: {row['atividade']} ({contagem_atv[row['atividade']]})"

            # Criar e adicionar marcadores aos 3 tipos de grupos
            for tipo, label, mostrar in [("S", label_s, True), ("R", label_r, False), ("A", label_a, False)]:
                if label not in grupos_dict[tipo]:
                    grupos_dict[tipo][label] = folium.FeatureGroup(name=label, show=mostrar).add_to(m)
                
                folium.Marker(
                    [lat_f, lon_f],
                    popup=folium.Popup(html_popup, max_width=320),
                    tooltip=folium.Tooltip(texto_tooltip),
                    icon=criar_marcador_div(row['tecnico'], cor_hex, row['tempo_projeto_meses'])
                ).add_to(grupos_dict[tipo][label])

        folium.LayerControl(collapsed=True).add_to(m)

        # Injeção de JS para o Menu Acordeão
        js_interface = """
        <style>
            .leaflet-control-layers-expanded { font-family: 'Segoe UI', Arial; padding: 10px !important; width: 360px !important; border-radius: 8px !important; }
            .btn-mapa { width: 48%; padding: 8px; cursor: pointer; font-size: 11px; font-weight: bold; border-radius: 4px; border: 1px solid #ccc; background: white; margin-bottom: 10px; }
            summary { background: #34495e; color: white; padding: 10px; cursor: pointer; font-weight: bold; font-size: 12px; border-radius: 4px; margin-top: 5px; list-style: none; }
            .lista-interna { padding: 4px; max-height: 400px; overflow-y: auto; background: #fff; }
            .leaflet-control-layers-list label { display: block; padding: 10px 4px; font-size: 11px; border-bottom: 1px solid #eee; font-weight: bold; line-height: 1.3; }
        </style>
        <script>
        document.addEventListener('DOMContentLoaded', function () {
            var observer = new MutationObserver(function () {
                var list = document.querySelector('.leaflet-control-layers-list');
                if (list && !list.querySelector('.btn-mapa')) {
                    var divBtns = document.createElement('div');
                    divBtns.style.display = 'flex'; divBtns.style.justifyContent = 'space-between';
                    divBtns.innerHTML = '<button class="btn-mapa" onclick="toggleMap(true)">✔ Marcar Tudo</button><button class="btn-mapa" onclick="toggleMap(false)">✖ Limpar</button>';
                    list.prepend(divBtns);
                    var labels = Array.from(list.querySelectorAll('label'));
                    var dSup = document.createElement('details'); dSup.open = true; dSup.innerHTML = "<summary>SUPERVISORES (POR ATIVIDADE)</summary><div class='lista-interna' id='sec-sup'></div>";
                    var dReg = document.createElement('details'); dReg.innerHTML = "<summary>REGIÕES (POR ATIVIDADE)</summary><div class='lista-interna' id='sec-reg'></div>";
                    var dAtv = document.createElement('details'); dAtv.innerHTML = "<summary>ATIVIDADES (TOTAIS)</summary><div class='lista-interna' id='sec-atv'></div>";
                    var dGeo = document.createElement('details'); dGeo.open = true; dGeo.innerHTML = "<summary>CAMADAS BASE</summary><div class='lista-interna' id='sec-geo'></div>";
                    labels.forEach(function (l) {
                        var txt = l.innerHTML;
                        if (txt.includes('S: ')) dSup.querySelector('#sec-sup').appendChild(l);
                        else if (txt.includes('R: ')) dReg.querySelector('#sec-reg').appendChild(l);
                        else if (txt.includes('A: ')) dAtv.querySelector('#sec-atv').appendChild(l);
                        else dGeo.querySelector('#sec-geo').appendChild(l);
                    });
                    list.appendChild(dGeo); list.appendChild(dSup); list.appendChild(dReg); list.appendChild(dAtv);
                }
            });
            observer.observe(document.querySelector('.leaflet-control-layers'), { attributes: true, subtree: true, childList: true });
        });
        function toggleMap(v) { document.querySelectorAll('.leaflet-control-layers-selector').forEach(x => { if(x.checked !== v) x.click(); }); }
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_interface))
        m.save("mapa_ateg_final.html")
        print("✅ Mapa gerado com sucesso!")

    except Exception as e:
        print(f"🔴 Erro fatal: {e}")

if __name__ == "__main__":
    gerar_mapa_ateg_consolidado()