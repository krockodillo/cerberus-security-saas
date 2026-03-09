import streamlit as st
import cv2
import numpy as np
from PIL import Image, ExifTags
import os
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import requests
import io
import time
import json
import whisper
import tempfile
from fpdf import FPDF
from datetime import datetime, timedelta
import random
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
import sqlite3
import pandas as pd
import urllib.parse
from google import genai

# ==================================================
# CONFIGURAÇÃO GERAL E CHAVES MESTRAS
# ==================================================
st.set_page_config(page_title="CERBERUS v4.9 - SaaS Intel", layout="wide", page_icon="🐕‍🦺")

# Sua Chave API do Google (Invisível para os clientes)
GEMINI_API_KEY = "AIzaSyBeFgncS12Y65hKCzPhlK9LVCxTzA89oZ0"

# Lista Mestra de Módulos Disponíveis
TODOS_MODULOS = [
    "1. Detecção de Armas",
    "2. Transcrição de Áudio",
    "3. Visão Forense",
    "4. Mapa de Vínculos",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "7. Checklist Tático",
    "8. Gerador de Persona (Cover)",
    "9. Gerador de Rosto (IA Avançada)"
]

# Definição do Plano SILVER (Fixo)
MODULOS_SILVER = [
    "1. Detecção de Armas",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "9. Gerador de Rosto (IA Avançada)"
]

st.markdown("""
    <style>
    .stApp {background-color: #0E1117;}
    .login-container { padding: 50px; background-color: #1f2937; border-radius: 10px; border: 1px solid #374151; text-align: center; }
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    .plan-gray { background-color: #475569; }
    .cyber-link { color: #38bdf8 !important; text-decoration: none; font-weight: bold; }
    .cyber-link:hover { color: #7dd3fc !important; text-decoration: underline; }
    .cyber-box { background-color: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #475569; color: #ffffff; margin-bottom: 15px; }
    .badge-warning { background-color: #f59e0b; color: #000; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    .badge-danger { background-color: #ef4444; color: #fff; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    </style>
""", unsafe_allow_html=True)

