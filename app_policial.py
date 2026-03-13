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
st.set_page_config(page_title="🐕‍🦺 CERBERUS BETA v0.4.5", layout="wide", page_icon="🛡️")

# PROTOCOLO DE SEGURANÇA MÁXIMA: Puxar a chave do cofre do Streamlit
try:
    GEMINI_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    GEMINI_API_KEY = "" # A chave está no painel Secrets do Streamlit

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

DB_PATH = "cerberus_users.db"

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

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, role, plan, vencimento FROM usuarios')
    users = c.fetchall()
    conn.close()
    return users

def create_user(username, password, role, plan, vencimento):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', (username, password, role, plan, vencimento))
        conn.commit()
        conn.close()
        return True, "✅ Agente cadastrado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "❌ Erro: Este nome de usuário já existe."

def update_user_db(username, password, role, plan, vencimento):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if password: 
        c.execute('UPDATE usuarios SET password=?, role=?, plan=?, vencimento=? WHERE username=?', (password, role, plan, vencimento, username))
    else:
        c.execute('UPDATE usuarios SET role=?, plan=?, vencimento=? WHERE username=?', (role, plan, vencimento, username))
    conn.commit()
    conn.close()
    return True, "✅ Dados do agente atualizados!"

def delete_user_db(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM usuarios WHERE username=?', (username,))
    conn.commit()
    conn.close()
    return True, "🚨 Acesso do agente revogado (Excluído)."

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

def gerar_persona_offline(sexo, idade, uf, pontuacao_str):
    pontuacao = pontuacao_str == "Sim"
    if sexo == "Aleatório": sexo = random.choice(["Masculino", "Feminino"])
    n_h = ["Miguel", "Arthur", "Gael", "Théo", "Heitor", "Ravi", "Davi", "Bernardo", "Noah", "Gabriel", "Samuel", "Pedro", "Anthony", "Isaac", "Benício", "Lucas", "Matheus"]
    n_m = ["Helena", "Alice", "Laura", "Maria", "Sophia", "Manuela", "Maitê", "Isabella", "Heloísa", "Valentina", "Sarah", "Isadora", "Lívia", "Beatriz", "Ana", "Julia"]
    sobrenomes = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida"]
    primeiro = random.choice(n_h) if sexo == "Masculino" else random.choice(n_m)
    nome = f"{primeiro} {random.choice(sobrenomes)} {random.choice(sobrenomes)}"
    mae = f"{random.choice(n_m)} {random.choice(sobrenomes)} {random.choice(sobrenomes)}"
    pai = f"{random.choice(n_h)} {random.choice(sobrenomes)} {random.choice(sobrenomes)}"
    nasc = datetime.now() - timedelta(days=(idade * 365) + random.randint(1, 360))
    cpf_n = [random.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        val = sum([(len(cpf_n) + 1 - i) * v for i, v in enumerate(cpf_n)]) % 11
        cpf_n.append(11 - val if val > 1 else 0)
    c_str = ''.join(map(str, cpf_n))
    cpf_f = f"{c_str[:3]}.{c_str[3:6]}.{c_str[6:9]}-{c_str[9:]}" if pontuacao else c_str
    r_str = ''.join([str(random.randint(0,9)) for _ in range(9)])
    rg_f = f"{r_str[:2]}.{r_str[2:5]}.{r_str[5:8]}-{r_str[8:]}" if pontuacao else r_str
    cidades = {"AC": ["Rio Branco"], "AL": ["Maceió"], "AP": ["Macapá"], "AM": ["Manaus"], "BA": ["Salvador", "Feira de Santana"], "CE": ["Fortaleza"], "DF": ["Brasília"], "ES": ["Vitória", "Vila Velha"], "GO": ["Goiânia"], "MA": ["São Luís"], "MT": ["Cuiabá"], "MS": ["Campo Grande"], "MG": ["Belo Horizonte", "Uberlândia", "Contagem"], "PA": ["Belém"], "PB": ["João Pessoa"], "PR": ["Curitiba", "Londrina"], "PE": ["Recife", "Olinda"], "PI": ["Teresina"], "RJ": ["Rio de Janeiro", "Niterói", "Nova Iguaçu", "São Gonçalo"], "RN": ["Natal"], "RS": ["Porto Alegre", "Caxias do Sul"], "RO": ["Porto Velho"], "RR": ["Boa Vista"], "SC": ["Florianópolis", "Joinville"], "SP": ["São Paulo", "Campinas", "Guarulhos", "Osasco"], "SE": ["Aracaju"], "TO": ["Palmas"]}
    cidade = random.choice(cidades.get(uf, [uf]))
    cep_s = f"{random.randint(10, 99)}{random.randint(100,999)}{random.randint(100,999)}"
    cep_f = f"{cep_s[:5]}-{cep_s[5:]}" if pontuacao else cep_s
    ddd = random.randint(11, 99)
    cel_s = f"{ddd}9{random.randint(1000,9999)}{random.randint(1000,9999)}"
    cel_f = f"({ddd}) 9{cel_s[3:7]}-{cel_s[7:]}" if pontuacao else cel_s
    fixo_s = f"{ddd}3{random.randint(100,999)}{random.randint(1000,9999)}"
    fixo_f = f"({ddd}) {fixo_s[2:6]}-{fixo_s[6:]}" if pontuacao else fixo_s
    return {
        "nome": nome, "cpf": cpf_f, "rg": rg_f, "data_nasc": nasc.strftime("%d/%m/%Y"), "idade": str(idade),
        "signo": random.choice(["Áries", "Touro", "Gêmeos", "Câncer", "Leão", "Virgem", "Libra", "Escorpião", "Sagitário", "Capricórnio", "Aquário", "Peixes"]),
        "sexo": sexo, "mae": mae, "pai": pai, "cep": cep_f, "endereco": f"{random.choice(['Rua', 'Avenida'])} {random.choice(sobrenomes)}",
        "numero": str(random.randint(10, 999)), "bairro": "Centro", "cidade": cidade, "estado": uf,
        "telefone_fixo": fixo_f, "celular": cel_f, "altura": f"1.{random.randint(55, 95)}", "peso": f"{random.randint(50, 110)} kg",
        "tipo_sanguineo": random.choice(["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]), "cor": random.choice(["Branca", "Parda", "Preta"]),
        "profissao": random.choice(["Analista", "Vendedor", "Gerente", "Professor", "Autônomo"]), "renda": f"R$ {random.randint(2000, 15000)},00",
        "email": f"{primeiro.lower()}.{sobrenomes[0].lower()}@email.com", "senha": f"{primeiro.lower()}@{random.randint(100,999)}",
        "cartao_numero": f"{random.randint(4000, 5000)} {random.randint(1000, 9999)} {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
        "cartao_validade": f"0{random.randint(1,9)}/{random.randint(26, 32)}", "cartao_cvv": str(random.randint(100, 999)), "cartao_bandeira": random.choice(["Visa", "MasterCard"]),
        "veiculo_placa": f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(0,9)}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.randint(10,99)}",
        "veiculo_renavam": str(random.randint(10000000000, 99999999999)), "veiculo_chassi": f"9BW{random.randint(10000000000000, 99999999999999)}",
        "veiculo_marca_modelo": random.choice(["VW Gol", "Fiat Uno", "Chevrolet Onix", "Toyota Corolla"]), "veiculo_ano": str(random.randint(2010, 2024))
    }

# ==============================================================================
# TELA DE LOGIN E NAVEGAÇÃO
# ==============================================================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: white;'>🐕‍🦺 CERBERUS <span style='font-size: 16px; color: #38bdf8;'>BETA v0.4.5</span></h1>", unsafe_allow_html=True)
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

    menu_options = TODOS_MODULOS.copy() if user_plan == 'GOLD' else MODULOS_SILVER.copy()
    if user_role == 'admin': menu_options.append("⚙️ Gestão de Efetivo (Admin)")

    menu = st.sidebar.radio("Módulos de Inteligência:", menu_options)

    # --------------------------------------------------------------------------
    # MÓDULOS DE ADMINISTRAÇÃO E INTELIGÊNCIA
    # --------------------------------------------------------------------------
    if menu == "⚙️ Gestão de Efetivo (Admin)":
        st.header("⚙️ Centro de Comando (Gestão de Agentes)")
        t_lista, t_novo, t_edita = st.tabs(["📋 Efetivo Ativo", "➕ Cadastrar Agente", "✏️ Editar/Remover Agente"])
        with t_lista:
            usuarios = get_all_users()
            if usuarios: st.dataframe(pd.DataFrame(usuarios, columns=["Credencial", "Cargo", "Plano", "Vencimento"]), use_container_width=True, hide_index=True)
        with t_novo:
            with st.form("form_novo_agente"):
                n_user = st.text_input("Credencial")
                n_pwd = st.text_input("Chave", type="password")
                c1, c2 = st.columns(2)
                with c1: n_role = st.selectbox("Nível", ["user", "admin"])
                with c2: n_plan = st.selectbox("Plano", ["GOLD", "SILVER"])
                n_venc = st.date_input("Vencimento", value=datetime.now() + timedelta(days=365))
                if st.form_submit_button("CADASTRAR", type="primary"):
                    if n_user and n_pwd:
                        suc, msg = create_user(n_user, n_pwd, n_role, n_plan, n_venc.strftime('%Y-%m-%d'))
                        if suc: st.success(msg)
                        else: st.error(msg)
        with t_edita:
            usuarios_lista = [u[0] for u in get_all_users()]
            if usuarios_lista:
                alvo = st.selectbox("Agente Alvo", usuarios_lista)
                with st.form("form_edita_agente"):
                    e_pwd = st.text_input("Nova Chave (Branco para manter)", type="password")
                    c3, c4 = st.columns(2)
                    with c3: e_role = st.selectbox("Novo Nível", ["user", "admin"])
                    with c4: e_plan = st.selectbox("Novo Plano", ["GOLD", "SILVER"])
                    e_venc = st.date_input("Novo Vencimento", value=datetime.now() + timedelta(days=365))
                    b1, b2 = st.columns(2)
                    with b1: btn_att = st.form_submit_button("ATUALIZAR", type="primary")
                    with b2: btn_del = st.form_submit_button("REVOGAR")
                    if btn_att:
                        suc, msg = update_user_db(alvo, e_pwd, e_role, e_plan, e_venc.strftime('%Y-%m-%d'))
                        if suc: st.success(msg)
                    if btn_del:
                        if alvo == 'leandro': st.error("Ação Bloqueada para o Comandante.")
                        else:
                            suc, msg = delete_user_db(alvo)
                            if suc: st.success(msg)

    elif menu == "1. Detecção de Armas":
        st.header("🔫 Análise de Armamento e Tática Visual")
        u = st.file_uploader("Submeter Evidência (Imagem)", type=['jpg','png','jpeg'])
        if u and st.button("INICIAR VARREDURA"):
            if not GEMINI_API_KEY: st.error("Erro: Chave API ausente no cofre (Secrets).")
            else:
                with st.spinner("Decodificando armamentos e perímetro..."):
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        model = genai.GenerativeModel('gemini-1.5-flash-latest')
                        res = model.generate_content(["Aja como perito criminal. Conte indivíduos e armas. Faça avaliação de risco tático. Seja direto e estruturado.", Image.open(u)])
                        st.image(u, use_container_width=True)
                        st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
                    except Exception as e: st.error(f"Falha na análise: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Decodificação de Áudio (Whisper)")
        if not STATUS_AUDIO:
            st.error("🛑 Módulo Whisper offline. Dependência ffmpeg ausente no servidor.")
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
            if not GEMINI_API_KEY: st.error("Erro: Chave API ausente no cofre.")
            else:
                with st.spinner("Acessando bases..."):
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    try:
                        res = model.generate_content(f"Gere um JSON simulando Dossiê para o CPF {cpf}: Nome, RG, Filiação, Endereços, Histórico. JSON PURO.")
                        json_str = res.text.strip().replace("`" * 3 + "json", "").replace("`" * 3, "").strip()
                        st.json(json.loads(json_str))
                    except Exception as e: st.error(f"Falha estrutural: {e}")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Cibernética")
        tab1, tab2, tab3 = st.tabs(["🤖 Análise de Perfil", "📡 Rastreio IP", "🔎 Motores de Busca"])
        with tab1:
            u_p = st.file_uploader("Evidência Digital", type=['jpg','png','jpeg'])
            if u_p and st.button("ANALISAR PERFIL"):
                if not GEMINI_API_KEY: st.error("Erro: Chave API ausente.")
                else:
                    genai.configure(api_key=GEMINI_API_KEY)
                    res = genai.GenerativeModel('gemini-1.5-flash-latest').generate_content(["Analise este perfil. Identifique logotipos, facções, nomes visíveis.", Image.open(u_p)])
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
        with tab2:
            ip_in = st.text_input("Endereço IP Alvo")
            if ip_in and st.button("RASTREAR ORIGEM"):
                try: 
                    # CORREÇÃO CRÍTICA: Removida a formatação de link que quebrava o requests
                    url_limpa = f"http://ip-api.com/json/{ip_in}"
                    resultado_ip = requests.get(url_limpa).json()
                    st.success(f"📍 {ip_in} | {resultado_ip.get('isp')} | {resultado_ip.get('city')}")
                except Exception as e: 
                    st.error(f"Falha na varredura: {e}")

    elif menu == "7. Checklist Tático":
        st.header("📋 Formulários e Procedimentos Operacionais")
        st.markdown("Protocolos padronizados para registro, atendimento e preservação da cadeia de custódia.")
        
        t1, t2, t3, t4 = st.tabs(["📄 Atendimento (BO / RO)", "📄 Condução/Flagrante", "📄 Registro PM (RO)", "📄 Local de Crime"])
        
        with t1:
            with st.form("form_bo"):
                st.markdown("**Abertura de Ocorrência (BO/RO)**")
                dt = st.date_input("Data do Fato", key="dt_bo")
                loc = st.text_input("Localização do Fato", key="loc_bo")
                env = st.text_area("Envolvidos (Vítima, Autor, Testemunhas com CPF/RG)")
                nar = st.text_area("Dinâmica dos Fatos (Relato Histórico)")
                chk = st.multiselect("Diligências Iniciais Realizadas:", ["Local Isolado", "Câmeras Verificadas", "Testemunhas Qualificadas", "Perícia Acionada", "Prisão Realizada"])
                btn_bo = st.form_submit_button("GERAR DOCUMENTO (BO)", type="primary")
            
            if btn_bo:
                dados = {"Documento": "BOLETIM DE OCORRENCIA", "Data": dt.strftime('%d/%m/%Y'), "Local": loc, "Envolvidos": env, "Dinâmica": nar, "Diligências": ", ".join(chk)}
                st.session_state['pdf_bo'] = gerar_pdf_checklist("BOLETIM DE OCORRENCIA", dados)
            
            if 'pdf_bo' in st.session_state:
                st.success("✅ Boletim de Ocorrência gerado.")
                st.download_button("BAIXAR BO (PDF)", st.session_state['pdf_bo'], file_name="BO_Gerado.pdf", mime="application/pdf")

        with t2:
            with st.form("form_flagrante"):
                st.markdown("**Lavratura de Flagrante Delito (PC/PF)**")
                dt_f = st.date_input("Data da Condução", key="dt_fl")
                nat = st.text_input("Natureza / Tipificação Penal (Artigo)")
                conduzido = st.text_area("Dados do Conduzido (Nome Completo, RG, CPF, Filiação)")
                relato_pm = st.text_area("Relato do Condutor (Agente que realizou a prisão)")
                c1, c2 = st.columns(2)
                with c1: 
                    ch1 = st.checkbox("Nota de Culpa Emitida e Assinada?")
                    ch2 = st.checkbox("Comunicação à Família / Advogado Realizada?")
                with c2:
                    ch3 = st.checkbox("Exame de Corpo de Delito (IML) Requisitado/Realizado?")
                    ch4 = st.checkbox("Material/Armas Apreendidas Relacionadas?")
                btn_fl = st.form_submit_button("GERAR DOCUMENTO (FLAGRANTE)", type="primary")

            if btn_fl:
                dados = {"Documento": "AUTO DE PRISAO EM FLAGRANTE", "Data": dt_f.strftime('%d/%m/%Y'), "Tipificacao": nat, "Conduzido": conduzido, "Relato Condutor": relato_pm, "Nota Culpa": str(ch1), "Aviso Familia": str(ch2), "IML": str(ch3), "Material Apreendido": str(ch4)}
                st.session_state['pdf_fl'] = gerar_pdf_checklist("AUTO DE FLAGRANTE", dados)

            if 'pdf_fl' in st.session_state:
                st.success("✅ Auto de Prisão gerado.")
                st.download_button("BAIXAR FLAGRANTE (PDF)", st.session_state['pdf_fl'], file_name="Flagrante.pdf", mime="application/pdf")

        with t3:
            with st.form("form_ro"):
                st.markdown("**Registro de Ocorrência (Policiamento Ostensivo)**")
                num_ro = st.text_input("Número do RO / BOPM")
                vtr = st.text_input("Prefixo VTR")
                efetivo = st.text_input("Composição da GU (Ex: CB Silva, SD Oliveira)")
                historico = st.text_area("Histórico Detalhado da Ocorrência")
                conclusao = st.text_area("Conclusão / Encaminhamento (Ex: Encaminhado à 1ª DP)")
                btn_ro = st.form_submit_button("GERAR DOCUMENTO (RO)", type="primary")

            if btn_ro:
                dados = {"Documento": "REGISTRO DE OCORRENCIA", "Numero": num_ro, "Viatura": vtr, "Efetivo": efetivo, "Historico": historico, "Conclusao": conclusao}
                st.session_state['pdf_ro'] = gerar_pdf_checklist("REGISTRO DE OCORRENCIA", dados)

            if 'pdf_ro' in st.session_state:
                st.success("✅ Registro Policial gerado.")
                st.download_button("BAIXAR RO (PDF)", st.session_state['pdf_ro'], file_name="RO.pdf", mime="application/pdf")

        with t4:
            with st.form("form_local"):
                st.markdown("**Atendimento de Local de Homicídio/Crime Grave**")
                dt_l = st.date_input("Data do Acionamento", key="dt_lc")
                ender = st.text_input("Endereço Exato do Local de Crime")
                ch_l1 = st.checkbox("Local Isola e Preservado adequadamente?")
                ch_l2 = st.checkbox("Perícia Técnica Acionada via Centro de Comando?")
                ch_l3 = st.checkbox("Corpo de Bombeiros / SAMU compareceu ao local?")
                ch_l4 = st.checkbox("Armas/Estojos/Projéteis Arrecadados e Acautelados?")
                ch_l5 = st.checkbox("Fotografias Iniciais Tiradas pela Primeira GU?")
                btn_lc = st.form_submit_button("GERAR DOCUMENTO (LOCAL DE CRIME)", type="primary")

            if btn_lc:
                dados = {"Documento": "RELATORIO DE LOCAL DE CRIME", "Data": dt_l.strftime('%d/%m/%Y'), "Endereco": ender, "Local Isolado": str(ch_l1), "Pericia Acionada": str(ch_l2), "Bombeiros": str(ch_l3), "Vestigios Arrecadados": str(ch_l4), "Fotografias": str(ch_l5)}
                st.session_state['pdf_lc'] = gerar_pdf_checklist("LOCAL DE CRIME", dados)

            if 'pdf_lc' in st.session_state:
                st.success("✅ Relatório de Local gerado.")
                st.download_button("BAIXAR RELATÓRIO (PDF)", st.session_state['pdf_lc'], file_name="LocalCrime.pdf", mime="application/pdf")

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Gerador de Pessoas (Identidade Cover)")
        st.markdown("⚠️ DIRETRIZ: Geração avançada **100% OFFLINE** e sem APIs externas.")
        
        with st.form("form_persona"):
            st.markdown("### ⚙️ Parâmetros de Geração")
            c1, c2 = st.columns(2)
            with c1:
                sx = st.radio("Sexo", ["Masculino", "Feminino", "Aleatório"], horizontal=True)
                idade = st.slider("Idade do Alvo", 18, 80, 30)
            with c2:
                uf = st.selectbox("Estado (UF)", ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"])
                pontuacao = st.radio("Pontuação", ["Sim", "Não"], horizontal=True)

            if st.form_submit_button("GERAR PESSOA", type="primary"):
                with st.spinner("Sintetizando Dados Matematicamente..."):
                    st.session_state['persona'] = gerar_persona_offline(sx, idade, uf, pontuacao)

        if 'persona' in st.session_state:
            p = st.session_state['persona']
            st.success("✅ Identidade Cover sintetizada.")
            
            c1, c2, c3 = st.columns(3)
            c1.text_input("Nome", p.get('nome',''))
            c2.text_input("CPF", p.get('cpf',''))
            c3.text_input("RG", p.get('rg',''))
            c4, c5, c6, c7 = st.columns(4)
            c4.text_input("Data de Nascimento", p.get('data_nasc',''))
            c5.text_input("Idade", str(p.get('idade','')))
            c6.text_input("Signo", p.get('signo',''))
            c7.text_input("Sexo", p.get('sexo',''))
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button("BAIXAR DOSSIÊ COMPLETO (PDF)", gerar_pdf_checklist("FICHA DE INTELIGENCIA COVER", p), file_name=f"Cover_{p.get('nome').replace(' ', '_')}.pdf", mime="application/pdf", type="primary")

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Síntese Facial Fotorrealista")
        st.markdown("Criação de avatares táticos com controle preciso de vestimenta e ambiente.")

        with st.form("form_rosto"):
            col1, col2 = st.columns(2)
            with col1:
                gender = st.selectbox("Gênero", ["Masculino", "Feminino"])
                age = st.slider("Idade Aproximada", 18, 70, 30)
                etnia = st.selectbox("Fenótipo Presumido", ["Pardo/Latino", "Branco", "Negro", "Asiático"])
            with col2:
                tipo = st.selectbox("Tipo de Enquadramento", ["Somente rosto", "Meio corpo", "Corpo inteiro"])
                roupa = st.selectbox("Tipo de Roupa", ["Casual", "Social", "Esportivo", "Tático militar", "Moletom com capuz escuro"])
                local = st.selectbox("Ambiente", ["Fundo neutro liso", "Rua urbana movimentada", "Viela escura", "Escritório", "Fundo de fotografia policial"])
            ratio = st.selectbox("Formato da Imagem", ["1:1", "4:3", "16:9"], index=0)

            gerar = st.form_submit_button("SINTETIZAR AVATAR", type="primary")

        if gerar:
            if not GEMINI_API_KEY:
                st.error("Erro: Chave API ausente no cofre (Secrets).")
            else:
                with st.spinner("Acionando rede neural de renderização (Imagen 3)..."):
                    try:
                        prompt = f"Fotografia hiper-realista. Gênero: {gender}, Idade: {age} anos, Fenótipo: {etnia}. Enquadramento: {tipo}. Vestimenta: {roupa}. Ambiente: {local}. Iluminação dramática e realista, alta definição 8k, textura de pele natural, estilo fotográfico profissional, sem distorções."
                        
                        # CORREÇÃO CRÍTICA: Removida a formatação de link [https...] que causava o Invalid URL
                        url_limpa = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={GEMINI_API_KEY}"
                        
                        payload = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1, "aspectRatio": ratio}}
                        response = requests.post(url_limpa, headers={"Content-Type": "application/json"}, json=payload)

                        if response.status_code == 200:
                            img_b64 = response.json()["predictions"][0]["bytesBase64Encoded"]
                            st.session_state['avatar_bytes'] = base64.b64decode(img_b64)
                        elif response.status_code == 403:
                            st.error("Erro 403: A sua Chave API foi bloqueada pela Google ou não tem permissão de geração.")
                        elif response.status_code == 429:
                            st.error("Erro 429: Cota de geração excedida. Aguarde.")
                        else:
                            st.error(f"Erro na API da Google: Código {response.status_code}")

                    except Exception as e:
                        st.error(f"Falha de comunicação: {e}")

        if 'avatar_bytes' in st.session_state:
            st.success("✅ Avatar tático sintetizado com sucesso.")
            st.image(Image.open(io.BytesIO(st.session_state['avatar_bytes'])), use_container_width=True)
            st.download_button("BAIXAR FOTOGRAFIA", st.session_state['avatar_bytes'], file_name=f"Avatar_{int(time.time())}.jpg", mime="image/jpeg", type="primary")

    elif menu == "10. Inteligência Documental":
        st.header("📄 Triagem Documental")
        u = st.file_uploader("Documento Escaneado (Imagem)", type=['png','jpg','jpeg'])
        if u and st.button("EXTRAIR ESTRUTURAS"):
            if not GEMINI_API_KEY: st.error("Erro: Chave API ausente no cofre.")
            else:
                genai.configure(api_key=GEMINI_API_KEY)
                res = genai.GenerativeModel('gemini-1.5-flash-latest').generate_content(["Extraia Nomes, CPFs, RGs, CNPJs, Placas.", Image.open(u)])
                st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)

    elif menu == "11. Gestão de Operações":
        st.header("📋 Comando e Controle (Ordem de Operações)")
        with st.form("form_op"):
            op_nome = st.text_input("Nome da Operação / Missão (Ex: Operação Cérbero)")
            op_data = st.date_input("Data Prevista de Deflagração")
            op_comandante = st.text_input("Autoridade Coordenadora / Delegado Responsável")
            op_alvos = st.text_area("Alvos Prioritários (Nomes, Vulgos e Vínculos)", height=100)
            op_end = st.text_area("Endereços Alvo para Cumprimento de Mandados (Busca/Prisão)", height=100)
            op_resumo = st.text_area("Resumo da Dinâmica Prevista e Ações Táticas", height=150)
            c1, c2 = st.columns(2)
            with c1: op_vtr = st.number_input("Qtd. de Viaturas Alocadas", min_value=1)
            with c2: op_efetivo = st.number_input("Qtd. de Efetivo Desdobrado", min_value=1)
            
            submit_op = st.form_submit_button("GERAR ORDEM DE OPERAÇÃO", type="primary")

        if submit_op:
            dados_op = {
                "Operacao": op_nome, "Data_Deflagracao": op_data.strftime('%d/%m/%Y'),
                "Comandante": op_comandante, "Alvos": op_alvos, "Enderecos": op_end,
                "Dinamica": op_resumo, "Viaturas": str(op_vtr), "Efetivo": str(op_efetivo)
            }
            st.session_state['pdf_op'] = gerar_pdf_checklist("ORDEM DE OPERACAO POLICIAL", dados_op)

        if 'pdf_op' in st.session_state:
            st.success("✅ Ordem estruturada com sucesso e pronta para protocolo.")
            st.download_button("BAIXAR PLANO DE OPERAÇÃO (PDF)", st.session_state['pdf_op'], file_name=f"Operacao_{int(time.time())}.pdf", mime="application/pdf", type="primary")
