"""FastAPI backend for MikeCheck Web UI.

Exposes the core legal research tools via REST endpoints.
"""

import io
import logging
import re
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
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

# Setup Templates
templates = Jinja2Templates(directory="app/templates")

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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/analyze/upload")
async def upload_document(request: Request, file: UploadFile = File(...)):
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

        citations = sorted(extract_citations(text))

        # Check for HTMX request
        if request.headers.get("hx-request"):
            return templates.TemplateResponse(
                "partials/citation_rows.html",
                {"request": request, "citations": citations}
            )

        return {
            "filename": file.filename,
            "status": "uploaded",
            "detected_citations": citations,
            "summary": f"Successfully extracted {len(citations)} citations from document."
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        if request.headers.get("hx-request"):
             return HTMLResponse(f"<div class='p-4 text-red-600'>Error: {str(e)}</div>")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/herding/analyze")
async def analyze_citation(request: AnalysisRequest):
    """Run treatment analysis on a citation (JSON API)."""
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

@app.post("/herding/analyze_html")
async def analyze_citation_html(request: Request, citation: str = Form(...), index: int = Form(0)):
    """Run treatment analysis on a citation (HTMX)."""
    try:
        result = await check_case_validity_impl(citation)
        return templates.TemplateResponse(
            "partials/citation_row_result.html",
            {
                "request": request,
                "result": result,
                "index": index
            }
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return HTMLResponse(f"<div class='text-red-600'>Error analyzing {citation}: {str(e)}</div>")

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

@app.post("/herding/details_html")
async def analyze_citation_details(request: Request, citation: str = Form(...)):
    """Get detailed treatment analysis for modal."""
    try:
        # Re-run or get cached analysis
        result = await check_case_validity_impl(citation)
        return templates.TemplateResponse(
            "partials/modal_treatment_details.html",
            {
                "request": request,
                "result": result
            }
        )
    except Exception as e:
        logger.error(f"Details failed: {e}")
        return HTMLResponse(f"<div class='p-4 text-red-600'>Error: {str(e)}</div>")

@app.post("/search/similar_html")
async def find_similar_html(request: Request, query: str = Form(...)):
    """Find similar cases returning HTML."""
    try:
        # Use semantic search
        result = await semantic_search_impl(query, limit=5)
        return templates.TemplateResponse(
            "partials/similar_cases_list.html",
            {
                "request": request,
                "results": result["results"]
            }
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return HTMLResponse(f"<div class='p-4 text-red-600'>Error: {str(e)}</div>")

# Mount static files (legacy support and for serving other assets if needed)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
