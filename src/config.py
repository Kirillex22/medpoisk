import os
from dotenv import load_dotenv

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