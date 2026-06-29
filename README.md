# 📖 Manga Search Engine

A search engine for manga panels using natural language descriptions (search by "vibes") rather than exact keywords. Powered by an Angular frontend and a Django backend, it implements panel cropping (OpenCV), semantic embeddings (OpenCLIP), and automated chapter webscraping (including MangaDex integration).

---

## 🚀 Key Features

* **Natural Language Search**: Enter queries like `"chibi shocked face"` or `"action fight scene"` to find semantic matches in the database.
* **Flexible Ingestion**:
  * **Direct Image Upload**: Upload single pages. The backend automatically crops panel boxes using OpenCV, generates vector embeddings using OpenCLIP, and uploads images to the selected storage provider.
  * **Web Scraping Ingestion**: Provide a URL to fetch pages and batch-process all panels.
  * **MangaDex Specific Flow**: Seamless integration with MangaDex chapter URLs. Downloads, processes, splits, and indexes chapters automatically.
* **Optimized Image Pipeline**: Converts uploaded pages into `.avif` formats with custom compression configurations to save storage.
* **Storage Options**: Plug-and-play support for local file storage or Amazon S3.
* **Modern UI**: Clean frontend built with Angular, featuring a responsive search bar, dark mode, and upload tracking.

---

## 🛠️ System Architecture

```mermaid
graph TD
    User([User]) -->|Search & Ingest| FE[Angular Frontend]
    FE -->|Proxy Request| BE[Django Backend]
    
    subgraph Ingestion Pipeline
        BE -->|Process Link| Scraper[Web Scraper / MangaDex Client]
        Scraper -->|Pages| OpenCV[OpenCV Panel Cropper]
        OpenCV -->|Panels| OpenCLIP[OpenCLIP Vector Generator]
        OpenCLIP -->|Embeddings| DB[(PostgreSQL / SQLite)]
        OpenCV -->|Compressed Images| Storage{Storage Backend: Local / S3}
    end

    subgraph Query Pipeline
        BE -->|Vector Search| DB
        BE -->|Fetch Images| Storage
    end
```

---

## 📦 Tech Stack

* **Frontend**: Angular 18+, TypeScript, Vanilla CSS
* **Backend**: Django 4.2+, Python 3.10+
* **Image Processing**: OpenCV, Pillow (PIL)
* **AI/Embeddings**: OpenCLIP, Hugging Face
* **Databases**: SQLite (dev) / PostgreSQL + pgvector (production)
* **Storage**: Local filesystem / AWS S3 / Tinify API (compression offloading)

---

## ⚙️ Development Setup

### 1. Prerequisites
Ensure you have the following installed:
* [Node.js](https://nodejs.org/) (v22.x recommended)
* [Python](https://www.python.org/) (v3.10+)
* [Git](https://git-scm.com/)

---

### 2. Backend Installation

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure your environment variables:
   ```bash
   cp .env.example .env
   ```
   Open the `.env` file and set the required variables. By default, it will fall back to local storage and SQLite if Postgres/S3 variables are left blank.

5. Apply migrations:
   ```bash
   python manage.py migrate
   ```

6. Run the development server:
   ```bash
   python manage.py runserver
   ```
   The backend server will run on `http://127.0.0.1:8000/`.

---

### 3. Frontend Installation

1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```

2. Install Node packages:
   ```bash
   npm install
   ```

3. Start the Angular development server:
   ```bash
   ng serve --open
   ```
   The frontend will compile and automatically open in your default browser at `http://localhost:4200/`.

