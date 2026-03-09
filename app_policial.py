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
# ⚙️ [MOTOR] CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
# AQUI VOCÊ MUDA O TÍTULO QUE APARECE NA ABA DO NAVEGADOR E O ÍCONE (EMOJI)
st.set_page_config(page_title="CERBERUS - Sistema Tático", layout="wide", page_icon="🛡️")

GEMINI_API_KEY = "AIzaSyBeFgncS12Y65hKCzPhlK9LVCxTzA89oZ0"

# ==============================================================================
# 🎨 [DESIGN] CENTRAL DE TEXTOS E IMAGENS (LOGIN)
# Mude os textos aqui e eles mudarão na tela automaticamente.
# ==============================================================================
# AQUI VOCÊ COLOCA O LINK DA SUA LOGO DO LOGIN
LINK_LOGO_LOGIN = "https://grupocerberus.com.br/wp-content/uploads/2026/02/f57239e7d983c652c66e252b056d6909a321c547.png"

# AQUI VOCÊ MUDA O TEXTO DO TÍTULO ABAIXO DA LOGO
TEXTO_TITULO_LOGIN = "CERBERUS"

# AQUI VOCÊ MUDA O TEXTO DE DENTRO DO BOTÃO DE ENTRAR
TEXTO_BOTAO_ENTRAR = "AUTENTICAR"

# AQUI VOCÊ MUDA O TEXTO FANTASMA (PLACEHOLDER) DO CAMPO DE USUÁRIO
TEXTO_DICA_USUARIO = "Digite sua credencial"

# AQUI VOCÊ MUDA O TEXTO FANTASMA (PLACEHOLDER) DO CAMPO DE SENHA
TEXTO_DICA_SENHA = "Digite sua senha"


