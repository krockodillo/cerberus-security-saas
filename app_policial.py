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

# ==================================================
# CONFIGURAÇÃO GERAL E CHAVES MESTRAS
# ==================================================
st.set_page_config(page_title="CERBERUS v4.7 - SaaS Intel", layout="wide", page_icon="🐕‍🦺")

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
    "9. Gerador de Rosto (IA Avançada)"
]

# Definição do Plano SILVER (Fixo)
MODULOS_SILVER = [
    "1. Detecção de Armas",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "9. Gerador de Rosto (IA Avançada)"
]

st.markdown("""
    <style>
    .stApp {background-color: #0E1117;}
    .login-container { padding: 50px; background-color: #1f2937; border-radius: 10px; border: 1px solid #374151; text-align: center; }
    .status-badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; color: white; }
    .plan-gold { background-color: #eab308; color: black; }
    .plan-silver { background-color: #94a3b8; color: black; }
    .plan-gray { background-color: #475569; }
    /* Estilo para links forçados a brilhar no modo escuro */
    .cyber-link { color: #38bdf8 !important; text-decoration: none; font-weight: bold; }
    .cyber-link:hover { color: #7dd3fc !important; text-decoration: underline; }
    .cyber-box { background-color: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #475569; color: #ffffff; }
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
    # Nota: Em produção na nuvem, o arquivo .db precisa persistir. 
    # No Streamlit Cloud gratuito, ele reseta a cada deploy. 
    # Para o BETA isso é aceitável.
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
def carregar_whisper(): 
    # Nota: No Streamlit Cloud gratuito, o Whisper Base pode ser pesado.
    # Se der erro de memória, mudar para "tiny".
    return whisper.load_model("tiny") 

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

def consultar_cpf_avancado(cpf):
    time.sleep(1)
    if len(cpf) < 11: return None
    return {
        "nome": "ALVO TESTE DA SILVA", "cpf": cpf, "mae": "MARIA SILVA",
        "enderecos": [{"log": "RUA TESTE", "num": "123", "bairro": "CENTRO"}],
        "veiculos": [{"modelo": "FIAT TORO", "placa": "ABC-1234"}],
        "score": {"risco": "ALTO", "pontos": 850}
    }

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
                        
                        prompt = """
                        Aja como um perito criminal e analista de inteligência militar. 
                        Analise detalhadamente esta imagem e forneça um relatório curto com:
                        1. Quantidade de pessoas/suspeitos.
                        2. Quantidade de armas visíveis.
                        3. Tipo e modelo provável de cada arma (ex: fuzil plataforma AR, AK-47, pistola 9mm). Especifique acessórios se houver (miras, carregadores alongados).
                        Seja direto, frio e profissional na descrição. Não faça julgamentos morais, apenas relate os fatos visuais.
                        """
                        
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=[prompt, image]
                        )
                        
                        st.markdown("### 📋 Relatório de Inteligência Visual")
                        
                        texto_formatado = response.text.replace('\n', '<br>')
                        st.markdown(f"<div class='cyber-box'>{texto_formatado}</div>", unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("📄 **Copiar Relatório Texto:**")
                            st.code(response.text, language="markdown")
                            
                        with col2:
                            st.write("📥 **Exportar Arquivo Oficial:**")
                            
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
                            
                            st.download_button(
                                label="Baixar Relatório Pericial (PDF)",
                                data=pdf_bytes,
                                file_name=f"Relatorio_Cerberus_{int(time.time())}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                            os.remove(tmp_img_path)
                            
                    except Exception as e:
                        st.error(f"Erro na análise de servidor. Verifique sua conexão. Detalhes: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição")
        a = st.file_uploader("Áudio", type=['mp3','wav'])
        if a and STATUS_AUDIO and st.button("TRANSCREVER"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as t: t.write(a.getvalue()); p=t.name
            r = whisper_model.transcribe(p); os.remove(p)
            for s in r['segments']: st.info(s['text'])

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento Forense")
        u = st.file_uploader("Imagem", type=['jpg','png'])
        if u: 
            img = np.array(Image.open(u))
            clean = cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, 10, 10, 7, 21)
            st.image(cv2.cvtColor(clean, cv2.COLOR_BGR2RGB))

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Vínculos")
        if st.button("Gerar"): gerar_mapa_vinculos()
        if os.path.exists("mapa_operacional.html"):
            with open("mapa_operacional.html", 'r', encoding='utf-8') as f:
                components.html(f.read(), height=600)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Smart Search CPF")
        cpf = st.text_input("CPF")
        if st.button("BUSCAR"): st.write(consultar_cpf_avancado(cpf))

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        st.markdown("Módulo avançado de rastreamento de alvos, IPs e análise psicológica de fontes abertas.")
        
        tab_ia, tab_ip, tab_dorks, tab_gps = st.tabs(["🤖 IA Forense de Perfil", "📡 Rastreador de IP", "🔎 Matriz de Rastro (Web)", "📍 Extração de Metadados"])
        
        with tab_ia:
            st.subheader("Análise Investigativa de Perfil (Printscreen)")
            st.markdown("Faça o upload de um print/captura de tela de um perfil do Instagram, TikTok ou Facebook. A IA fará a leitura forense da biografia, símbolos, emojis e fotos visíveis.")
            u_print = st.file_uploader("Carregar Print do Perfil", type=['jpg','png', 'jpeg'], key="up_print")
            
            if u_print:
                img_print = Image.open(u_print)
                st.image(img_print, caption="Evidência Submetida", use_container_width=True)
                
                if st.button("EXECUTAR PERFILAMENTO PSICOLÓGICO", type="primary"):
                    with st.spinner("Decodificando símbolos, gírias e contexto visual..."):
                        try:
                            client = genai.Client(api_key=GEMINI_API_KEY)
                            prompt_osint = """
                            Aja como um analista de inteligência criminal e OSINT. Analise este print de perfil de rede social e extraia:
                            1. Nome ou Vulgo utilizado.
                            2. Análise de Símbolos: Há emojis ou códigos na biografia que sugiram afiliação a facções (ex: 🚩, ☯️, 🃏, TD2, TD3, etc)? O que eles significam no jargão criminal?
                            3. Perfil Comportamental: Qual a impressão geral? Ostentação? Discreto? Ameaçador?
                            4. Contatos ou Links visíveis (se houver).
                            Entregue a resposta em tópicos diretos e técnicos. Se for um perfil comum sem indícios criminais, afirme isso com clareza.
                            """
                            response_ia = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt_osint, img_print])
                            texto_ia = response_ia.text.replace('\n', '<br>')
                            st.markdown(f"<div class='cyber-box'><h4>🧠 Dossiê Analítico IA:</h4>{texto_ia}</div>", unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"Falha na conexão com o servidor de Inteligência: {e}")

        with tab_ip:
            st.subheader("Geolocalização Cibernética (IP Tracker)")
            st.markdown("Ferramenta essencial para quebras de sigilo (ex: IP fornecido pelo WhatsApp/Meta). Descubra provedor e localização do alvo.")
            ip_alvo = st.text_input("Endereço de IP (IPv4)", placeholder="Ex: 177.12.34.56")
            
            if st.button("RASTREAR CONEXÃO", type="primary"):
                if ip_alvo:
                    with st.spinner("Consultando bases de dados globais..."):
                        try:
                            # Nota: Usando API pública gratuita ip-api.com. Em produção, considerar API paga para maior volume.
                            res_ip = requests.get(f"http://ip-api.com/json/{ip_alvo}?lang=pt-BR").json()
                            if res_ip.get("status") == "success":
                                st.