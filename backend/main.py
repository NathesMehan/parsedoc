from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader
from pydantic import BaseModel
import docx
import uuid
import io
import requests
import numpy as np

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

document_store: dict[str, dict] = {}

#Function to chunk the text
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50)-> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size-overlap
    return chunks

#Function to get embedding
def get_embedding(text: str)->list[float]:
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": text}
    )
    response.raise_for_status()
    return response.json()["embedding"]

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    a = np.array(vec1)
    b = np.array(vec2)
    return float(np.dot(a,b) / (np.linalg.norm(a) * np.linalg.norm(b)))

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

    chunks = chunk_text(text)
    embeddings = [get_embedding(chunk) for chunk in chunks]
    
    file_id = str(uuid.uuid4())
    document_store[file_id] = {
        "filename": file.filename,
        "chunks": chunks,
        "embeddings": embeddings
    }

    return{"file_id": file_id, "filename": file.filename, "char_count": len(text), "text": text, "chunk_count": len(chunks)}

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

    doc = document_store[request.file_id]

    question_embedding = get_embedding(request.prompt)

    similarities = [
        cosine_similarity(question_embedding, chunk_embedding)
        for chunk_embedding in doc["embeddings"]
    ]

    top_n = 3
    top_indices = np.argsort(similarities)[::-1][:top_n]
    relevant_chunks = [doc["chunks"][i] for i in top_indices]

    context = "\n\n".join(relevant_chunks)


    #Construct and send the full prompt to Ollama
    full_prompt = f"Context from document: {context}\n\nQuestion:{request.prompt}"
    answer = query_ollama(full_prompt)

    return {"response": answer}






