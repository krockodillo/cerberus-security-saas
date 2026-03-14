import streamlit as st
import cv2
import numpy as np
from PIL import Image
import os
import requests
import io
import time
import json
import whisper
import tempfile
from fpdf import FPDF
from datetime import datetime, timedelta
import random
import sqlite3
import pandas as pd
import urllib.parse
import google.generativeai as genai
import base64

# ==============================================================================
# ⚙️ CONFIGURAÇÃO INICIAL E SEGURANÇA
# ==============================================================================
st.set_page_config(page_title="🐕‍🦺 CERBERUS BETA v0.5.1", layout="wide", page_icon="🛡️")

# Puxar a chave do cofre (Secrets) do Streamlit
try:
    GEMINI_API_KEY = st.secrets["GOOGLE_API_KEY"]
except Exception:
    GEMINI_API_KEY = "" 

# ==============================================================================
# 🎨 UI / UX - ESTÉTICA MILITAR E CYBERPUNK
# ==============================================================================
st.markdown("""
    <style>
    .stApp {background-color: #0c1015 !important;}
    .stApp, .stApp p, .stApp span, .stApp h1, .stApp h2, .stApp h3, .stApp label, .stMarkdown {color: #ffffff !important;}
    [data-testid="stSidebar"] {background-color: #111827 !important;}
    div[data-testid="stForm"] {
        background-color: #1e293b !important; border: 2px solid #3f4a5c !important; border-radius: 8px; padding: 20px !important; margin-bottom: 20px;
    }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div>div {
        background-color: #0f172a !important; color: #ffffff !important; border: 1px solid #475569 !important;
    }
    .stButton>button, .stFormSubmitButton>button {
        background-color: #2563eb !important; color: #ffffff !important; font-weight: bold !important; width: 100%; border: none !important;
    }
    .cyber-box { background-color: #171c24; border: 2px solid #38bdf8; color: #ffffff; padding: 20px; border-radius: 8px; margin-bottom: 15px;}
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    div.row-widget.stRadio > div {flex-direction: row;}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# ⚙️ GESTÃO DE BANCO DE DADOS (SQLITE EM /TMP)
# ==============================================================================
DB_PATH = "/tmp/cerberus_v11_master.db"

def get_db_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY, password TEXT, role TEXT, plan TEXT, vencimento TEXT)''')
        c.execute('INSERT OR IGNORE INTO usuarios VALUES (?,?,?,?,?)', 
                  ('leandro', '239546Dl', 'admin', 'GOLD', '2099-12-31'))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Erro de Banco: {e}")

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

init_db()

# ==============================================================================
# 🛠️ MOTORES DE IA E FUNÇÕES AUXILIARES
# ==============================================================================
@st.cache_resource
def carregar_whisper():
    try: return whisper.load_model("tiny")
    except: return None

whisper_model = carregar_whisper()
STATUS_AUDIO = whisper_model is not None

def gerar_pdf(titulo, dados):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"CERBERUS - {titulo.upper()}", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=10)
    for k, v in dados.items():
        if v:
            pdf.set_font("Arial", 'B', 10)
            pdf.write(7, f"{str(k).upper().replace('_', ' ')}: ")
            pdf.set_font("Arial", '', 10)
            pdf.multi_cell(0, 7, txt=str(v).encode('latin-1', 'replace').decode('latin-1'))
            pdf.ln(1)
    return pdf.output(dest='S').encode('latin-1')

def gerar_persona_offline(sexo, idade, uf, pontuacao_str):
    pontuacao = pontuacao_str == "Sim"
    if sexo == "Aleatório": sexo = random.choice(["Masculino", "Feminino"])
    n_h = ["Miguel", "Arthur", "Gael", "Théo", "Heitor", "Ravi", "Davi", "Bernardo"]
    n_m = ["Helena", "Alice", "Laura", "Maria", "Sophia", "Manuela", "Maitê", "Isabella"]
    sobrenomes = ["Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira"]
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
    ddd = random.randint(11, 99)
    cel_f = f"({ddd}) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}" if pontuacao else f"{ddd}9{random.randint(10000000,99999999)}"
    return {
        "nome": nome, "cpf": cpf_f, "rg": rg_f, "data_nasc": nasc.strftime("%d/%m/%Y"), "idade": str(idade),
        "sexo": sexo, "mae": mae, "pai": pai, "cidade": "Capital", "estado": uf,
        "celular": cel_f, "profissao": random.choice(["Vendedor", "Analista", "Autônomo", "Motorista"]),
        "tipo_sanguineo": random.choice(["A+", "O+", "B-", "AB+"]), "email": f"{primeiro.lower()}@provedor.com.br"
    }

# ==============================================================================
# 🚪 CONTROLE DE ACESSO
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>🐕‍🦺 CERBERUS <span style='font-size:18px; color:#38bdf8;'>BETA</span></h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color:#94a3b8;'>SISTEMA DE INTELIGÊNCIA E OPERAÇÕES TÁTICAS</p>", unsafe_allow_html=True)
        with st.form("login_form"):
            user_input = st.text_input("Credencial Operacional")
            pass_input = st.text_input("Chave de Acesso", type="password")
            if st.form_submit_button("AUTENTICAR CONEXÃO"):
                user_data, msg = login_user(user_input, pass_input)
                if user_data:
                    st.session_state['logged_in'] = True
                    st.session_state['user'] = user_data[0]
                    st.session_state['role'] = user_data[1]
                    st.session_state['plan'] = user_data[2]
                    st.rerun()
                else: st.error(msg)
else:
    # --- ÁREA OPERACIONAL ---
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

    # Filtro de Módulos por Plano
    TODOS_MODULOS = [
        "1. Detecção de Armas", "2. Transcrição de Áudio", "3. Visão Forense",
        "4. Mapa de Vínculos", "5. Investigação CPF", "6. Cyber OSINT & Forense",
        "7. Checklist Tático", "8. Gerador de Persona (Cover)",
        "9. Gerador de Rosto (IA Avançada)", "10. Inteligência Documental", "11. Gestão de Operações"
    ]
    MODULOS_SILVER = [
        "1. Detecção de Armas", "5. Investigação CPF", "6. Cyber OSINT & Forense",
        "7. Checklist Tático", "8. Gerador de Persona (Cover)", "10. Inteligência Documental", "11. Gestão de Operações"
    ]
    
    opcoes = TODOS_MODULOS if u_plan == "GOLD" else MODULOS_SILVER
    if u_role == "admin": opcoes.append("⚙️ Gestão de Efetivo (Admin)")

    menu = st.sidebar.radio("Navegação:", opcoes)

    # 1. DETECÇÃO DE ARMAS
    if menu == "1. Detecção de Armas":
        st.header("🔫 Varredura Tática de Imagens")
        up = st.file_uploader("Submeter Evidência", type=['jpg','png','jpeg'])
        if up and st.button("INICIAR ANÁLISE"):
            with st.spinner("IA Analisando ameaças..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    res = model.generate_content(["Analise armas, indivíduos e nível de perigo tático. Seja técnico.", Image.open(up)])
                    st.image(up, use_container_width=True)
                    st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)
                except Exception as e: st.error(f"Erro na IA: {e}")

    # 2. TRANSCRIÇÃO DE ÁUDIO
    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Descodificação de Áudio")
        t1, t2 = st.tabs(["📁 Arquivo", "🎤 Microfone"])
        with t1: audio_up = st.file_uploader("Submeter Áudio", type=['mp3','wav','m4a'])
        with t2: audio_in = st.audio_input("Grave a evidência")
        
        audio_final = audio_up if audio_up else audio_in
        if audio_final and st.button("PROCESSAR TRANSCRIÇÃO"):
            if not STATUS_AUDIO: st.error("Motor Whisper Offline.")
            else:
                with st.spinner("A extrair texto..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                        t.write(audio_final.getvalue()); p = t.name
                    res = whisper_model.transcribe(p, language="pt")
                    st.markdown(f"<div class='cyber-box'>{res['text']}</div>", unsafe_allow_html=True)

    # 3. VISÃO FORENSE
    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento e Restauração Forense")
        u = st.file_uploader("Imagem Evidência", type=['jpg','png','jpeg'])
        if u:
            img = Image.open(u)
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            c1, c2 = st.columns(2)
            with c1: st.image(u, caption="Original", use_container_width=True)
            with c2:
                if st.button("REDUZIR RUÍDO (DENOISE)"):
                    dn = cv2.fastNlMeansDenoisingColored(cv_img, None, 10, 10, 7, 21)
                    st.image(cv2.cvtColor(dn, cv2.COLOR_BGR2RGB), use_container_width=True)
                s = st.slider("Nitidez", 1, 5, 2)
                if st.button("AGUÇAR BORDAS"):
                    k = np.array([[0, -s, 0], [-s, 4*s+1, -s], [0, -s, 0]])
                    sh = cv2.filter2D(cv_img, -1, k)
                    st.image(cv2.cvtColor(sh, cv2.COLOR_BGR2RGB), use_container_width=True)

    # 5. INVESTIGAÇÃO CPF
    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Triagem")
        cpf = st.text_input("CPF do Alvo (11 dígitos)")
        if cpf and st.button("PUXAR REGISTROS"):
            with st.spinner("Acedendo a bases neurais..."):
                try:
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    res = model.generate_content(f"Gere um JSON simulando Dossiê para o CPF {cpf}: Nome, RG, Filiação, Endereços, Histórico Criminal. JSON PURO.")
                    json_str = res.text.strip().replace("`" * 3 + "json", "").replace("`" * 3, "").strip()
                    st.json(json.loads(json_str))
                except Exception as e: st.error(f"Erro: {e}")

    # 6. CYBER OSINT
    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Rastreio")
        tab1, tab2 = st.tabs(["📡 Rastreio IP", "🤖 Análise de Perfil"])
        with tab1:
            ip_in = st.text_input("Endereço IP Alvo")
            if ip_in and st.button("RASTREAR ORIGEM"):
                try:
                    res = requests.get(f"http://ip-api.com/json/{ip_in}").json()
                    st.success(f"📍 {ip_in} | {res.get('isp')} | {res.get('city')}, {res.get('country')}")
                except: st.error("Falha na varredura.")
        with tab2:
            u_p = st.file_uploader("Print de Perfil Social", type=['jpg','png'])
            if u_p and st.button("ANALISAR PERFIL"):
                genai.configure(api_key=GEMINI_API_KEY)
                res = genai.GenerativeModel('gemini-1.5-flash-latest').generate_content(["Identifique logotipos, facções, nomes e localizações neste perfil.", Image.open(u_p)])
                st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)

    # 7. CHECKLIST TÁTICO
    elif menu == "7. Checklist Tático":
        st.header("📋 Procedimentos Operacionais")
        tabs = st.tabs(["📄 BO / RO", "📄 Flagrante", "📄 Local de Crime"])
        with tabs[0]:
            with st.form("f_bo"):
                loc = st.text_input("Localização")
                nar = st.text_area("Dinâmica dos Fatos")
                if st.form_submit_button("GERAR PDF"):
                    st.session_state['pdf_bo'] = gerar_pdf("BOLETIM", {"Local": loc, "Relato": nar})
            if 'pdf_bo' in st.session_state:
                st.download_button("BAIXAR BO (PDF)", st.session_state['pdf_bo'], "BO.pdf")

    # 8. PERSONA COVER
    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Identidade Sintética (Offline)")
        with st.form("p_c"):
            sx = st.radio("Sexo", ["Masculino", "Feminino"], horizontal=True)
            id_ = st.slider("Idade", 18, 80, 30)
            uf = st.selectbox("Estado", ["SP", "RJ", "MG", "BA", "PR"])
            if st.form_submit_button("SINTETIZAR"):
                st.session_state['cover'] = gerar_persona_offline(sx, id_, uf, "Sim")
        if 'cover' in st.session_state:
            p = st.session_state['cover']
            st.success("✅ Identidade sintetizada.")
            st.json(p)
            st.download_button("BAIXAR FICHA", gerar_pdf("COVER", p), "cover.pdf")

    # 9. GERADOR DE ROSTO
    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Síntese Neural de Face")
        with st.form("f_r"):
            g = st.selectbox("Gênero", ["Masculino", "Feminino"])
            prompt = st.text_input("Detalhes (etnia, acessórios, ambiente)", "Pardo, óculos escuros, fundo de rua")
            if st.form_submit_button("SINTETIZAR ROSTO"):
                with st.spinner("A processar rede neural..."):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={GEMINI_API_KEY}"
                    payload = {"instances": [{"prompt": f"Realistic photo of a {g}, {prompt}"}]}
                    res = requests.post(url, json=payload)
                    if res.status_code == 200:
                        img_b64 = res.json()["predictions"][0]["bytesBase64Encoded"]
                        st.session_state['face'] = base64.b64decode(img_b64)
                    else: st.error("Falha na IA.")
        if 'face' in st.session_state:
            st.image(st.session_state['face'], use_container_width=True)
            st.download_button("BAIXAR IMAGEM", st.session_state['face'], "face.jpg")

    # 10. INTELIGÊNCIA DOCUMENTAL
    elif menu == "10. Inteligência Documental":
        st.header("📄 Triagem e OCR de Documentos")
        u = st.file_uploader("Submeter Documento (Imagem)", type=['jpg','png','jpeg'])
        if u and st.button("EXTRAIR DADOS"):
            genai.configure(api_key=GEMINI_API_KEY)
            res = genai.GenerativeModel('gemini-1.5-flash-latest').generate_content(["Extraia Nomes, CPFs, RGs, Datas e Placas deste documento.", Image.open(u)])
            st.markdown(f"<div class='cyber-box'>{res.text}</div>", unsafe_allow_html=True)

    # 11. GESTÃO DE OPERAÇÕES
    elif menu == "11. Gestão de Operações":
        st.header("📋 Ordem de Operação")
        with st.form("f_op"):
            op_nome = st.text_input("Operação")
            op_alvos = st.text_area("Alvos e Endereços")
            if st.form_submit_button("GERAR PLANO"):
                st.session_state['pdf_op'] = gerar_pdf("ORDEM DE OPERACAO", {"Missao": op_nome, "Alvos": op_alvos})
        if 'pdf_op' in st.session_state:
            st.download_button("BAIXAR PLANO (PDF)", st.session_state['pdf_op'], "Operacao.pdf")

    # GESTÃO DE EFETIVO (ADMIN)
    elif menu == "⚙️ Gestão de Efetivo (Admin)":
        st.header("⚙️ Centro de Comando (Admin)")
        t1, t2 = st.tabs(["📋 Efetivo", "➕ Novo Agente"])
        with t1:
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT username, role, plan, vencimento FROM usuarios", conn)
            st.dataframe(df, use_container_width=True, hide_index=True)
            alvo = st.selectbox("Revogar Acesso:", df['username'].tolist())
            if st.button("EXCLUIR"):
                if alvo == "leandro": st.error("Comandante Supremo não pode ser excluído.")
                else:
                    c = conn.cursor(); c.execute('DELETE FROM usuarios WHERE username=?', (alvo,)); conn.commit()
                    st.success("Acesso revogado."); st.rerun()
            conn.close()
        with t2:
            with st.form("add_u"):
                n_u = st.text_input("Credencial")
                n_p = st.text_input("Chave/Senha")
                n_r = st.selectbox("Cargo", ["user", "admin"])
                n_pl = st.selectbox("Plano", ["GOLD", "SILVER"])
                if st.form_submit_button("CADASTRAR"):
                    conn = get_db_connection(); c = conn.cursor()
                    try:
                        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?)', (n_u, n_p, n_r, n_pl, "2099-12-31"))
                        conn.commit(); st.success("Agente integrado.")
                    except: st.error("Erro ou Agente já existe.")
                    conn.close()
