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
st.set_page_config(page_title="🐕‍🦺 CERBERUS BETA v0.4.7", layout="wide", page_icon="🛡️")

# PROTOCOLO DE SEGURANÇA MÁXIMA: Puxar a chave do cofre do Streamlit
try:
    GEMINI_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    GEMINI_API_KEY = "" 

try:
    import PyPDF2
    import docx
    LIBS_DOC = True
except ImportError:
    LIBS_DOC = False

# ==============================================================================
# 🎨 PAINEL DE CONTROLE DE CORES E UI (CSS)
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
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    div.row-widget.stRadio > div {flex-direction: row;}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ⚙️ BANCO DE DADOS E GESTÃO DE ACESSO
# ==============================================================================
TODOS_MODULOS = [
    "1. Detecção de Armas", "2. Transcrição de Áudio", "3. Visão Forense",
    "4. Mapa de Vínculos", "5. Investigação CPF", "6. Cyber OSINT & Forense",
    "7. Checklist Tático", "8. Gerador de Persona (Cover)",
    "9. Gerador de Rosto (IA Avançada)", "10. Inteligência Documental", "11. Gestão de Operações"
]

MODULOS_SILVER = [
    "1. Detecção de Armas", "5. Investigação CPF", "6. Cyber OSINT & Forense",
    "8. Gerador de Persona (Cover)", "10. Inteligência Documental", "11. Gestão de Operações"
]

