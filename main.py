import os
import asyncio
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx
from langchain_gigachat import GigaChat

load_dotenv()

# ========== Конфигурация GigaChat ==========
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_TEMPERATURE = float(os.getenv("GIGACHAT_TEMPERATURE", 0.3))
GIGACHAT_MAX_TOKENS = int(os.getenv("GIGACHAT_MAX_TOKENS", 1024))

# ========== Конфигурация PubMed (Entrez) ==========
PUBMED_MAX_RESULTS = int(os.getenv("PUBMED_MAX_RESULTS", 5))
PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "your-email@example.com")
ENTREZ_TOOL = os.getenv("ENTREZ_TOOL", "MedicalQueryMediator")
ENTREZ_API_KEY = os.getenv("ENTREZ_API_KEY", None)

# ========== Модели данных ==========
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
    rating: str  # "like" / "dislike"

class FetchResultsRequest(BaseModel):
    query: str
    original_query: str

# ========== Инициализация GigaChat ==========
gigachat = GigaChat(
    credentials=GIGACHAT_CREDENTIALS,
    model=GIGACHAT_MODEL,
    temperature=GIGACHAT_TEMPERATURE,
    max_tokens=GIGACHAT_MAX_TOKENS,
    verify_ssl_certs=False,
)

# ========== Функции для работы с PubMed через httpx ==========
async def entrez_request(endpoint: str, params: dict, max_retries: int = 3) -> str:
    params["email"] = ENTREZ_EMAIL
    params["tool"] = ENTREZ_TOOL
    if ENTREZ_API_KEY:
        params["api_key"] = ENTREZ_API_KEY

    url = f"{PUBMED_BASE_URL}{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.text
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                raise
            except Exception:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
    raise HTTPException(500, "Не удалось выполнить запрос к PubMed")

async def esearch(query: str, retmax: int = 5) -> List[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "xml",
        "usehistory": "n",
    }
    xml_text = await entrez_request("esearch.fcgi", params)
    root = ET.fromstring(xml_text)
    id_list = root.findall(".//Id")
    return [id_elem.text for id_elem in id_list if id_elem.text]

async def esummary(pmids: List[str]) -> List[dict]:
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    xml_text = await entrez_request("esummary.fcgi", params)
    root = ET.fromstring(xml_text)

    articles = []
    for docsum in root.findall(".//DocSum"):
        pmid_elem = docsum.find("Id")
        if pmid_elem is None or not pmid_elem.text:
            continue
        pmid = pmid_elem.text

        article = {
            "pmid": pmid,
            "title": "",
            "authors": [],
            "journal": "",
            "pubdate": "",
            "volume": "",
            "issue": "",
            "pages": "",
            "doi": ""
        }

        for item in docsum.findall("Item"):
            name = item.get("Name")
            if name == "Title":
                article["title"] = item.text or ""
            elif name == "AuthorList":
                authors = []
                for author in item.findall("Item"):
                    if author.get("Name") == "Author" and author.text:
                        authors.append(author.text)
                article["authors"] = authors
            elif name == "FullJournalName":
                article["journal"] = item.text or ""
            elif name == "PubDate":
                article["pubdate"] = item.text or ""
            elif name == "Volume":
                article["volume"] = item.text or ""
            elif name == "Issue":
                article["issue"] = item.text or ""
            elif name == "Pages":
                article["pages"] = item.text or ""
            elif name == "DOI":
                article["doi"] = item.text or ""

        authors_list = article["authors"]
        authors_str = ", ".join(authors_list[:3]) + (" et al." if len(authors_list) > 3 else "")
        article["authors"] = authors_str

        articles.append(article)
    return articles

async def efetch_abstracts(pmids: List[str]) -> Dict[str, str]:
    if not pmids:
        return {}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    xml_text = await entrez_request("efetch.fcgi", params)
    root = ET.fromstring(xml_text)

    abstracts = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = None
        abstract = ""

        article_id_list = article.findall(".//ArticleId")
        for aid in article_id_list:
            if aid.get("IdType") == "pubmed":
                pmid = aid.text
                break
        if not pmid:
            continue

        abstract_parts = []
        for elem in article.findall(".//AbstractText"):
            if elem.text:
                abstract_parts.append(elem.text)
        abstract = "\n\n".join(abstract_parts) if abstract_parts else ""

        abstracts[pmid] = abstract

    return abstracts

async def search_pubmed(query: str, max_results: int = PUBMED_MAX_RESULTS) -> List[Article]:
    pmids = await esearch(query, retmax=max_results)
    if not pmids:
        return []
    summaries = await esummary(pmids)
    abstracts_dict = await efetch_abstracts(pmids)

    articles = []
    for s in summaries:
        pmid = s["pmid"]
        articles.append(Article(
            pmid=pmid,
            title=s["title"],
            authors=s["authors"],
            journal=s["journal"],
            pubdate=s["pubdate"],
            volume=s["volume"],
            issue=s["issue"],
            pages=s["pages"],
            doi=s["doi"],
            abstract=abstracts_dict.get(pmid, ""),
            relevance_score=0.0,
        ))
    return articles

