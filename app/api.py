"""FastAPI backend for MikeCheck Web UI.

Exposes the core legal research tools via REST endpoints.
"""

import logging
from typing import Any

import re
import io
import json
from pypdf import PdfReader
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.analysis.treatment_classifier import TreatmentClassifier
from app.analysis.citation_network import CitationNetworkBuilder
from app.tools.search import search_server
from app.config import settings
from app.mcp_client import get_client

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
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    citation: str

# Initialize tools
treatment_classifier = TreatmentClassifier()

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
    # Common patterns:
    # 410 U.S. 113
    # 123 F.3d 456
    # 123 F. Supp. 2d 456
    # 17 Cal. 4th 800
    
    # Regex explanation:
    # (\d+)       : Volume number
    # \s+         : Space
    # ([A-Za-z\d\.\s]+?) : Reporter abbreviation (non-greedy, allows letters, numbers, dots, spaces)
    # \s+         : Space
    # (\d+)       : Page number
    pattern = r"(\d+)\s+([A-Za-z\d\.\s]+?)\s+(\d+)"
    
    matches = re.finditer(pattern, text)
    citations = []
    
    # Terms to exclude if found as the "reporter"
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
        
        # Basic validation
        if len(reporter) < 2:
            continue
            
        # Check against excluded terms (case-insensitive)
        if reporter.lower() in EXCLUDED_TERMS:
            continue
            
        # Filter out purely numeric reporters (unlikely)
        if reporter.isdigit():
            continue
            
        # Filter out if reporter looks like a year (e.g. "1999")
        if len(reporter) == 4 and reporter.isdigit():
            continue

        # Normalize: 410 U.S. 113
        citation = f"{volume} {reporter} {page}"
        citations.append(citation)
        
    # Deduplicate and return unique citations
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
            # Fallback for other types or mock
            text = content.decode("utf-8", errors="ignore")

        if not text:
            raise HTTPException(status_code=400, detail="Could not extract text from file")

        citations = extract_citations(text)
        
        return {
            "filename": file.filename,
            "status": "uploaded",
            "detected_citations": citations[:20], # Limit to top 20
            "summary": f"Successfully extracted {len(citations)} citations from document."
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/herding/analyze")
async def analyze_citation(request: AnalysisRequest):
    """Run treatment analysis on a citation."""
    try:
        client = get_client()
        
        # 1. Search for the case to get metadata
        search_results = await client.search_opinions(q=f'citation:"{request.citation}"', limit=1)
        if not search_results.get("results"):
            logger.warning(f"Case not found for citation: {request.citation}")
            # Try a looser search without quotes if strict search fails
            search_results = await client.search_opinions(q=request.citation, limit=1)
            if not search_results.get("results"):
                 raise HTTPException(status_code=404, detail=f"Case not found for citation: {request.citation}")
            
        target_case = search_results["results"][0]
        # Log the full case data for debugging
        logger.info(f"Target case data: {json.dumps(target_case, default=str)}")
        
        target_case_id = target_case.get("id")
        if not target_case_id:
            # Try cluster_id as fallback
            if target_case.get("cluster_id"):
                target_case_id = target_case["cluster_id"]
                logger.info(f"Using cluster_id {target_case_id} as fallback")
            
            # Try resource_uri
            elif target_case.get("resource_uri"):
                resource_uri = target_case.get("resource_uri", "")
                match = re.search(r"/(\d+)/?$", resource_uri)
                if match:
                    target_case_id = match.group(1)
                    logger.info(f"Extracted ID {target_case_id} from resource_uri")
            
            if not target_case_id:
                logger.error("CRITICAL: Could not find any ID (id, cluster_id, resource_uri) in case data")
                raise HTTPException(status_code=500, detail="Found case but could not determine ID. See server logs.")
        
        target_case_id = str(target_case_id)
        
        # 2. Find citing cases (simulated depth 1 for speed)
        # In a real full run, we'd use CitationNetworkBuilder, but for this quick check
        # we'll just fetch a few citing opinions to analyze.
        # We use the citation string to find cases that cite it.
        citing_docs = await client.find_citing_cases(request.citation, limit=10)
        citing_list = citing_docs.get("results", [])
        
        # 3. Analyze treatment for each citing case
        treatments = []
        for citing in citing_list:
            # We need text to analyze. If snippet is empty, we might skip or fetch full text.
            # For speed, we rely on snippets first.
            analysis = treatment_classifier.classify_treatment(citing, request.citation)
            treatments.append(analysis)
            
        # 4. Aggregate results
        aggregated = treatment_classifier.aggregate_treatments(treatments, request.citation)
        
        # Format detailed results for frontend
        detailed_treatments = []
        for t in treatments:
            detailed_treatments.append({
                "case_name": t.case_name,
                "date": t.date_filed,
                "treatment": t.treatment_type.value,
                "confidence": t.confidence,
                "excerpt": t.excerpt
            })
        
        return {
            "citation": request.citation,
            "status": "completed",
            "result": {
                "is_good_law": aggregated.is_good_law,
                "confidence": aggregated.confidence,
                "summary": aggregated.summary,
                "positive_count": aggregated.positive_count,
                "negative_count": aggregated.negative_count,
                "neutral_count": aggregated.neutral_count,
                "treatments": detailed_treatments
            }
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/similar")
async def find_similar(request: AnalysisRequest):
    """Find similar cases (Placeholder)."""
    # TODO: Implement real similarity search (e.g. using embeddings or more complex queries)
    return {
        "citation": request.citation,
        "results": [
            {"case_name": "Planned Parenthood v. Casey", "similarity": 0.89, "note": "Simulated Result"},
            {"case_name": "Dobbs v. Jackson", "similarity": 0.85, "note": "Simulated Result"}
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
