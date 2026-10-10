import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, Response
from google import genai
from google.genai import types
import uvicorn

# --- НАСТРОЙКА ПРОКСИ НА УРОВНЕ СИСТЕМЫ ---
proxy_url = "http://XQVMxzHD:t5qPM53G@23.230.241.112:64556"
os.environ["http_proxy"] = proxy_url
os.environ["https_proxy"] = proxy_url

app = FastAPI()

# --- КОНФИГУРАЦИЯ ---
API_KEY = "AIzaSyBDNWzO82m2HCtsyFH_wtnvxldpcqM21jI"

# КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: 
# Мы указываем 'http' в качестве транспорта, так как gRPC через прокси часто выдает 404.
client = genai.Client(
    api_key=API_KEY,
    http_options={'api_version': 'v1beta'}
)

# Используем полное имя модели, которое понимает v1beta
MODEL_ID = "gemini-1.5-flash"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>AI Document Intelligence</title>
    <style>
        :root {
            --apple-blue: #0071e3;
            --apple-bg: #f5f5f7;
            --apple-text: #1d1d1f;
        }
        body { 
            background-color: var(--apple-bg); 
            color: var(--apple-text);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
            margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh;
            -webkit-font-smoothing: antialiased;
        }
        .container { 
            background: white; padding: 48px; border-radius: 24px; 
            box-shadow: 0 10px 40px rgba(0,0,0,0.05); width: 100%; max-width: 500px; 
        }
        h1 { font-size: 34px; font-weight: 600; letter-spacing: -0.022em; margin: 0 0 8px; text-align: center; }
        p { color: #86868b; text-align: center; margin-bottom: 40px; font-size: 19px; }
        .form-group { margin-bottom: 24px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; font-size: 13px; color: #86868b; text-transform: uppercase; }
        select, input { 
            width: 100%; padding: 14px; border-radius: 12px; border: 1px solid #d2d2d7; 
            background: #fbfbfd; font-size: 16px; box-sizing: border-box;
        }
        button { 
            width: 100%; padding: 16px; background: var(--apple-blue); color: white; 
            border: none; border-radius: 980px; font-size: 17px; font-weight: 600; cursor: pointer;
            transition: all 0.2s ease; margin-top: 10px;
        }
        button:hover { opacity: 0.9; transform: scale(0.99); }
        #result { 
            margin-top: 30px; background: #fbfbfd; padding: 20px; border-radius: 12px; 
            font-family: "SF Mono", monospace; font-size: 12px; 
            display: none; overflow-x: auto; border: 1px solid #d2d2d7;
            max-height: 350px; line-height: 1.5; color: #1d1d1f;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Intelligence.</h1>
        <p>OCR сервис (Proxy Mode)</p>
        <form id="uploadForm">
            <div class="form-group">
                <label>Тип документа</label>
                <select name="doc_type">
                    <option value="УПД">Универсальный передаточный документ</option>
                    <option value="Акт">Акт выполненных работ</option>
                    <option value="Счет-фактура">Счет-фактура</option>
                </select>
            </div>
            <div class="form-group">
                <label>PDF Файл</label>
                <input type="file" name="file" accept="application/pdf" required>
            </div>
            <button type="submit">Сформировать XML</button>
        </form>
        <div id="loader" style="display:none; text-align:center; margin-top:20px; color:var(--apple-blue);">ИИ распознает данные...</div>
        <pre id="result"></pre>
    </div>

    <script>
        const form = document.getElementById('uploadForm');
        form.onsubmit = async (e) => {
            e.preventDefault();
            document.getElementById('loader').style.display = 'block';
            document.getElementById('result').style.display = 'none';

            const formData = new FormData(form);
            try {
                const response = await fetch('/process', { method: 'POST', body: formData });
                const text = await response.text();
                if (!response.ok) throw new Error(text);
                document.getElementById('loader').style.display = 'none';
                document.getElementById('result').innerText = text;
                document.getElementById('result').style.display = 'block';
            } catch (err) {
                document.getElementById('loader').innerText = "Ошибка: " + err.message;
            }
        };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE

@app.post("/process")
async def process(file: UploadFile = File(...), doc_type: str = Form(...)):
    try:
        file_bytes = await file.read()
        
        # Инструкция для ИИ
        prompt = f"""
        Ты эксперт ФНС. Распознай PDF ({doc_type}). 
        Сформируй XML строго по схеме ON_NSCHFDOPPR (КНД 1115131). 
        Номер и дату ищи в первой строке документа.
        Выдай ТОЛЬКО чистый XML текст без Markdown.
        """

        # Вызов через новую библиотеку
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
                prompt
            ]
        )

        xml_clean = response.text.replace("```xml", "").replace("```", "").strip()
        return Response(content=xml_clean, media_type="application/xml")

    except Exception as e:
        return Response(content=f"API Error: {str(e)}", status_code=500)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=2000)