# ==================================================
# SISTEMA DE BANCO DE DADOS E PERMISSÕES
# ==================================================
def init_db():
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            password TEXT,
            role TEXT,
            plan TEXT,
            permissions TEXT,
            vencimento TEXT,
            status TEXT
        )
    ''')
    c.execute('SELECT * FROM usuarios WHERE username = "admin"')
    if not c.fetchone():
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)', 
                  ('admin', 'admin', 'admin', 'GOLD', 'ALL', '2099-12-31', 'ativo'))
        conn.commit()
    conn.close()

def login_user(username, password):
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, password))
    user = c.fetchone()
    conn.close()
    
    if user:
        vencimento = datetime.strptime(user[5], '%Y-%m-%d')
        if datetime.now() > vencimento:
            return None, "🚫 Acesso Expirado. Renove seu plano."
        return user, "OK"
    return None, "❌ Usuário ou senha inválidos."

def criar_usuario(username, password, role, plan, permissions_list, dias):
    try:
        conn = sqlite3.connect('cerberus_users.db')
        c = conn.cursor()
        validade = (datetime.now() + timedelta(days=int(dias))).strftime('%Y-%m-%d')
        perms_str = ",".join(permissions_list) if permissions_list else "NONE"
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)', 
                 (username, password, role, plan, perms_str, validade, 'ativo'))
        conn.commit()
        conn.close()
        return True, "Usuário criado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Erro: Usuário já existe."
    except Exception as e:
        return False, f"Erro: {e}"

def listar_usuarios():
    conn = sqlite3.connect('cerberus_users.db')
    df = pd.read_sql_query("SELECT username, role, plan, vencimento, status FROM usuarios", conn)
    conn.close()
    return df

def deletar_usuario(username):
    if username == "admin": return False
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE username=?", (username,))
    conn.commit()
    conn.close()
    return True

init_db()

# ==================================================
# MOTORES & FUNÇÕES DO SISTEMA (CORE)
# ==================================================
@st.cache_resource
def carregar_whisper(): return whisper.load_model("tiny")
try: whisper_model = carregar_whisper(); STATUS_AUDIO = True
except: STATUS_AUDIO = False

def get_decimal_from_dms(dms, ref):
    res = dms[0] + (dms[1]/60.0) + (dms[2]/3600.0)
    return -res if ref in ['S','W'] else res

def extrair_geolocalizacao(image):
    try:
        exif = image._getexif()
        if not exif: return None, "Sem EXIF"
        gps = {}
        for t,v in exif.items():
            if ExifTags.TAGS.get(t) == "GPSInfo": gps = v; break
        if not gps: return None, "Sem GPS"
        lat = get_decimal_from_dms(gps[2], gps[1])
        lon = get_decimal_from_dms(gps[4], gps[3])
        return (lat, lon), "Sucesso"
    except: return None, "Erro EXIF"

def gerar_mapa_vinculos():
    net=Network(height='600px',width='100%',bgcolor='#222222',font_color='white'); net.force_atlas_2based()
    net.add_node(1,label="ALVO",color='red'); net.add_edge(1,2); net.save_graph("mapa_operacional.html")

def gerar_pessoa_4devs():
    try: return requests.post("https://www.4devs.com.br/ferramentas_online.php", data={'acao':'gerar_pessoa','sexo':'I','txt_qtde':1}, headers={'Content-Type':'application/x-www-form-urlencoded'}).json()[0]
    except: return None

# ==================================================
# INTERFACE DE LOGIN & SESSÃO
# ==================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<br><h1 style='text-align:center'>🔒 CERBERUS SaaS</h1>", unsafe_allow_html=True)
        with st.form("login"):
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            btn = st.form_submit_button("ENTRAR", type="primary")
            if btn:
                u_data, msg = login_user(user, pwd)
                if u_data:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u_data[0]
                    st.session_state['role'] = u_data[2]
                    st.session_state['plan'] = u_data[3]
                    st.session_state['perms'] = u_data[4]
                    st.rerun()
                else:
                    st.error(msg)
else:
    # ==================================================
    # LOGADO: BARRA LATERAL INTELIGENTE
    # ==================================================
    user_role = st.session_state['role']
    user_plan = st.session_state['plan']
    user_perms = st.session_state['perms']
    
    st.sidebar.title("🐕‍🦺 CERBERUS")
    st.sidebar.caption(f"Usuário: {st.session_state['username']}")
    
    if user_plan == 'GOLD': st.sidebar.markdown("<span class='status-badge plan-gold'>PLANO GOLD</span>", unsafe_allow_html=True)
    elif user_plan == 'SILVER': st.sidebar.markdown("<span class='status-badge plan-silver'>PLANO SILVER</span>", unsafe_allow_html=True)
    else: st.sidebar.markdown("<span class='status-badge plan-gray'>PLANO GRAY</span>", unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("SAIR"):
        st.session_state['logged_in'] = False
        st.rerun()

    menu_options = []
    
    if user_role == 'admin':
        menu_options = ["🛠️ PAINEL ADMIN"] + TODOS_MODULOS
    else:
        if user_plan == 'GOLD':
            menu_options = TODOS_MODULOS
        elif user_plan == 'SILVER':
            menu_options = MODULOS_SILVER
        elif user_plan == 'GRAY':
            menu_options = user_perms.split(",")
    
    menu = st.sidebar.radio("Ferramentas:", menu_options)

    # ==================================================
    # 🛠️ ÁREA DO ADMINISTRADOR
    # ==================================================
    if menu == "🛠️ PAINEL ADMIN":
        st.title("🛠️ Gestão de Assinaturas")
        tab1, tab2 = st.tabs(["➕ Novo Cliente", "📋 Base de Usuários"])
        
        with tab1:
            st.subheader("Configurar Novo Acesso")
            with st.form("create_user"):
                c1, c2 = st.columns(2)
                new_user = c1.text_input("Login")
                new_pass = c2.text_input("Senha")
                c3, c4 = st.columns(2)
                new_role = c3.selectbox("Hierarquia", ["operacional", "gerente", "admin"])
                new_plan = c4.selectbox("Plano de Assinatura", ["GOLD", "SILVER", "GRAY"])
                
                permissoes_gray = []
                if new_plan == "GRAY":
                    st.markdown("##### ⚙️ Personalizar Plano Gray")
                    st.info("Selecione quais ferramentas este cliente poderá acessar:")
                    permissoes_gray = st.multiselect("Módulos Liberados", TODOS_MODULOS)
                dias = st.number_input("Dias de Acesso", value=30, min_value=1)
                btn_cri = st.form_submit_button("CRIAR ACESSO")
                
                if btn_cri:
                    perms_final = []
                    if new_plan == "GOLD": perms_final = ["ALL"]
                    elif new_plan == "SILVER": perms_final = MODULOS_SILVER
                    else: perms_final = permissoes_gray
                    if new_user and new_pass:
                        ok, txt = criar_usuario(new_user, new_pass, new_role, new_plan, perms_final, dias)
                        if ok: st.success(txt)
                        else: st.error(txt)
                    else:
                        st.warning("Preencha Login e Senha.")
        with tab2:
            st.dataframe(listar_usuarios(), use_container_width=True)
            u_del = st.selectbox("Deletar Usuário", listar_usuarios()['username'].unique())
            if st.button("EXCLUIR"):
                deletar_usuario(u_del)
                st.rerun()

    # ==================================================
    # 🔌 MÓDULOS DO SISTEMA
    # ==================================================
    elif menu == "1. Detecção de Armas":
        st.header("🔫 Análise Tática e Identificação de Armamento")
        st.markdown("Utiliza IA Multimodal para identificar suspeitos e catalogar o tipo de armamento visível.")
        u = st.file_uploader("Carregar Evidência (Imagem)", type=['jpg','png', 'jpeg'])
        if u:
            image = Image.open(u)
            st.image(image, caption="Evidência Original", use_container_width=True)
            if st.button("INICIAR VARREDURA TÁTICA", type="primary"):
                with st.spinner("Analisando armamento e suspeitos..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        prompt = "Aja como um perito criminal... [Instrução Oculta]"
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image])
                        st.markdown("### 📋 Relatório de Inteligência Visual")
                        texto_formatado = response.text.replace('\n', '<br>')
                        st.markdown(f"<div class='cyber-box'>{texto_formatado}</div>", unsafe_allow_html=True)
                    except Exception as e:
                        st.error(f"Erro na análise: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática e Interceptação")
        tab_upload, tab_mic = st.tabs(["📁 Upload de Arquivo", "🎤 Gravar Áudio (Microfone)"])
        audio_data = None
        with tab_upload:
            a_up = st.file_uploader("Carregar Áudio", type=['mp3','wav', 'm4a', 'ogg'])
            if a_up: audio_data = a_up
        with tab_mic:
            a_mic = st.audio_input("Gravação Tática")
            if a_mic: audio_data = a_mic
            
        if audio_data and STATUS_AUDIO:
            st.audio(audio_data)
            if st.button("INICIAR TRANSCRIÇÃO", type="primary"):
                with st.spinner("Decodificando áudio..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                            t.write(audio_data.getvalue()); p = t.name
                        r = whisper_model.transcribe(p); os.remove(p)
                        texto_completo = "".join([s['text'] + "\n" for s in r['segments']])
                        st.markdown(f"<div class='cyber-box'>{texto_completo.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                    except Exception as e: st.error(f"Erro: {e}")

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento Forense")
        u = st.file_uploader("Imagem", type=['jpg','png'])
        if u: 
            img = np.array(Image.open(u))
            clean = cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, 10, 10, 7, 21)
            st.image(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB))

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Vínculos")
        if st.button("Gerar"): gerar_mapa_vinculos()
        if os.path.exists("mapa_operacional.html"):
            with open("mapa_operacional.html", 'r', encoding='utf-8') as f:
                components.html(f.read(), height=600)

    # --- MÓDULO 5 REFORMULADO: DASHBOARD INVESTIGATIVO CPF ---
    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
        
        # Etiqueta de Aviso de Manutenção/Homologação
        st.markdown("""
        <div style='background-color: #451a03; border: 1px solid #b45309; padding: 10px; border-radius: 8px; margin-bottom: 20px;'>
            <span class='badge-warning'>⚠️ STATUS: EM HOMOLOGAÇÃO DE API</span>
            <span style='color: #fbbf24; margin-left: 10px; font-size: 14px;'>A integração com o Bureau de Dados oficial está em fase de ativação contratual. O painel abaixo opera em Modo Demonstração (MOCK) para exibição da interface gráfica.</span>
        </div>
        """, unsafe_allow_html=True)
        
        cpf_busca = st.text_input("CPF do Suspeito / Alvo", placeholder="Apenas números ou formato 000.000.000-00")
        
        if st.button("PUXAR DOSSIÊ COMPLETO", type="primary"):
            if len(cpf_busca) >= 11:
                with st.spinner("Estabelecendo conexão criptografada com servidores de dados..."):
                    time.sleep(2) # Simula o tempo de busca da API
                    
                    st.success("✅ Conexão simulada com sucesso. Dados estruturais carregados.")
                    
                    # Dashboard Metrics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Situação RFB", "REGULAR")
                    col2.metric("Score de Risco", "MÉDIO", "Nível 3", delta_color="off")
                    col3.metric("Óbitos SIRC", "NÃO CONSTA")
                    col4.metric("Mandados (BNMP)", "0 ATIVOS", "Limpo")
                    
                    st.markdown("---")
                    
                    # Painel de Dados Pessoais
                    st.markdown("### 👤 Qualificação Principal (Demonstração)")
                    st.markdown(f"""
                    <div class='cyber-box'>
                        <table style='width: 100%; text-align: left; border-collapse: collapse;'>
                            <tr><td style='padding: 5px; color:#94a3b8;'><b>Nome Completo:</b></td><td style='padding: 5px; font-weight:bold;'>JOHN DOE DA SILVA (DADO FICTÍCIO)</td></tr>
                            <tr><td style='padding: 5px; color:#94a3b8;'><b>CPF Vinculado:</b></td><td style='padding: 5px;'>{cpf_busca}</td></tr>
                            <tr><td style='padding: 5px; color:#94a3b8;'><b>Data de Nascimento:</b></td><td style='padding: 5px;'>01/01/1980 (Idade: 45 anos)</td></tr>
                            <tr><td style='padding: 5px; color:#94a3b8;'><b>Nome da Mãe:</b></td><td style='padding: 5px;'>MARIA DOE DA SILVA</td></tr>
                            <tr><td style='padding: 5px; color:#94a3b8;'><b>Sexo / Gênero:</b></td><td style='padding: 5px;'>Masculino</td></tr>
                        </table>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Abas de Investigação Profunda
                    t_end, t_tel, t_veic, t_soc = st.tabs(["📍 Endereços (3)", "📞 Telefones (2)", "🚗 Veículos (1)", "🏢 Quadro Societário"])
                    
                    with t_end:
                        st.markdown("#### Histórico de Endereços Vinculados")
                        st.info("RUA FICTÍCIA DOS TESTES, 123 - APTO 4B - BAIRRO CENTRO, SÃO PAULO/SP - CEP: 01000-000")
                        st.info("AVENIDA DEMONSTRAÇÃO, 999 - BAIRRO INDUSTRIAL, CAMPINAS/SP - CEP: 13000-000")
                        st.info("TRAVESSA DO SISTEMA, S/N - ZONA RURAL, ATIBAIA/SP - CEP: 12940-000")
                    
                    with t_tel:
                        st.markdown("#### Telefones e Linhas Móveis")
                        st.markdown("- 🟢 **(11) 99999-9999** (VIVO) - *Visto recentemente (Score Alto)*")
                        st.markdown("- 🟡 **(11) 3333-4444** (CLARO FIXO) - *Visto há 8 meses*")
                    
                    with t_veic:
                        st.markdown("#### Frota e Bens")
                        st.markdown("- 🚙 **FIAT TORO FREEDOM 2.0 (Prata)** - Placa: `ABC-1234` | Renavam: `00123456789`")
                        
                    with t_soc:
                        st.markdown("#### Participação em Empresas (CNPJ)")
                        st.markdown("- **CNPJ: 00.000.000/0001-00** - *EMPRESA DEMONSTRATIVA LTDA* (Sócio Administrador)")
                        
            else:
                st.warning("⚠️ O CPF precisa ter no mínimo 11 números.")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        tab_ia, tab_ip, tab_dorks, tab_gps = st.tabs(["🤖 IA Forense de Perfil", "📡 Rastreador de IP", "🔎 Matriz de Rastro (Web)", "📍 Extração de Metadados"])
        with tab_ia:
            u_print = st.file_uploader("Carregar Print", type=['jpg','png'])
            if u_print and st.button("ANALISAR PERFIL"):
                with st.spinner("Analisando..."):
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    r = client.models.generate_content(model='gemini-2.5-flash', contents=["Analise este perfil criminoso.", Image.open(u_print)])
                    st.markdown(f"<div class='cyber-box'>{r.text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        with tab_ip:
            ip_alvo = st.text_input("IP Alvo")
            if st.button("RASTREAR") and ip_alvo:
                res = requests.get(f"http://ip-api.com/json/{ip_alvo}?lang=pt-BR").json()
                if res.get('status') == 'success':
                    st.success(f"IP: {res['query']} | Cidade: {res['city']} | ISP: {res['isp']}")
        with tab_dorks:
            n = st.text_input("Nome/Vulgo")
            if st.button("GERAR MATRIZ"): st.markdown(f"[Buscar {n} no Google](https://www.google.com/search?q={n})")
        with tab_gps:
            u_gps = st.file_uploader("Carregar Imagem Original", key="g")
            if u_gps:
                g, m = extrair_geolocalizacao(Image.open(u_gps))
                if g: st.success(f"Lat: {g[0]}, Lon: {g[1]}")

    elif menu == "7. Checklist Tático":
        st.header("📋 Checklist de Plantão")
        st.selectbox("Ocorrência", ["Flagrante", "B.O."])

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Cover")
        if st.button("GERAR"): st.write(gerar_pessoa_4devs())

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover")
        with st.form("gerador_cover"):
            genero = st.selectbox("Gênero", ["Homem", "Mulher"])
            idade = st.slider("Idade", 18, 80, 35)
            etnia = st.selectbox("Etnia", ["Latino/Pardo", "Caucasiano/Branco", "Negro", "Asiático"])
            btn_gerar = st.form_submit_button("GERAR NANO BANANA 2", type="primary")
        if btn_gerar:
            with st.spinner("Sintetizando..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    result = client.models.generate_images(
                        model='gemini-3.1-flash-image-preview', 
                        prompt=f"Rosto fotorrealista de {genero}, {idade} anos, {etnia}.",
                        config=genai.types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="1:1")
                    )
                    st.image(Image.open(io.BytesIO(result.generated_images[0].image.image_bytes)))
                except Exception as e: st.error(f"Erro: {e}")