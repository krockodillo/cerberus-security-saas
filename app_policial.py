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

# ==============================================================================
# ⚙️ CONFIGURAÇÃO INICIAL E SEGURANÇA
# ==============================================================================
st.set_page_config(page_title="🐕‍🦺 CERBERUS BETA v0.3.3", layout="wide", page_icon="🛡️")

GEMINI_API_KEY = "COLE_SUA_CHAVE_NOVA_AQUI" # MANTENHA A SUA CHAVE AQUI

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
    /* Ajuste para alinhar os rótulos de rádio na horizontal */
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

DB_PATH = "/tmp/cerberus_users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, role TEXT, plan TEXT, vencimento TEXT)''')
    c.execute('SELECT * FROM usuarios WHERE username = "leandro"')
    if not c.fetchone():
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', ('leandro', '239546Dl', 'admin', 'GOLD', '2099-12-31'))
        conn.commit()
    conn.close()

def login_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM usuarios WHERE username = ? AND password = ?', (username, password))
    user = c.fetchone()
    conn.close()
    if user:
        vencimento = datetime.strptime(user[4], '%Y-%m-%d')
        if datetime.now() > vencimento: return None, "🚫 Acesso Expirado."
        return user, "OK"
    return None, "❌ Usuário ou senha inválidos."

