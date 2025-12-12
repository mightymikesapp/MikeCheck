"""FastAPI backend for MikeCheck Web UI.

Exposes the core legal research tools via REST endpoints.
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, AsyncGenerator, List, Optional

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.analysis.document_processing import extract_citations, extract_text_from_pdf
from app.config import settings
from app.tools.research import issue_map_impl, run_research_pipeline_impl
from app.tools.search import semantic_search_impl
from app.tools.treatment import check_case_validity_impl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Graceful shutdown state
_shutdown_event: asyncio.Event | None = None


def _signal_handler(sig: int, frame: Any) -> None:
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    sig_name = signal.Signals(sig).name
    logger.info(
        "Shutdown signal received",
        extra={"signal": sig_name, "event": "signal_received"}
    )
    # Set shutdown event if running in async context
    if _shutdown_event:
        _shutdown_event.set()
    # Exit gracefully
    sys.exit(0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown events.

    Handles:
    - Registering signal handlers on startup
    - Graceful shutdown with connection draining
    - Resource cleanup (cache, connections, etc.)
    """
    global _shutdown_event

    # STARTUP
    logger.info("Application startup initiated", extra={"event": "startup_start"})

    # Initialize shutdown event for signal handling
    _shutdown_event = asyncio.Event()

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info(
        "Signal handlers registered (SIGTERM, SIGINT)",
        extra={"event": "startup_complete"}
    )

    try:
        yield
    except Exception as e:
        logger.error(
            f"Error during application lifecycle: {e}",
            extra={"event": "error", "error": str(e)}
        )
    finally:
        # SHUTDOWN
        logger.info("Application shutdown initiated", extra={"event": "shutdown_start"})

        # Give in-flight requests time to complete (connection drain)
        # This delay allows clients to notice connection close and reconnect
        drain_timeout = 15  # seconds
        logger.info(
            f"Draining connections (waiting {drain_timeout}s for in-flight requests)",
            extra={"event": "draining", "timeout_seconds": drain_timeout}
        )
        await asyncio.sleep(drain_timeout)

        # Clean up resources
        logger.info("Cleaning up resources", extra={"event": "cleanup_start"})

        # Close caches if they have close methods
        try:
            # Placeholder for future cache cleanup
            # await cache_manager.close()
            pass
        except Exception as e:
            logger.error(f"Error closing cache: {e}")

        logger.info("Shutdown complete", extra={"event": "shutdown_complete"})

app = FastAPI(
    title="MikeCheck API",
    description="Backend API for MikeCheck Legal Assistant",
    version="0.1.0",
    lifespan=lifespan,  # Enable graceful shutdown handling
)

# Configure CORS from settings (environment-configurable)
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
cors_methods = [method.strip() for method in settings.cors_methods.split(",")]
cors_headers = [header.strip() for header in settings.cors_headers.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add comprehensive security headers to all responses."""
    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Prevent XSS attacks
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy
    if settings.enable_csp:
        response.headers["Content-Security-Policy"] = settings.csp_policy

    # HSTS (HTTP Strict Transport Security) - production only
    if settings.enable_hsts:
        response.headers["Strict-Transport-Security"] = (
            f"max-age={settings.hsts_max_age}; includeSubDomains; preload"
        )

    # Permissions Policy (formerly Feature-Policy)
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), microphone=(), payment=(), usb=()"
    )

    return response


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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "MikeCheck API"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Serve the main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze/upload")
async def upload_document(request: Request, file: UploadFile = File(...)) -> Any:
    """Handle document upload and parsing."""
    try:
        content = await file.read()
        filename = (file.filename or "").lower()

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
                {"request": request, "citations": citations},
            )

        return {
            "filename": file.filename,
            "status": "uploaded",
            "detected_citations": citations,
            "summary": f"Successfully extracted {len(citations)} citations from document.",
        }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        if request.headers.get("hx-request"):
            return templates.TemplateResponse(
                "partials/error.html", {"request": request, "error": str(e)}
            )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/herding/analyze")
async def analyze_citation(request: AnalysisRequest) -> dict[str, Any]:
    """Run treatment analysis on a citation (JSON API)."""
    try:
        result = await check_case_validity_impl(request.citation)
        return {
            "citation": request.citation,
            "status": "completed",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/herding/analyze_html")
async def analyze_citation_html(
    request: Request, citation: str = Form(...), index: int = Form(0)
) -> Any:
    """Run treatment analysis on a citation (HTMX)."""
    try:
        result = await check_case_validity_impl(citation)
        return templates.TemplateResponse(
            "partials/citation_row_result.html",
            {"request": request, "result": result, "index": index},
        )
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": f"Error analyzing {citation}: {str(e)}"},
        )


@app.post("/search/similar")
async def find_similar(request: SearchRequest) -> dict[str, Any]:
    """Find similar cases using semantic search."""
    try:
        result = await semantic_search_impl(request.query, request.limit)
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/research/analyze")
async def run_research(request: ResearchRequest) -> dict[str, Any]:
    """Run comprehensive research pipeline."""
    try:
        result = await run_research_pipeline_impl(request.citations, request.key_questions)
        return result
    except Exception as e:
        logger.error(f"Research failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/research/issue_map_html")
async def get_issue_map_html(
    request: Request, primary_case: str = Form(...), key_questions: Optional[str] = Form(None)
) -> Any:
    """Generate issue map and return HTML."""
    try:
        questions_list = [q.strip() for q in key_questions.split("\n")] if key_questions else None
        result = await issue_map_impl(primary_case=primary_case, key_questions=questions_list)
        return templates.TemplateResponse(
            "partials/issue_map_results.html", {"request": request, "result": result}
        )
    except Exception as e:
        logger.error(f"Issue map failed: {e}")
        return templates.TemplateResponse(
            "partials/error.html", {"request": request, "error": str(e)}
        )


@app.post("/herding/details_html")
async def analyze_citation_details(request: Request, citation: str = Form(...)) -> Any:
    """Get detailed treatment analysis for modal."""
    try:
        # Re-run or get cached analysis
        result = await check_case_validity_impl(citation)
        return templates.TemplateResponse(
            "partials/modal_treatment_details.html",
            {"request": request, "result": result},
        )
    except Exception as e:
        logger.error(f"Details failed: {e}")
        return templates.TemplateResponse(
            "partials/error.html", {"request": request, "error": str(e)}
        )


@app.post("/search/similar_html")
async def find_similar_html(request: Request, query: str = Form(...)) -> Any:
    """Find similar cases returning HTML."""
    try:
        # Use semantic search
        result = await semantic_search_impl(query, limit=5)
        return templates.TemplateResponse(
            "partials/similar_cases_list.html",
            {"request": request, "results": result["results"]},
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return templates.TemplateResponse(
            "partials/error.html", {"request": request, "error": str(e)}
        )


# Mount static files (legacy support and for serving other assets if needed)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
