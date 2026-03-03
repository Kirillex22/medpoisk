// Элементы DOM
const messagesDiv = document.getElementById('messages');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');

// Базовый URL API
const API_BASE_URL = 'http://127.0.0.1:8000';

// Кэш результатов: ключ — строка запроса, значение — массив статей
const resultsCache = new Map();

// Последний исходный запрос пользователя
let lastOriginalQuery = '';

// --- Вспомогательные функции ---
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function scrollToBottom() {
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function slugify(str) {
    return str.replace(/[^a-z0-9]/gi, '_').toLowerCase();
}

// --- Добавление сообщений ---
function addUserMessage(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';
    messageDiv.innerHTML = `
        <div class="avatar">👤</div>
        <div class="bubble">${escapeHtml(text)}</div>
    `;
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
}

function addBotMessageText(text) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';
    messageDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">${escapeHtml(text)}</div>
    `;
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();
}

function addBotMessageWithQueries(queries) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot';

    let queriesHtml = '';
    queries.forEach((q, index) => {
        queriesHtml += `
            <div class="query-card" data-query="${escapeHtml(q)}" data-index="${index}">
                <pre>${escapeHtml(q)}</pre>
            </div>
        `;
    });

    messageDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">
            <p style="margin-bottom: 12px; font-weight: 500;">На основе вашего вопроса я подготовил несколько вариантов поисковых запросов. Нажмите на любой, чтобы выполнить поиск:</p>
            ${queriesHtml}
        </div>
    `;
    messagesDiv.appendChild(messageDiv);
    scrollToBottom();

    messageDiv.querySelectorAll('.query-card').forEach(card => {
        card.addEventListener('click', async () => {
            const query = card.dataset.query;
            messageDiv.querySelectorAll('.query-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            await executeQuery(query);
        });
    });
}

function addLoadingMessage() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot';
    loadingDiv.id = 'loading-message';
    loadingDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">
            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    messagesDiv.appendChild(loadingDiv);
    scrollToBottom();
}

function removeLoadingMessage() {
    const loadingMsg = document.getElementById('loading-message');
    if (loadingMsg) loadingMsg.remove();
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'message bot';
    errorDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble" style="color: #d32f2f;">
            <p>Произошла ошибка:</p>
            <p>${escapeHtml(message)}</p>
        </div>
    `;
    messagesDiv.appendChild(errorDiv);
    scrollToBottom();
}

// --- Отображение результатов поиска (статьи) ---
function displayResults(query, articles) {
    const resultsId = `results-${slugify(query)}`;
    let resultsDiv = document.getElementById(resultsId);
    if (!resultsDiv) {
        resultsDiv = document.createElement('div');
        resultsDiv.className = 'message bot';
        resultsDiv.id = resultsId;
        messagesDiv.appendChild(resultsDiv);
    }

    let articlesHtml = '';
    if (articles.length === 0) {
        articlesHtml = '<p style="color: #666; font-style: italic;">Статей не найдено.</p>';
    } else {
        articlesHtml = '<div class="articles-container">';
        articles.forEach(article => {
            const metaParts = [];
            if (article.authors) metaParts.push(article.authors);
            if (article.journal) metaParts.push(article.journal);
            if (article.pubdate) metaParts.push(article.pubdate);
            if (article.volume && article.pages) metaParts.push(`${article.volume}:${article.pages}`);
            const metaStr = metaParts.join(' • ');

            const doiLink = article.doi ? `https://doi.org/${article.doi}` : '#';
            const abstractText = article.abstract || 'Аннотация отсутствует';

            articlesHtml += `
                <div class="article-item" data-pmid="${escapeHtml(article.pmid)}">
                    <div class="article-title">${escapeHtml(article.title || 'Без названия')}</div>
                    <div class="article-meta">${escapeHtml(metaStr)}</div>
                    ${article.doi ? `<a href="${doiLink}" target="_blank" class="article-doi">${escapeHtml(article.doi)}</a>` : ''}
                    <div class="article-actions">
                        <button class="rating-btn like" data-pmid="${escapeHtml(article.pmid)}" data-rating="like">👍</button>
                        <button class="rating-btn dislike" data-pmid="${escapeHtml(article.pmid)}" data-rating="dislike">👎</button>
                    </div>
                    <div class="tooltip">${escapeHtml(abstractText)}</div>
                </div>
            `;
        });
        articlesHtml += '</div>';
    }

    resultsDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="bubble">
            <p style="margin-bottom: 12px; font-weight: 500;">Результаты по запросу: <code>${escapeHtml(query)}</code></p>
            ${articlesHtml}
        </div>
    `;

    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });

    resultsDiv.querySelectorAll('.rating-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            e.preventDefault();
            const pmid = btn.dataset.pmid;
            const rating = btn.dataset.rating;
            await rateArticle(pmid, rating);
            btn.style.opacity = '0.5';
            btn.disabled = true;
        });
    });
}

// --- API вызовы ---
async function searchQuery(question) {
    const response = await fetch(`${API_BASE_URL}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: question })
    });

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(`Ошибка API: ${response.status} ${JSON.stringify(data)}`);
        }
        return data;
    } else {
        const text = await response.text();
        if (!response.ok) {
            throw new Error(`Ошибка API: ${response.status} ${text}`);
        }
        return text;
    }
}

async function fetchResults(query, originalQuery) {
    const response = await fetch(`${API_BASE_URL}/fetch_results`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, original_query: originalQuery })
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Ошибка API: ${response.status} ${errorText}`);
    }

    const data = await response.json();
    return data.results;
}

async function rateArticle(pmid, rating) {
    try {
        const response = await fetch(`${API_BASE_URL}/rate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pmid, rating })
        });
        if (!response.ok) {
            console.error('Ошибка при отправке оценки');
        } else {
            console.log(`Оценка ${rating} для PMID ${pmid} отправлена`);
        }
    } catch (error) {
        console.error('Ошибка сети при оценке:', error);
    }
}

// --- Основные действия ---
async function executeQuery(query) {
    if (resultsCache.has(query)) {
        displayResults(query, resultsCache.get(query));
        return;
    }

    addLoadingMessage();
    try {
        const results = await fetchResults(query, lastOriginalQuery);
        resultsCache.set(query, results);
        removeLoadingMessage();
        displayResults(query, results);
    } catch (error) {
        removeLoadingMessage();
        showError(`Ошибка при выполнении запроса: ${error.message}`);
    }
}

async function handleSend() {
    const question = userInput.value.trim();
    if (question === '') return;

    addUserMessage(question);
    userInput.value = '';

    addLoadingMessage();

    try {
        const data = await searchQuery(question);
        removeLoadingMessage();

        if (typeof data === 'string') {
            // Сервер вернул простую строку (например, сообщение от LLM)
            addBotMessageText(data);
        } else if (data && Array.isArray(data.generated_queries)) {
            // Успешно получили список запросов
            lastOriginalQuery = question;
            addBotMessageWithQueries(data.generated_queries);
        } else {
            // Неожиданный формат ответа
            addBotMessageText('Получен некорректный ответ от сервера.');
        }
    } catch (error) {
        removeLoadingMessage();
        showError(error.message);
    }
}

// --- Инициализация событий ---
sendBtn.addEventListener('click', handleSend);
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
    }
});