# 📡 App Live – Interação em Tempo Real com Participantes

**App Live** é um web app interativo desenvolvido com [Streamlit](https://streamlit.io/) que permite criar sessões em tempo real para coletar respostas do público de forma simples, rápida e visual. Ideal para **aulas, lives, eventos e treinamentos**, com exibição de gráficos, nuvem de palavras e QR Code para fácil acesso.

## 🔧 Funcionalidades

- 🎯 Criação de sessões com PIN único
- 🙋 Participação por PIN ou QR Code
- 📋 Coleta de respostas em tempo real
- 📈 Gráfico dinâmico com as respostas mais frequentes
- ☁️ Nuvem de palavras gerada automaticamente
- 🔄 Atualização automática no modo moderador
- 📱 Interface responsiva com design customizado via CSS
- 🗃️ Banco de dados local em SQLite

## 🚀 Tecnologias Utilizadas

- [Python 3.9+](https://www.python.org/)
- [Streamlit](https://streamlit.io/)
- [Plotly](https://plotly.com/python/)
- [Matplotlib](https://matplotlib.org/)
- [SQLite3](https://www.sqlite.org/)
- [QRCode](https://pypi.org/project/qrcode/)
- HTML + CSS customizados

## 🖼️ Interface

### Participante
- Digita o PIN
- Visualiza a pergunta
- Envia sua resposta
- Acompanha visualizações da sessão

### Moderador
- Cria perguntas
- Compartilha o PIN e QR Code
- Acompanha respostas em tempo real
- Analisa resultados por gráfico, nuvem ou lista

## 🗂️ Estrutura do Projeto

📁 app/
└── app.py # Código principal do Streamlit App
└── app_live.db # Banco de dados SQLite (gerado automaticamente)
└── README.md # Documentação do projeto


## ▶️ Como Executar Localmente

1. Clone o repositório:

```bash
git clone https://github.com/aryribeiro/app-live.git
cd app-live

    Instale as dependências:

pip install -r requirements.txt

    Execute o app:

streamlit run app.py

    Acesse via navegador:

http://localhost:8501

📦 Requisitos

    Python 3.9 ou superior

    Pip

    Navegador moderno (Chrome, Firefox, Edge)

✅ To-do Futuro

Suporte a múltiplas perguntas por sessão (modo quiz)

Exportação de resultados em CSV ou PDF

Autenticação de moderador

    Deploy na nuvem (Streamlit Cloud / Render / Hugging Face Spaces)

👨‍💻 Autor

Desenvolvido por Ary Ribeiro
📧 aryribeiro@gmail.com