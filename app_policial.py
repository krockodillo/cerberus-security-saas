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
st.set_page_config(page_title="🐺 CERBERUS BETA v0.3.2", layout="wide", page_icon="🛡️")

# Puxa a chave do cofre secreto do Streamlit (st.secrets) ou do ambiente (Github)
try:
    GEMINI_API_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

try:
    import PyPDF2
    import docx
    LIBS_DOC = True
except ImportError:
    LIBS_DOC = False

# ==============================================================================
# 🎨 PAINEL DE CONTROLE DE CORES (CSS)
# ==============================================================================
st.markdown("""
    <style>
    /* ========================================================
       👇 MAPA DE CORES: MUDE OS HEXADECIMAIS (#000000) ABAIXO 
       ======================================================== 
    */

    /* 1. FUNDO GERAL DA TELA PRINCIPAL */
    .stApp {
        background-color: #0c1015 !important; /* <-- TROQUE AQUI O FUNDO GERAL */
    }

    /* 2. COR DE TODO O TEXTO GERAL DA TELA PRINCIPAL */
    .stApp, .stApp p, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp label, .stMarkdown {
        color: #ffffff !important; /* <-- TROQUE AQUI A COR DO TEXTO GERAL */
    }

    /* 3. FUNDO DO MENU LATERAL (SIDEBAR) */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important; /* <-- TROQUE AQUI O FUNDO DO MENU LATERAL */
    }

    /* 4. TEXTO DO MENU LATERAL */
    [data-testid="stSidebar"], [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {
        color: #000000 !important; /* <-- TROQUE AQUI O TEXTO DO MENU LATERAL */
    }

    /* 5. FUNDO DAS CAIXAS DE FORMULÁRIO (CARDS) */
    div[data-testid="stForm"] {
        background-color: #1e293b !important; /* <-- TROQUE AQUI O FUNDO DOS FORMULÁRIOS */
        border: 2px solid #3f4a5c !important; /* <-- TROQUE AQUI A COR DA BORDA DOS FORMULÁRIOS */
        border-radius: 8px;
        padding: 20px !important;
        margin-bottom: 20px;
    }

    /* 6. CAIXAS DE DIGITAÇÃO (Inputs, Selects, TextAreas) */
    .stTextInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea {
        background-color: #0f172a !important; /* <-- TROQUE AQUI O FUNDO DA CAIXA ONDE O USUÁRIO DIGITA */
        color: #ffffff !important; /* <-- TROQUE AQUI A COR DA LETRA DIGITADA */
        border: 1px solid #475569 !important; /* <-- TROQUE AQUI A BORDA DA CAIXA DE DIGITAÇÃO */
    }

    /* 7. BOTÕES PADRÃO */
    .stButton>button, .stFormSubmitButton>button {
        background-color: #2563eb !important; /* <-- TROQUE AQUI O FUNDO DOS BOTÕES */
        color: #ffffff !important; /* <-- TROQUE AQUI A COR DO TEXTO DOS BOTÕES */
        border: none !important;
        font-weight: bold !important;
    }

    /* 8. BOTÕES AO PASSAR O MOUSE (HOVER) */
    .stButton>button:hover, .stFormSubmitButton>button:hover {
        background-color: #1d4ed8 !important; /* <-- TROQUE AQUI A COR DO BOTÃO QUANDO O MOUSE PASSA POR CIMA */
        color: #ffffff !important;
    }

    /* 9. CAIXAS DE RESPOSTA DA IA (CYBER-BOX) */
    .cyber-box { 
        background-color: #171c24; /* <-- TROQUE AQUI O FUNDO DAS CAIXAS DE TEXTO DA IA */
        border: 2px solid #38bdf8; /* <-- TROQUE AQUI A BORDA DAS CAIXAS DA IA */
        color: #ffffff;            /* <-- TROQUE AQUI A COR DO TEXTO DA IA */
        padding: 20px; 
        border-radius: 8px; 
        margin-bottom: 15px; 
    }

    /* Ocultar MainMenu e Rodapé do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
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

# Rota segura de gravação no servidor Linux
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
    pdf.set_font("Arial", size=12)
    for k, v in dados.items():
        if v:
            pdf.set_font("Arial", 'B', 12)
            pdf.write(7, f"{k.upper()}: ")
            pdf.set_font("Arial", '', 12)
            clean_v = str(v).replace('\n', ' ')
            clean_v = clean_v.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 7, txt=clean_v)
            pdf.ln(2)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, "_", ln=True, align='C')
    pdf.cell(0, 10, "DOCUMENTO OFICIAL PARA USO INTERNO / SIGILOSO", ln=True, align='C')
    return pdf.output(dest='S').encode('latin-1')

def extrair_geolocalizacao(image):
    try:
        exif = image._getexif()
        if not exif: return None, "Sem EXIF"
        gps = {}
        for t,v in exif.items():
            if ExifTags.TAGS.get(t) == "GPSInfo": gps = v; break
        if not gps: return None, "Sem GPS"
        def to_dec(dms, ref):
            res = dms[0] + (dms[1]/60.0) + (dms[2]/3600.0)
            return -res if ref in ['S','W'] else res
        lat = to_dec(gps[2], gps[1])
        lon = to_dec(gps[4], gps[3])
        return (lat, lon), "Sucesso"
    except: return None, "Erro EXIF"

# ==============================================================================
# TELA DE LOGIN
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center; color: white;'>🐕‍🦺 CERBERUS <span style='font-size: 16px; color: #38bdf8;'>BETA v0.3.2</span></h1>", unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Credencial Operacional")
            pwd = st.text_input("Chave de Acesso", type="password")
            btn = st.form_submit_button("ENTRAR NO SISTEMA", use_container_width=True)
            if btn:
                with st.spinner("Autenticando conexão segura..."):
                    u_data, msg = login_user(user, pwd)
                    if u_data:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = u_data[0]
                        st.session_state['role'] = u_data[2]
                        st.session_state['plan'] = u_data[3]
                        st.session_state['vencimento'] = u_data[4]
                        st.rerun()
                    else:
                        st.error(msg)
        if st.button("SOLICITAR ACESSO OPERACIONAL", use_container_width=True):
            st.info("Entre em contato com o comando da sua unidade.")

else:
    # ==============================================================================
    # ÁREA LOGADA - DASHBOARD E MÓDULOS
    # ==============================================================================
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
        if not GEMINI_API_KEY: st.error("Erro de Conexão: Chave API ausente no servidor.")
        u = st.file_uploader("Submeter Evidência (Imagem)", type=['jpg','png','jpeg'])
        if u and GEMINI_API_KEY and st.button("INICIAR VARREDURA"):
            with st.spinner("Decodificando armamentos e perímetro..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    prompt = "Aja como perito criminal. Conte os indivíduos e armas. Especifique os tipos de armas, calibre presumido e faça uma avaliação de risco tático do ambiente. Seja direto, técnico, estruturado em tópicos e não use emojis."
                    res = model.generate_content([prompt, Image.open(u)])
                    txt = res.text
                    st.markdown("### 📄 Relatório Operacional")
                    st.image(u, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{txt}</div>", unsafe_allow_html=True)
                    pdf_bytes = gerar_pdf_checklist("RELATORIO TACTICO VISUAL", {"Analise_Pericial": txt})
                    st.download_button("Baixar Relatório (PDF)", pdf_bytes, file_name=f"Relatorio_Armas_{int(time.time())}.pdf", mime="application/pdf")
                except Exception as e: st.error(f"Falha na análise: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Decodificação de Áudio (Whisper)")
        if not STATUS_AUDIO: st.error("Módulo de processamento de áudio offline.")
        t1, t2 = st.tabs(["📁 Arquivo Físico", "🎤 Captura de Microfone"])
        audio_up = None
        with t1: audio_up = st.file_uploader("Submeter Áudio", type=['mp3','wav', 'm4a', 'ogg'])
        with t2: audio_input = st.audio_input("Grave a evidência")
        audio_core = audio_up if audio_up else audio_input
        
        if audio_core and st.button("PROCESSAR TRANSCRIÇÃO (PT-BR)"):
            if STATUS_AUDIO:
                with st.spinner("Extraindo texto..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                        t.write(audio_core.getvalue())
                        p = t.name
                    try:
                        res = whisper_model.transcribe(p, language="pt", fp16=False)
                        os.remove(p)
                        txt = "".join([segment['text'] + "\n" for segment in res["segments"]])
                        st.markdown(f"<div class='cyber-box'>{txt}</div>", unsafe_allow_html=True)
                        pdf_bytes = gerar_pdf_checklist("DECODIFICACAO DE AUDIO", {"Conteudo_Transcrito": txt})
                        st.download_button("Baixar Transcrição (PDF)", pdf_bytes, file_name=f"Transcricao_{int(time.time())}.pdf", mime="application/pdf")
                    except Exception as e: st.error(f"Falha na decodificação: {e}")

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento e Restauração Forense")
        st.markdown("⚠️ PROTOCOLO DE CADEIA DE CUSTÓDIA: O processamento digital visa realçar evidências. A imagem original permanece inalterada nos registros.")
        u = st.file_uploader("Imagem Evidência (jpg/png)", type=['jpg','png','jpeg'])
        if u:
            img = Image.open(u)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Captura Original**")
                st.image(u, use_container_width=True)
            with c2:
                st.markdown("**Módulo de Realce**")
                with st.container():
                    st.markdown("<p style='font-weight: bold;'>Filtro de Ruído (Denoise)</p>", unsafe_allow_html=True)
                    if st.button("APLICAR FILTRO"):
                        with st.spinner("Limpando imagem..."):
                            dn = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
                            st.image(cv2.cvtColor(dn, cv2.COLOR_BGR2RGB), use_container_width=True)
                with st.container():
                    st.markdown("<p style='font-weight: bold;'>Nitidez de Bordas</p>", unsafe_allow_html=True)
                    s = st.slider("Intensidade", 1, 5, 2)
                    if st.button("AGUÇAR BORDAS"):
                        with st.spinner("Processando..."):
                            k = np.array([[0, -s, 0], [-s, 4*s+1, -s], [0, -s, 0]])
                            sh = cv2.filter2D(cv_img, -1, k)
                            st.image(cv2.cvtColor(sh, cv2.COLOR_BGR2RGB), use_container_width=True)
                with st.container():
                    st.markdown("<p style='font-weight: bold;'>Contraste Tático (CLAHE)</p>", unsafe_allow_html=True)
                    if st.button("APLICAR CLAHE"):
                        cl = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                        res = cl.apply(cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY))
                        st.image(res, use_container_width=True)

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Diagrama de Vínculos")
        st.error("🛑 MÓDULO EM MANUTENÇÃO. A integração com grafos e visualização interativa está sendo finalizada pela equipe de engenharia.")
        st.markdown("O sistema permitirá mapear conexões financeiras e telefônicas entre investigados.")

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Triagem")
        st.markdown("⚠️ ALERTA OPERACIONAL: Acesso a dados restritos registrado em log. Siga as diretrizes corporativas.")
        cpf = st.text_input("CPF do Alvo (11 dígitos)")
        if cpf and GEMINI_API_KEY and st.button("PUXAR REGISTROS"):
            if len(cpf) != 11: st.error("CPF Inválido. Digite apenas números.")
            else:
                with st.spinner("Acessando bases e estruturando dossiê..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    prompt = f"Processe a triagem para o CPF {cpf}. Forneça: 1. Nome Completo. 2. RG. 3. Filiação. 4. Últimos Endereços Conhecidos. 5. Histórico Criminal Presumido. Retorne EXATAMENTE em formato JSON."
                    try:
                        res = model.generate_content(prompt)
                        json_str = res.text.strip().replace("```json\n", "").replace("\n```", "")
                        dados = json.loads(json_str)
                        st.json(dados)
                        pdf_bytes = gerar_pdf_checklist("DOSSIE DE INTELIGENCIA", dados)
                        st.download_button("Baixar Dossiê (PDF)", pdf_bytes, file_name=f"Dossie_{cpf}.pdf", mime="application/pdf")
                    except Exception as e: st.error(f"Falha na compilação do dossiê estruturado.")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Cibernética")
        st.markdown("⚠️ PROTOCOLO DE SEGURANÇA: Todo material processado está sujeito a auditoria interna. Nível de Sigilo: CONFIDENCIAL.")
        tab1, tab2, tab3 = st.tabs(["🤖 Análise de Perfil", "📡 Rastreio IP", "🔎 Motores de Busca"])
        with tab1:
            u_p = st.file_uploader("Evidência Digital (Print)", type=['jpg','png','jpeg'])
            if u_p and st.button("ANALISAR VÍNCULOS E PERFIL"):
                with st.spinner("Extraindo metadados visuais e conexões..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    res = model.generate_content(["Analise este perfil. Identifique logotipos, símbolos de facções, padrões comportamentais e nomes visíveis. Seja técnico e objetivo.", Image.open(u_p)])
                    st.image(u_p, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
        with tab2:
            ip_in = st.text_input("Endereço IP Alvo")
            if ip_in and st.button("RASTREAR ORIGEM"):
                try:
                    res = requests.get(f"http://ip-api.com/json/{ip_in}").json()
                    if res.get("status") == "success":
                        st.success(f"📍 Localização Estimada: {ip_in} | Provedor: {res.get('isp')} | Cidade: {res.get('city')}")
                    else: st.error("Nó não encontrado ou IP mascarado.")
                except: st.error("Falha na varredura de rede.")
        with tab3:
            query = st.text_input("Alvo de Busca (Nome, Vulgo ou Organização)")
            if query and st.button("CRIAR DORKS TÁTICOS"):
                termo = urllib.parse.quote(query)
                st.markdown(f"👉 [Varredura de PDF/Processos Judiciais](https://www.google.com/search?q=%22{termo}%22+filetype:pdf+(rg+OR+cpf))")
                st.markdown(f"👉 [Varredura de Planilhas/Telefones](https://www.google.com/search?q=%22{termo}%22+filetype:xls+(fone+OR+tel))")

    elif menu == "7. Checklist Tático":
        st.header("📋 Formulários e Procedimentos (Plantão)")
        st.markdown("Protocolos padronizados para registro, atendimento e preservação da cadeia de custódia.")
        t1, t2, t3, t4 = st.tabs(["📄 Atendimento (BO)", "📄 Condução/Flagrante", "📄 Registro PM (RO)", "📄 Local de Crime"])
        with t1:
            with st.form("form_bo"):
                st.markdown("**Abertura de Ocorrência**")
                dt = st.date_input("Data do Fato")
                loc = st.text_input("Localização do Fato")
                env = st.text_area("Envolvidos (Vítima, Autor, Testemunha)")
                nar = st.text_area("Dinâmica dos Fatos")
                chk = st.multiselect("Diligências Iniciais:", ["Local Isolado", "Câmeras Verificadas", "Testemunhas Qualificadas", "Perícia Acionada"])
                if st.form_submit_button("GERAR DOCUMENTO"):
                    dados = {"Data": dt.strftime('%d/%m/%Y'), "Local": loc, "Envolvidos": env, "Dinâmica": nar, "Diligências": ", ".join(chk)}
                    pdf = gerar_pdf_checklist("BOLETIM DE OCORRENCIA", dados)
                    st.download_button("Baixar BO (PDF)", pdf, file_name="BO_Gerado.pdf", mime="application/pdf")
        with t2:
            with st.form("form_flagrante"):
                st.markdown("**Lavratura de Flagrante Delito**")
                nat = st.text_input("Natureza / Tipificação Penal")
                conduzido = st.text_input("Dados do Conduzido (Nome, RG, CPF)")
                relato_pm = st.text_area("Relato do Condutor")
                c1, c2 = st.columns(2)
                with c1: st.checkbox("Nota de Culpa Emitida")
                with c2: st.checkbox("Comunicação à Família/Advogado Realizada")
                if st.form_submit_button("GERAR DOCUMENTO"):
                    st.success("Procedimento validado para impressão.")
        with t3:
            with st.form("form_ro"):
                st.markdown("**Registro de Ocorrência - Guarnição PM**")
                vtr = st.text_input("Prefixo VTR")
                efetivo = st.text_input("Composição da GU")
                historico = st.text_area("Histórico da Ocorrência")
                if st.form_submit_button("GERAR DOCUMENTO"):
                    st.success("RO Consolidado.")
        with t4:
            with st.form("form_local"):
                st.markdown("**Atendimento de Local de Homicídio/Crime Grave**")
                st.checkbox("Perícia Técnica Acionada via CECOM?")
                st.checkbox("Corpo de Bombeiros no Local?")
                st.checkbox("Armas/Projéteis Arrecadados e Acautelados?")
                st.checkbox("Fotografias Iniciais Tiradas pelo Agente?")
                if st.form_submit_button("GERAR DOCUMENTO"):
                    st.success("Checklist de Preservação Concluído.")

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Inteligência Encoberta (Síntese de Cover)")
        st.markdown("⚠️ DIRETRIZ DE INTELIGÊNCIA: Identidades geradas exclusivamente para operações de infiltração cibernética (OSINT/HUMINT).")
        with st.form("form_persona"):
            sx = st.selectbox("Sexo Alvo", ["Homem", "Mulher", "Indiferente"])
            i_min = st.number_input("Idade Mín", 18)
            i_max = st.number_input("Idade Máx", 50)
            uf = st.selectbox("Estado de Origem", ["RJ", "SP", "MG", "ES", "RS", "PR", "SC", "BA", "PE", "CE", "DF", "GO", "MT"])
            if st.form_submit_button("CRIAR IDENTIDADE COVER"):
                # URL da API do 4devs
                url = "https://www.4devs.com.br/ferramentas_online.php"
                post_data = {
                  'acao': 'gerar_pessoa',
                  'sexo': 'H' if sx=="Homem" else 'M' if sx=="Mulher" else 'I',
                  'idade_min': i_min,
                  'idade_max': i_max,
                  'cep_estado': uf,
                  'pontuacao': 'N'
                }
                with st.spinner("Sintetizando identidade operacional..."):
                    try:
                        r = requests.post(url, data=post_data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
                        persona = r.json()[0]
                        st.markdown("### 📄 Dados de Cover Gerados")
                        st.json(persona)
                        pdf_bytes = gerar_pdf_checklist("FICHA DE INTELIGENCIA COVER", persona)
                        st.download_button("Baixar Ficha (PDF)", pdf_bytes, file_name=f"Cover_{persona.get('nome')}.pdf", mime="application/pdf")
                    except Exception as e:
                        st.error(f"Falha na comunicação com o servidor de síntese: {e}")

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Síntese Facial Fotorrealista")
        st.markdown("Geração de biometria facial sintética para avatares operacionais.")
        if not GEMINI_API_KEY: st.error("Chave API ausente no servidor.")
        with st.form("form_rosto"):
            gender = st.selectbox("Gênero", ["Masculino", "Feminino"])
            age = st.slider("Faixa Etária", 18, 70, 30)
            etnia = st.selectbox("Fenótipo Presumido", ["Pardo/Latino", "Branco", "Negro", "Asiático"])
            ratio = st.selectbox("Aspecto", ["1:1", "16:9"], index=0)
            if st.form_submit_button("SINTETIZAR ROSTO"):
                with st.spinner("Renderizando biometria facial..."):
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={GEMINI_API_KEY}"
                        headers = {'Content-Type': 'application/json'}
                        payload = {
                            "instances": [
                                {"prompt": f"Fotografia realista frontal de rosto, gênero {gender}, {age} anos de idade, fenótipo {etnia}, iluminação neutra de documento oficial, alta resolução."}
                            ],
                            "parameters": {
                                "sampleCount": 1,
                                "aspectRatio": ratio
                            }
                        }
                        response = requests.post(url, headers=headers, json=payload)
                        if response.status_code == 200:
                            img_b64 = response.json()['predictions'][0]['bytesBase64Encoded']
                            import base64
                            img_bytes = base64.b64decode(img_b64)
                            st.image(Image.open(io.BytesIO(img_bytes)), use_container_width=True)
                            st.download_button("Baixar Rosto", img_bytes, file_name=f"Rosto_{int(time.time())}.jpg", mime="image/jpeg")
                        else:
                            st.error(f"Erro da IA: {response.text}")
                    except Exception as e:
                        st.error(f"Falha de Síntese Facial: {e}")

    elif menu == "10. Inteligência Documental":
        st.header("📄 Triagem e Extração Documental")
        st.markdown("⚠️ DIRETRIZ: Documentos classificados processados em ambiente isolado.")
        if not GEMINI_API_KEY: st.error("Chave API ausente.")
        u = st.file_uploader("Documento Escaneado (Imagem)", type=['png','jpg','jpeg'])
        if u and st.button("EXTRAIR ESTRUTURAS DE INTERESSE"):
            with st.spinner("Processando OCR Inteligente..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    prompt = "Aja como analista de inteligência. Extraia deste documento: Nomes Próprios, CPFs, RGs, CNPJs, Placas de Veículos e Valores Financeiros. Apresente em formato estruturado."
                    res = model.generate_content([prompt, Image.open(u)])
                    st.image(u, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Falha na extração: {e}")

    elif menu == "11. Gestão de Operações":
        st.header("📋 Comando e Controle: Relatórios Operacionais")
        st.markdown("Painel consolidado para formulação de Relatórios de Missão, Mandados de Busca e Ordens de Operação.")
        with st.form("form_op"):
            st.markdown("**Formulário de Relatório Operacional Tático**")
            op_nome = st.text_input("Nome da Operação / Missão", placeholder="Ex: Operação Cérbero")
            op_data = st.date_input("Data de Deflagração")
            op_comandante = st.text_input("Autoridade Coordenadora / Delegado", placeholder="Nome e Matrícula")
            op_alvos = st.text_area("Alvos Prioritários (Nomes e Vínculos)", height=100)
            op_end = st.text_area("Endereços de Cumprimento de Mandados (Busca/Prisão)", height=100)
            op_resumo = st.text_area("Resumo da Dinâmica Prevista / Situação Atual", height=150)
            
            st.markdown("**Recursos Empregados**")
            c1, c2 = st.columns(2)
            with c1: op_vtr = st.number_input("Qtd. Viaturas Envolvidas", min_value=1)
            with c2: op_efetivo = st.number_input("Qtd. Efetivo Desdobrado", min_value=1)
            
            if st.form_submit_button("GERAR ORDEM DE OPERAÇÃO"):
                dados_op = {
                    "Operacao": op_nome,
                    "Data_Deflagracao": op_data.strftime('%d/%m/%Y'),
                    "Comandante": op_comandante,
                    "Alvos": op_alvos,
                    "Enderecos": op_end,
                    "Dinamica": op_resumo,
                    "Viaturas": str(op_vtr),
                    "Efetivo": str(op_efetivo)
                }
                pdf_bytes = gerar_pdf_checklist("ORDEM DE OPERACAO POLICIAL", dados_op)
                st.success("Ordem estruturada e pronta para protocolo.")
                st.download_button("Baixar Ordem (PDF)", pdf_bytes, file_name=f"Operacao_{op_nome.replace(' ', '_')}.pdf", mime="application/pdf")
