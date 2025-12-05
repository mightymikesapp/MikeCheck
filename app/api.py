"""FastAPI backend for MikeCheck Web UI.

Exposes the core legal research tools via REST endpoints.
"""

import io
import logging
import re
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pypdf import PdfReader

from app.tools.research import run_research_pipeline_impl
from app.tools.search import semantic_search_impl
from app.tools.treatment import check_case_validity_impl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MikeCheck API",
    description="Backend API for MikeCheck Legal Assistant",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for simplicity during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    citation: str

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class ResearchRequest(BaseModel):
    citations: List[str]
    key_questions: Optional[List[str]] = None

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF content."""
    try:
        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""

def extract_citations(text: str) -> list[str]:
    """Extract legal citations from text using regex."""
    pattern = r"(\d+)\s+([A-Za-z\d\.\s]+?)\s+(\d+)"

    matches = re.finditer(pattern, text)
    citations = []

    EXCLUDED_TERMS = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "section", "sec", "id", "at", "and", "or", "the", "see", "cf"
    }

    for match in matches:
        volume = match.group(1)
        reporter = match.group(2).strip()
        page = match.group(3)

        if len(reporter) < 2:
            continue
        if reporter.lower() in EXCLUDED_TERMS:
            continue
        if reporter.isdigit():
            continue
        if len(reporter) == 4 and reporter.isdigit():
            continue

        citation = f"{volume} {reporter} {page}"
        citations.append(citation)

    return list(set(citations))

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "MikeCheck API"}

@app.post("/analyze/upload")
async def upload_document(file: UploadFile = File(...)):
    """Handle document upload and parsing."""
    try:
        content = await file.read()
        filename = file.filename.lower()

        text = ""
        if filename.endswith(".pdf"):
            text = extract_text_from_pdf(content)
        elif filename.endswith(".txt"):
            text = content.decode("utf-8")
        else:
            text = content.decode("utf-8", errors="ignore")

        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from file")

        citations = extract_citations(text)

        return {
            "filename": file.filename,
            "status": "uploaded",
            "detected_citations": sorted(citations),
            "summary": f"Successfully extracted {len(citations)} citations from document."
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/herding/analyze")
async def analyze_citation(request: AnalysisRequest):
    """Run treatment analysis on a citation."""
    try:
        result = await check_case_validity_impl(request.citation)
        return {
            "citation": request.citation,
            "status": "completed",
            "result": result
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/similar")
async def find_similar(request: SearchRequest):
    """Find similar cases using semantic search."""
    try:
        result = await semantic_search_impl(request.query, request.limit)
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/research/analyze")
async def run_research(request: ResearchRequest):
    """Run comprehensive research pipeline."""
    try:
        result = await run_research_pipeline_impl(request.citations, request.key_questions)
        return result
    except Exception as e:
        logger.error(f"Research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
