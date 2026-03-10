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
# CONFIGURAÇÃO GERAL
# ==============================================================================
st.set_page_config(page_title="CERBERUS - Sistema Tático", layout="wide", page_icon="🛡️")

GEMINI_API_KEY = "AIzaSyBeFgncS12Y65hKCzPhlK9LVCxTzA89oZ0"

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
    "10. Inteligência Documental",
    "11. Geolocalização Forense"
]

MODULOS_SILVER = [
    "1. Detecção de Armas",
    "5. Investigação CPF",
    "6. Cyber OSINT & Forense",
    "9. Gerador de Rosto (IA Avançada)",
    "10. Inteligência Documental",
    "11. Geolocalização Forense"
]

# ==============================================================================
# BANCO DE DADOS E GESTÃO DE USUÁRIOS/NOTIFICAÇÕES
# ==============================================================================
def init_db():
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (username TEXT PRIMARY KEY, password TEXT, role TEXT, plan TEXT, permissions TEXT, vencimento TEXT, status TEXT)''')
    
    # Tabela de Notificações
    c.execute('''CREATE TABLE IF NOT EXISTS notificacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, destinatario TEXT, mensagem TEXT, imagem BLOB, data_envio TEXT)''')
    
    # Cria o usuário LEANDRO como Mestre (CEO)
    c.execute('SELECT * FROM usuarios WHERE username = "leandro"')
    if not c.fetchone():
        c.execute('INSERT INTO usuarios VALUES (?,?,?,?,?,?,?)', ('leandro', '239546Dl', 'admin', 'GOLD', 'ALL', '2099-12-31', 'ativo'))
        conn.commit()
        
    # Automação: Primeira notificação de sistema automática para TODOS
    c.execute('SELECT count(*) FROM notificacoes')
    if c.fetchone()[0] == 0:
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        msg_auto = "SISTEMA ATUALIZADO: A central de notificações e o seu perfil agora ficam localizados no canto superior direito da tela."
        c.execute('INSERT INTO notificacoes (destinatario, mensagem, imagem, data_envio) VALUES (?, ?, ?, ?)', ('TODOS', msg_auto, None, data_atual))
        conn.commit()
        
    conn.close()

def enviar_notificacao(destinatario, mensagem, imagem_bytes=None):
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.execute('INSERT INTO notificacoes (destinatario, mensagem, imagem, data_envio) VALUES (?, ?, ?, ?)', (destinatario, mensagem, imagem_bytes, data_atual))
    conn.commit()
    conn.close()

def ler_notificacoes(username):
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute('SELECT mensagem, imagem, data_envio FROM notificacoes WHERE destinatario = "TODOS" OR destinatario = ? ORDER BY id DESC', (username,))
    notas = c.fetchall()
    conn.close()
    return notas

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
    if username == "leandro": return False # Proteção para não deletar o CEO
    conn = sqlite3.connect('cerberus_users.db')
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE username=?", (username,))
    conn.commit()
    conn.close()
    return True

init_db()

# ==============================================================================
# MOTORES E FUNÇÕES CORE
# ==============================================================================
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
    except: return False

def extrair_texto_arquivo(uploaded_file):
    if not LIBS_DOC: return "Erro"
    nome = uploaded_file.name.lower()
    try:
        if nome.endswith('.pdf'):
            leitor = PyPDF2.PdfReader(uploaded_file)
            return "\n".join([p.extract_text() for p in leitor.pages if p.extract_text()])
        elif nome.endswith('.docx'):
            doc = docx.Document(uploaded_file)
            return "\n".join([p.text for p in doc.paragraphs])
        elif nome.endswith('.txt'): return uploaded_file.getvalue().decode("utf-8")
        elif nome.endswith(('.xlsx', '.xls', '.csv')):
            df = pd.read_excel(uploaded_file) if 'xls' in nome else pd.read_csv(uploaded_file)
            return df.to_string()
        else: return None
    except Exception as e: return f"Erro: {e}"

def gerar_mapa_vinculos():
    net=Network(height='600px',width='100%',bgcolor='#222222',font_color='white'); net.force_atlas_2based()
    net.add_node(1,label="ALVO",color='red'); net.add_edge(1,2); net.save_graph("mapa_operacional.html")

def gerar_pessoa_4devs():
    try: return requests.post("https://www.4devs.com.br/ferramentas_online.php", data={'acao':'gerar_pessoa','sexo':'I','txt_qtde':1}, headers={'Content-Type':'application/x-www-form-urlencoded'}).json()[0]
    except: return None

# ==============================================================================
# TELA DE LOGIN (NATIVA E LIMPA)
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center;'>CERBERUS</h1>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            
            btn_entrar = st.form_submit_button("ENTRAR", use_container_width=True)
            
            if btn_entrar:
                with st.spinner("Autenticando..."):
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
        
        # Botão secundário nativo fora do form
        if st.button("Solicitar acesso", use_container_width=True):
            st.info("Função de solicitação de acesso em desenvolvimento.")

else:
    # ==============================================================================
    # ÁREA LOGADA - MÓDULOS DO SISTEMA E TOPO SUPERIOR
    # ==============================================================================
    user_role = st.session_state['role']
    user_plan = st.session_state['plan']
    user_perms = st.session_state['perms']
    username_logado = st.session_state['username']
    
    # --- ÁREA DO TOPO DIREITO (Perfil e Notificações) ---
    col_espaco, col_notif, col_perfil = st.columns([8, 1.5, 1.5])
    
    with col_notif:
        with st.popover("🔔 Avisos"):
            st.markdown("**Caixa de Mensagens**")
            notas = ler_notificacoes(username_logado)
            if not notas:
                st.info("Nenhuma novidade no momento.")
            else:
                for msg, img_blob, data in notas:
                    st.caption(data)
                    st.write(msg)
                    if img_blob:
                        st.image(Image.open(io.BytesIO(img_blob)), use_container_width=True)
                    st.divider()

    with col_perfil:
        with st.popover("👤 Perfil"):
            st.markdown(f"**Agente:** {username_logado.upper()}")
            st.markdown(f"**Plano:** {user_plan}")
            st.divider()
            if st.button("Sair do Sistema", use_container_width=True):
                st.session_state['logged_in'] = False
                st.rerun()
    st.markdown("---")
    
    # --- MENU LATERAL ---
    st.sidebar.title("🐕‍🦺 CERBERUS")
    if user_plan == 'GOLD': st.sidebar.markdown("**PLANO GOLD**")
    elif user_plan == 'SILVER': st.sidebar.markdown("**PLANO SILVER**")
    else: st.sidebar.markdown("**PLANO GRAY**")
    
    st.sidebar.markdown("---")

    menu_options = ["🛠️ PAINEL ADMIN"] + TODOS_MODULOS if user_role == 'admin' else TODOS_MODULOS if user_plan == 'GOLD' else MODULOS_SILVER if user_plan == 'SILVER' else user_perms.split(",")
    menu = st.sidebar.radio("Ferramentas:", menu_options)

    if menu == "🛠️ PAINEL ADMIN":
        st.title("🛠️ Gestão e Comunicação")
        tab_clientes, tab_base, tab_notif = st.tabs(["➕ Novo Cliente", "📋 Base de Usuários", "📢 Disparar Notificações"])
        
        with tab_clientes:
            st.subheader("Configurar Novo Acesso")
            with st.form("create_user"):
                c1, c2 = st.columns(2)
                new_user = c1.text_input("Login")
                new_pass = c2.text_input("Senha")
                c3, c4 = st.columns(2)
                new_role = c3.selectbox("Hierarquia", ["operacional", "gerente", "admin"])
                new_plan = c4.selectbox("Plano de Assinatura", ["GOLD", "SILVER", "GRAY"])
                permissoes_gray = st.multiselect("Módulos Liberados", TODOS_MODULOS) if new_plan == "GRAY" else []
                dias = st.number_input("Dias de Acesso", value=30, min_value=1)
                if st.form_submit_button("CRIAR ACESSO", type="primary"):
                    perms_final = ["ALL"] if new_plan == "GOLD" else MODULOS_SILVER if new_plan == "SILVER" else permissoes_gray
                    if new_user and new_pass:
                        ok, txt = criar_usuario(new_user, new_pass, new_role, new_plan, perms_final, dias)
                        st.success(txt) if ok else st.error(txt)
                    else: st.warning("Preencha tudo.")
                    
        with tab_base:
            st.dataframe(listar_usuarios(), use_container_width=True)
            u_del = st.selectbox("Deletar Usuário", listar_usuarios()['username'].unique())
            if st.button("EXCLUIR"): deletar_usuario(u_del); st.rerun()
            
        with tab_notif:
            st.subheader("Central de Transmissão")
            st.markdown("Envie recados, alertas ou imagens para os usuários do sistema.")
            with st.form("form_disparo"):
                lista_users = ["TODOS"] + list(listar_usuarios()['username'].unique())
                alvo_notificacao = st.selectbox("Para quem deseja enviar?", lista_users)
                texto_msg = st.text_area("Mensagem:", placeholder="Escreva o aviso aqui...")
                imagem_up = st.file_uploader("Anexar Imagem (Opcional)", type=['jpg', 'png', 'jpeg'])
                
                if st.form_submit_button("DISPARAR NOTIFICAÇÃO", type="primary"):
                    if texto_msg:
                        bytes_img = imagem_up.getvalue() if imagem_up else None
                        enviar_notificacao(alvo_notificacao, texto_msg, bytes_img)
                        st.success(f"✅ Notificação enviada com sucesso para: {alvo_notificacao}")
                    else:
                        st.error("A mensagem não pode estar vazia.")

    elif menu == "1. Detecção de Armas":
        st.header("🔫 Análise Tática e Identificação de Armamento")
        u = st.file_uploader("Carregar Evidência (Imagem)", type=['jpg','png', 'jpeg'])
        
        if u:
            image = Image.open(u)
            st.image(image, caption="Evidência Original", use_container_width=True)
            
            if st.button("GERAR RELATÓRIO PERICIAL", type="primary"):
                with st.spinner("Analisando evidência com IA Tática..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        
                        prompt = """
                        Aja como um Perito Criminal de Elite e Analista de Inteligência Policial. 
                        Analise esta imagem minuciosamente e gere um relatório técnico oficial respondendo EXATAMENTE aos seguintes tópicos de forma direta e objetiva:
                        
                        1. QUANTIDADE DE INDIVÍDUOS: (Quantas pessoas aparecem na imagem?)
                        2. CARACTERÍSTICAS FÍSICAS E VESTIMENTAS: (Descreva roupas, máscaras, tatuagens, coletes balísticos ou itens de identificação).
                        3. QUANTIDADE DE ARMAS VISÍVEIS: (Quantos armamentos estão visíveis na imagem?)
                        4. CLASSIFICAÇÃO DO ARMAMENTO: (Para cada arma identifique: Tipo [Ex: Fuzil, Pistola, Espingarda], Modelo provável e Calibre presumido).
                        5. ACESSÓRIOS BÉLICOS: (Há miras ópticas, carregadores alongados, supressores/silenciadores, bandoleiras?)
                        6. ANÁLISE DO CENÁRIO: (Descreva o ambiente: é área de mata, comunidade, via pública, interior de imóvel? Qual a condição de luminosidade?)
                        7. AVALIAÇÃO DE RISCO TÁTICO: (Qual a atitude dos indivíduos? Estão em posição de tiro/prontidão? Há reféns ou civis próximos?)
                        
                        Não use emojis nas respostas. Seja extremamente técnico, frio e descritivo.
                        """
                        r = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image])
                        texto_ia = r.text
                        
                        st.markdown("### 📋 Relatório de Inteligência Visual")
                        st.info(texto_ia)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_img:
                            image.convert("RGB").save(tmp_img.name)
                            tmp_img_path = tmp_img.name
                        
                        pdf = FPDF()
                        pdf.add_page()
                        
                        pdf.set_font("Arial", 'B', 16)
                        pdf.cell(0, 8, "CERBERUS INTEL - SISTEMA DE INTELIGENCIA TATICA", ln=True, align='C')
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(0, 6, "RELATORIO PERICIAL DE ANALISE VISUAL", ln=True, align='C')
                        pdf.set_font("Arial", '', 10)
                        data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        pdf.cell(0, 6, f"Data da Analise: {data_hora}", ln=True, align='C')
                        pdf.ln(5)
                        
                        w, h = image.size
                        ratio = h / w
                        img_h = 190 * ratio
                        if img_h > 110:
                            img_h = 110
                            w_img = img_h / ratio
                            pdf.image(tmp_img_path, x=(210-w_img)/2, w=w_img, h=img_h)
                        else:
                            pdf.image(tmp_img_path, x=10, w=190, h=img_h)
                        
                        pdf.set_y(pdf.get_y() + img_h + 8)
                        
                        pdf.set_font("Arial", size=10)
                        clean_text = texto_ia.replace("**", "") 
                        clean_text = clean_text.encode('latin-1', 'replace').decode('latin-1')
                        pdf.multi_cell(0, 6, txt=clean_text)
                        
                        pdf.ln(15)
                        
                        pdf.set_font("Arial", 'B', 10)
                        operador = st.session_state.get('username', 'OPERADOR NÃO IDENTIFICADO').upper()
                        pdf.cell(0, 5, "_"*60, ln=True, align='C')
                        pdf.cell(0, 5, f"Assinatura do Agente Analista: {operador}", ln=True, align='C')
                        pdf.cell(0, 5, "CERBERUS INTEL - PCERJ / PMERJ", ln=True, align='C')
                        
                        pdf_bytes = pdf.output(dest='S').encode('latin-1')
                        
                        st.download_button(
                            label="📥 Baixar Relatório Oficial (PDF)",
                            data=pdf_bytes,
                            file_name=f"Dossie_Armamento_{int(time.time())}.pdf",
                            mime="application/pdf",
                            type="primary"
                        )
                        
                        os.remove(tmp_img_path)
                        
                    except Exception as e: 
                        st.error(f"Erro na geração do relatório: {e}")

    elif menu == "2. Transcrição de Áudio":
        st.header("🎙️ Transcrição Tática")
        tab_up, tab_mic = st.tabs(["📁 Upload", "🎤 Gravar"])
        audio_data = None
        with tab_up: a_up = st.file_uploader("Áudio", type=['mp3','wav', 'm4a', 'ogg']); audio_data = a_up if a_up else audio_data
        with tab_mic: a_mic = st.audio_input("Gravação"); audio_data = a_mic if a_mic else audio_data
        if audio_data and STATUS_AUDIO:
            st.audio(audio_data)
            if st.button("TRANSCREVER", type="primary"):
                with st.spinner("Decodificando..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as t: t.write(audio_data.getvalue()); p = t.name
                    r = whisper_model.transcribe(p); os.remove(p)
                    st.write(''.join([s['text']+'\n' for s in r['segments']]))

    elif menu == "3. Visão Forense":
        st.header("👁️ Tratamento Forense")
        u = st.file_uploader("Imagem", type=['jpg','png'])
        if u: 
            img = np.array(Image.open(u))
            st.image(cv2.cvtColor(cv2.fastNlMeansDenoisingColored(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), None, 10, 10, 7, 21), cv2.COLOR_BGR2RGB))

    elif menu == "4. Mapa de Vínculos":
        st.header("🔗 Vínculos (Manual)")
        if st.button("Gerar Base"): gerar_mapa_vinculos()
        if os.path.exists("mapa_operacional.html"):
            with open("mapa_operacional.html", 'r', encoding='utf-8') as f: components.html(f.read(), height=600)

    elif menu == "5. Investigação CPF":
        st.header("🔍 Dossiê Pessoal e Smart Search CPF")
        st.warning("⚠️ STATUS: EM HOMOLOGAÇÃO DE API")
        cpf = st.text_input("CPF")
        if st.button("PUXAR DOSSIÊ", type="primary") and len(cpf) >= 11:
            with st.spinner("Buscando..."): time.sleep(1)
            st.success("Dados demonstrativos carregados.")
            st.write(f"**Nome:** ALVO DE TESTE\n\n**CPF:** {cpf}")

    elif menu == "6. Cyber OSINT & Forense":
        st.header("🌐 Cyber OSINT e Inteligência Forense")
        tab_ia, tab_ip, tab_d = st.tabs(["🤖 IA Forense", "📡 IP", "🔎 Dorks"])
        
        with tab_ia:
            u_p = st.file_uploader("Print", type=['jpg','png'])
            if u_p and st.button("ANALISAR PERFIL"):
                with st.spinner("Analisando..."):
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    r = client.models.generate_content(model='gemini-2.5-flash', contents=["Analise este perfil criminoso.", Image.open(u_p)])
                    st.write(r.text)
                    
        with tab_ip:
            ip = st.text_input("IP")
            if st.button("RASTREAR") and ip:
                res = requests.get(f"http://ip-api.com/json/{ip}?lang=pt-BR").json()
                if res.get('status') == 'success': st.success(f"Cidade: {res['city']} | ISP: {res['isp']}")
                
        with tab_d:
            n = st.text_input("Alvo")
            if st.button("BUSCAR") and n: st.markdown(f"[Pesquisar {n} no Google](https://www.google.com/search?q={n})")

    elif menu == "7. Checklist Tático":
        st.header("📋 Checklist de Plantão")
        st.selectbox("Ocorrência", ["Flagrante", "B.O."])

    elif menu == "8. Gerador de Persona (Cover)":
        st.header("🕵️ Cover - Gerador de Dados Falsos")
        if st.button("GERAR PERSONA"): 
            d = gerar_pessoa_4devs()
            if d: st.write(f"**Nome:** {d.get('nome')}\n\n**CPF:** {d.get('cpf')}")

    elif menu == "9. Gerador de Rosto (IA Avançada)":
        st.header("👤 Criação de Perfil Cover")
        with st.form("g_cover"):
            g, i, e = st.selectbox("Gênero", ["Homem", "Mulher"]), st.slider("Idade", 18, 80, 35), st.selectbox("Etnia", ["Latino/Pardo", "Branco", "Negro", "Asiático"])
            c = st.text_input("Características Específicas")
            if st.form_submit_button("GERAR (NANO BANANA 2)", type="primary"):
                with st.spinner("Gerando..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        prompt = f"Rosto fotorrealista de {g}, {i} anos, {e}. {c}"
                        res = client.models.generate_images(model='imagen-3.0-generate-002', prompt=prompt, config=genai.types.GenerateImagesConfig(number_of_images=1, output_mime_type="image/jpeg", aspect_ratio="1:1"))
                        st.image(Image.open(io.BytesIO(res.generated_images[0].image.image_bytes)))
                    except Exception as err: st.error(f"Erro: {err}")

    elif menu == "10. Inteligência Documental":
        st.header("📄 Análise de Vínculos e Extração Tática")
        if not LIBS_DOC: st.error("⚠️ Bibliotecas PyPDF2/docx ausentes.")
        with st.form("f_doc"):
            arq = st.file_uploader("Evidência", type=['pdf', 'docx', 'txt', 'csv', 'xlsx', 'jpg', 'png'])
            agt = st.selectbox("Agente Analítico", ["🔎 GENÉRICO", "💰 FININT", "🌐 OSINT"])
            if st.form_submit_button("PROCESSAR", type="primary") and arq:
                with st.spinner("Analisando..."):
                    try:
                        client = genai.Client(api_key=GEMINI_API_KEY)
                        conteudo = [Image.open(arq)] if arq.name.endswith(('.jpg', '.png')) else [f"TEXTO:\n{extrair_texto_arquivo(arq)[:15000]}"]
                        prompt = f"Analise como agente {agt}. Retorne: 1. Resumo. 2. JSON de conexões com 'nodes' (id, label, group) e 'edges' (from, to, label)."
                        conteudo.insert(0, prompt)
                        res = client.models.generate_content(model='gemini-2.5-flash', contents=conteudo)
                        txt = res.text
                        js = re.search(r'```json\n(.*?)\n```', txt, re.DOTALL)
                        relatorio = txt.replace(js.group(0), "") if js else txt
                        st.write(relatorio)
                        if js and gerar_mapa_vinculos_json(json.loads(js.group(1))) and os.path.exists("grafo_inteligencia.html"):
                            with open("grafo_inteligencia.html", 'r', encoding='utf-8') as f: components.html(f.read(), height=500)
                    except Exception as err: st.error(f"Erro: {err}")

    elif menu == "11. Geolocalização Forense":
        st.header("📍 Extração Automática de Metadados (EXIF)")
        st.markdown("Faça o upload da evidência original. O sistema fará a varredura automática por coordenadas GPS ocultas no arquivo.")
        
        u_geo = st.file_uploader("Carregar Imagem Original (.JPG / .JPEG)", type=['jpg', 'jpeg', 'png'])
        
        if u_geo:
            img_geo = Image.open(u_geo)
            st.image(img_geo, caption="Evidência Submetida", width=300)
            
            with st.spinner("Varrendo arquivo em busca de dados de satélite..."):
                geo, msg = extrair_geolocalizacao(img_geo)
                time.sleep(1) 
                
                if geo:
                    st.success(f"✅ ALVO LOCALIZADO! Latitude: {geo[0]} | Longitude: {geo[1]}")
                    m = folium.Map([geo[0], geo[1]], zoom_start=15)
                    folium.Marker([geo[0], geo[1]], tooltip="Origem EXIF da Foto").add_to(m)
                    st_folium(m, height=400, use_container_width=True)
                else:
                    st.error("❌ EVIDÊNCIA LIMPA: Nenhum dado de GPS (EXIF) foi encontrado neste arquivo.")
                    st.warning("**NOTA OPERACIONAL:** Arquivos recebidos via WhatsApp, Redes Sociais ou salvos como Printscreen perdem os metadados de localização automaticamente. Utilize a foto original extraída do aparelho.")