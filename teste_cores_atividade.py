import pandas as pd
import folium
import folium.plugins
import hashlib
from folium import DivIcon
from sqlalchemy import create_engine, text
import warnings

warnings.filterwarnings("ignore")

# =========================================================
# 1. CONEXÃO E CONFIGURAÇÕES
# =========================================================
engine_pg = create_engine("postgresql+psycopg2://postgres:faecsenar2022@localhost:5432/api_sisateg")

REGIOES_OFICIAIS = {
    "Região Centro Sul", "Região da Ibiapaba", "Região do Baixo Jaguaribe",
    "Região do Cariri", "Região do Litoral Leste", "Região do Litoral Oeste",
    "Região do Sertão Central", "Região dos Inhamuns/Crateús",
    "Região Maciço de Baturité", "Região Norte",
}

# Cores vibrantes para as atividades
CORES_HEX = [
    "#E63946", "#457B9D", "#2D6A4F", "#7B2D8B", "#E76F51", 
    "#8B0000", "#2A9D8F", "#1D3557", "#F4A261", "#606C38"
]

def criar_marcador_div(nome_tecnico, cor_hex, tempo_meses):
    tamanho = min(28 + int(float(tempo_meses or 0) / 3), 44)
    inicial = nome_tecnico.strip()[0].upper() if nome_tecnico else "?"
    font_size = max(tamanho // 3, 9)
    html = f"""<div style="width:{tamanho}px; height:{tamanho}px; border-radius:50%; background:{cor_hex}; border:2px solid white; box-shadow:0 1px 5px rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; font-family:Arial; font-size:{font_size}px; font-weight:bold; color:white; cursor:pointer;">{inicial}</div>"""
    return DivIcon(html=html, icon_size=(tamanho, tamanho), icon_anchor=(tamanho // 2, tamanho // 2))

def formatar_subtotais(df_base, col_agrupadora, valor_agrupador):
    sub = df_base[df_base[col_agrupadora] == valor_agrupador].drop_duplicates(subset=['tecnico', 'atividade'])
    contagem = sub.groupby('atividade')['tecnico'].nunique().to_dict()
    partes = [f"<span style='display:inline-block; background:#e8f0fe; color:#1a56db; border-radius:4px; padding:1px 5px; margin:1px; font-size:9px; font-weight:600;'>{k[:12].upper()}: {v}</span>" for k, v in sorted(contagem.items())]
    return f"<br>{' '.join(partes)}"

# =========================================================
# 2. GERAÇÃO DO MAPA
# =========================================================
def gerar_mapa_ateg_consolidado():
    try:
        query_sql = "SELECT * FROM public.vw_mapa_consolidado_ateg_georrefercnaiAS"
        with engine_pg.connect() as conn:
            df = pd.read_sql(text(query_sql), conn)

        if df.empty: return print("⚠️ Sem dados.")

        df = df.assign(cod_ibge=df['codigos_ibge'].str.split(', ')).explode('cod_ibge')
        df['cod_ibge'] = df['cod_ibge'].astype(str).str.strip()
        df_coords = pd.read_csv("https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/csv/municipios.csv")
        df_coords['codigo_ibge'] = df_coords['codigo_ibge'].astype(str)
        df_final = df.merge(df_coords, left_on='cod_ibge', right_on='codigo_ibge', how='inner')

        m = folium.Map(location=[-5.2, -39.5], zoom_start=7, tiles='cartodbpositron')

        # Divisórias Municipais
        geojson_url = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-23-mun.json"
        folium.GeoJson(geojson_url, name="Divisórias Municipais",
            style_function=lambda x: {'fillColor': 'transparent', 'color': '#555555', 'weight': 0.5, 'fillOpacity': 0}
        ).add_to(m)

        # --- NOVA LÓGICA DE CORES: MAPEANDO POR ATIVIDADE ---
        atividades = sorted(df_final['atividade'].dropna().unique())
        cor_atv_map = {atv: CORES_HEX[i % len(CORES_HEX)] for i, atv in enumerate(atividades)}
        
        contagem_sup = df_final.groupby('supervisor_atual')['tecnico'].nunique().to_dict()
        contagem_reg = df_final.groupby('regiao_faec')['tecnico'].nunique().to_dict()
        contagem_atv = df_final.groupby('atividade')['tecnico'].nunique().to_dict()

        grupos_dict = {"S": {}, "R": {}, "A": {}}

        for _, row in df_final.iterrows():
            # Define a cor com base na ATIVIDADE
            cor_hex = cor_atv_map.get(row['atividade'], '#457B9D')
            
            seed = int(hashlib.md5(row['tecnico'].encode()).hexdigest(), 16)
            lat_f = row['latitude'] + (((seed % 100) - 50) / 2000.0)
            lon_f = row['longitude'] + ((((seed // 100) % 100) - 50) / 2000.0)

            # Popup Estilizado
            html_popup = f"""
            <div style="font-family: 'Segoe UI', Arial; width: 260px; padding: 5px;">
                <div style="display: flex; align-items: center; margin-bottom: 12px;">
                    <div style="width: 45px; height: 45px; background: {cor_hex}; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px; margin-right: 12px; border: 2px solid #eee;">
                        {row['tecnico'][0].upper()}
                    </div>
                    <div>
                        <b style="font-size: 15px; color: #2c3e50; display: block; line-height: 1.2;">{row['tecnico'].upper()}</b>
                        <span style="font-size: 12px; color: #7f8c8d;">Técnico(a)</span>
                    </div>
                </div>
                <hr style="border: 0; border-top: 1px solid #eee; margin: 10px 0;">
                <div style="background: {cor_hex}; color: white; padding: 4px 12px; border-radius: 20px; display: inline-block; font-size: 11px; font-weight: 600; margin-bottom: 15px;">
                    {row['atividade'].upper()}
                </div>
                <div style="font-size: 13px; color: #34495e;">
                    <p style="margin: 5px 0; display: flex; justify-content: space-between;"><span>👤 <b>Supervisor</b></span> <span style="color: #555;">{row['supervisor_atual']}</span></p>
                    <p style="margin: 5px 0; display: flex; justify-content: space-between;"><span>🌍 <b>Região</b></span> <span style="color: #555;">{row['regiao_faec']}</span></p>
                    <p style="margin: 5px 0; display: flex; justify-content: space-between;"><span>🏘️ <b>Município</b></span> <span style="color: #555;">{row['nome']}</span></p>
                    <p style="margin: 10px 0 5px 0; display: flex; justify-content: space-between; align-items: center;">
                        <span>⏱️ <b>Projeto</b></span> 
                        <span style="color: #e67e22; font-weight: 800; font-size: 14px;">{int(row['tempo_projeto_meses'])} meses</span>
                    </p>
                </div>
            </div>
            """

            label_s = f"S: {row['supervisor_atual']} ({contagem_sup[row['supervisor_atual']]}){formatar_subtotais(df_final, 'supervisor_atual', row['supervisor_atual'])}"
            val_reg = str(row['regiao_faec']).strip()
            tipo_r = "R" if val_reg in REGIOES_OFICIAIS else "A"
            label_r = f"{tipo_r}: {val_reg} ({contagem_reg[val_reg]})" + (formatar_subtotais(df_final, 'regiao_faec', val_reg) if tipo_r == "R" else "")
            label_a = f"A: {row['atividade']} ({contagem_atv[row['atividade']]})"

            for tipo, label, mostrar in [("S", label_s, True), (tipo_r, label_r, False), ("A", label_a, False)]:
                if label not in grupos_dict[tipo]:
                    grupos_dict[tipo][label] = folium.FeatureGroup(name=label, show=mostrar).add_to(m)
                
                marker = folium.Marker(
                    [lat_f, lon_f], 
                    icon=criar_marcador_div(row['tecnico'], cor_hex, row['tempo_projeto_meses'])
                )
                folium.Popup(html_popup, max_width=300).add_to(marker)
                marker.add_to(grupos_dict[tipo][label])

        folium.LayerControl(collapsed=True).add_to(m)

        # Interface CSS permanece a mesma
        js_interface = """
        <style>
            .leaflet-popup-content-wrapper { border-radius: 12px; }
            .leaflet-control-layers-expanded { font-family: 'Segoe UI', Arial; width: 380px !important; border-radius: 8px; }
            @media (max-width: 600px) { .leaflet-control-layers-expanded { width: 90vw !important; } }
            .btn-mapa { width: 48%; padding: 8px; cursor: pointer; font-size: 11px; font-weight: bold; border-radius: 5px; border: none; background: #34495e; color: white; margin-bottom: 10px; }
            summary { background: #2c3e50; color: white; padding: 10px; cursor: pointer; font-weight: bold; font-size: 11px; border-radius: 5px; margin-top: 5px; }
            .lista-interna { padding: 5px; max-height: 400px; overflow-y: auto; background: #f8f9fa; }
            label { display: block; padding: 6px; border-bottom: 1px solid #eee; font-size: 11px; }
        </style>
        <script>
        function toggleMap(v) { document.querySelectorAll('.leaflet-control-layers-selector').forEach(cb => { if (cb.checked !== v) cb.click(); }); }
        document.addEventListener('DOMContentLoaded', function () {
            var observer = new MutationObserver(function () {
                var list = document.querySelector('.leaflet-control-layers-list');
                if (list && !list.querySelector('.btn-mapa')) {
                    var divBtns = document.createElement('div');
                    divBtns.style.display = 'flex'; divBtns.style.justifyContent = 'space-between';
                    divBtns.innerHTML = '<button class="btn-mapa" onclick="toggleMap(true)">✔ MARCAR TUDO</button>'
                                      + '<button class="btn-mapa" style="background:#e74c3c" onclick="toggleMap(false)">✖ LIMPAR MAPA</button>';
                    list.prepend(divBtns);
                    var labels = Array.from(list.querySelectorAll('label'));
                    var dSup = document.createElement('details'); dSup.open = true;
                    dSup.innerHTML = "<summary>👥 SUPERVISORES</summary><div class='lista-interna'></div>";
                    var dReg = document.createElement('details');
                    dReg.innerHTML = "<summary>🗺️ REGIÕES</summary><div class='lista-interna'></div>";
                    var dAtv = document.createElement('details');
                    dAtv.innerHTML = "<summary>🌱 ATIVIDADES</summary><div class='lista-interna'></div>";
                    var dGeo = document.createElement('details'); dGeo.open = true;
                    dGeo.innerHTML = "<summary>🗾 BASE</summary><div class='lista-interna'></div>";
                    labels.forEach(l => {
                        var txt = l.innerText.trim();
                        if (txt.startsWith('S:')) dSup.querySelector('.lista-interna').appendChild(l);
                        else if (txt.startsWith('R:')) dReg.querySelector('.lista-interna').appendChild(l);
                        else if (txt.startsWith('A:')) dAtv.querySelector('.lista-interna').appendChild(l);
                        else dGeo.querySelector('.lista-interna').appendChild(l);
                    });
                    list.appendChild(dGeo); list.appendChild(dSup); list.appendChild(dReg); list.appendChild(dAtv);
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        });
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_interface))
        m.save("index.html")
        print("✅ Mapa atualizado: Cores agora por Atividade!")

    except Exception as e: print(f"🔴 Erro: {e}")

if __name__ == "__main__": gerar_mapa_ateg_consolidado()