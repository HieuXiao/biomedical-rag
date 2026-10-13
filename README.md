# Healthcare RAG

Clinical Healthcare AI RAG Mockup Project.

## Tổng quan

Ứng dụng trợ lý y tế dựa trên RAG (Retrieval Augmented Generation), gồm FastAPI backend và React + Vite frontend. Hệ thống truy xuất từ Vector DB, xử lý OCR cho PDF, và hỏi đáp bằng Gemini.

## Kiến trúc

Luồng chính:

1. Người dùng nhập câu hỏi trên giao diện React.
2. Frontend gọi `POST /api/chat` đến FastAPI.
3. Backend dựa vào LlamaIndex: truy xuất từ Vector DB, sau đó gọi Gemini để sinh câu trả lời.
4. Trả về câu trả lời + nguồn tài liệu.

Thành phần chính:

- Frontend: [frontend/](frontend/) (React 19, Vite 8)
- Backend API: [backend/main.py](backend/main.py)
- Routing: [backend/api/routes.py](backend/api/routes.py)
- RAG engine: [backend/core/generator.py](backend/core/generator.py)
- Ingestion + OCR: [backend/core/ingestion.py](backend/core/ingestion.py), [backend/core/ocr_reader.py](backend/core/ocr_reader.py)
- Vector DB on disk: [backend/vector_db/](backend/vector_db/)
- Usage tracking: [backend/data/model_usage.json](backend/data/model_usage.json)

## Công nghệ

Backend:

- FastAPI, Uvicorn
- LlamaIndex (RAG)
- Gemini (Google GenAI) cho LLM
- HuggingFace Embeddings (keepitreal/vietnamese-sbert)
- OCR: PyMuPDF, Tesseract, pdf2image, Pillow

Frontend:

- React 19, Vite 8

## Tools / Yêu cầu

- Python 3.10+ (khuyến nghị 3.11)
- Node.js 18+ và npm
- Tesseract OCR (có thêm ngôn ngữ `vie`)
- Poppler (cần cho `pdf2image` nếu chạy trên Windows)

## Cấu hình biến môi trường

Backend đọc biến môi trường từ `backend/.env`.

Tối thiểu:

```env
GEMINI_API_KEY=your_key_here
# hoặc
GOOGLE_API_KEY=your_key_here
```

Tùy chọn:

```env
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8001
UVICORN_RELOAD=true
```

Frontend có thể dùng `frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## Hướng dẫn chạy project

### 1) Cài đặt backend

```powershell
cd backend
python -m venv .venv
\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu cần, chạy ingestion để tạo Vector DB (đọc file từ `backend/data`):

```powershell
python core\ingestion.py
```

Chạy API:

```powershell
python main.py
```

Mặc định API ở `http://127.0.0.1:8001`.

### 2) Cài đặt frontend

```powershell
cd ..\frontend
npm install
npm run dev
```

Truy cập UI theo URL Vite in ra (thường là `http://127.0.0.1:5173`).

## API chính

- `GET /api/models`: danh sách model + usage
- `POST /api/chat`: hỏi đáp RAG

## Thư mục dữ liệu

- `backend/data/`: chứa PDF/TXT đầu vào
- `backend/vector_db/`: Vector DB được tạo từ ingestion

## Ghi chú

- Hệ thống có thể dùng API key mặc định từ .env hoặc API key người dùng nhập trên UI.
- Khi model hết quota, frontend sẽ tự động chuyển sang model tiếp theo nếu có.
