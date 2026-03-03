from langchain_gigachat import GigaChat
from langchain_core.messages import SystemMessage

from .config import GIGACHAT_CREDENTIALS, GIGACHAT_MAX_TOKENS, GIGACHAT_MODEL, GIGACHAT_TEMPERATURE


def get_system_propmt(prompt_name: str) -> SystemMessage:
    with open(f"prompts/{prompt_name}", 'r', encoding='utf-8') as f:
        prompt = SystemMessage(content=f.read())
        return prompt


def get_llm():
    return GigaChat(
        credentials=GIGACHAT_CREDENTIALS,
        model=GIGACHAT_MODEL,
        temperature=GIGACHAT_TEMPERATURE,
        max_tokens=GIGACHAT_MAX_TOKENS,
        verify_ssl_certs=False,
    )
