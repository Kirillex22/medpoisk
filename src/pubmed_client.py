import httpx
import xml.etree.ElementTree as ET
from typing import List, Dict

from .models import Article
from .config import ENTREZ_API_KEY, ENTREZ_EMAIL, ENTREZ_TOOL, PUBMED_BASE_URL, PUBMED_MAX_RESULTS 


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