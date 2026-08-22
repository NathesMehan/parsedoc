from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from pydantic import BaseModel
import docx
import uuid
import io
import requests

class QueryRequest(BaseModel):
    file_id: str
    prompt: str


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

#In-memory storage: {file_id: extracted_text}
document_store: dict[str, str] = {}

#Function to extract text from a PDF document
def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text

#Function to extract text from a Word Document
def extract_text_from_docx(file_bytes: bytes) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)

@app.get("/")
def read_root():
    return{"status": "ParseDoc backend is running"}

#Function to receive POST request when a user uploads a file
@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    file_bytes = await file.read()
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(file_bytes)
    elif filename.endswith(".docx"):
        text = extract_text_from_docx(file_bytes)
    elif filename.endswith(".txt"):
        text=file_bytes.decode("utf-8")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. File must be either PDF, DOCX, or TXT")

    if not text.strip():
        raise HTTPException(status_code=400, detail = "Could not extract any text from this file.")

    file_id = str(uuid.uuid4())
    document_store[file_id] = text

    return{"file_id": file_id, "filename": file.filename, "char_count": len(text), "text": text}

#Function to query Ollama
def query_ollama(prompt:str, model: str = "llama3.2") -> str:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 1024
            }
        }
    )
    response.raise_for_status()
    return response.json()["response"]

#Function to receive POST request when user asks something about the file
@app.post("/query")
def query_document(request: QueryRequest):

    #Check if file exists
    if request.file_id not in document_store:
        raise HTTPException(status_code=404, detail = "File not found. Did you upload it first?")

    document_text = document_store[request.file_id]

    #Construct and send the full prompt to Ollama
    full_prompt = f"Document:{document_text}\n\nInstruction:{request.prompt}"
    answer = query_ollama(full_prompt)

    return {"response": answer}






