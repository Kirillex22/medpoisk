from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class UserQuery(BaseModel):
    text: str = Field(..., description="Медицинский запрос на естественном языке")


class Article(BaseModel):
    pmid: str
    title: str
    authors: Optional[str] = None
    journal: Optional[str] = None
    pubdate: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    relevance_score: float = 0.0


class SearchResponse(BaseModel):
    original_query: str
    generated_queries: List[str]


class QueryResultResponse(BaseModel):
    query: str
    results: List[Article]


class RatingRequest(BaseModel):
    pmid: str
    rating: str  


class FetchResultsRequest(BaseModel):
    query: str
    original_query: str