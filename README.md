# 💷 Finance Agent

## Overview

Finance Agent is an AI-powered personal finance assistant that combines transaction management, receipt and bank statement ingestion, anomaly detection, semantic memory, financial research, sentiment analysis, and conversational AI into a single platform.

The project follows an agentic architecture where a Large Language Model (OpenAI) is combined with deterministic business rules, persistent memory, finance-specific tools, and human-in-the-loop validation to help users manage and understand their finances safely.

The solution includes:

- FastAPI backend
- Streamlit dashboard
- SQLite transaction store
- OpenAI-powered finance assistant
- ChromaDB semantic memory
- Receipt OCR and parsing
- PDF bank statement ingestion
- Transaction categorisation
- Financial anomaly detection
- News, research and sentiment tooling
- MCP tool integration for external capabilities

---

# Key Features

### Transaction Management
- Store and retrieve financial transactions
- Manual transaction entry
- Category and merchant filtering
- Historical transaction analysis

### Receipt Processing
- OCR extraction from receipt images
- LLM-powered receipt understanding
- Automatic merchant detection
- Transaction categorisation
- Human approval workflow before persistence

### Bank Statement Ingestion
- PDF statement parsing
- Transaction extraction
- Batch approval workflow
- Auto-categorisation support

### AI Finance Assistant
- Natural language finance conversations
- Financial research support
- News summarisation
- Sentiment analysis
- Finance-specific agent routing

### Persistent Memory
- ChromaDB vector database
- Long-term user preference storage
- Semantic memory retrieval
- Context-aware conversations

### Anomaly Detection
- Large transaction detection
- Category outlier detection
- Duplicate payment detection
- Rare merchant identification
- Severity scoring

### Dashboard & Analytics
- Interactive Streamlit interface
- Spending visualisation
- Transaction exploration
- Anomaly monitoring

---

# System Architecture

```text
┌──────────────────────────────┐
│         Streamlit UI         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│         FastAPI API          │
└──────────────┬───────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
SQLite DB   AI Agent   ChromaDB
Finance     Router     Memory
Database               Store
    │          │          │
    ▼          ▼          ▼
Transactions OpenAI   Semantic
Anomalies    Tools    Retrieval
Statements   MCP
Receipts
```

---

# Technical Architecture

## Frontend Layer

### Streamlit
Provides:

- Spending dashboard
- Transaction explorer
- File upload interface
- AI chat interface
- Analytics views

Location:

```text
src/finance_agent/interfaces/app.py
```

---

## API Layer

### FastAPI

Responsible for:

- Transaction APIs
- Anomaly APIs
- Receipt ingestion
- Statement ingestion
- Backend orchestration

Location:

```text
src/finance_agent/interfaces/api.py
```

Example endpoints:

```http
GET    /health
GET    /transactions
POST   /transactions
GET    /anomalies
```

---

## Agent Layer

The agent layer determines user intent and routes requests to the appropriate tool.

Components:

```text
agent/
├── categorizer.py
├── router.py
├── tools.py
└── mcp_tools.py
```

Responsibilities:

- Intent classification
- Tool selection
- Finance-specific reasoning
- MCP integration

---

## Memory Layer

Persistent semantic memory powered by ChromaDB.

```text
memory/
├── memory_store.py
└── memory_policy.py
```

Capabilities:

- Store user preferences
- Store important financial insights
- Semantic search
- Long-term conversational context

---

## Data Layer

### SQLite Database

Stores:

- Transactions
- Categories
- Merchant history

Location:

```text
finance.db
```

### ChromaDB

Stores:

- Embedded memories
- Semantic vectors
- Conversation context

Location:

```text
memory/chroma/
```

---

## Intelligence Layer

### Anomaly Detection Engine

Current detection rules:

1. Large spend vs overall spending baseline
2. Large spend vs category baseline
3. Duplicate payment patterns
4. Rare merchant detection

Location:

```text
src/finance_agent/services/anomaly_detection.py
```

---

# Project Structure

```text
finance_agent/
│
├── finance.db
├── streamlit_app.py
├── pyproject.toml
│
├── memory/
│   └── chroma/
│
└── src/
    └── finance_agent/
        │
        ├── agent/
        ├── data/
        ├── domain/
        ├── intelligence/
        ├── interfaces/
        ├── memory/
        ├── services/
        └── tools/
```

---

# Technology Stack

## AI & LLM

- OpenAI
- LangChain
- MCP Integration

## Backend

- FastAPI
- Python 3.12+
- Uvicorn

## Frontend

- Streamlit

## Data Storage

- SQLite
- ChromaDB

## OCR & Document Processing

- Tesseract OCR
- PDFPlumber
- PyPDF

## Analytics

- Pandas
- Matplotlib

---

# Installation

## Clone Repository

```bash
git clone <repository-url>
cd finance-agent
```

## Create Virtual Environment

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
```

### Linux / Mac

```bash
source .venv/bin/activate
```

## Install Dependencies

Using uv:

```bash
uv sync
```

Or pip:

```bash
pip install -r requirements.txt
```

---

# Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key
FINANCE_DB_PATH=finance.db
```

---

# Running the Application

## Start FastAPI Backend

```bash
uv run uvicorn finance_agent.interfaces.api:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

---

## Launch Streamlit

```bash
streamlit run streamlit_app.py
```

Frontend:

```text
http://localhost:8501
```

---

# Example Workflow

## Receipt Upload

```text
Receipt Image
      │
      ▼
OCR Extraction
      │
      ▼
LLM Parsing
      │
      ▼
Category Assignment
      │
      ▼
Anomaly Check
      │
      ▼
User Approval
      │
      ▼
SQLite Storage
```

---

## Statement Processing

```text
PDF Statement
      │
      ▼
Transaction Extraction
      │
      ▼
Auto Categorisation
      │
      ▼
User Validation
      │
      ▼
Database Storage
```

---

# Finance Research Capabilities

The platform includes:

- Financial news collection
- Market research gathering
- Sentiment analysis
- Trusted news source aggregation
- AI-generated summaries

Modules:

```text
tools/
├── research.py
├── sentiment.py
├── news.py
├── gdelt_news.py
└── trusted_news.py
```

---

# Security & Governance

Current safeguards include:

- Human-in-the-loop approval
- Explicit transaction confirmation
- Controlled database writes
- Persistent audit-friendly storage
- Rule-based validation before persistence

Recommended future enhancements:

- Authentication
- RBAC
- Encryption at rest
- API key management
- Audit logging
- User isolation

---

# Future Roadmap

## Short Term

- Enhanced anomaly detection
- Improved categorisation accuracy
- Better dashboard analytics
- Expanded OCR support

## Medium Term

- RAG-based finance knowledge base
- Investment portfolio tracking
- Budget forecasting
- Goal planning

## Long Term

- Multi-user support
- Cloud deployment
- Autonomous finance workflows
- Real-time banking integrations
- Production MLOps monitoring

---

# Development Highlights

This project demonstrates practical implementation of:

- Agentic AI systems
- Retrieval and memory architectures
- Human-in-the-loop AI workflows
- LLM orchestration
- FastAPI application development
- Streamlit analytics dashboards
- OCR document pipelines
- Financial anomaly detection
- Vector databases
- Semantic search systems

---

# License

This repository is intended for educational, portfolio, and experimentation purposes. Add an appropriate open-source license if distributing publicly.

---

# Author

Finance Agent was developed as an end-to-end AI engineering project showcasing modern LLM application design, agent orchestration, memory systems, document intelligence, and financial analytics.
