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
st.set_page_config(page_title="CERBERUS v5.1 - SaaS Intel", layout="wide", page_icon="🐕‍🦺")

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
                        prompt = """Aja como um perito criminal e analista de inteligência militar. 
                        Analise detalhadamente esta imagem e forneça um relatório curto com quantidade de pessoas, armas e o tipo provável."""
                        response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image])
                        st.markdown("### 📋 Relatório de Inteligência Visual")
                        texto_formatado = response.text.replace('\n', '<br>')
                        st.markdown(f"<div class='cyber-box'>{texto_formatado}</div>", unsafe_allow_html=True)
                        
                        # Export PDF logic
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_img:
                            image.convert("RGB").save(tmp_img.name)
                            tmp_img_path = tmp_img.name
                        pdf = FPDF()
                        pdf.add_page()
                        pdf.set_font("Arial", 'B', 16)
                        pdf.cell(0, 10, "CERBERUS - RELATORIO TATICO VISUAL", ln=True, align='C')
                        pdf.ln(5)
                        w, h = image.size
                        ratio = h / w
                        img_h = 190 * ratio
                        if img_h > 150: 
                            img_h = 150
                            w_img = img_h / ratio
                            pdf.image(tmp_img_path, x=(210-w_img)/2, w=w_img, h=img_h)
                        else:
                            pdf.image(tmp_img_path, x=10, w=190, h=img_h)
                        pdf.set_y(pdf.get_y() + img_h + 10)
                        pdf.set_font("Arial", size=12)
                        clean_text = response.text.encode('latin-1', 'replace').decode('latin-1')
                        pdf.multi_cell(0, 7, txt=clean_text)
                        pdf_bytes = pdf.output(dest='S').encode('latin-1')
                        st.download_button(label="Baixar Relatório (PDF)", data=pdf_bytes, file_name=f"Relatorio_{int(time.time())}.pdf", mime="application/pdf")
                        os.remove(tmp_img_path)
                    except Exception as e:
                        st.error(f"Erro na análise: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática e Interceptação")
        st.markdown("Faça o upload de um arquivo de áudio ou grave diretamente do microfone para transcrição via IA (Whisper).")
        tab_upload, tab_mic = st.tabs(["📁 Upload de Arquivo", "🎤 Gravar Áudio (Microfone)"])
        audio_data = None
        with tab_upload:
            a_up = st.file_uploader("Carregar Áudio Oculto", type=['mp3','wav', 'm4a', 'ogg'])
            if a_up: audio_data = a_up
        with tab_mic:
            st.info("Pressione o botão do microfone abaixo para iniciar a gravação ambiente.")
            a_mic = st.audio_input("Gravação Tática")
            if a_mic: audio_data = a_mic
            
        if audio_data and STATUS_AUDIO:
            st.markdown("---")
            st.markdown("### 🎧 Áudio Capturado")
            st.audio(audio_data)
            if st.button("INICIAR TRANSCRIÇÃO", type="primary"):
                with st.spinner("Decodificando e transcrevendo áudio..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                            t.write(audio_data.getvalue())
                            p = t.name
                        r = whisper_model.transcribe(p)
                        os.remove(p)
                        texto_completo = ""
                        for s in r['segments']: texto_completo += s['text'] + "\n"
                        st.markdown("### 📝 Transcrição Oficial")
                        st.markdown(f"<div class='cyber-box'>{texto_completo.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                        st.write("📄 **Copiar Transcrição:**")
                        st.code(texto_completo, language="markdown")
                    except Exception as e:
                        st.error(f"Erro no processamento do áudio: {e}")
        elif not STATUS_AUDIO:
            st.error("⚠️ O motor Whisper não foi carregado corretamente.")

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento Forense")
        st.markdown("Utiliza algoritmos de filtragem para redução de ruído (denoising) em fotos noturnas ou de câmeras de segurança.")
        u = st.file_uploader("Carregar Imagem para Tratamento", type=['jpg','png'])
        if u: 
            img = np.array(Image.open(u))
            clean = cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, 10, 10, 7, 21)
            st.image(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB), caption="Imagem Tratada (Ruído Reduzido)")

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Vínculos e Grafos (Manual)")
        st.markdown("Gerador de mapas de relacionamento manual.")
        if st.button("Gerar Mapa Base"): gerar_mapa_vinculos()
        if os.path.exists("mapa_operacional.html"):
            with open("mapa_operacional.html", 'r', encoding='utf-8') as f:
                components.html(f.read(), height=600)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
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
                    time.sleep(2)
                    st.success("✅ Conexão simulada com sucesso. Dados estruturais carregados.")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Situação RFB", "REGULAR")
                    col2.metric("Score de Risco", "MÉDIO", "Nível 3", delta_color="off")
                    col3.metric("Óbitos SIRC", "NÃO CONSTA")
                    col4.metric("Mandados (BNMP)", "0 ATIVOS", "Limpo")
                    
                    st.markdown("---")
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
                    
                    t_end, t_tel, t_veic, t_soc = st.tabs(["📍 Endereços (3)", "📞 Telefones (2)", "🚗 Veículos (1)", "🏢 Quadro Societário"])
                    with t_end:
                        st.markdown("#### Histórico de Endereços Vinculados")
                        st.info("RUA FICTÍCIA DOS TESTES, 123 - APTO 4B - BAIRRO CENTRO, SÃO PAULO/SP")
                        st.info("AVENIDA DEMONSTRAÇÃO, 999 - BAIRRO INDUSTRIAL, CAMPINAS/SP")
                    with t_tel:
                        st.markdown("#### Telefones e Linhas Móveis")
                        st.markdown("- 🟢 **(11) 99999-9999** (VIVO) - *Visto recentemente*")
                        st.markdown("- 🟡 **(11) 3333-4444** (CLARO FIXO) - *Visto há 8 meses*")
                    with t_veic:
                        st.markdown("#### Frota e Bens")
                        st.markdown("- 🚙 **FIAT TORO FREEDOM 2.0 (Prata)** - Placa: `ABC-1234`")
                    with t_soc:
                        st.markdown("#### Participação em Empresas (CNPJ)")
                        st.markdown("- **CNPJ: 00.000.000/0001-00** - *EMPRESA DEMONSTRATIVA LTDA*")
            else:
                st.warning("⚠️ O CPF precisa ter no mínimo 11 números.")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        st.markdown("Módulo avançado de rastreamento de alvos, IPs e análise psicológica de fontes abertas.")
        tab_ia, tab_ip, tab_dorks, tab_gps = st.tabs(["🤖 IA Forense de Perfil", "📡 Rastreador de IP", "🔎 Matriz de Rastro (Web)", "📍 Extração de Metadados"])
        
        with tab_ia:
            st.subheader("Análise Investigativa de Perfil (Printscreen)")
            u_print = st.file_uploader("Carregar Print do Perfil", type=['jpg','png', 'jpeg'], key="up_print")
            if u_print:
                img_print = Image.open(u_print)
                st.image(img_print, caption="Evidência Submetida", use_container_width=True)
                if st.button("EXECUTAR PERFILAMENTO PSICOLÓGICO", type="primary"):
                    with st.spinner("Decodificando símbolos e contexto..."):
                        try:
                            client = genai.Client(api_key=GEMINI_API_KEY)
                            prompt_osint = "Aja como um analista de inteligência criminal e OSINT. Analise este print de perfil e extraia: Nome, Símbolos/Facções, Perfil Comportamental."
                            response_ia = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt_osint, img_print])
                            st.markdown(f"<div class='cyber-box'><h4>🧠 Dossiê Analítico IA:</h4>{response_ia.text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"Falha na IA: {e}")

        with tab_ip:
            st.subheader("Geolocalização Cibernética (IP Tracker)")
            ip_alvo = st.text_input("Endereço de IP (IPv4)", placeholder="Ex: 177.12.34.56")
            if st.button("RASTREAR CONEXÃO", type="primary"):
                if ip_alvo:
                    try:
                        res_ip = requests.get(f"http://ip-api.com/json/{ip_alvo}?lang=pt-BR").json()
                        if res_ip.get("status") == "success":
                            st.markdown(f"""
                            <div class='cyber-box'>
                                <h4>📍 Rastreamento Concluído: {ip_alvo}</h4>
                                País: {res_ip.get('country')} | Cidade: {res_ip.get('city')} | Provedor: {res_ip.get('isp')}
                            </div>
                            """, unsafe_allow_html=True)
                            m_ip = folium.Map([res_ip.get('lat'), res_ip.get('lon')], zoom_start=12)
                            folium.Marker([res_ip.get('lat'), res_ip.get('lon')], tooltip=f"ISP: {res_ip.get('isp')}").add_to(m_ip)
                            st_folium(m_ip, height=350, use_container_width=True)
                        else: st.error("❌ IP Inválido.")
                    except: st.error("Erro na comunicação.")

        with tab_dorks:
            st.subheader("Matriz de Cruzamento de Dados (Web)")
            c_d1, c_d2 = st.columns(2)
            dork_nome = c_d1.text_input("Nome/Vulgo do Alvo", placeholder="Ex: Zé Gotinha da Silva")
            target_user = c_d2.text_input("Username (@) se conhecido", placeholder="Ex: pcc_matador157")
            if st.button("GERAR MATRIZ DE EXTRAÇÃO", type="primary"):
                if dork_nome or target_user:
                    st.markdown("<div class='cyber-box'>✅ <b>Links Táticos Gerados.</b></div>", unsafe_allow_html=True)
                    if dork_nome:
                        termo = urllib.parse.quote(f'"{dork_nome}"')
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:instagram.com+{termo}' target='_blank'>Varredura Instagram</a>", unsafe_allow_html=True)
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:facebook.com+{termo}' target='_blank'>Varredura Facebook</a>", unsafe_allow_html=True)
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:jusbrasil.com.br+{termo}' target='_blank'>Busca Jusbrasil</a>", unsafe_allow_html=True)
                    if target_user:
                        t_user = target_user.replace("@", "").strip()
                        st.markdown(f"🔗 <a class='cyber-link' href='https://www.instagram.com/{t_user}/' target='_blank'>Instagram @{t_user}</a>", unsafe_allow_html=True)
                        st.markdown(f"🔗 <a class='cyber-link' href='https://www.tiktok.com/@{t_user}' target='_blank'>TikTok @{t_user}</a>", unsafe_allow_html=True)

        with tab_gps:
            st.subheader("Extração de Coordenadas Ocultas (EXIF)")
            u_gps = st.file_uploader("Carregar Arquivo de Imagem Original", key="gps_up")
            if u_gps:
                geo, msg = extrair_geolocalizacao(Image.open(u_gps))
                if geo:
                    st.success(f"📍 Alvo Localizado! Lat: {geo[0]}, Lon: {geo[1]}")
                    m = folium.Map([geo[0], geo[1]], zoom_start=15)
                    folium.Marker([geo[0], geo[1]], tooltip="Origem da Foto").add_to(m)
                    st_folium(m, height=400, use_container_width=True)
                else: st.error(f"❌ Não foi possível extrair a localização. Motivo: {msg}")

    elif menu == "7. Checklist Tático":
        st.header("📋 Checklist de Plantão")
        tipo = st.selectbox("Ocorrência", ["Flagrante", "B.O.", "Ato Infracional"])
        if st.button("GERAR LISTA"):
            st.success("Lista gerada para: " + tipo)
            st.checkbox("Boletim de Ocorrência")
            st.checkbox("Exame IML")
            st.checkbox("Oitivas")
            if tipo == "Flagrante": st.checkbox("Nota de Culpa")

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Cover - Gerador de Dados Falsos")
        st.markdown("Gera perfis de disfarce operacional completos.")
        if st.button("GERAR NOVA PERSONA", type="primary"): 
            dados = gerar_pessoa_4devs()
            if dados:
                st.markdown(f"""
                <div class='cyber-box'>
                    <b>Nome:</b> {dados.get('nome')}<br>
                    <b>CPF:</b> {dados.get('cpf')}<br>
                    <b>RG:</b> {dados.get('rg')}<br>
                    <b>Data de Nasc:</b> {dados.get('data_nasc')}<br>
                    <b>Mãe:</b> {dados.get('mae')}<br>
                    <b>CEP:</b> {dados.get('cep')} - {dados.get('endereco')}, {dados.get('numero')}<br>
                    <b>Cartão de Crédito Falso:</b> {dados.get('numero_cartao')} (Val: {dados.get('data_validade')})
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error("Erro na comunicação com o servidor de Personas.")

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover (Fotorrealismo Fast)")
        with st.form("gerador_cover"):
            c1, c2 = st.columns(2)
            genero = c1.selectbox("Gênero", ["Homem", "Mulher"])
            idade = c2.slider("Idade Aproximada", 18, 80, 35)
            etnia = st.selectbox("Etnia/Aparência", ["Latino/Pardo", "Caucasiano/Branco", "Negro", "Asiático", "Indígena"])
            caracteristicas = st.text_input("Características Específicas", placeholder="Ex: Cicatriz, tatuagem, óculos...")
            btn_gerar = st.form_submit_button("GERAR IDENTIDADE VISUAL (NANO BANANA 2)", type="primary")

        if btn_gerar:
            with st.spinner("Sintetizando rosto via Nano Banana 2..."):
                try:
                    prompt_base = f"Fotografia fotorrealista de documento (fundo cinza) de {genero}, {idade} anos, etnia {etnia}."
                    if caracteristicas: prompt_base += f" Visível: {caracteristicas}."
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    result = client.models.generate_images(
                        model='gemini-3.1-flash-image-preview', 
                        prompt=prompt_base,
                        config=genai.types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="1:1")
                    )
                    image = Image.open(io.BytesIO(result.generated_images[0].image.image_bytes))
                    col_img, _ = st.columns([1, 1])
                    with col_img: st.image(image, caption="Perfil Gerado", use_container_width=True)
                    st.success("✅ Imagem pronta.")
                except Exception as e:
                    st.error(f"Erro na geração visual: {e}")

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
                        conteudo_envio.append(f"CONTEÚDO DO DOCUMENTO:\n{texto_extraido[:15000]}")
                    
                    prompt_doc = f"""
                    Você é um Analista Chefe de Inteligência Policial focado em: {tipo_agente}.
                    Analise os dados fornecidos e entregue a resposta EXATAMENTE nestas duas partes:
                    
                    PARTE 1: RELATÓRIO ANALÍTICO
                    Escreva um resumo de inteligência (máximo 3 parágrafos). Destaque os principais alvos, endereços, empresas ou anomalias.
                    
                    PARTE 2: GRAFO DE VÍNCULOS (JSON)
                    Logo abaixo do relatório, você DEVE retornar um bloco de código JSON válido contendo os nós e arestas detectados. 
                    - 'nodes' devem ter: "id", "label", "group" ("Pessoa", "Empresa", "Local", "Telefone", "Conta").
                    - 'edges' devem ter: "from", "to", "label" (qual a relação).
                    
                    Formato:
                    ```json
                    {{
                      "nodes": [ {{"id": "João", "label": "João Silva", "group": "Pessoa"}} ],
                      "edges": [ {{"from": "João", "to": "EmpresaX", "label": "Dono"}} ]
                    }}
                    ```
                    """
                    conteudo_envio.insert(0, prompt_doc)
                    
                    resposta = client.models.generate_content(model='gemini-2.5-flash', contents=conteudo_envio)
                    texto_resposta = resposta.text
                    bloco_json = re.search(r'```json\n(.*?)\n```', texto_resposta, re.DOTALL)
                    
                    relatorio = texto_resposta
                    if bloco_json:
                        relatorio = texto_resposta.replace(bloco_json.group(0), "")
                        
                    st.markdown("### 📋 Dossiê Analítico do Agente")
                    st.markdown(f"<div class='cyber-box'>{relatorio.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
                    
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