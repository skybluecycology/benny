"""
RAG Routes - Document ingestion and semantic search
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import fitz  # PyMuPDF

from ..core.workspace import get_workspace_path
from ..tools.knowledge import get_chromadb_client
from ..core.models import LOCAL_PROVIDERS, configure_local_provider
from ..core.models import LOCAL_PROVIDERS, configure_local_provider
import httpx
import json


router = APIRouter()


class IngestRequest(BaseModel):
    workspace: str = "default"
    notebook_id: Optional[str] = None  # If provided, use notebook-scoped collection
    files: Optional[List[str]] = None  # If None, ingest all files



class QueryRequest(BaseModel):
    query: str
    workspace: str = "default"
    top_k: int = 20
    provider: Optional[str] = "fastflowlm"
    model: Optional[str] = None


def extract_text_from_file(file_path: Path) -> str:
    """Extract text from various file types"""
    ext = file_path.suffix.lower()
    
    if ext == '.txt' or ext == '.md':
        return file_path.read_text(encoding='utf-8')
    
    elif ext == '.pdf':
        doc = fitz.open(file_path)
        text = ""
        is_scanned = True
        
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                is_scanned = False
            text += page_text
            
        if is_scanned and not text.strip():
            print(f"File {file_path.name} is scanned. Running OCR...")
            import pytesseract
            from PIL import Image
            import io
            import sys
            
            if sys.platform == 'win32':
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                
            text = ""
            # Limit OCR to max 25 pages to avoid extreme API timeouts for massive books
            # In a production system, this should run asynchronously.
            limit = min(25, len(doc))
            for i in range(limit):
                print(f"OCRing page {i+1}/{limit}...", end="\r", flush=True)
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text += pytesseract.image_to_string(img) + "\n\n"
            print(f"\\nFinished OCR. Extracted {len(text)} chars.\\n")
            
        doc.close()
        return text
    
    else:
        raise ValueError(f"Unsupported file type: {ext}")


@router.post("/rag/ingest")
async def ingest_files(request: IngestRequest):
    """Ingest files from data_in into ChromaDB"""
    try:
        data_in_path = get_workspace_path(request.workspace, "data_in")
        
        if not data_in_path.exists():
            raise HTTPException(404, "No files found in data_in")
        
        # Get files to ingest
        if request.files:
            file_paths = [data_in_path / f for f in request.files]
        else:
            file_paths = list(data_in_path.glob("*.*"))
        
        # Filter for supported types
        supported = ['.txt', '.md', '.pdf']
        file_paths = [f for f in file_paths if f.suffix.lower() in supported]
        
        if not file_paths:
            raise HTTPException(404, "No supported files found")
        
        # Get ChromaDB client
        client = get_chromadb_client(request.workspace)
        
        # Use notebook-scoped collection if notebook_id provided
        if request.notebook_id:
            collection_name = f"notebook_{request.notebook_id}"
        else:
            collection_name = "knowledge"
        
        collection = client.get_or_create_collection(collection_name)

        
        # Ingest files
        ingested = []
        for file_path in file_paths:
            try:
                text = extract_text_from_file(file_path)
                
                # Simple chunking (split by paragraphs)
                chunks = [c.strip() for c in text.split('\n\n') if c.strip()]
                
                # Add to ChromaDB
                for i, chunk in enumerate(chunks):
                    collection.add(
                        documents=[chunk],
                        metadatas=[{
                            "source": file_path.name,
                            "chunk_index": i
                        }],
                        ids=[f"{file_path.stem}_{i}"]
                    )
                
                ingested.append({
                    "file": file_path.name,
                    "chunks": len(chunks)
                })
            except Exception as e:
                ingested.append({
                    "file": file_path.name,
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "workspace": request.workspace,
            "ingested": ingested,
            "total_documents": collection.count()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@router.get("/rag/status")
async def get_rag_status(workspace: str = "default"):
    """Get RAG status and document count"""
    try:
        client = get_chromadb_client(workspace)
        collection = client.get_or_create_collection("knowledge")
        
        # Get unique sources
        all_data = collection.get(include=['metadatas'])
        sources = set()
        for meta in all_data['metadatas']:
            sources.add(meta.get('source', 'Unknown'))
        
        return {
            "workspace": workspace,
            "total_chunks": collection.count(),
            "unique_documents": len(sources),
            "documents": list(sources)
        }
    except Exception as e:
        raise HTTPException(500, f"Status check failed: {str(e)}")


@router.post("/rag/query")
async def query_rag(request: QueryRequest):
    """Test semantic search"""
    try:
        client = get_chromadb_client(request.workspace)
        collection = client.get_or_create_collection("knowledge")
        
        if collection.count() == 0:
            return {
                "results": [],
                "message": "Knowledge base is empty"
            }
        
        results = collection.query(
            query_texts=[request.query],
            n_results=min(request.top_k, collection.count())
        )
        
        formatted_results = []
        for doc, meta, distance in zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ):
            formatted_results.append({
                "text": doc,
                "source": meta.get('source', 'Unknown'),
                "relevance": round((1 - distance) * 100, 1)
            })
        

        return {
            "query": request.query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Query failed: {str(e)}")


@router.post("/rag/chat")
async def chat_rag(request: QueryRequest):
    """RAG-augmented chat for workspace documents"""
    try:
        # 1. Retrieve context
        client = get_chromadb_client(request.workspace)
        collection = client.get_or_create_collection("knowledge")
        
        context_text = ""
        sources = []
        
        if collection.count() > 0:
            import re
            from pathlib import Path
            all_data = collection.get(include=['metadatas'])
            available_sources = set(meta.get('source', 'Unknown') for meta in all_data['metadatas'] if 'source' in meta)
            
            mentioned_sources = []
            query_lower = request.query.lower()
            for source in available_sources:
                source_stem = Path(source).stem.lower()
                words = [w for w in set(re.split(r'[^a-zA-Z0-9]', source_stem)) if len(w) > 3]
                for w in words:
                    if w in query_lower:
                        mentioned_sources.append(source)
                        break
                        
            results_list = []
            
            if mentioned_sources:
                k_per_source = max(3, request.top_k // len(mentioned_sources))
                for source in mentioned_sources:
                    try:
                        res = collection.query(
                            query_texts=[request.query],
                            n_results=min(k_per_source, collection.count()),
                            where={"source": source}
                        )
                        if res['documents'] and res['documents'][0]:
                            for doc, meta in zip(res['documents'][0], res['metadatas'][0]):
                                results_list.append((doc, meta))
                    except Exception:
                        pass
                
                # add a few general query chunks too
                try:
                    gen_res = collection.query(
                        query_texts=[request.query],
                        n_results=min(3, collection.count())
                    )
                    if gen_res['documents'] and gen_res['documents'][0]:
                        for doc, meta in zip(gen_res['documents'][0], gen_res['metadatas'][0]):
                            results_list.append((doc, meta))
                except Exception:
                    pass
            else:
                try:
                    res = collection.query(
                        query_texts=[request.query],
                        n_results=min(request.top_k, collection.count())
                    )
                    if res['documents'] and res['documents'][0]:
                        for doc, meta in zip(res['documents'][0], res['metadatas'][0]):
                            results_list.append((doc, meta))
                except Exception:
                    pass

            seen_docs = set()
            for doc, meta in results_list:
                if doc not in seen_docs:
                    seen_docs.add(doc)
                    source = meta.get('source', 'Unknown')
                    context_text += f"[Source: {source}]\n{doc}\n\n"
                    sources.append(source)

        
        # 2. Build Prompt
        system_prompt = """You are a helpful AI assistant for the user's workspace.
