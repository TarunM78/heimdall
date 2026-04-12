# 👁️‍🗨️ Heimdall: AI-Powered Financial Morning Brief

Heimdall is an advanced, high-fidelity financial dashboard designed to provide investors with a synthesized "Morning Brief" of their portfolio. By integrating real-time portfolio data from **SnapTrade**, market news from **NewsAPI**, and advanced LLM analysis via **Featherless**, Heimdall delivers actionable insights and sentiment analysis in a sleek, modern interface.

![Aesthetics](https://img.shields.io/badge/Aesthetics-Premium-blueviolet)
![Backend](https://img.shields.io/badge/Backend-FastAPI-009688)
![Frontend](https://img.shields.io/badge/Frontend-Vanilla_JS-f7df1e)

---

## 🚀 Key Features

- **Personalized Morning Brief**: Automated synthesis of news impacting your specific holdings, generated using Llama-3 (Featherless AI).
- **SnapTrade Integration**: Securely connect and sync your brokerage accounts to track actual positions and cost basis.
- **Analytics Dashboard**:
  - **Sector Breakdown**: Visualize your portfolio's diversification.
  - **Correlation Cluster Map**: Identify hidden risks through asset relationships.
  - **Alpha Quadrant**: Performance and risk scoring.
- **Interactive Audio Briefing**: Listen to your daily update on the go with high-quality Text-to-Speech (ElevenLabs).
- **Secure Authentication**: Enterprise-grade login and account protection powered by Auth0.

---

## 🛠️ Technology Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn.
- **Frontend**: Vanilla JavaScript (ES6+), CSS3 (Glassmorphism & CSS Variables), Semantic HTML5.
- **AI/ML**:
  - LLM: `NousResearch/Meta-Llama-3-8B-Instruct` via Featherless.ai.
  - TTS: ElevenLabs API.
- **External APIs**: SnapTrade (Brokerage), yFinance (Market Data), NewsAPI.

---

## 🏃 Getting Started

### Prerequisites
- Python 3.11 or higher
- A virtual environment (recommended)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/AR22-cr/newstracker.git
   cd newstracker
   ```

2. **Set up the virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the root directory and add your API keys:
   ```env
   NEWSAPI_KEY="your_newsapi_key"
   FEATHERLESS_API_KEY="your_featherless_key"
   FEATHERLESS_BASE_URL="https://api.featherless.ai/v1"
   FEATHERLESS_MODEL="NousResearch/Meta-Llama-3-8B-Instruct"
   
   AUTH0_DOMAIN="your_auth0_domain"
   AUTH0_CLIENT_ID="your_auth0_client_id"
   
   SNAPTRADE_CLIENT_ID="your_snaptrade_id"
   SNAPTRADE_CONSUMER_KEY="your_snaptrade_key"
   
   ELEVENLABS_API_KEY="your_elevenlabs_key"
   ```

4. **Launch the Application**:
   ```bash
   # Use the provided start script
   chmod +x start.sh
   ./start.sh
   ```
   The application will be available at `http://127.0.0.1:8000/`.

---

## 📁 Project Structure

```text
.
├── main.py             # FastAPI Backend Entry Point
├── services/           # Backend Logic (Analysis, Analytics, APIs)
├── static/             # Primary Frontend Assets
│   ├── index.html      # Main Dashboard
│   ├── app.js          # Client-side Logic
│   └── styles.css      # Core Design System
├── start.sh            # One-click startup script
└── requirements.txt    # Python dependencies
```

---

## 🧪 Development

Heimdall was built with a focus on **visual excellence** and **user agency**. The design system utilizes a dark-mode first approach with HSL-tailored colors and smooth cubic-bezier transitions for a premium experience.

---
*Created for Bitcamp 2026*
