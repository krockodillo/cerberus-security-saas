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
st.set_page_config(page_title="CERBERUS v4.8 - SaaS Intel", layout="wide", page_icon="🐕‍🦺")

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
    .cyber-link { color: #38bdf8 !important; text-decoration: none; font-weight: bold; }
    .cyber-link:hover { color: #7dd3fc !important; text-decoration: underline; }
    .cyber-box { background-color: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #475569; color: #ffffff; margin-bottom: 15px; }
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

    # --- MÓDULO 2 REFORMULADO: GRAVAÇÃO NATIVA + UPLOAD ---
    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática e Interceptação")
        st.markdown("Faça o upload de um arquivo de áudio ou grave diretamente do microfone para transcrição via IA (Whisper).")
        
        tab_upload, tab_mic = st.tabs(["📁 Upload de Arquivo", "🎤 Gravar Áudio (Microfone)"])
        
        audio_data = None
        
        with tab_upload:
            a_up = st.file_uploader("Carregar Áudio Oculto", type=['mp3','wav', 'm4a', 'ogg'])
            if a_up: 
                audio_data = a_up
                
        with tab_mic:
            st.info("Pressione o botão do microfone abaixo para iniciar a gravação ambiente.")
            a_mic = st.audio_input("Gravação Tática")
            if a_mic: 
                audio_data = a_mic
            
        if audio_data and STATUS_AUDIO:
            st.markdown("---")
            st.markdown("### 🎧 Áudio Capturado")
            st.audio(audio_data)
            
            if st.button("INICIAR TRANSCRIÇÃO", type="primary"):
                with st.spinner("Decodificando e transcrevendo áudio..."):
                    try:
                        # Salva o arquivo na memória temporária do servidor
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t:
                            t.write(audio_data.getvalue())
                            p = t.name
                        
                        r = whisper_model.transcribe(p)
                        os.remove(p)
                        
                        texto_completo = ""
                        for s in r['segments']: 
                            texto_completo += s['text'] + "\n"
                        
                        st.markdown("### 📝 Transcrição Oficial")
                        texto_formatado = texto_completo.replace('\n', '<br>')
                        st.markdown(f"<div class='cyber-box'>{texto_formatado}</div>", unsafe_allow_html=True)
                        
                        st.write("📄 **Copiar Transcrição:**")
                        st.code(texto_completo, language="markdown")
                        
                    except Exception as e:
                        st.error(f"Erro no processamento do áudio: {e}")
        elif not STATUS_AUDIO:
            st.error("⚠️ O motor Whisper não foi carregado corretamente. Verifique a instalação do servidor.")

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
                            res_ip = requests.get(f"http://ip-api.com/json/{ip_alvo}?lang=pt-BR").json()
                            if res_ip.get("status") == "success":
                                st.markdown(f"""
                                <div class='cyber-box'>
                                    <h4>📍 Rastreamento Concluído: {ip_alvo}</h4>
                                    <ul>
                                        <li><b>País/Região:</b> {res_ip.get('country')} / {res_ip.get('regionName')}</li>
                                        <li><b>Cidade:</b> {res_ip.get('city')}</li>
                                        <li><b>Provedor (ISP):</b> {res_ip.get('isp')} - {res_ip.get('org')}</li>
                                        <li><b>Coordenadas Aproximadas:</b> {res_ip.get('lat')}, {res_ip.get('lon')}</li>
                                    </ul>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                m_ip = folium.Map([res_ip.get('lat'), res_ip.get('lon')], zoom_start=12)
                                folium.Marker([res_ip.get('lat'), res_ip.get('lon')], tooltip=f"ISP: {res_ip.get('isp')}").add_to(m_ip)
                                st_folium(m_ip, height=350, use_container_width=True)
                            else:
                                st.error("❌ IP Inválido ou não encontrado na base pública.")
                        except:
                            st.error("Erro na comunicação com o servidor de rastreamento.")

        with tab_dorks:
            st.subheader("Matriz de Cruzamento de Dados (Web)")
            st.markdown("Utiliza operadores boleanos invisíveis para forçar bancos de dados a exporem o alvo.")
            c_d1, c_d2 = st.columns(2)
            dork_nome = c_d1.text_input("Nome/Vulgo do Alvo", placeholder="Ex: Zé Gotinha da Silva")
            target_user = c_d2.text_input("Username (@) se conhecido", placeholder="Ex: pcc_matador157")
            
            if st.button("GERAR MATRIZ DE EXTRAÇÃO", type="primary"):
                if dork_nome or target_user:
                    st.markdown("<div class='cyber-box'>✅ <b>Links Táticos Gerados.</b> (Clique para forçar a busca em nova aba)</div><br>", unsafe_allow_html=True)
                    
                    if dork_nome:
                        termo = urllib.parse.quote(f'"{dork_nome}"')
                        st.markdown("#### 🔍 Buscas Profundas pelo Nome:")
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:instagram.com+{termo}' target='_blank'>Varredura no Instagram</a>", unsafe_allow_html=True)
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:facebook.com+{termo}' target='_blank'>Varredura no Facebook</a>", unsafe_allow_html=True)
                        st.markdown(f"👉 <a class='cyber-link' href='https://www.google.com/search?q=site:jusbrasil.com.br+{termo}' target='_blank'>Busca de Antecedentes (Jusbrasil)</a>", unsafe_allow_html=True)
                    
                    st.write("---")
                    if target_user:
                        t_user = target_user.replace("@", "").strip()
                        st.markdown(f"#### 👣 Rastro Digital do @{t_user}:")
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.markdown(f"🔗 <a class='cyber-link' href='https://www.instagram.com/{t_user}/' target='_blank'>Instagram Direto</a>", unsafe_allow_html=True)
                            st.markdown(f"🔗 <a class='cyber-link' href='https://www.facebook.com/{t_user}' target='_blank'>Facebook Direto</a>", unsafe_allow_html=True)
                        with c2:
                            st.markdown(f"🔗 <a class='cyber-link' href='https://www.tiktok.com/@{t_user}' target='_blank'>TikTok Direto</a>", unsafe_allow_html=True)
                            st.markdown(f"🔗 <a class='cyber-link' href='https://twitter.com/{t_user}' target='_blank'>X (Twitter) Direto</a>", unsafe_allow_html=True)
                        with c3:
                            st.markdown(f"🔗 <a class='cyber-link' href='https://br.pinterest.com/{t_user}/' target='_blank'>Pinterest Direto</a>", unsafe_allow_html=True)
                            st.markdown(f"🔗 <a class='cyber-link' href='https://www.youtube.com/@{t_user}' target='_blank'>YouTube Direto</a>", unsafe_allow_html=True)

        with tab_gps:
            st.subheader("Extração de Coordenadas Ocultas (EXIF)")
            st.info("Arquivos enviados via WhatsApp perdem o metadado. Use fotos originais apreendidas em celulares.")
            u_gps = st.file_uploader("Carregar Arquivo de Imagem Original", key="gps_up")
            if u_gps:
                geo, msg = extrair_geolocalizacao(Image.open(u_gps))
                if geo:
                    st.success(f"📍 Alvo Localizado! Lat: {geo[0]}, Lon: {geo[1]}")
                    m = folium.Map([geo[0], geo[1]], zoom_start=15)
                    folium.Marker([geo[0], geo[1]], tooltip="Origem da Foto").add_to(m)
                    st_folium(m, height=400, use_container_width=True)
                else: 
                    st.error(f"❌ Não foi possível extrair a localização. Motivo: {msg}")

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
        st.header("🕵️ Cover")
        if st.button("GERAR"): st.write(gerar_pessoa_4devs())

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover (Fotorrealismo Fast)")
        st.markdown("Gere rostos específicos para operações de inteligência utilizando o motor Nano Banana 2 (Gemini Flash Image).")

        with st.form("gerador_cover"):
            c1, c2 = st.columns(2)
            genero = c1.selectbox("Gênero", ["Homem", "Mulher"])
            idade = c2.slider("Idade Aproximada", 18, 80, 35)

            etnia = st.selectbox("Etnia/Aparência", ["Latino/Pardo", "Caucasiano/Branco", "Negro", "Asiático", "Indígena"])
            caracteristicas = st.text_input("Características Específicas (Opcional)", placeholder="Ex: Cicatriz, tatuagem, óculos...")

            btn_gerar = st.form_submit_button("GERAR IDENTIDADE VISUAL (NANO BANANA 2)", type="primary")

        if btn_gerar:
            with st.spinner("Sintetizando rosto via Nano Banana 2... (isso leva segundos)"):
                try:
                    prompt_base = f"Fotografia em estilo documento (fundo cinza claro, iluminação de estúdio realista, alta resolução, fotorrealista) de um(a) {genero}, {idade} anos de idade, etnia {etnia}."
                    if caracteristicas:
                        prompt_base += f" Características visíveis: {caracteristicas}."

                    client = genai.Client(api_key=GEMINI_API_KEY)
                    result = client.models.generate_images(
                        model='gemini-3.1-flash-image-preview', 
                        prompt=prompt_base,
                        config=genai.types.GenerateImagesConfig(
                            number_of_images=1,
                            output_mime_type="image/jpeg",
                            aspect_ratio="1:1"
                        )
                    )

                    for generated_image in result.generated_images:
                        image = Image.open(io.BytesIO(generated_image.image.image_bytes))
                        col_img, _ = st.columns([1, 1])
                        with col_img:
                            st.image(image, caption="Perfil Gerado (Nano Banana 2)", use_container_width=True)
                        
                        st.success("✅ Imagem pronta para uso operacional.")

                except Exception as e:
                    st.error(f"Erro na geração visual. Verifique sua conexão ou cota da API. Detalhes técnicos: ({e})")