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
import re

try:
    import PyPDF2
    import docx
    LIBS_DOC = True
except ImportError:
    LIBS_DOC = False

# ==============================================================================
# ⚙️ CONFIGURAÇÃO GERAL
# ==============================================================================
st.set_page_config(page_title="CERBERUS - Sistema Tático", layout="wide", page_icon="🛡️")

GEMINI_API_KEY = "AIzaSyBeFgncS12Y65hKCzPhlK9LVCxTzA89oZ0"

# ==============================================================================
# 🎨 DESIGN E ESTILOS (IMPORTANDO FONTE INTER)
# ==============================================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

    .stApp {background-color: #0E1117;}
    
    /* Remove as bordas feias do Streamlit no form */
    div[data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
        background-color: transparent !important;
    }

    /* Estilização dos campos de input do Login */
    .stTextInput>div>div>input {
        background-color: #111827 !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
        border-radius: 6px !important;
        padding: 10px !important;
    }

    .stTextInput>div>div>input:focus {
        border-color: #38bdf8 !important;
    }

    /* Botão de Entrar */
    div[data-testid="stFormSubmitButton"] > button {
        background-color: #2563eb !important;
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        width: 100% !important;
        padding: 8px !important;
        margin-top: 10px !important;
    }

    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #1d4ed8 !important;
    }

    /* Estilos dos Módulos Internos */
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    .plan-gray { background-color: #475569; }
    .cyber-link { color: #38bdf8 !important; text-decoration: none; font-weight: bold; }
    .cyber-link:hover { color: #7dd3fc !important; text-decoration: underline; }
    .cyber-box { background-color: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #475569; color: #ffffff; margin-bottom: 15px; }
    .badge-warning { background-color: #f59e0b; color: #000; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
    
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ⚙️ BANCO DE DADOS E LISTA DE MÓDULOS
# ==============================================================================
TODOS_MODULOS = [
    "🔔 Notificações e Atualizações", "1. Detecção de Armas", "2. Transcrição de Áudio",
    "3. Visão Forense", "4. Mapa de Vínculos", "5. Investigação CPF",
    "6. Cyber OSINT & Forense", "7. Checklist Tático", "8. Gerador de Persona (Cover)",
    "9. Gerador de Rosto (IA Avançada)", "10. Inteligência Documental"
]

MODULOS_SILVER = [
    "🔔 Notificações e Atualizações", "1. Detecção de Armas", "5. Investigação CPF",
    "6. Cyber OSINT & Forense", "9. Gerador de Rosto (IA Avançada)", "10. Inteligência Documental"
]

def init_db():
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, role TEXT, plan TEXT, permissions TEXT, vencimento TEXT, status TEXT)''')
    c.execute('SELECT * FROM usuarios WHERE username = "admin"')
    if not c.fetchone():
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)', ('admin', 'admin', 'admin', 'GOLD', 'ALL', '2099-12-31', 'ativo'))
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
        if datetime.now() > vencimento: return None, "🚫 Acesso Expirado."
        return user, "OK"
    return None, "❌ Usuário ou senha inválidos."

def criar_usuario(username, password, role, plan, permissions_list, dias):
    try:
        conn = sqlite3.connect('cerberus_users.db')
        c = conn.cursor()
        validade = (datetime.now() + timedelta(days=int(dias))).strftime('%Y-%m-%d')
        perms_str = ",".join(permissions_list) if permissions_list else "NONE"
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)', (username, password, role, plan, perms_str, validade, 'ativo'))
        conn.commit()
        conn.close()
        return True, "Usuário criado com sucesso!"
    except Exception as e: return False, f"Erro: {e}"

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

# ==============================================================================
# ⚙️ FUNÇÕES CORE
# ==============================================================================
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

def gerar_mapa_vinculos_json(json_dados):
    net = Network(height='500px', width='100%', bgcolor='#1e293b', font_color='white')
    net.force_atlas_2based()
    try:
        for node in json_dados.get("nodes", []):
            cor = "#ef4444" if node.get("group") == "Pessoa" else "#3b82f6" if node.get("group") == "Empresa" else "#10b981"
            net.add_node(node["id"], label=node["label"], color=cor, title=node.get("group", ""))
        for edge in json_dados.get("edges", []):
            net.add_edge(edge["from"], edge["to"], label=edge["label"], color="#94a3b8")
        net.save_graph("grafo_inteligencia.html")
        return True
    except Exception as e: return False

def extrair_texto_arquivo(uploaded_file):
    if not LIBS_DOC: return "Erro"
    nome = uploaded_file.name.lower()
    try:
        if nome.endswith('.pdf'):
            leitor = PyPDF2.PdfReader(uploaded_file)
            return "\n".join([p.extract_text() for p in leitor.pages if p.extract_text()])
        elif nome.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        elif nome.endswith('.txt'): return uploaded_file.getvalue().decode("utf-8")
        elif nome.endswith(('.xlsx', '.xls', '.csv')):
            df = pd.read_excel(uploaded_file) if 'xls' in nome else pd.read_csv(uploaded_file)
            return df.to_string()
        else: return None
    except Exception as e: return f"Erro: {e}"

def gerar_mapa_vinculos():
    net=Network(height='600px',width='100%',bgcolor='#222222',font_color='white'); net.force_atlas_2based()
    net.add_node(1,label="ALVO",color='red'); net.add_edge(1,2); net.save_graph("mapa_operacional.html")

def gerar_pessoa_4devs():
    try: return requests.post("https://www.4devs.com.br/ferramentas_online.php", data={'acao':'gerar_pessoa','sexo':'I','txt_qtde':1}, headers={'Content-Type':'application/x-www-form-urlencoded'}).json()[0]
    except: return None


# ==============================================================================
# 🎨 TELA DE LOGIN MINIMALISTA
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    LINK_LOGO_LOGIN = "https://static.wikia.nocookie.net/nopixel/images/b/bd/Cpd_insignia.png/revision/latest?cb=20221117105741"
    
    # Estrutura HTML da caixa alinhada ao centro com a hierarquia de fontes Inter
    st.markdown(f"""
        <div style="text-align: center; max-width: 380px; margin: 0 auto; padding: 40px 30px; background-color: #1f2937; border-radius: 12px; border: 1px solid #374151; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
            
            <img src="{LINK_LOGO_LOGIN}" style="max-width: 110px; margin: 0 auto 20px auto; display: block;">
            
            <h1 style="font-family: 'Inter', sans-serif; font-weight: 600; font-size: 30px; color: #ffffff; margin: 0 0 5px 0; letter-spacing: 1px;">CERBERUS</h1>
            <h2 style="font-family: 'Inter', sans-serif; font-weight: 400; font-size: 16px; color: #9ca3af; margin: 0 0 5px 0;">Sistema de Inteligência Tática</h2>
            <h3 style="font-family: 'Inter', sans-serif; font-weight: 400; font-size: 13px; color: #6b7280; margin: 0 0 25px 0; letter-spacing: 2px;">PCERJ • PMERJ</h3>
            
            <div style="text-align: left;">
    """, unsafe_allow_html=True)
    
    with st.form("login_form"):
        user = st.text_input("Usuário", placeholder="Credencial", label_visibility="collapsed")
        pwd = st.text_input("Senha", type="password", placeholder="Senha", label_visibility="collapsed")
        
        btn = st.form_submit_button("ENTRAR")
        
        if btn:
            with st.spinner("Autenticando..."):
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
                    
    st.markdown("""
            </div>
        </div>
    """, unsafe_allow_html=True)

else:
    # ==============================================================================
    # ⚙️ ÁREA LOGADA - MÓDULOS E DASHBOARD
    # ==============================================================================
    user_role = st.session_state['role']
    user_plan = st.session_state['plan']
    user_perms = st.session_state['perms']
    
    st.sidebar.title("🐕‍🦺 CERBERUS")
    st.sidebar.caption(f"Usuário: {st.session_state['username']}")
    
    if user_plan == 'GOLD': st.sidebar.markdown("<span class='status-badge plan-gold'>PLANO GOLD</span>", unsafe_allow_html=True)
    elif user_plan == 'SILVER': st.sidebar.markdown("<span class='status-badge plan-silver'>PLANO SILVER</span>", unsafe_allow_html=True)
    else: st.sidebar.markdown("<span class='status-badge plan-gray'>PLANO GRAY</span>", unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("SAIR DO SISTEMA"):
        st.session_state['logged_in'] = False
        st.rerun()

    menu_options = ["🛠️ PAINEL ADMIN"] + TODOS_MODULOS if user_role == 'admin' else TODOS_MODULOS if user_plan == 'GOLD' else MODULOS_SILVER if user_plan == 'SILVER' else user_perms.split(",")
    menu = st.sidebar.radio("Ferramentas:", menu_options)

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
                permissoes_gray = st.multiselect("Módulos Liberados", TODOS_MODULOS) if new_plan == "GRAY" else []
                dias = st.number_input("Dias de Acesso", value=30, min_value=1)
                if st.form_submit_button("CRIAR ACESSO"):
                    perms_final = ["ALL"] if new_plan == "GOLD" else MODULOS_SILVER if new_plan == "SILVER" else permissoes_gray
                    if new_user and new_pass:
                        ok, txt = criar_usuario(new_user, new_pass, new_role, new_plan, perms_final, dias)
                        st.success(txt) if ok else st.error(txt)
                    else: st.warning("Preencha tudo.")
        with tab2:
            st.dataframe(listar_usuarios(), use_container_width=True)
            u_del = st.selectbox("Deletar Usuário", listar_usuarios()['username'].unique())
            if st.button("EXCLUIR"): deletar_usuario(u_del); st.rerun()

    elif menu == "🔔 Notificações e Atualizações":
        st.header("🔔 Central de Notificações")
        st.markdown("### 📋 Histórico")
        st.markdown("""
        <div class='cyber-box'>
            <span style='color: #38bdf8; font-weight: bold;'>[Atualização] v5.5</span> - Nova interface de login minimalista adicionada (Fonte Inter).<br>
            <span style='color: #38bdf8; font-weight: bold;'>[Atualização] v5.0</span> - Lançamento da Inteligência Documental.<br>
        </div>
        """, unsafe_allow_html=True)

    elif menu == "1. Detecção de Armas":
        st.header("🔫 Análise Tática e Identificação de Armamento")
        u = st.file_uploader("Carregar Evidência", type=['jpg','png', 'jpeg'])
        if u and st.button("INICIAR VARREDURA TÁTICA", type="primary"):
            with st.spinner("Analisando..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    r = client.models.generate_content(model='gemini-2.5-flash', contents=["Analise armas e pessoas de forma militar.", Image.open(u)])
                    st.markdown(f"<div class='cyber-box'>{r.text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Erro: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática")
        tab_up, tab_mic = st.tabs(["📁 Upload", "🎤 Gravar"])
        audio_data = None
        with tab_up: a_up = st.file_uploader("Áudio", type=['mp3','wav', 'm4a', 'ogg']); audio_data = a_up if a_up else audio_data
        with tab_mic: a_mic = st.audio_input("Gravação"); audio_data = a_mic if a_mic else audio_data
        if audio_data and STATUS_AUDIO:
            st.audio(audio_data)
            if st.button("TRANSCREVER", type="primary"):
                with st.spinner("Decodificando..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t: t.write(audio_data.getvalue()); p = t.name
                    r = whisper_model.transcribe(p); os.remove(p)
                    st.markdown(f"<div class='cyber-box'>{''.join([s['text']+'<br>' for s in r['segments']])}</div>", unsafe_allow_html=True)

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento Forense")
        u = st.file_uploader("Imagem", type=['jpg','png'])
        if u: 
            img = np.array(Image.open(u))
            st.image(cv2.cvtColor(cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, 10, 10, 7, 21), cv2.COLOR_BGR2RGB))

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Vínculos (Manual)")
        if st.button("Gerar Base"): gerar_mapa_vinculos()
        if os.path.exists("mapa_operacional.html"):
            with open("mapa_operacional.html", 'r', encoding='utf-8') as f: components.html(f.read(), height=600)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
        st.markdown("<div style='background-color: #451a03; border: 1px solid #b45309; padding: 10px; border-radius: 8px;'><span class='badge-warning'>⚠️ STATUS: EM HOMOLOGAÇÃO DE API</span></div><br>", unsafe_allow_html=True)
        cpf = st.text_input("CPF")
        if st.button("PUXAR DOSSIÊ", type="primary") and len(cpf) >= 11:
            with st.spinner("Buscando..."): time.sleep(1)
            st.success("Dados demonstrativos carregados.")
            st.markdown(f"<div class='cyber-box'><b>Nome:</b> JOHN DOE<br><b>CPF:</b> {cpf}</div>", unsafe_allow_html=True)

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        tab_ia, tab_ip, tab_d, tab_g = st.tabs(["🤖 IA Forense", "📡 IP", "🔎 Dorks", "📍 EXIF"])
        with tab_ia:
            u_p = st.file_uploader("Print", type=['jpg','png'])
            if u_p and st.button("ANALISAR PERFIL"):
                with st.spinner("Analisando..."):
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    r = client.models.generate_content(model='gemini-2.5-flash', contents=["Analise este perfil criminoso.", Image.open(u_p)])
                    st.markdown(f"<div class='cyber-box'>{r.text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        with tab_ip:
            ip = st.text_input("IP")
            if st.button("RASTREAR") and ip:
                res = requests.get(f"http://ip-api.com/json/{ip}?lang=pt-BR").json()
                if res.get('status') == 'success': st.success(f"Cidade: {res['city']} | ISP: {res['isp']}")
        with tab_d:
            n = st.text_input("Alvo")
            if st.button("BUSCAR") and n: st.markdown(f"[Pesquisar {n} no Google](https://www.google.com/search?q={n})")
        with tab_g:
            u_g = st.file_uploader("Foto Original", key="g")
            if u_g:
                geo, msg = extrair_geolocalizacao(Image.open(u_g))
                if geo: st.success(f"Lat: {geo[0]}, Lon: {geo[1]}")

    elif menu == "7. Checklist Tático":
        st.header("📋 Checklist de Plantão")
        st.selectbox("Ocorrência", ["Flagrante", "B.O."])

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Cover - Gerador de Dados Falsos")
        if st.button("GERAR PERSONA"): 
            d = gerar_pessoa_4devs()
            if d: st.markdown(f"<div class='cyber-box'><b>Nome:</b> {d.get('nome')}<br><b>CPF:</b> {d.get('cpf')}</div>", unsafe_allow_html=True)

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover")
        with st.form("g_cover"):
            g, i, e = st.selectbox("Gênero", ["Homem", "Mulher"]), st.slider("Idade", 18, 80, 35), st.selectbox("Etnia", ["Latino/Pardo", "Branco", "Negro", "Asiático"])
            c = st.text_input("Características Específicas")
            if st.form_submit_button("GERAR (NANO BANANA 2)", type="primary"):
                with st.spinner("Gerando..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        prompt = f"Rosto fotorrealista de {g}, {i} anos, {e}. {c}"
                        res = client.models.generate_images(model='imagen-3.0-generate-002', prompt=prompt, config=genai.types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="1:1"))
                        st.image(Image.open(io.BytesIO(res.generated_images[0].image.image_bytes)))
                    except Exception as err: st.error(f"Erro: {err}")

    elif menu == "10. Inteligência Documental":
        st.header("📄 Análise de Vínculos e Extração Tática")
        if not LIBS_DOC: st.error("⚠️ Bibliotecas PyPDF2/docx ausentes.")
        with st.form("f_doc"):
            arq = st.file_uploader("Evidência", type=['pdf', 'docx', 'txt', 'csv', 'xlsx', 'jpg', 'png'])
            agt = st.selectbox("Agente Analítico", ["🔎 GENÉRICO", "💰 FININT", "🌐 OSINT"])
            if st.form_submit_button("PROCESSAR", type="primary") and arq:
                with st.spinner("Analisando..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        conteudo = [Image.open(arq)] if arq.name.endswith(('.jpg', '.png')) else [f"TEXTO:\n{extrair_texto_arquivo(arq)[:15000]}"]
                        prompt = f"Analise como agente {agt}. Retorne: 1. Resumo. 2. JSON de conexões com 'nodes' (id, label, group) e 'edges' (from, to, label)."
                        conteudo.insert(0, prompt)
                        res = client.models.generate_content(model='gemini-2.5-flash', contents=conteudo)
                        txt = res.text
                        js = re.search(r'```json\n(.*?)\n```', txt, re.DOTALL)
                        relatorio = txt.replace(js.group(0), "") if js else txt
                        st.markdown(f"<div class='cyber-box'>{relatorio.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                        if js and gerar_mapa_vinculos_json(json.loads(js.group(1))) and os.path.exists("grafo_inteligencia.html"):
                            with open("grafo_inteligencia.html", 'r', encoding='utf-8') as f: components.html(f.read(), height=500)
                    except Exception as err: st.error(f"Erro: {err}")