init_db()

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
    pdf.cell(0, 8, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    for k, v in dados.items():
        if v and isinstance(v, str):
            pdf.set_font("Arial", 'B', 10)
            pdf.write(7, f"{str(k).upper().replace('_', ' ')}: ")
            pdf.set_font("Arial", '', 10)
            clean_v = str(v).replace('\n', ' ').encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 7, txt=clean_v)
            pdf.ln(1)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, "_", ln=True, align='C')
    pdf.cell(0, 10, "DOCUMENTO OFICIAL PARA USO INTERNO / SIGILOSO", ln=True, align='C')
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# TELA DE LOGIN E NAVEGAÇÃO
# ==============================================================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: white;'>🐕‍🦺 CERBERUS <span style='font-size: 16px; color: #38bdf8;'>BETA v0.3.3</span></h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Credencial Operacional")
            pwd = st.text_input("Chave de Acesso", type="password")
            btn = st.form_submit_button("ENTRAR NO SISTEMA", use_container_width=True)
            if btn:
                with st.spinner("Autenticando..."):
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
    
    st.sidebar.title("🐕‍🦺 CERBERUS")
    st.sidebar.caption(f"Agente: {st.session_state['username'].upper()}")
    if user_plan == 'GOLD': st.sidebar.markdown("<span class='status-badge plan-gold'>PLANO GOLD</span>", unsafe_allow_html=True)
    elif user_plan == 'SILVER': st.sidebar.markdown("<span class='status-badge plan-silver'>PLANO SILVER</span>", unsafe_allow_html=True)
    st.sidebar.markdown("---")
    if st.sidebar.button("ENCERRAR SESSÃO"):
        st.session_state['logged_in'] = False
        st.rerun()

    menu_options = TODOS_MODULOS if user_plan == 'GOLD' else MODULOS_SILVER
    menu = st.sidebar.radio("Módulos de Inteligência:", menu_options)

    if menu == "1. Detecção de Armas":
        st.header("🔫 Análise de Armamento e Tática Visual")
        u = st.file_uploader("Submeter Evidência (Imagem)", type=['jpg','png','jpeg'])
        if u and st.button("INICIAR VARREDURA"):
            with st.spinner("Decodificando armamentos e perímetro..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    prompt = "Aja como perito criminal. Conte os indivíduos e armas. Especifique os tipos de armas, calibre presumido e faça uma avaliação de risco tático do ambiente. Seja direto, técnico, estruturado em tópicos e não use emojis."
                    res = model.generate_content([prompt, Image.open(u)])
                    st.image(u, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Falha na análise: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Decodificação de Áudio (Whisper)")
        t1, t2 = st.tabs(["📁 Arquivo Físico", "🎤 Captura de Microfone"])
        audio_up = None
        with t1: audio_up = st.file_uploader("Submeter Áudio", type=['mp3','wav', 'm4a', 'ogg'])
        with t2: audio_input = st.audio_input("Grave a evidência")
        audio_core = audio_up if audio_up else audio_input
        if audio_core and st.button("PROCESSAR TRANSCRIÇÃO"):
            with st.spinner("Extraindo texto..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                    t.write(audio_core.getvalue()); p = t.name
                try:
                    res = whisper_model.transcribe(p, language="pt", fp16=False)
                    os.remove(p)
                    txt = "".join([s['text'] + "\n" for s in res["segments"]])
                    st.markdown(f"<div class='cyber-box'>{txt}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Falha na decodificação: {e}")

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento e Restauração Forense")
        u = st.file_uploader("Imagem Evidência", type=['jpg','png','jpeg'])
        if u:
            img = Image.open(u)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            c1, c2 = st.columns(2)
            with c1: st.image(u, caption="Original", use_container_width=True)
            with c2:
                if st.button("FILTRO DE RUÍDO (DENOISE)"):
                    dn = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
                    st.image(cv2.cvtColor(dn, cv2.COLOR_BGR2RGB), use_container_width=True)
                s = st.slider("Nitidez", 1, 5, 2)
                if st.button("AGUÇAR BORDAS"):
                    k = np.array([[0, -s, 0], [-s, 4*s+1, -s], [0, -s, 0]])
                    sh = cv2.filter2D(cv_img, -1, k)
                    st.image(cv2.cvtColor(sh, cv2.COLOR_BGR2RGB), use_container_width=True)

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Diagrama de Vínculos")
        st.error("🛑 MÓDULO EM MANUTENÇÃO.")

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Triagem")
        cpf = st.text_input("CPF do Alvo (11 dígitos)")
        if cpf and st.button("PUXAR REGISTROS"):
            with st.spinner("Acessando bases..."):
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash-latest')
                prompt = f"Gere um JSON simulando Dossiê para o CPF {cpf}: Nome, RG, Filiação, Endereços, Histórico. JSON PURO."
                try:
                    res = model.generate_content(prompt)
                    dados = json.loads(res.text.strip().replace("```json\n", "").replace("\n```", "").replace("```",""))
                    st.json(dados)
                except Exception as e: st.error(f"Falha estrutural: {e}")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Cibernética")
        tab1, tab2, tab3 = st.tabs(["🤖 Análise de Perfil", "📡 Rastreio IP", "🔎 Motores de Busca"])
        with tab1:
            u_p = st.file_uploader("Evidência Digital", type=['jpg','png','jpeg'])
            if u_p and st.button("ANALISAR PERFIL"):
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash-latest')
                res = model.generate_content(["Analise este perfil. Identifique logotipos, facções, nomes visíveis.", Image.open(u_p)])
                st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
        with tab2:
            ip_in = st.text_input("Endereço IP Alvo")
            if ip_in and st.button("RASTREAR ORIGEM"):
                try:
                    res = requests.get(f"[http://ip-api.com/json/](http://ip-api.com/json/){ip_in}").json()
                    st.success(f"📍 {ip_in} | {res.get('isp')} | {res.get('city')}")
                except: st.error("Falha na varredura.")

    elif menu == "7. Checklist Tático":
        st.header("📋 Formulários e Procedimentos")
        with st.form("form_bo"):
            loc = st.text_input("Localização do Fato")
            nar = st.text_area("Dinâmica dos Fatos")
            if st.form_submit_button("GERAR BOLETIM"): st.success("Registrado.")

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Gerador de Pessoas (Identidade Cover)")
        st.markdown("⚠️ DIRETRIZ: Geração avançada via Motor de IA Neural. Formatação idêntica a bancos de dados nacionais.")
        
        with st.form("form_persona"):
            st.markdown("### ⚙️ Parâmetros de Geração")
            
            c1, c2 = st.columns(2)
            with c1:
                sx = st.radio("Sexo", ["Masculino", "Feminino", "Aleatório"], horizontal=True)
                idade = st.slider("Idade do Alvo", 18, 80, 30)
            with c2:
                uf = st.selectbox("Estado (UF)", ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"])
                pontuacao = st.radio("Pontuação (Mascáras visuais)", ["Sim", "Não"], horizontal=True)

            if st.form_submit_button("GERAR PESSOA", type="primary"):
                with st.spinner("Acionando Motor de Síntese de Identidade (Aguarde)..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        model = genai.GenerativeModel('gemini-1.5-flash-latest')
                        
                        pont_inst = "USE máscara de pontuação (ex: 123.456.789-00, (11) 99999-9999)" if pontuacao == "Sim" else "NÃO use pontuação, apenas números contínuos (ex: 12345678900, 11999999999)"
                        
                        prompt = f"""
                        Gere uma identidade sintética brasileira hiper-realista.
                        Parâmetros Obrigatórios: Sexo {sx}, Idade Exata {idade} anos, Estado {uf}.
                        Regra de formatação: {pont_inst} para CPF, RG, CEP e Telefones.

                        Atenção: A Cidade DEVE ser uma cidade real que pertence ao estado de {uf}.
                        
                        Retorne EXATAMENTE este JSON puro (sem markdown de formatação, apenas abra com {{ e feche com }}):
                        {{
                            "nome": "", "cpf": "", "rg": "", "data_nasc": "", "idade": "{idade}", "signo": "", "sexo": "{sx}",
                            "mae": "", "pai": "",
                            "cep": "", "endereco": "", "numero": "", "bairro": "", "cidade": "", "estado": "{uf}",
                            "telefone_fixo": "", "celular": "",
                            "altura": "", "peso": "", "tipo_sanguineo": "", "cor": "",
                            "profissao": "", "renda": "", "email": "", "senha": "",
                            "cartao_numero": "", "cartao_validade": "", "cartao_cvv": "", "cartao_bandeira": "",
                            "veiculo_placa": "", "veiculo_renavam": "", "veiculo_chassi": "", "veiculo_marca_modelo": "", "veiculo_ano": ""
                        }}
                        """
                        res = model.generate_content(prompt)
                        json_str = res.text.strip()
                        if json_str.startswith("
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2
