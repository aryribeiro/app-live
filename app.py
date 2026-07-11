import html
import random
import sqlite3
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from io import BytesIO

import pandas as pd
import plotly.express as px
import qrcode
import streamlit as st
from wordcloud import WordCloud

# Configuração da página
st.set_page_config(
    page_title="App Live",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Configuração do banco de dados com thread lock
db_lock = threading.Lock()

@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect('app_live.db', check_same_thread=False, timeout=30)
    # WAL reduz contenção entre leituras e escritas concorrentes
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def run_db(operation, max_attempts=4, base_delay=0.1, max_delay=2.0):
    """Executa uma operação no banco com retry e backoff exponencial com jitter.

    Retenta apenas sqlite3.OperationalError (ex.: 'database is locked');
    erros de programação/integridade propagam imediatamente.
    """
    delay = base_delay
    for attempt in range(1, max_attempts + 1):
        try:
            with db_lock:
                return operation(get_db_connection())
        except sqlite3.OperationalError:
            if attempt == max_attempts:
                raise
            time.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, max_delay)


def init_db():
    def op(conn):
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

    try:
        run_db(op)
    except Exception as e:
        st.error(f"Erro ao inicializar banco: {e}")

@st.cache_data(ttl=60, show_spinner=False)
def get_moderator_password():
    def op(conn):
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'moderator_password'")
        result = c.fetchone()
        return result[0] if result else 'admin123'

    try:
        return run_db(op)
    except Exception as e:
        st.error(f"Erro ao buscar senha: {e}")
        return 'admin123'

def update_moderator_password(new_password):
    def op(conn):
        c = conn.cursor()
        c.execute("UPDATE config SET value = ? WHERE key = 'moderator_password'", (new_password,))
        conn.commit()

    try:
        run_db(op)
        get_moderator_password.clear()  # write-invalidate
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
    def op(conn):
        c = conn.cursor()

        # Gerar PIN de 6 dígitos, re-checando unicidade até conseguir
        for _ in range(20):
            pin = f"{random.SystemRandom().randrange(100000, 1000000)}"
            c.execute("SELECT 1 FROM sessions WHERE pin = ?", (pin,))
            if not c.fetchone():
                break
        else:
            raise RuntimeError("Não foi possível gerar um PIN único")

        session_id = str(uuid.uuid4())
        c.execute("INSERT INTO sessions (id, pin, question, created_at) VALUES (?, ?, ?, ?)",
                  (session_id, pin, question, datetime.now()))
        conn.commit()
        return session_id, pin

    try:
        result = run_db(op)
        get_session_by_pin.clear()  # write-invalidate: PIN novo não pode ficar preso em cache negativo
        return result
    except Exception as e:
        st.error(f"Erro ao criar sessão: {e}")
        return None, None

@st.cache_data(ttl=30, show_spinner=False)
def get_session_by_pin(pin):
    def op(conn):
        c = conn.cursor()
        c.execute("SELECT id, pin, question, created_at FROM sessions WHERE pin = ?", (pin,))
        return c.fetchone()

    try:
        return run_db(op)
    except Exception as e:
        st.error(f"Erro ao buscar sessão: {e}")
        return None

def add_response(session_id, response):
    def op(conn):
        c = conn.cursor()
        c.execute("INSERT INTO responses (id, session_id, response, created_at) VALUES (?, ?, ?, ?)",
                  (str(uuid.uuid4()), session_id, response.strip(), datetime.now()))
        conn.commit()

    try:
        run_db(op)
        get_responses.clear(session_id)  # write-invalidate apenas desta sessão
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar resposta: {e}")
        return False

@st.cache_data(ttl=3, show_spinner=False)
def get_responses(session_id):
    def op(conn):
        c = conn.cursor()
        c.execute("SELECT response FROM responses WHERE session_id = ? ORDER BY created_at DESC", (session_id,))
        return [r[0] for r in c.fetchall() if r[0] and r[0].strip()]

    try:
        return run_db(op)
    except Exception as e:
        st.error(f"Erro ao buscar respostas: {e}")
        return []

# Paleta categórica validada (todas as cores >= 3:1 de contraste sobre branco)
WORDCLOUD_PALETTE = [
    "#2a78d6", "#199e70", "#c98500", "#008300",
    "#4a3aa7", "#e34948", "#d55181", "#eb6834",
]


def _wordcloud_color_func(word, **kwargs):
    # Cor determinística por palavra: estável entre atualizações da tela
    return random.Random(word).choice(WORDCLOUD_PALETTE)


@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def create_wordcloud(responses):
    """Gera a nuvem de palavras como PNG (bytes) a partir das respostas.

    O posicionamento usa o algoritmo espiral da lib `wordcloud`, com teste de
    colisão pixel a pixel — nenhuma palavra sobrepõe outra. O tamanho da fonte
    é proporcional à frequência da resposta.
    """
    try:
        phrases = [r.upper().strip() for r in responses if r and r.strip()]
        if not phrases:
            return None

        top_phrases = dict(Counter(phrases).most_common(50))

        wc = WordCloud(
            width=1600,
            height=900,
            background_color="white",
            max_words=50,
            min_font_size=18,
            max_font_size=280,
            prefer_horizontal=0.9,
            relative_scaling=0.55,
            margin=18,
            color_func=_wordcloud_color_func,
            random_state=42,
            collocations=False,
        ).generate_from_frequencies(top_phrases)

        buf = BytesIO()
        wc.to_image().save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        st.error(f"Erro ao criar nuvem de palavras: {e}")
        return None


def render_moderator_auth(form_key, info_text):
    """Formulário de autenticação do moderador (compartilhado pelos modos criar/moderar)."""
    st.header("🔐 Autenticação de Moderador")
    st.info(info_text)

    with st.form(form_key):
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
                💬 {html.escape(session_data[2])}
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
                wordcloud_png = create_wordcloud(current_responses)
                if wordcloud_png:
                    st.image(wordcloud_png, use_container_width=True)
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
        render_moderator_auth("auth_form", "Digite a senha de moderador para criar uma sessão.")
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
        render_moderator_auth("auth_moderate_form", "Digite a senha de moderador para acessar o painel de moderação.")
    else:
        if st.session_state.current_session:

            # Auto-refresh sem bloquear thread: o fragment reexecuta apenas o
            # painel a cada 5s, em vez de time.sleep(5) + rerun da página toda
            @st.fragment(run_every=5 if st.session_state.auto_refresh else None)
            def render_moderator_panel():
                session_data = get_session_by_pin(st.session_state.current_pin)
                if not session_data:
                    st.error("❌ Sessão não encontrada.")
                    st.session_state.current_session = None
                    st.session_state.current_pin = None
                    return

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
                        st.rerun(scope="fragment")
                    
                    if st.button("🛑 Encerrar Sessão"):
                        st.session_state.current_session = None
                        st.session_state.current_pin = None
                        st.session_state.session_mode = 'create'
                        st.rerun()
                
                with col1:
                    st.markdown(f"""
                    <div class="question-container">
                        📋 {html.escape(session_data[2])}
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
                            wordcloud_png = create_wordcloud(responses)
                            if wordcloud_png:
                                st.image(wordcloud_png, use_container_width=True)
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
                
            render_moderator_panel()
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
    header {display: none !important;}
    footer {display: none !important;}
    #MainMenu {display: none !important;}
    div[data-testid="stAppViewBlockContainer"] {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }
    .element-container {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
</style>
""", unsafe_allow_html=True)