# ==============================================================================
# 🎨 [DESIGN] CENTRAL DE CORES E ESTILOS (CSS CSS)
# Aqui você tem o controle total dos pixels, cores e botões de todo o sistema.
# ==============================================================================
st.markdown("""
    <style>
    /* ------------------------------------------------------------------
       1. FUNDOS GERAIS DO SISTEMA
       ------------------------------------------------------------------ */
    /* AQUI VOCÊ MUDA A COR DO BACKGROUND (FUNDO) DE TODO O SITE */
    .stApp {
        background-color: #0E1117 !important; 
    }
    
    /* AQUI VOCÊ MUDA A COR DO MENU LATERAL (SIDEBAR) ONDE FICAM OS MÓDULOS */
    [data-testid="stSidebar"] {
        background-color: #111827 !important;
    }

    /* ------------------------------------------------------------------
       2. CAIXA DE LOGIN (A ÁREA BLINDADA NO CENTRO DA TELA)
       ------------------------------------------------------------------ */
    /* AQUI VOCÊ MUDA A COR DA CAIXA EXTERNA ONDE FICAM OS CAMPOS DE SENHA */
    .login-wrapper {
        background-color: #1f2937 !important; 
        max-width: 420px; /* AQUI VOCÊ MUDA A LARGURA DA CAIXA DE LOGIN */
        margin: 50px auto;
        border-radius: 12px; /* AQUI VOCÊ MUDA O ARREDONDAMENTO DAS BORDAS DA CAIXA */
        border: 1px solid #374151; /* AQUI VOCÊ MUDA A COR DA LINHA EM VOLTA DA CAIXA */
        box-shadow: 0 10px 25px rgba(0,0,0,0.8); /* AQUI VOCÊ MUDA A SOMBRA DA CAIXA */
    }

    /* AQUI VOCÊ MUDA A COR DO BANNER SUPERIOR (ONDE FICA A LOGO) */
    .login-topo {
        background-color: #000000 !important; 
        padding: 40px 20px 30px 20px;
        border-bottom: 2px solid #2563eb; /* AQUI VOCÊ MUDA A LINHA COLORIDA QUE SEPARA A LOGO DOS CAMPOS */
        text-align: center;
    }
    
    /* AQUI VOCÊ MUDA O TAMANHO DA IMAGEM DA LOGO NO LOGIN */
    .login-logo-img {
        max-width: 140px !important; 
        margin: 0 auto;
        display: block;
    }

    /* AQUI VOCÊ MUDA A FONTE E A COR DO TÍTULO (Ex: CERBERUS INTEL) */
    .login-titulo {
        color: #ffffff !important; 
        font-family: 'Courier New', Courier, monospace; /* AQUI VOCÊ TROCA A FONTE DO TÍTULO */
        font-weight: bold;
        font-size: 24px; /* AQUI VOCÊ MUDA O TAMANHO DA LETRA DO TÍTULO */
        margin-top: 15px;
        letter-spacing: 2px; /* AQUI VOCÊ MUDA O ESPAÇO ENTRE AS LETRAS */
    }

    /* ------------------------------------------------------------------
       3. CAMPOS DE DIGITAÇÃO (USUÁRIO E SENHA E BUSCAS INTERNAS)
       ------------------------------------------------------------------ */
    /* AQUI VOCÊ MUDA A COR DO FUNDO DE ONDE O USUÁRIO DIGITA OS TEXTOS/SENHA */
    .stTextInput>div>div>input {
        background-color: #111827 !important; 
        color: #ffffff !important; /* AQUI VOCÊ MUDA A COR DA LETRA QUE O USUÁRIO DIGITA */
        border: 1px solid #475569 !important; /* AQUI VOCÊ MUDA A COR DA BORDA DO CAMPO */
        border-radius: 8px !important; /* AQUI VOCÊ DEIXA O CAMPO MAIS REDONDO OU QUADRADO */
        padding: 12px !important; /* AQUI VOCÊ DEIXA O CAMPO MAIS GORDINHO OU FINO */
    }

    /* AQUI VOCÊ MUDA A COR DA BORDA QUANDO O USUÁRIO CLICA NO CAMPO PARA DIGITAR */
    .stTextInput>div>div>input:focus {
        border-color: #38bdf8 !important; 
        box-shadow: 0 0 5px rgba(56, 189, 248, 0.5) !important;
    }

    /* ------------------------------------------------------------------
       4. BOTÕES GERAIS E BOTÃO DE LOGIN
       ------------------------------------------------------------------ */
    /* AQUI VOCÊ MUDA O ESTILO PRINCIPAL DE TODOS OS BOTÕES (INCLUSIVE O DE ENTRAR) */
    div[data-testid="stFormSubmitButton"] > button, 
    div[data-testid="stButton"] > button {
        background-color: #2563eb !important; /* AQUI VOCÊ TROCA A COR DE FUNDO DO BOTÃO (AZUL) */
        color: #ffffff !important; /* AQUI VOCÊ TROCA A COR DO TEXTO DENTRO DO BOTÃO */
        border: none !important; /* SE QUISER ADICIONAR BORDA NO BOTÃO, MUDE AQUI */
        border-radius: 8px !important; /* AQUI VOCÊ ARREDONDA AS PONTAS DO BOTÃO */
        font-weight: bold !important;
        padding: 10px 20px !important; /* AQUI VOCÊ MUDA A ALTURA (10px) E LARGURA (20px) DO BOTÃO */
        width: 100% !important; /* DEIXA O BOTÃO ESTICADO ATÉ O FINAL DA CAIXA */
    }

    /* AQUI VOCÊ MUDA A COR DO BOTÃO QUANDO PASSA O MOUSE POR CIMA (HOVER) */
    div[data-testid="stFormSubmitButton"] > button:hover, 
    div[data-testid="stButton"] > button:hover {
        background-color: #1d4ed8 !important; /* AZUL MAIS ESCURO PARA O MOUSE */
        color: #ffffff !important;
        border-color: transparent !important;
    }

    /* ------------------------------------------------------------------
       5. CAIXAS DE RELATÓRIO (ONDE A IA ESCREVE AS RESPOSTAS)
       ------------------------------------------------------------------ */
    /* AQUI VOCÊ MUDA AS CAIXAS DE RESULTADOS DENTRO DO SISTEMA (AQUELES PAINEIS TÁTICOS) */
    .cyber-box { 
        background-color: #1e293b !important; /* COR DE FUNDO DA CAIXA DO RELATÓRIO */
        padding: 20px !important; 
        border-radius: 8px !important; 
        border: 1px solid #475569 !important; /* BORDA DA CAIXA DO RELATÓRIO */
        color: #e2e8f0 !important; /* COR DA LETRA DA IA */
        margin-bottom: 15px !important; 
    }

    /* AQUI VOCÊ MUDA AS CORES DOS LINKS AZUIS CLAROS DENTRO DO SISTEMA */
    .cyber-link { color: #38bdf8 !important; text-decoration: none; font-weight: bold; }
    .cyber-link:hover { color: #7dd3fc !important; text-decoration: underline; }

    /* Remove lixos visuais do Streamlit */
    div[data-testid="stForm"] { border: none !important; padding: 0 !important; background-color: transparent !important; }
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)


# ==============================================================================
# ⚙️ [MOTOR] LISTA DE MÓDULOS E BANCO DE DADOS
# ==============================================================================
TODOS_MODULOS = [
    "🔔 Notificações e Atualizações",
    "1. Detecção de Armas",
    "2. Transcrição de Áudio",
    "3. Visão Forense",
    "4. Mapa de Vínculos",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "7. Checklist Tático",
    "8. Gerador de Persona (Cover)",
    "9. Gerador de Rosto (IA Avançada)",
    "10. Inteligência Documental"
]

MODULOS_SILVER = [
    "🔔 Notificações e Atualizações",
    "1. Detecção de Armas",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "9. Gerador de Rosto (IA Avançada)",
    "10. Inteligência Documental"
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

init_db()

# ==============================================================================
# ⚙️ [MOTOR] FUNÇÕES DOS MÓDULOS (CORE)
# ==============================================================================
@st.cache_resource
def carregar_whisper(): return whisper.load_model("tiny")
try: whisper_model = carregar_whisper(); STATUS_AUDIO = True
except: STATUS_AUDIO = False

def extrair_geolocalizacao(image): pass # Simplificado para estrutura principal
def gerar_mapa_vinculos_json(json_dados): pass 
def extrair_texto_arquivo(uploaded_file): pass
def gerar_pessoa_4devs(): pass


# ==============================================================================
# 🎨 [DESIGN] MONTAGEM HTML DA TELA DE LOGIN 
# (As cores e posições daqui são controladas pelo CSS lá em cima)
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    
    # 🎨 [DESIGN] Espaços em branco para empurrar a caixa para o meio da tela. 
    # Adicione ou remova <br> se quiser a caixa mais pra cima ou mais pra baixo.
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    
    # Monta a Estrutura da Caixa de Login
    st.markdown(f"""
        <div class="login-wrapper">
            <div class="login-topo">
                <img src="{LINK_LOGO_LOGIN}" class="login-logo-img">
                <div class="login-titulo">{TEXTO_TITULO_LOGIN}</div>
            </div>
            <div style="padding: 30px;">
    """, unsafe_allow_html=True)
    
    with st.form("login_form"):
        # ⚙️ [MOTOR] e 🎨 [DESIGN]
        # Aqui estão os inputs reais. O "placeholder" é o que muda o texto fantasma.
        user = st.text_input("Usuário", placeholder=TEXTO_DICA_USUARIO, label_visibility="collapsed")
        pwd = st.text_input("Senha", type="password", placeholder=TEXTO_DICA_SENHA, label_visibility="collapsed")
        
        # O Botão
        btn = st.form_submit_button(TEXTO_BOTAO_ENTRAR)
        
        if btn:
            with st.spinner("Autenticando na Rede Segura..."):
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
                    
    # Fecha o HTML da Caixa
    st.markdown("""
            </div>
        </div>
    """, unsafe_allow_html=True)

else:
    # ==============================================================================
    # ⚙️ [MOTOR] ÁREA INTERNA - MÓDULOS E DASHBOARD
    # (Mantendo a estrutura funcional)
    # ==============================================================================
    user_role = st.session_state['role']
    user_plan = st.session_state['plan']
    user_perms = st.session_state['perms']
    
    st.sidebar.title("🐕‍🦺 CERBERUS")
    st.sidebar.caption(f"Usuário: {st.session_state['username']}")
    
    if st.sidebar.button("SAIR DO SISTEMA"):
        st.session_state['logged_in'] = False
        st.rerun()

    menu_options = ["🛠️ PAINEL ADMIN"] + TODOS_MODULOS if user_role == 'admin' else TODOS_MODULOS if user_plan == 'GOLD' else MODULOS_SILVER if user_plan == 'SILVER' else user_perms.split(",")
    menu = st.sidebar.radio("Ferramentas:", menu_options)

    if menu == "🔔 Notificações e Atualizações":
        st.header("🔔 Central de Notificações")
        st.info("💡 **DICA DE DESIGN:** Altere as cores da interface modificando o CSS no topo do arquivo `app_policial.py`.")
        st.markdown("### 📋 Histórico")
        st.markdown("""
        <div class='cyber-box'>
            <span style='color: #38bdf8; font-weight: bold;'>[Atualização] v5.4</span> - Sistema Master de Design adicionado. Controle total de CSS desbloqueado.<br>
            <span style='color: #38bdf8; font-weight: bold;'>[Atualização] v5.3</span> - Nova interface visual de login integrada.<br>
        </div>
        """, unsafe_allow_html=True)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
        st.markdown("<div style='background-color: #451a03; border: 1px solid #b45309; padding: 10px; border-radius: 8px; color: #fbbf24;'>⚠️ STATUS: EM HOMOLOGAÇÃO DE API</div><br>", unsafe_allow_html=True)
        cpf = st.text_input("CPF do Suspeito")
        if st.button("PUXAR DOSSIÊ") and len(cpf) >= 11:
            st.success("Dados demonstrativos carregados.")
            st.markdown(f"<div class='cyber-box'><b>Nome:</b> ALVO DE TESTE<br><b>CPF:</b> {cpf}</div>", unsafe_allow_html=True)
            
    # Os demais módulos mantêm a mesma estrutura funcional do V5.3. 
    # (Encurtei aqui apenas a lógica complexa de IA dos módulos 1 ao 10 para focar no CSS/Login que você pediu. 
    # Para o seu código final na nuvem, usaremos o conteúdo do v5.3 com este novo topo de CSS).