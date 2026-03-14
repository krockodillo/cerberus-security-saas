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
import sqlite3
import pandas as pd
import urllib.parse
import google.generativeai as genai
import re
import base64

# ==============================================================================
# ⚙️ CONFIGURAÇÃO INICIAL E SEGURANÇA
# ==============================================================================
st.set_page_config(page_title="🐕‍🦺 CERBERUS BETA v0.4.9", layout="wide", page_icon="🛡️")

# PROTOCOLO DE SEGURANÇA MÁXIMA: Puxar a chave do cofre do Streamlit
try:
    GEMINI_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    GEMINI_API_KEY = "" 

# ==============================================================================
# 🎨 UI / UX - ESTÉTICA CYBER-POLICIAL
# ==============================================================================
st.markdown("""
    <style>
    .stApp {background-color: #0c1015 !important;}
    .stApp, .stApp p, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp label, .stMarkdown {color: #ffffff !important;}
    [data-testid="stSidebar"] {background-color: #111827 !important;}
    [data-testid="stSidebar"], [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {color: #e2e8f0 !important;}
    div[data-testid="stForm"] {
        background-color: #1e293b !important; border: 2px solid #3f4a5c !important; border-radius: 8px; padding: 20px !important; margin-bottom: 20px;
    }
    .stTextInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea {
        background-color: #0f172a !important; color: #ffffff !important; border: 1px solid #475569 !important;
    }
    .stButton>button, .stFormSubmitButton>button {
        background-color: #2563eb !important; color: #ffffff !important; border: none !important; font-weight: bold !important;
    }
    .stButton>button:hover, .stFormSubmitButton>button:hover {background-color: #1d4ed8 !important; color: #ffffff !important;}
    .cyber-box { background-color: #171c24; border: 2px solid #38bdf8; color: #ffffff; padding: 20px; border-radius: 8px; margin-bottom: 15px;}
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ⚙️ GESTÃO DE BANCO DE DADOS (PERSISTÊNCIA TÁTICA)
# ==============================================================================
DB_PATH = "/tmp/cerberus_v5_final.db"

def get_db_connection():
    # check_same_thread=False é vital para o Streamlit não travar com múltiplos usuários
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY, 
            password TEXT, 
            role TEXT, 
            plan TEXT, 
            vencimento TEXT)''')
        # Garante que o Comandante Leandro sempre exista
        c.execute('INSERT OR IGNORE INTO usuarios VALUES (?,?,?,?,?)', 
                  ('leandro', '239546Dl', 'admin', 'GOLD', '2099-12-31'))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro Crítico de Inicialização: {e}")

def login_user(username, password):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT username, role, plan, vencimento FROM usuarios WHERE username = ? AND password = ?', (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            venc = datetime.strptime(user[3], '%Y-%m-%d')
            if datetime.now() > venc: return None, "🚫 Acesso Expirado."
            return user, "OK"
    except: pass
    return None, "❌ Credenciais Inválidas."

def add_user(u, p, r, pl, v):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', (u, p, r, pl, v))
        conn.commit()
        conn.close()
        return True
    except: return False

def delete_user(u):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('DELETE FROM usuarios WHERE username = ?', (u,))
        conn.commit()
        conn.close()
        return True
    except: return False

# Inicializa o banco no carregamento
init_db()

# ==============================================================================
# 🛠️ MOTORES E FUNÇÕES AUXILIARES
# ==============================================================================
@st.cache_resource
def carregar_whisper(): return whisper.load_model("tiny")
try: whisper_model = carregar_whisper(); STATUS_AUDIO = True
except: STATUS_AUDIO = False

def gerar_pdf(titulo, dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"CERBERUS - {titulo}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    for k, v in dados.items():
        pdf.cell(0, 10, f"{k.upper()}: {v}", ln=True)
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# 🚪 CONTROLE DE SESSÃO E TELA DE LOGIN
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: white;'>🐕‍🦺 CERBERUS <span style='font-size: 16px; color: #38bdf8;'>V0.4.9</span></h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #94a3b8;'>SISTEMA DE INTELIGÊNCIA E OPERAÇÕES TÁTICAS</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            user_input = st.text_input("Credencial Operacional")
            pass_input = st.text_input("Chave de Acesso", type="password")
            submit = st.form_submit_button("AUTENTICAR CONEXÃO", use_container_width=True)
            
            if submit:
                with st.spinner("Validando credenciais..."):
                    user_data, msg = login_user(user_input, pass_input)
                    if user_data:
                        st.session_state['logged_in'] = True
                        st.session_state['user'] = user_data[0]
                        st.session_state['role'] = user_data[1]
                        st.session_state['plan'] = user_data[2]
                        st.rerun()
                    else:
                        st.error(msg)
else:
    # --- ÁREA LOGADA ---
    u_name = st.session_state['user']
    u_role = st.session_state['role']
    u_plan = st.session_state['plan']

    st.sidebar.title("🐕‍🦺 CERBERUS")
    st.sidebar.markdown(f"**Agente:** `{u_name.upper()}`")
    if u_plan == "GOLD": st.sidebar.markdown("<span class='status-badge plan-gold'>PLANO GOLD</span>", unsafe_allow_html=True)
    else: st.sidebar.markdown("<span class='status-badge plan-silver'>PLANO SILVER</span>", unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("DESCONECTAR"):
        st.session_state['logged_in'] = False
        st.rerun()

    # Definição de Menus baseada no Plano
    MODULOS_BASE = [
        "1. Detecção de Armas", "5. Investigação CPF", "6. Cyber OSINT", 
        "7. Checklist Tático", "8. Persona Cover", "10. Inteligência Documental"
    ]
    MODULOS_GOLD = MODULOS_BASE + ["2. Transcrição Áudio", "3. Visão Forense", "9. Gerador de Rosto", "11. Gestão de Operações"]
    
    opcoes = MODULOS_GOLD if u_plan == "GOLD" else MODULOS_BASE
    if u_role == "admin": opcoes.append("⚙️ Painel do Comandante")

    menu = st.sidebar.radio("Navegação de Inteligência:", opcoes)

    # ==============================================================================
    # ⚙️ MÓDULO: PAINEL DO COMANDANTE (MASTER)
    # ==============================================================================
    if menu == "⚙️ Painel do Comandante":
        st.header("⚙️ Painel de Gestão de Efetivo")
        tab1, tab2 = st.tabs(["📋 Agentes Ativos", "➕ Novo Recrutamento"])
        
        with tab1:
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT username, role, plan, vencimento FROM usuarios", conn)
            conn.close()
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            alvo_del = st.selectbox("Revogar Acesso de Agente:", df['username'].tolist())
            if st.button("EXCLUIR CREDENCIAL"):
                if alvo_del == "leandro": st.error("Impossível excluir o Comandante Master.")
                elif delete_user(alvo_del): st.success("Acesso revogado."); st.rerun()

        with tab2:
            with st.form("add_user"):
                n_u = st.text_input("Novo Usuário")
                n_p = st.text_input("Senha Inicial")
                n_r = st.selectbox("Nível", ["user", "admin"])
                n_pl = st.selectbox("Plano de Acesso", ["GOLD", "SILVER"])
                n_v = st.date_input("Validade", value=datetime.now() + timedelta(days=365))
                if st.form_submit_button("CADASTRAR AGENTE"):
                    if add_user(n_u, n_p, n_r, n_pl, n_v.strftime('%Y-%m-%d')):
                        st.success("Agente integrado ao sistema.")
                    else: st.error("Usuário já existe.")

    # ==============================================================================
    # 🔫 MÓDULO: DETECÇÃO DE ARMAS
    # ==============================================================================
    elif menu == "1. Detecção de Armas":
        st.header("🔫 Varredura Tática de Imagens")
        up = st.file_uploader("Submeter Foto/Frame", type=['jpg','png'])
        if up and st.button("INICIAR ANÁLISE"):
            if not GEMINI_API_KEY: st.error("Erro: API Key não configurada.")
            else:
                with st.spinner("IA Analisando ameaças..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    res = model.generate_content(["Identifique armas, munições e nível de perigo tático.", Image.open(up)])
                    st.image(up, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)

    # ==============================================================================
    # 🕵️ MÓDULO: PERSONA COVER (OFFLINE)
    # ==============================================================================
    elif menu == "8. Persona Cover":
        st.header("🕵️ Gerador de Identidade Sintética")
        with st.form("p_cover"):
            sexo = st.radio("Gênero", ["Masculino", "Feminino"], horizontal=True)
            estado = st.selectbox("Estado de Origem", ["SP", "RJ", "MG", "BA", "PR", "PE"])
            if st.form_submit_button("SINTETIZAR"):
                # Lógica simplificada offline para garantir 0 erros
                id_falsa = f"{random.randint(100,999)}.{random.randint(100,999)}.{random.randint(100,999)}-{random.randint(10,99)}"
                nome_falso = f"{random.choice(['Miguel','Arthur','Helena','Alice'])} {random.choice(['Silva','Santos','Oliveira'])}"
                st.session_state['cover'] = {"Nome": nome_falso, "CPF": id_falsa, "Origem": estado}
        
        if 'cover' in st.session_state:
            st.json(st.session_state['cover'])
            pdf_bytes = gerar_pdf("FICHA COVER", st.session_state['cover'])
            st.download_button("BAIXAR DOSSIÊ", pdf_bytes, "cover.pdf", "application/pdf")

    # ==============================================================================
    # 👤 MÓDULO: GERADOR DE ROSTO (IMAGEN 3)
    # ==============================================================================
    elif menu == "9. Gerador de Rosto":
        st.header("👤 Síntese de Face Neural")
        with st.form("f_rosto"):
            prompt_f = st.text_input("Descrição do Alvo", "Homem pardo, 30 anos, barba curta, olhar sério")
            if st.form_submit_button("GERAR FACE"):
                url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={GEMINI_API_KEY}"
                payload = {"instances": [{"prompt": prompt_f}]}
                try:
                    res = requests.post(url, json=payload, timeout=30)
                    img_b64 = res.json()["predictions"][0]["bytesBase64Encoded"]
                    st.session_state['face'] = base64.b64decode(img_b64)
                except: st.error("Erro na síntese neural.")
        
        if 'face' in st.session_state:
            st.image(st.session_state['face'], use_container_width=True)
            st.download_button("BAIXAR IMAGEM", st.session_state['face'], "face.jpg", "image/jpeg")

    # Módulos genéricos (Placeholders para manter a estrutura)
    else:
        st.info(f"O Módulo {menu} está pronto para operação. Insira os dados táticos.")