Answer questions based on the provided context.
If the answer is not in the context, say so, but you can use general knowledge to help explain if relevant.
Always cite your sources when using the context."""

        user_prompt = f"""CONTEXT FROM DOCUMENTS:
{context_text if context_text else "No specific documents found."}

USER QUESTION:
{request.query}

ANSWER:"""

        # 3. Call LLM
        try:
            # Configure provider settings
            provider_name = request.provider or "fastflowlm"
            provider_config = LOCAL_PROVIDERS.get(provider_name, LOCAL_PROVIDERS["fastflowlm"])
            
            debug_response = {}
            payload = {}
            
            # Configure API base and key for this request
            # Note: litellm uses env vars, but we can pass api_base/api_key explicitly if needed
            # or set them temproarily. Since requests might be concurrent, 
            # passing params to completion() is safer if supported, but for local use 
            # env vars are often expected.
            
            # For local models, we construct the model string expected by litellm
            # E.g. "openai/custom" pointing to local base_url
            

            # Determine model name
            if request.model:
                # Lemonade models are often registered as e.g 'amd/Qwen3...' but the backend
                # expects just the base name when chatting.
                model_name = request.model.split('/')[-1]
            else:
                if provider_name == "ollama":
                    model_name = "llama3"
                elif provider_name == "lemonade":
                    model_name = "amd/Qwen3-8B-Hybrid-quantized_int4-float16-cpu-onnx"
                elif provider_name == "fastflowlm":
                    model_name = "gemma3:4b"
                else:
                    model_name = "default"

            # Use httpx for direct API call to avoid litellm dependency issues
            api_base = provider_config["base_url"]
            chat_url = f"{api_base}/chat/completions"
            
            # Combine system and user prompt to ensure compatibility with all local models
            if provider_name == "fastflowlm":
                # FastFlowLM (Gemma 3) prefers acceptable instruction format.
                # Use a specific structure that proved to work in testing.
                # We limit context to ~4000 chars to avoid overflowing local model context window (often 8k or 4k)
                safe_context = context_text[:4000] if context_text else "No specific documents found."
                content = f"Instructions: {system_prompt}\n\nContext:\n{safe_context}\n\nUser Question: {request.query}\n\nAnswer:"
            else:
                 content = f"{system_prompt}\n\n{user_prompt}"
            
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": content}
                ],
                "temperature": 0.7
            }
            
            # print(f"DEBUG PAYLOAD: {json.dumps(payload)}")
            
            print(f"DEBUG: Calling {chat_url} with model {model_name}")
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    chat_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    answer = data['choices'][0]['message']['content']
                    debug_response = data
                else:
                    error_msg = f"Status {response.status_code}: {response.text}"
                    print(f"LLM Error: {error_msg}")
                    answer = f"Error from {request.provider}: {error_msg}"
                    debug_response = {"error": error_msg}

        except Exception as llm_error:
            error_details = str(llm_error) if str(llm_error) else repr(llm_error)
            print(f"LLM Exception: {error_details}")
            answer = f"Connection error with {request.provider}: {error_details}. Please check if the service is running or if the model timed out preparing the response."
            debug_response = {"exception": error_details}

        return {
            "answer": answer,
            "sources": list(set(sources)),
            "query": request.query,
            "debug_payload": payload,
            "debug_response": debug_response
        }

    except Exception as e:
        raise HTTPException(500, f"Chat failed: {str(e)}")
