import asyncio
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from .models import SearchResponse, UserQuery, QueryResultResponse, FetchResultsRequest, RatingRequest
from .dependencies import get_llm, get_system_propmt
from .services import generate_queries, rank_articles_by_relevance
from .pubmed_client import search_pubmed


llm: BaseChatModel = get_llm()
query_gen_system_prompt: SystemMessage = get_system_propmt("query_generate.prompt")

app = FastAPI(title="Medical Query Mediator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_frontend():
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)


@app.post("/search", response_model=str | SearchResponse)
async def search(query: UserQuery):
    user_prompt: HumanMessage = HumanMessage(content=query.text)

    generated: List[str] | str = await generate_queries(
        llm=llm, 
        system_message=query_gen_system_prompt, 
        user_message=user_prompt
    )
    
    if isinstance(generated, str):
        return generated

    if not generated:
        raise HTTPException(status_code=500, detail="Не удалось сгенерировать запросы")
    return SearchResponse(
        original_query=query.text,
        generated_queries=generated
    )


@app.post("/fetch_results", response_model=QueryResultResponse)
async def fetch_results(request_data: FetchResultsRequest):
    query = request_data.query
    original_query = request_data.original_query
    results = await search_pubmed(query)
    if results:
        results = await rank_articles_by_relevance(
            llm=llm,
            original_query=original_query, 
            articles=results
        )
    return QueryResultResponse(query=query, results=results)


@app.post("/rate")
async def rate_article(rating_req: RatingRequest):
    return {"status": "ok", "message": f"Рейтинг {rating_req.rating} для статьи {rating_req.pmid} принят"}