# ========== Ранжирование статей по релевантности исходному запросу ==========
async def rank_articles_by_relevance(original_query: str, articles: List[Article]) -> List[Article]:
    if not articles:
        return articles

    # Формируем промпт
    articles_text = ""
    for a in articles:
        abstract_sample = a.abstract[:500] + "..." if a.abstract and len(a.abstract) > 500 else (a.abstract or "")
        articles_text += f"PMID: {a.pmid}\nTitle: {a.title}\nAbstract: {abstract_sample}\n---\n"

    prompt = f"""
Original user query: "{original_query}"

Below is a list of scientific articles with their PMID, title, and abstract. Please sort them by relevance to the original query, from most relevant to least relevant. Return only the PMIDs in the sorted order, separated by commas, without any additional text.

Articles:
{articles_text}

Sorted PMIDs:
"""

    try:
        response = await gigachat.ainvoke(prompt)
        content = response.content.strip()
        # Ожидаем строку с PMID через запятую
        pmid_list = [p.strip() for p in content.split(",") if p.strip()]
        # Создаем словарь для быстрого доступа
        article_dict = {a.pmid: a for a in articles}
        sorted_articles = []
        for pmid in pmid_list:
            if pmid in article_dict:
                sorted_articles.append(article_dict[pmid])
                del article_dict[pmid]
        # Добавляем оставшиеся (если LLM пропустила какие-то) в исходном порядке
        for a in articles:
            if a.pmid in article_dict:
                sorted_articles.append(a)
        return sorted_articles
    except Exception as e:
        # В случае ошибки возвращаем исходный порядок
        print(f"Ошибка ранжирования: {e}")
        return articles

# ========== Генерация запросов через GigaChat ==========
async def generate_queries(user_text: str) -> List[str]:
    prompt = f"""
    Ты — помощник для формирования точных поисковых запросов к базе медицинских статей PubMed через Entrez ESearch.

    Запрос пользователя: "{user_text}"

    Твоя задача: сгенерировать 3 различных варианта поисковых запросов на английском языке, которые максимально полно и точно отражают суть запроса. Запросы должны соответствовать синтаксису Entrez ESearch, описанному в документации NCBI.

    Правила формирования запросов:
    1. Используй только английские термины и поля в квадратных скобках, например: [All Fields], [MeSH Terms], [Title], [Abstract], [Author], [Journal], [Publication Date], [Date - Publication], [Date - MeSH], [Subset], [Text Word] и др.
    2. Для объединения условий используй логические операторы AND, OR, NOT (записываются заглавными буквами).
    3. **ВАЖНО: Не используй двойные кавычки (" ") вокруг терминов.** Запрос должен состоять из терминов с полями, соединённых операторами. Пример правильного запроса: `asthma[MeSH Terms] AND leukotrienes[MeSH Terms] AND 2009[Publication Date]`
    4. Если пользователь упоминает конкретное заболевание, препарат, симптом, добавь соответствующие MeSH-термины и текстовые поля.
    5. Разнообразь варианты: один может быть более широким, другой — узким, третий — использовать синонимы или другие поля.
    6. Выводи только сами запросы, каждый на отдельной строке, без нумерации, без пояснений, без дополнительных символов.

    Примеры правильных запросов (для справки):
    - science[journal] AND breast cancer AND 2008[pdat]
    - hypertension[MeSH Terms] AND diabetes mellitus[MeSH Terms] AND therapy[Subheading]
    - (covid-19[Title] OR SARS-CoV-2[Title]) AND vaccine[All Fields] AND 2023[Publication Date]
    - paracetamol[All Fields] AND liver injury[MeSH Terms] AND clinical trial[Publication Type]

    Сгенерируй 3 варианта для запроса: "{user_text}"
    """
    try:
        response = await gigachat.ainvoke(prompt)
        content = response.content.strip()
        queries = []
        for line in content.split("\n"):
            line = line.strip()
            if line:
                line = line.replace('"', '')
                if line.endswith('.'):
                    line = line[:-1]
                queries.append(line)
        return queries[:3]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка GigaChat: {str(e)}")

# ========== FastAPI приложение ==========
app = FastAPI(title="Medical Query Mediator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/search", response_model=SearchResponse)
async def search(query: UserQuery):
    generated = await generate_queries(query.text)
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
        results = await rank_articles_by_relevance(original_query, results)
    return QueryResultResponse(query=query, results=results)

@app.post("/rate")
async def rate_article(rating_req: RatingRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(log_rating, rating_req.pmid, rating_req.rating)
    return {"status": "ok", "message": f"Рейтинг {rating_req.rating} для статьи {rating_req.pmid} принят"}

def log_rating(pmid: str, rating: str):
    print(f"Рейтинг: {rating} для PMID {pmid}")