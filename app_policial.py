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

# Bibliotecas para leitura de documentos
try:
    import PyPDF2
    import docx
    LIBS_DOC = True
except ImportError:
    LIBS_DOC = False

# ==================================================
# CONFIGURAÇÃO GERAL E CHAVES MESTRAS
# ==================================================
st.set_page_config(page_title="CERBERUS v5.0 - SaaS Intel", layout="wide", page_icon="🐕‍🦺")

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
    "9. Gerador de Rosto (IA Avançada)",
    "10. Inteligência Documental"
]

# Definição do Plano SILVER (Fixo)
MODULOS_SILVER = [
    "1. Detecção de Armas",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "9. Gerador de Rosto (IA Avançada)",
    "10. Inteligência Documental"
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
    except Exception as e:
        print("Erro no grafo:", e)
        return False

def extrair_texto_arquivo(uploaded_file):
    if not LIBS_DOC: return "Bibliotecas de documento não instaladas. Use apenas Imagens."
    nome = uploaded_file.name.lower()
    try:
        if nome.endswith('.pdf'):
            leitor = PyPDF2.PdfReader(uploaded_file)
            return "\n".join([p.extract_text() for p in leitor.pages if p.extract_text()])
        elif nome.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        elif nome.endswith('.txt'):
            return uploaded_file.getvalue().decode("utf-8")
        elif nome.endswith(('.xlsx', '.xls', '.csv')):
            df = pd.read_excel(uploaded_file) if 'xls' in nome else pd.read_csv(uploaded_file)
            return df.to_string()
        else: return None
    except Exception as e: return f"Erro na leitura: {e}"

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
                else: st.error(msg)
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
    if st.sidebar.button("SAIR"): st.session_state['logged_in'] = False; st.rerun()

    menu_options = ["🛠️ PAINEL ADMIN"] + TODOS_MODULOS if user_role == 'admin' else TODOS_MODULOS if user_plan == 'GOLD' else MODULOS_SILVER if user_plan == 'SILVER' else user_perms.split(",")
    menu = st.sidebar.radio("Ferramentas:", menu_options)

    # ==================================================
    # 🔌 MÓDULOS DO SISTEMA
    # ==================================================
    if menu == "🛠️ PAINEL ADMIN":
        st.title("🛠️ Gestão")
        # Mantido o admin simplificado para foco na nova ferramenta
        st.info("Painel de Administração ativo.")

    elif menu == "1. Detecção de Armas":
        st.header("🔫 Análise Tática e Identificação de Armamento")
        u = st.file_uploader("Carregar Evidência (Imagem)", type=['jpg','png', 'jpeg'])
        if u and st.button("INICIAR VARREDURA TÁTICA", type="primary"):
            with st.spinner("Analisando..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    response = client.models.generate_content(model='gemini-2.5-flash', contents=["Descreva pessoas e armas nesta foto de forma técnica militar.", Image.open(u)])
                    st.markdown(f"<div class='cyber-box'>{response.text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Erro: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática")
        a_up = st.file_uploader("Carregar Áudio", type=['mp3','wav', 'm4a', 'ogg'])
        if a_up and STATUS_AUDIO and st.button("TRANSCREVER"):
            with st.spinner("Decodificando áudio..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                    t.write(a_up.getvalue()); p = t.name
                r = whisper_model.transcribe(p); os.remove(p)
                st.markdown(f"<div class='cyber-box'>{''.join([s['text'] + '<br>' for s in r['segments']])}</div>", unsafe_allow_html=True)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
        st.markdown("<div style='background-color: #451a03; border: 1px solid #b45309; padding: 10px; border-radius: 8px;'><span class='badge-warning'>⚠️ STATUS: EM HOMOLOGAÇÃO DE API</span></div><br>", unsafe_allow_html=True)
        cpf = st.text_input("CPF")
        if st.button("BUSCAR") and len(cpf) >= 11:
            with st.spinner("Buscando..."): time.sleep(1)
            st.success("Dados demonstrativos carregados.")
            st.markdown(f"<div class='cyber-box'><b>Nome:</b> JOHN DOE<br><b>CPF:</b> {cpf}</div>", unsafe_allow_html=True)

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        tab_ia, tab_ip = st.tabs(["🤖 IA Forense", "📡 Rastreador de IP"])
        with tab_ip:
            ip = st.text_input("IP Alvo")
            if st.button("RASTREAR") and ip:
                res = requests.get(f"http://ip-api.com/json/{ip}?lang=pt-BR").json()
                if res.get('status') == 'success': st.success(f"Cidade: {res['city']} | ISP: {res['isp']}")

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover")
        if st.button("GERAR"): st.info("Motor Nano Banana 2 pronto para geração.")

    # --- NOVO MÓDULO 10: INTELIGÊNCIA DOCUMENTAL E VÍNCULOS ---
    elif menu == "10. Inteligência Documental":
        st.header("📄 Análise de Vínculos e Extração Tática")
        st.markdown("""
        <div class='cyber-box' style='border-color: #eab308; background-color: #1a1a1a;'>
            <h4 style='color: #eab308; margin-top:0;'>ANÁLISE DE VÍNCULOS</h4>
            Envie documentos (PDF, DOCX, Excel) ou Imagens (JPG/PNG). A IA irá ler o conteúdo e gerar um gráfico interativo de conexões entre Pessoas, Empresas e Locais.
        </div>
        """, unsafe_allow_html=True)

        if not LIBS_DOC:
            st.error("⚠️ As bibliotecas PyPDF2 e python-docx não foram encontradas. A extração de PDF/Word está inativa.")

        with st.form("form_doc"):
            arq_doc = st.file_uploader("Carregar Evidência (Suporta: PDF, DOCX, TXT, CSV, XLSX, JPG, PNG)", type=['pdf', 'docx', 'txt', 'csv', 'xlsx', 'jpg', 'png', 'jpeg'])
            
            tipo_agente = st.selectbox("TIPO DE ANÁLISE (SELECIONE O AGENTE)", [
                "🔎 INVESTIGAÇÃO GENÉRICA (Vínculos Padrão)",
                "📞 SIGINT: QUEBRA TELEMÁTICA / ERBs",
                "🌐 OSINT: REDES SOCIAIS E NUVEM",
                "🌍 GEOINT: PADRÃO DE VIDA E ROTAS",
                "🤔 SCAN: ANÁLISE DE VERACIDADE E DISCURSO",
                "💰 FININT: LAVAGEM DE DINHEIRO (RIF V2)"
            ])
            
            btn_doc = st.form_submit_button("PROCESSAR INTELIGÊNCIA DOCUMENTAL", type="primary")

        if btn_doc and arq_doc:
            with st.spinner(f"Acionando Agente Analítico: {tipo_agente.split(':')[0]}..."):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    
                    # Preparar o conteúdo para a IA
                    conteudo_envio = []
                    
                    if arq_doc.name.lower().endswith(('.jpg', '.jpeg', '.png')):
                        img_doc = Image.open(arq_doc)
                        conteudo_envio.append(img_doc)
                        st.image(img_doc, caption="Evidência Visual", width=300)
                    else:
                        texto_extraido = extrair_texto_arquivo(arq_doc)
                        if not texto_extraido or "Erro" in texto_extraido:
                            st.error(f"Falha ao ler o documento: {texto_extraido}")
                            st.stop()
                        conteudo_envio.append(f"CONTEÚDO DO DOCUMENTO:\n{texto_extraido[:15000]}") # Limite seguro para API
                    
                    # Prompt mestre instruindo a IA a gerar análise e um JSON estrito para o Grafo
                    prompt_doc = f"""
                    Você é um Analista Chefe de Inteligência Policial focado em: {tipo_agente}.
                    Analise os dados fornecidos e entregue a resposta EXATAMENTE nestas duas partes:
                    
                    PARTE 1: RELATÓRIO ANALÍTICO
                    Escreva um resumo de inteligência (máximo 3 parágrafos) focado no escopo do seu agente ({tipo_agente.split(':')[0]}). Destaque os principais alvos, endereços, empresas ou anomalias financeiras/comportamentais encontradas.
                    
                    PARTE 2: GRAFO DE VÍNCULOS (JSON)
                    Logo abaixo do relatório, você DEVE retornar um bloco de código JSON válido contendo os nós e arestas detectados no documento. 
                    - 'nodes' devem ter: "id" (nome curto), "label" (nome exibido), "group" (escolha entre "Pessoa", "Empresa", "Local", "Telefone", "Conta").
                    - 'edges' devem ter: "from" (id de origem), "to" (id de destino), "label" (qual a relação, ex: "Sócio de", "Mora em", "Transferiu para").
                    
                    Siga este formato exato para a PARTE 2:
                    ```json
                    {{
                      "nodes": [
                        {{"id": "João", "label": "João Silva", "group": "Pessoa"}},
                        {{"id": "EmpresaX", "label": "Loja X", "group": "Empresa"}}
                      ],
                      "edges": [
                        {{"from": "João", "to": "EmpresaX", "label": "Dono"}}
                      ]
                    }}
                    ```
                    """
                    conteudo_envio.insert(0, prompt_doc)
                    
                    resposta = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=conteudo_envio
                    )
                    
                    # Separar texto e JSON
                    texto_resposta = resposta.text
                    bloco_json = re.search(r'```json\n(.*?)\n```', texto_resposta, re.DOTALL)
                    
                    relatorio = texto_resposta
                    if bloco_json:
                        relatorio = texto_resposta.replace(bloco_json.group(0), "")
                        
                    st.markdown("### 📋 Dossiê Analítico do Agente")
                    st.markdown(f"<div class='cyber-box'>{relatorio.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                    
                    # Renderizar Grafo
                    if bloco_json:
                        st.markdown("### 🕸️ Matriz de Vínculos Gerada")
                        dados_json = json.loads(bloco_json.group(1))
                        sucesso_grafo = gerar_mapa_vinculos_json(dados_json)
                        
                        if sucesso_grafo and os.path.exists("grafo_inteligencia.html"):
                            with open("grafo_inteligencia.html", 'r', encoding='utf-8') as f:
                                components.html(f.read(), height=500)
                    else:
                        st.warning("⚠️ O documento não continha vínculos claros suficientes para gerar o mapa visual.")
                        
                except Exception as e:
                    st.error(f"Erro na análise de inteligência: {e}")