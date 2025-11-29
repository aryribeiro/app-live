import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
import qrcode
from io import BytesIO
import sqlite3
import time
from datetime import datetime
import uuid
from collections import Counter
import threading
import base64

# Configuração da página
st.set_page_config(
    page_title="App Live",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# CSS customizado
st.markdown("""
<style>
    .main > div {
        padding-top: 1rem;
    }
    .stApp > header {
        background-color: transparent;
    }
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        color: white;
        margin-bottom: 20px;
    }
    .pin-display {
        background: white;
        color: #667eea;
        padding: 10px 20px;
        border-radius: 25px;
        font-weight: bold;
        font-size: 18px;
        display: inline-block;
        margin: 10px;
    }
    .participants-count {
        font-size: 16px;
        color: white;
        margin-top: 10px;
    }
    .question-container {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        padding: 30px;
        border-radius: 15px;
        text-align: center;
        color: white;
        font-size: 24px;
        font-weight: bold;
        margin: 20px 0;
    }
    .response-form {
        background: #f8f9fa;
        padding: 20px;
        border-radius: 10px;
        margin: 20px 0;
        border: 2px solid #e9ecef;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 10px 30px;
        border-radius: 25px;
        font-weight: bold;
        width: 100%;
    }
    .success-message {
        background: #d4edda;
        color: #155724;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #c3e6cb;
        margin: 10px 0;
    }
    .error-message {
        background: #f8d7da;
        color: #721c24;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #f5c6cb;
        margin: 10px 0;
    }
    .participant-interface {
        max-width: 600px;
        margin: 0 auto;
        padding: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Configuração do banco de dados com thread lock
db_lock = threading.Lock()

@st.cache_resource
def get_db_connection():
    return sqlite3.connect('app_live.db', check_same_thread=False, timeout=30)

def init_db():
    with db_lock:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS sessions
                         (id TEXT PRIMARY KEY, pin TEXT UNIQUE, question TEXT, created_at TIMESTAMP)''')
            c.execute('''CREATE TABLE IF NOT EXISTS responses
                         (id TEXT PRIMARY KEY, session_id TEXT, response TEXT, created_at TIMESTAMP,
                          FOREIGN KEY(session_id) REFERENCES sessions(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS config
                         (key TEXT PRIMARY KEY, value TEXT)''')
            
            # Inserir senha padrão se não existir
            c.execute("SELECT value FROM config WHERE key = 'moderator_password'")
            if not c.fetchone():
                c.execute("INSERT INTO config (key, value) VALUES ('moderator_password', 'admin123')")
            
            conn.commit()
        except Exception as e:
            st.error(f"Erro ao inicializar banco: {e}")

def get_moderator_password():
    with db_lock:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM config WHERE key = 'moderator_password'")
            result = c.fetchone()
            return result[0] if result else 'admin123'
        except Exception as e:
            st.error(f"Erro ao buscar senha: {e}")
            return 'admin123'

def update_moderator_password(new_password):
    with db_lock:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE config SET value = ? WHERE key = 'moderator_password'", (new_password,))
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Erro ao atualizar senha: {e}")
            return False

def generate_qr_code(url):
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except Exception as e:
        st.error(f"Erro ao gerar QR Code: {e}")
        return None

def create_session(question):
    with db_lock:
        try:
            # Gerar PIN mais simples
            pin = str(uuid.uuid4().int)[:6]
            session_id = str(uuid.uuid4())
            
            conn = get_db_connection()
            c = conn.cursor()
            
            # Verificar se PIN já existe
            c.execute("SELECT pin FROM sessions WHERE pin = ?", (pin,))
            if c.fetchone():
                pin = str(uuid.uuid4().int)[:6]  # Gerar novo se existir
            
            c.execute("INSERT INTO sessions (id, pin, question, created_at) VALUES (?, ?, ?, ?)", 
                      (session_id, pin, question, datetime.now()))
            conn.commit()
            return session_id, pin
        except Exception as e:
            st.error(f"Erro ao criar sessão: {e}")
            return None, None

def get_session_by_pin(pin):
    with db_lock:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT id, pin, question, created_at FROM sessions WHERE pin = ?", (pin,))
            result = c.fetchone()
            return result
        except Exception as e:
            st.error(f"Erro ao buscar sessão: {e}")
            return None

def add_response(session_id, response):
    with db_lock:
        try:
            response_id = str(uuid.uuid4())
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO responses (id, session_id, response, created_at) VALUES (?, ?, ?, ?)", 
                      (response_id, session_id, response.strip(), datetime.now()))
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Erro ao adicionar resposta: {e}")
            return False

def get_responses(session_id):
    with db_lock:
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT response FROM responses WHERE session_id = ? ORDER BY created_at DESC", (session_id,))
            results = c.fetchall()
            return [r[0] for r in results if r[0] and r[0].strip()]
        except Exception as e:
            st.error(f"Erro ao buscar respostas: {e}")
            return []

def create_wordcloud(responses):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from collections import Counter
        
        # Processar respostas mantendo frases completas e convertendo para MAIÚSCULAS
        all_phrases = []
        for response in responses:
            # Converter para maiúsculas e manter a resposta completa
            phrase = response.upper().strip()
            if phrase:
                all_phrases.append(phrase)
        
        phrase_counts = Counter(all_phrases)
        top_phrases = dict(phrase_counts.most_common(20))
        
        if not top_phrases:
            return None
            
        # Criar visualização simples com matplotlib
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='white')
        ax.set_facecolor('white')
        
        # Posições aleatórias para as palavras
        np.random.seed(42)
        positions = np.random.rand(len(top_phrases), 2)
        
        # Cores diferentes para cada palavra
        colors = plt.cm.viridis(np.linspace(0, 1, len(top_phrases)))
        
        # Rotações aleatórias (0 = horizontal, 90 = vertical)
        np.random.seed(42)
        rotations = np.random.choice([0, 90], size=len(top_phrases))
        
        for i, (phrase, count) in enumerate(top_phrases.items()):
            # Aumentar tamanho: menor fonte +4px, demais +8px
            base_size = 20 + count * 5
            if base_size <= 25:  # Fontes menores
                size = min(base_size + 4, 54)
            else:  # Fontes maiores
                size = min(base_size + 8, 58)
            
            ax.text(positions[i][0], positions[i][1], phrase, 
                   fontsize=size, color=colors[i], 
                   ha='center', va='center', weight='bold',
                   rotation=rotations[i])  # Adiciona rotação vertical
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        ax.set_title('Nuvem de Palavras das Respostas', fontsize=20, pad=20)
        
        plt.tight_layout()
        return fig
        
    except Exception as e:
        st.error(f"Erro ao criar nuvem de palavras: {e}")
        return None

# Inicializar banco
init_db()

# Estados da sessão
if 'session_mode' not in st.session_state:
    st.session_state.session_mode = 'participate'  # Modo padrão: participante
if 'current_session' not in st.session_state:
    st.session_state.current_session = None
if 'current_pin' not in st.session_state:
    st.session_state.current_pin = None
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = True
if 'moderator_authenticated' not in st.session_state:
    st.session_state.moderator_authenticated = False
if 'show_change_password' not in st.session_state:
    st.session_state.show_change_password = False

# Verificar se PIN foi passado via URL
query_params = st.query_params
if 'pin' in query_params and query_params['pin']:
    st.session_state.participant_pin = query_params['pin']
elif 'participant_pin' not in st.session_state:
    st.session_state.participant_pin = ""

# Interface principal
st.markdown("""
<div class="main-header">
    <h1>📡 App Live</h1>
    <p>Interação em tempo real para aulas e lives</p>
</div>
""", unsafe_allow_html=True)

# Sidebar para controle
with st.sidebar:
    st.header("🎛️ Controle da Sessão")
    mode = st.radio("Selecione o modo:", ["🙋 Participar", "🎯 Criar Sessão", "📊 Moderar Sessão"])
    
    if mode == "🙋 Participar":
        st.session_state.session_mode = 'participate'
    elif mode == "🎯 Criar Sessão":
        st.session_state.session_mode = 'create'
    else:
        st.session_state.session_mode = 'moderate'
    
    st.markdown("---")
    if st.session_state.session_mode == 'moderate':
        st.session_state.auto_refresh = st.checkbox("🔄 Auto-refresh", value=True)

# Modo Participar (TELA PRINCIPAL)
if st.session_state.session_mode == 'participate':
    st.markdown('<div class="participant-interface">', unsafe_allow_html=True)
    st.header("🙋🏼‍♀️ Participar da Sessão")
    
    pin_input = st.text_input(
        "PIN da sessão:", 
        value=st.session_state.participant_pin,
        placeholder="123456",
        help="Solicite o PIN ao moderador da sessão",
        key="pin_input"
    )
    
    if pin_input.strip():
        session_data = get_session_by_pin(pin_input.strip())
        if session_data:
            st.markdown(f"""
            <div class="question-container">
                💬 {session_data[2]}
            </div>
            """, unsafe_allow_html=True)
            
            # Formulário de resposta
            with st.form("response_form", clear_on_submit=True):
                response = st.text_input(
                    "✏️ Sua resposta:", 
                    placeholder="Digite sua resposta aqui...",
                    help="Seja claro e objetivo em sua resposta"
                )
                submitted = st.form_submit_button("📤 Enviar Resposta")
                
                if submitted and response.strip():
                    if add_response(session_data[0], response.strip()):
                        st.success("✅ Resposta enviada com sucesso! Obrigado pela sua participação!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Erro ao enviar resposta. Tente novamente.")
                elif submitted:
                    st.warning("⚠️ Por favor, digite uma resposta válida.")
            
            # Mostrar estatísticas básicas
            current_responses = get_responses(session_data[0])
            if current_responses:
                st.info(f"📊 **{len(current_responses)}** pessoas já participaram desta sessão!")
                
                # Mostrar nuvem de palavras para participantes
                st.subheader("☁️ Nuvem de Palavras das Respostas")
                wordcloud_fig = create_wordcloud(current_responses)
                if wordcloud_fig:
                    st.pyplot(wordcloud_fig)
                else:
                    st.info("Aguardando mais respostas para gerar a nuvem de palavras...")
                    
        else:
            st.error("❌ PIN inválido! Verifique o código com o moderador.")
    else:
        st.info("👆 Digite o PIN para começar...")
    
    st.markdown("---")
    st.markdown("### ℹ️ Como participar:")
    st.markdown("""
    1. **Obtenha o PIN** da sessão com o moderador
    2. **Digite o PIN** no campo acima
    3. **Responda** à pergunta apresentada
    4. **Clique em Enviar** para participar
    
    Sua resposta aparecerá instantaneamente na tela do moderador.
    """)
    st.markdown('</div>', unsafe_allow_html=True)

# Modo Criar Sessão
elif st.session_state.session_mode == 'create':
    # Verificar autenticação
    if not st.session_state.moderator_authenticated:
        st.header("🔐 Autenticação de Moderador")
        st.info("Digite a senha de moderador para criar uma sessão.")
        
        with st.form("auth_form"):
            password_input = st.text_input("Senha:", type="password", placeholder="Digite a senha")
            auth_submit = st.form_submit_button("🔓 Entrar")
            
            if auth_submit:
                if password_input == get_moderator_password():
                    st.session_state.moderator_authenticated = True
                    st.success("✅ Autenticação bem-sucedida!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta!")
    else:
        st.header("🎯 Criar Nova Sessão Interativa")
        
        # Botão para mudar senha
        if st.button("🔑 Alterar Senha de Moderador"):
            st.session_state.show_change_password = not st.session_state.show_change_password
        
        if st.session_state.show_change_password:
            with st.form("change_password_form"):
                st.subheader("🔐 Alterar Senha")
                current_pass = st.text_input("Senha atual:", type="password")
                new_pass = st.text_input("Nova senha:", type="password")
                confirm_pass = st.text_input("Confirmar nova senha:", type="password")
                change_submit = st.form_submit_button("💾 Salvar Nova Senha")
                
                if change_submit:
                    if current_pass == get_moderator_password():
                        if new_pass == confirm_pass and len(new_pass) >= 6:
                            if update_moderator_password(new_pass):
                                st.success("✅ Senha alterada com sucesso!")
                                st.session_state.show_change_password = False
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error("❌ Erro ao alterar senha.")
                        else:
                            st.error("❌ As senhas não coincidem ou são muito curtas (mínimo 6 caracteres).")
                    else:
                        st.error("❌ Senha atual incorreta!")
            st.markdown("---")
        
        with st.form("create_session_form"):
            question = st.text_input(
                "📝 Digite sua pergunta:", 
                placeholder="Ex: De qual estado você é?",
                help="Esta pergunta será exibida para todos os participantes"
            )
            
            submitted = st.form_submit_button("🚀 Criar Sessão")
            
            if submitted and question.strip():
                session_id, pin = create_session(question.strip())
                if session_id and pin:
                    st.session_state.current_session = session_id
                    st.session_state.current_pin = pin
                    st.session_state.session_mode = 'moderate'
                    st.success("✅ Sessão criada com sucesso!")
                    st.info(f"📌 PIN da sessão: **{pin}**")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("❌ Erro ao criar sessão. Tente novamente.")
            elif submitted:
                st.warning("⚠️ Por favor, digite uma pergunta válida.")

# Modo Moderar Sessão
elif st.session_state.session_mode == 'moderate':
    # Verificar autenticação
    if not st.session_state.moderator_authenticated:
        st.header("🔐 Autenticação de Moderador")
        st.info("Digite a senha de moderador para acessar o painel de moderação.")
        
        with st.form("auth_moderate_form"):
            password_input = st.text_input("Senha:", type="password", placeholder="Digite a senha")
            auth_submit = st.form_submit_button("🔓 Entrar")
            
            if auth_submit:
                if password_input == get_moderator_password():
                    st.session_state.moderator_authenticated = True
                    st.success("✅ Autenticação bem-sucedida!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Senha incorreta!")
    else:
        if st.session_state.current_session:
            session_data = get_session_by_pin(st.session_state.current_pin)
            if session_data:
                responses = get_responses(st.session_state.current_session)
                
                # Layout principal
                col1, col2 = st.columns([3, 1])
                
                with col2:
                    st.markdown(f"""
                    <div class="main-header" style="margin-bottom: 10px;">
                        <div class="pin-display">PIN: {st.session_state.current_pin}</div>
                        <div class="participants-count">👥 {len(responses)} participantes</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # QR Code
                    st.subheader("📱 QR Code")
                    base_url = "https://applive.streamlit.app"
                    current_url = f"{base_url}?pin={st.session_state.current_pin}"
                    qr_buf = generate_qr_code(current_url)
                    if qr_buf:
                        st.image(qr_buf, width=200)
                    
                    st.markdown("**🔗 Link:**")
                    st.code(current_url, language=None)
                    
                    # Controles
                    if st.button("🔄 Atualizar Agora"):
                        st.rerun()
                    
                    if st.button("🛑 Encerrar Sessão"):
                        st.session_state.current_session = None
                        st.session_state.current_pin = None
                        st.session_state.session_mode = 'create'
                        st.rerun()
                
                with col1:
                    st.markdown(f"""
                    <div class="question-container">
                        📋 {session_data[2]}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if responses:
                        # Processar respostas
                        response_counts = Counter(responses)
                        
                        # Métricas
                        col_m1, col_m2, col_m3 = st.columns(3)
                        with col_m1:
                            st.metric("📊 Total de Respostas", len(responses))
                        with col_m2:
                            st.metric("🔢 Respostas Únicas", len(response_counts))
                        with col_m3:
                            if response_counts:
                                most_common = response_counts.most_common(1)[0]
                                st.metric("🥇 Mais Popular", f"{most_common[0]} ({most_common[1]}x)")
                        
                        # Tabs para visualizações
                        tab1, tab2, tab3 = st.tabs(["📊 Gráfico", "☁️ Nuvem", "📋 Lista"])
                        
                        with tab1:
                            # Gráfico de barras
                            df_responses = pd.DataFrame(list(response_counts.items()), 
                                                      columns=['Resposta', 'Quantidade'])
                            df_responses = df_responses.sort_values('Quantidade', ascending=False).head(15)
                            
                            if not df_responses.empty:
                                fig = px.bar(
                                    df_responses, 
                                    x='Resposta', 
                                    y='Quantidade',
                                    color='Quantidade', 
                                    color_continuous_scale='viridis',
                                    title="📈 Respostas Mais Frequentes"
                                )
                                fig.update_layout(
                                    height=400,
                                    xaxis_tickangle=-45,
                                    showlegend=False
                                )
                                st.plotly_chart(fig, use_container_width=True)
                        
                        with tab2:
                            # Nuvem de palavras
                            wordcloud_fig = create_wordcloud(responses)
                            if wordcloud_fig:
                                st.pyplot(wordcloud_fig)
                            else:
                                st.info("💭 Aguardando mais respostas para gerar a nuvem de palavras...")
                        
                        with tab3:
                            # Lista de respostas
                            st.markdown("### 📝 Todas as Respostas")
                            for i, (response, count) in enumerate(response_counts.most_common(), 1):
                                st.markdown(f"**{i}.** {response} `({count}x)`")
                    else:
                        st.info("📭 Aguardando respostas dos participantes...")
                        st.markdown("### 📢 Compartilhe o PIN ou QR Code com seus participantes!")
                
                # Auto-refresh para moderador
                if st.session_state.auto_refresh:
                    time.sleep(5)
                    st.rerun()
            else:
                st.error("❌ Sessão não encontrada.")
                st.session_state.current_session = None
                st.session_state.current_pin = None
        else:
            st.info("ℹ️ Nenhuma sessão ativa. Crie uma nova sessão primeiro.")
            if st.button("➕ Criar Nova Sessão"):
                st.session_state.session_mode = 'create'
                st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 20px;">
    <strong>📡 App Live</strong> - Desenvolvido para interação em tempo real<br>
    Criado durante a Live da ANETI, por <strong>Ary Ribeiro</strong>: <a href="mailto:aryribeiro@gmail.com">aryribeiro@gmail.com</a><br>
    <small>Versão 1.0 | Streamlit + Python</small>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .main {
        background-color: #ffffff;
        color: #333333;
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
    }
    /* Esconde completamente todos os elementos da barra padrão do Streamlit */
    header {display: none !important;}
    footer {display: none !important;}
    #MainMenu {display: none !important;}
    /* Remove qualquer espaço em branco adicional */
    div[data-testid="stAppViewBlockContainer"] {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    /* Remove quaisquer margens extras */
    .element-container {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
</style>
""", unsafe_allow_html=True)