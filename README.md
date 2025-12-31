# SmartAgent-RAG: Advanced AI Assistant

SmartAgent-RAG is a professional **Local RAG (Retrieval-Augmented Generation)** system designed for the Legal Tech sector. It enables law firms and legal professionals to chat with their own document archives (PDF, DOCX, DOC) using advanced LLM capabilities (GPT-4o/GPT-5.2), securely and efficiently.

**Developed by:** Idan Suliman 

---

## 🚀 Key Features

*   **Smart Incremental Indexing**: Efficiently processes only new or modified files, detecting changes via robust hashing (Name + Size + Modified Time). Reuse existing chunks to save time and API costs.
*   **Ad-Hoc File Analysis**: Upload files directly into the chat for immediate, temporary analysis without permanently adding them to the database.
*   **Professional UI/UX**: A clean, "Legal Tech" dark-mode interface built with Vanilla JS and CSS for maximum speed and simplicity.
*   **Hybrid Search**: Combines **Semantic Search** (OpenAI Embeddings) with **Lexical Search** (BM25) for high-precision retrieval of legal precedents.
*   **Secure & Local**: All document vectors and indexes are stored locally. API keys are managed securely via environment variables.

---

## 📦 Installation & Usage

Choose the method that works best for you.

### Option 1: Standalone Windows App (Quick Start)
*No Python installation required.*

1.  **Setup Files**: Download the executable (`.exe`). **Crucial**: Ensure your `.env` file is placed in the same folder as the executable.
2.  **Launch**: Double-click `SmartAgentRAG.exe` to open the application.
3.  **Activate System (Required)**:
    *   Go to the **Model Training** tab.
    *   In the **Key** field (side panel), enter the code: `1111`.
4.  **Configure API**: Go to the **Settings** tab and paste your OpenAI API Key.
5.  **Add Data**: Place your document files into the `INBOX` folder.
6.  **Process Data**:
    *   On the web interface, click **Generate Chunks**.
    *   Immediately after, click **Generate Vectors**.
7.  **Success!**: The model is now fully operational. Good luck!

### Option 2: Run from Source (For Developers)

**Prerequisites**:
*   **Python 3.10+**
*   **OpenAI API Key**

1.  **Clone & Setup**:
    ```bash
    git clone https://github.com/your-username/SmartAgent-RAG.git
    cd SmartAgent-RAG
    
    python -m venv .venv
    # Windows: .venv\Scripts\activate
    # Mac/Linux: source .venv/bin/activate
    
    pip install -r requirements.txt
    ```

2.  **Configure API Key**:
    *   Create a `.env` file in the root directory.
    *   Add `OPENAI_API_KEY=sk-your-key-here`.

3.  **Run**:
    ```bash
    uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
    ```
    Open `http://localhost:8000` in your browser.

---

## 📚 Usage Guide

### 1. Building the Knowledge Base (Indexing)
*   Place your legal documents (PDF, DOCX, TXT) into the `data/INBOX` folder.
*   In the app, go to the **"Dev / Index"** tab.
*   Enter the Admin Password (default: `1111`) to unlock.
*   Click **"Sync (Smart Index)"**. The system will scan `data/INBOX`, chunk the files, and prepare them for search.
*   Once indexing is complete, click **"Generate Vectors"** to create the embeddings.

### 2. Chatting & Research
*   Go to the **"Chat"** tab.
*   Select your preferred model (e.g., GPT-4o).
*   Type a legal question. The system will search your local index, cite relevant sources, and generate a professional response.

### 3. Ad-Hoc File Upload
*   Need to ask a question about a specific contract not in the DB?
*   Click the **Paperclip Icon** in the chat window.
*   Upload the file. It will be analyzed instantly for the current conversation context.

---

## 📂 Project Structure

```
SmartAgent-RAG/
├── backend/
│   ├── app/
│   │   ├── api/            # API Endpoints (Chat, Indexing, Admin)
│   │   ├── core/           # Core Logic (Search Engine, Chunking, Config)
│   │   ├── static/         # Frontend Assets (HTML, CSS, JS)
│   │   ├── main.py         # App Entry Point
│   │   └── settings.py     # Configuration
├── data/
│   ├── INBOX/              # Put your documents here
│   ├── INDEX/              # Generated indices (chunks.jsonl, embeddings.npy)
└── requirements.txt        # Python Dependencies
```

---

## 🛡️ Security Note

*   **API Keys**: Your keys are stored locally in `.env`. Never commit this file to public repositories.
*   **Authentication**: The Admin panel is protected by a simple passcode. For production deployment, implement robust authentication (OAuth2).

---

**License**: MIT
