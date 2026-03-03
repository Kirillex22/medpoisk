from typing import List
from fastapi import HTTPException

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel

from .models import Article

conversation_history = []

async def rank_articles_by_relevance(
    llm: BaseChatModel, 
    original_query: str, 
    articles: List[Article]
    ) -> List[Article]:

    if not articles:
        return articles

    # Формируем промпт
    articles_text = ""
    for a in articles:
        abstract_sample = a.abstract[:500] + "..." if a.abstract and len(a.abstract) > 500 else (a.abstract or "")
        articles_text += f"PMID: {a.pmid}\nTitle: {a.title}\nAbstract: {abstract_sample}\n---\n"
    
    prompt = HumanMessage(content=f"""
    Original user query: "{original_query}"

    Below is a list of scientific articles with their PMID, title, and abstract. Please sort them by relevance to the original query, from most relevant to least relevant. Return only the PMIDs in the sorted order, separated by commas, without any additional text.

    Articles:
    {articles_text}

    Sorted PMIDs:
    """)

    try:
        response = await llm.ainvoke([prompt])
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
        
        conversation_history.append(prompt)
        conversation_history.append(response)
        return sorted_articles
    except Exception as e:
        print(e)
        return articles


async def generate_queries(
    llm: BaseChatModel, 
    system_message: SystemMessage,
    user_message: HumanMessage
) -> List[str] | str:
    try:     
        # Добавляем новое сообщение в историю
        conversation_history.append(user_message)
        
        # Передаем ВСЮ историю в LLM (система + весь контекст + новое)
        input_messages = [system_message] + conversation_history
        response = await llm.ainvoke(input_messages)
        
        # Сохраняем ответ в историю
        conversation_history.append(response)
        content = response.content.strip()
        if content.find("[CHAT]") != -1:
            return content.replace("[CHAT]", "")

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
        raise HTTPException(status_code=500, detail=f"Ошибка LLM: {str(e)}")