DB_PATH = "/tmp/cerberus_users_v2.db"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, role TEXT, plan TEXT, vencimento TEXT)''')
    c.execute('SELECT * FROM usuarios WHERE username = "leandro"')
    if not c.fetchone():
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', ('leandro', '239546Dl', 'admin', 'GOLD', '2099-12-31'))
        conn.commit()
    conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, password))
    user = c.fetchone()
    conn.close()
    if user:
        vencimento = datetime.strptime(user[4], '%Y-%m-%d')
        if datetime.now() > vencimento: return None, "🚫 Acesso Expirado."
        return user, "OK"
    return None, "❌ Credenciais Inválidas."

def get_all_users():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('SELECT username, role, plan, vencimento FROM usuarios')
    users = c.fetchall()
    conn.close()
    return users

def create_user(username, password, role, plan, vencimento):
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', (username, password, role, plan, vencimento))
        conn.commit()
        conn.close()
        return True, "✅ Agente cadastrado!"
    except:
        return False, "❌ Erro ao cadastrar."

init_db()

# ==============================================================================
# 🚪 PROTOCOLO DE ACESSO DIRETO (BYPASS LOGIN)
# ==============================================================================
if 'logged_in' not in st.session_state:
    # Ao iniciar, o sistema assume automaticamente o comando do Comandante Leandro
    st.session_state['logged_in'] = True
    st.session_state['username'] = 'leandro'
    st.session_state['role'] = 'admin'
    st.session_state['plan'] = 'GOLD'

# ==============================================================================
# MOTORES DE IA E FUNÇÕES TÁTICAS
# ==============================================================================
@st.cache_resource
def carregar_whisper(): return whisper.load_model("tiny")
try: whisper_model = carregar_whisper(); STATUS_AUDIO = True
except: STATUS_AUDIO = False

def gerar_pdf_checklist(titulo, dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"CERBERUS - {titulo.upper()}", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.ln(10)
    for k, v in dados.items():
        if v and isinstance(v, str):
            pdf.set_font("Arial", 'B', 10)
            pdf.write(7, f"{str(k).upper()}: ")
            pdf.set_font("Arial", '', 10)
            pdf.multi_cell(0, 7, txt=str(v).encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

def gerar_persona_offline(sexo, idade, uf, pontuacao_str):
    pontuacao = pontuacao_str == "Sim"
    if sexo == "Aleatório": sexo = random.choice(["Masculino", "Feminino"])
    n_h = ["Miguel", "Arthur", "Gael", "Théo", "Heitor", "Noah", "Gabriel"]
    n_m = ["Helena", "Alice", "Laura", "Maria", "Sophia", "Beatriz"]
    sobrenomes = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Lima"]
    primeiro = random.choice(n_h) if sexo == "Masculino" else random.choice(n_m)
    nome = f"{primeiro} {random.choice(sobrenomes)} {random.choice(sobrenomes)}"
    nasc = datetime.now() - timedelta(days=(idade * 365) + random.randint(1, 360))
    c_str = ''.join([str(random.randint(0,9)) for _ in range(11)])
    cpf_f = f"{c_str[:3]}.{c_str[3:6]}.{c_str[6:9]}-{c_str[9:]}" if pontuacao else c_str
    return {
        "nome": nome, "cpf": cpf_f, "data_nasc": nasc.strftime("%d/%m/%Y"), "idade": str(idade),
        "sexo": sexo, "cidade": "Capital", "estado": uf, "celular": "(11) 9" + str(random.randint(10000000, 99999999))
    }

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
if not st.session_state['logged_in']:
    # Esta tela só aparecerá se você clicar em "Encerrar Sessão" propositalmente
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🐕‍🦺 LOGIN CERBERUS</h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            if st.form_submit_button("ENTRAR", use_container_width=True):
                u_data, msg = login_user(user, pwd)
                if u_data:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u_data[0]
                    st.session_state['role'] = u_data[2]
                    st.session_state['plan'] = u_data[3]
                    st.rerun()
                else: st.error(msg)
else:
    user_role = st.session_state['role']
    user_plan = st.session_state['plan']
    
    st.sidebar.title("🐕‍🦺 CERBERUS TÁTICO")
    st.sidebar.caption(f"Operador: {st.session_state['username'].upper()}")
    if user_role == 'admin': st.sidebar.markdown("<span class='status-badge plan-gold'>COMANDANTE</span>", unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("ENCERRAR SESSÃO"):
        st.session_state['logged_in'] = False
        st.rerun()

    menu_options = TODOS_MODULOS.copy() if user_plan == 'GOLD' else MODULOS_SILVER.copy()
    if user_role == 'admin': menu_options.append("⚙️ Gestão de Efetivo")

    menu = st.sidebar.radio("Selecione o Módulo:", menu_options)

    # --- MÓDULO 9: GERADOR DE ROSTO (VERSÃO CORRIGIDA) ---
    if menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Síntese Facial Fotorrealista")
        with st.form("form_rosto"):
            c1, c2 = st.columns(2)
            with c1:
                gender = st.selectbox("Gênero", ["Masculino", "Feminino"])
                age = st.slider("Idade", 18, 70, 30)
            with c2:
                tipo = st.selectbox("Enquadramento", ["Somente rosto", "Meio corpo"])
                roupa = st.selectbox("Vestimenta", ["Casual", "Tático militar", "Social"])
            gerar = st.form_submit_button("SINTETIZAR IMAGEM", type="primary")

        if gerar:
            if not GEMINI_API_KEY: st.error("Chave API ausente nos Secrets.")
            else:
                with st.spinner("Renderizando..."):
                    try:
                        prompt = f"Fotografia realista de {gender}, {age} anos, vestindo {roupa}, enquadramento {tipo}, alta definição."
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={GEMINI_API_KEY}"
                        res = requests.post(url, json={"instances": [{"prompt": prompt}]}, timeout=30)
                        if res.status_code == 200:
                            img_b64 = res.json()["predictions"][0]["bytesBase64Encoded"]
                            st.session_state['avatar'] = base64.b64decode(img_b64)
                        else: st.error(f"Erro API: {res.status_code}")
                    except Exception as e: st.error(f"Erro: {e}")

        if 'avatar' in st.session_state:
            st.image(st.session_state['avatar'], use_container_width=True)
            st.download_button("BAIXAR IMAGEM", st.session_state['avatar'], file_name="avatar.jpg", mime="image/jpeg")

    # --- MÓDULO 8: PERSONA OFFLINE ---
    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Gerador de Persona")
        with st.form("form_p"):
            sx = st.radio("Sexo", ["Masculino", "Feminino"], horizontal=True)
            id_ = st.slider("Idade", 18, 80, 35)
            uf = st.selectbox("Estado", ["SP", "RJ", "MG", "BA"])
            if st.form_submit_button("GERAR"):
                st.session_state['p_data'] = gerar_persona_offline(sx, id_, uf, "Sim")
        
        if 'p_data' in st.session_state:
            st.json(st.session_state['p_data'])
            st.download_button("BAIXAR FICHA (PDF)", gerar_pdf_checklist("PERSONA", st.session_state['p_data']), file_name="persona.pdf")

    # --- MÓDULO 7: CHECKLIST ---
    elif menu == "7. Checklist Tático":
        st.header("📋 Relatórios Operacionais")
        with st.form("f_check"):
            op = st.text_input("Nome da Operação")
            rel = st.text_area("Relato dos Fatos")
            if st.form_submit_button("GERAR RELATÓRIO"):
                st.session_state['pdf_rel'] = gerar_pdf_checklist("RELATÓRIO", {"Operação": op, "Relato": rel})
        if 'pdf_rel' in st.session_state:
            st.download_button("BAIXAR PDF", st.session_state['pdf_rel'], file_name="relatorio.pdf")

    # --- MÓDULO 11: GESTÃO ---
    elif menu == "⚙️ Gestão de Efetivo":
        st.header("⚙️ Gestão de Agentes")
        users = get_all_users()
        st.table(pd.DataFrame(users, columns=["Usuário", "Nível", "Plano", "Vencimento"]))

    # --- DEMAIS MÓDULOS (PLACEHOLDERS) ---
    else:
        st.info(f"Módulo '{menu}' carregado e aguardando entrada de dados.")
