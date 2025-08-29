import os
import re
from pathlib import Path
from typing import Optional, Tuple
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.vectorstores.base import VectorStoreRetriever
from langchain.schema import Document
from bot.config import load_config

config = load_config()

DATA_DIR = Path("bot/data")
CHUNKS_DB = DATA_DIR / "knowledge_chunks.db"
DOCS_DIR = Path("bot/docs")

os.environ["OPENAI_API_KEY"] = config.OPENAI_API_KEY


def split_markdown_text(markdown_text: str, strip_headers: bool = False) -> list[Document]:
    """
    Формирует чанки в формат LangChain Document из текста с Markdown разметкой.
    
    Args:
        markdown_text: Текст с markdown разметкой
        strip_headers: НЕ удалять заголовки под '#..' из page_content
    
    Returns:
        Список чанков в формате LangChain Document
    """
    # Удалить пустые строки и лишние пробелы
    markdown_text = re.sub(r' {1,}', ' ', re.sub(r'\n\s*\n', '\n', markdown_text))
    
    # Определяем заголовки, по которым будем разбивать текст
    headers_to_split_on = [
        ("#", "Header 1"),    # Заголовок первого уровня
        ("##", "Header 2"),   # Заголовок второго уровня  
        ("###", "Header 3")   # Заголовок третьего уровня
    ]
    
    # Создаем экземпляр MarkdownHeaderTextSplitter с заданными заголовками
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=strip_headers
    )
    
    # Разбиваем текст на чанки в формат LangChain Document
    chunks = markdown_splitter.split_text(markdown_text)
    return chunks


def load_and_split_documents():
    """Загружает документы и разбивает их на чанки с помощью MarkdownHeaderTextSplitter"""
    documents = []
    if DOCS_DIR.exists():
        docs_loader = DirectoryLoader(
            path=str(DOCS_DIR),
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"}
        )
        docs = docs_loader.load()
        
        for doc in docs:
            text = doc.page_content
            # Используем новую функцию split_markdown_text
            chunks = split_markdown_text(text, strip_headers=False)
            documents.extend(chunks)
            
        print(f"✅ Загружено {len(docs)} документов, создано {len(documents)} чанков")
    else:
        print("⚠️ Папка bot/docs не найдена")
    
    return documents


def create_vector_db():
    """Создает векторную базу данных из документов"""
    documents = load_and_split_documents()
    if not documents:
        print("❌ Нет документов для создания базы данных")
        return
        
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_documents(documents, embeddings)
    vectorstore.save_local(str(CHUNKS_DB))
    print(f"✅ Векторная база успешно создана из {len(documents)} чанков")


def get_retriever() -> VectorStoreRetriever:
    """Возвращает retriever для поиска в векторной базе"""
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.load_local(
        str(CHUNKS_DB),
        embeddings,
        allow_dangerous_deserialization=True
    )
    return vectorstore.as_retriever(search_type="similarity", k=5)


import logging

logger = logging.getLogger(__name__)

def is_course_suitable(course_text: str, user_age: int = None, user_experience: str = None) -> bool:
    """
    Проверяет, подходит ли курс по возрасту и опыту пользователя.
    
    Args:
        course_text: Текст с информацией о курсе
        user_age: Возраст пользователя
        user_experience: Опыт пользователя ("без опыта" или "с опытом")
    
    Returns:
        True если курс подходит, False если не подходит
    """
    if not user_age and not user_experience:
        return True  # Если нет данных о пользователе, показываем все курсы
    
    # Проверяем возраст
    if user_age:
        # Ищем возрастные ограничения в тексте курса
        age_patterns = [
            r'Возраст:\s*(\d+)-?(\d+)?\s*лет?',
            r'(\d+)-?(\d+)?\s*лет?',
            r'от\s*(\d+)\s*до\s*(\d+)\s*лет?',
            r'(\d+)\+?\s*лет?'
        ]
        
        for pattern in age_patterns:
            age_match = re.search(pattern, course_text, re.IGNORECASE)
            if age_match:
                if len(age_match.groups()) == 2 and age_match.group(2):
                    # Диапазон возрастов (например, "7-10 лет")
                    min_age = int(age_match.group(1))
                    max_age = int(age_match.group(2))
                    if not (min_age <= user_age <= max_age):
                        logger.info(f"Курс не подходит по возрасту: пользователю {user_age} лет, курс для {min_age}-{max_age} лет")
                        return False
                elif age_match.group(1):
                    # Минимальный возраст (например, "10+ лет")
                    min_age = int(age_match.group(1))
                    if user_age < min_age:
                        logger.info(f"Курс не подходит по возрасту: пользователю {user_age} лет, курс от {min_age} лет")
                        return False
    
    # Проверяем опыт
    if user_experience:
        user_exp_lower = user_experience.lower()
        course_text_lower = course_text.lower()
        
        if user_exp_lower == "без опыта":
            # Если пользователь без опыта, исключаем курсы для опытных
            if any(phrase in course_text_lower for phrase in ["с опытом", "для опытных", "продвинутый", "advanced"]):
                logger.info(f"Курс не подходит по опыту: пользователь без опыта, курс для опытных")
                return False
        elif user_exp_lower == "с опытом":
            # Если пользователь с опытом, исключаем базовые курсы
            if any(phrase in course_text_lower for phrase in ["для начинающих", "базовый", "начальный", "без опыта"]):
                logger.info(f"Курс не подходит по опыту: пользователь с опытом, курс для начинающих")
                return False
    
    return True


async def search_knowledge(query: str, user_age: int = None, user_experience: str = None) -> str:
    """
    Поиск информации в векторной базе знаний с фильтрацией по возрасту и опыту.
    
    Args:
        query: Поисковый запрос
        user_age: Возраст пользователя
        user_experience: Опыт пользователя
    
    Returns:
        Отфильтрованная информация о курсах
    """
    retriever = get_retriever()
    results = retriever.invoke(query)
    logger.info(f"🔍 Поиск по запросу '{query}' вернул {len(results)} результатов.")
    
    # Фильтруем результаты по возрасту и опыту
    filtered_results = []
    for doc in results:
        if is_course_suitable(doc.page_content, user_age, user_experience):
            filtered_results.append(doc)
    
    # Если после фильтрации ничего не осталось, возвращаем первые 2 результата
    if not filtered_results and results:
        logger.info(f"После фильтрации по возрасту {user_age} и опыту '{user_experience}' ничего не найдено, показываем общие результаты")
        filtered_results = results[:2]
    
    result_texts = "\n\n".join([doc.page_content for doc in filtered_results])
    
    # Ищем демо-ссылку
    demo_link = extract_demo_link(result_texts)
    if demo_link:
        logger.info(f"🔗 Найдена ссылка на демо: {demo_link}")
        result_texts += f"\n\nСсылка на демо: {demo_link}"
    
    logger.info(f"✅ Возвращаем {len(filtered_results)} подходящих результатов")
    return result_texts.strip()


def extract_demo_link(text: str) -> str | None:
    """Извлекает ссылку на демо из текста"""
    match = re.search(r"https://codim\.online/teach/control/stream/view/id/\d+", text)
    return match.group(0) if match else None


# --- Точный поиск блока курса и демо-ссылки по названию курса ---

def _normalize_course_name(name: str) -> str:
    """
    Нормализует название курса для сопоставления.
    Убирает лишние пробелы, приводит к нижнему регистру и применяет простые алиасы.
    """
    if not name:
        return ""
    text = name.lower()
    # Убираем служебные слова в начале
    text = re.sub(r"^(демо|по|про|на курс|курс|по курсу|про курс)\s+", "", text)
    # Удаляем пунктуацию и лишние символы, оставляем буквы/цифры/пробелы
    text = re.sub(r"[^\w\s+#]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()

    # Алиасы для частых русско-английских написаний
    aliases = {
        "роблокс": "roblox",
        "юнити": "unity",
        "юнити блоки": "unity",
        "unity блоки": "unity",
        "unity c#": "unity_csharp",
        "майнкрафт": "minecraft",
        "скретч": "scratch",
        "скретч джуниор": "scratch junior",
        "джуниор": "scratch junior",
        "ворд": "word",
        "гугл": "google",
        "гугл диск": "google",
        "google диск": "google",
        "co spaces": "cospaces",
        "co-spaces": "cospaces",
        "co spaces vr": "cospaces",
        "ai": "ии просто",
        "искусственный интеллект": "ии просто",
        "uniti": "unity",
    }
    for key, value in aliases.items():
        if key in text:
            return value
    return text


def _split_docs_by_headers(text: str) -> list[Tuple[str, str]]:
    """
    Делит общий текст на блоки по заголовкам вида "### **Name**" и возвращает пары (name, block_text).
    """
    # Найдём все заголовки третьего уровня и их позиции
    pattern = re.compile(r"^###\s*\*\*(.+?)\*\*\s*$", re.MULTILINE)
    blocks: list[Tuple[str, str]] = []
    matches = list(pattern.finditer(text))
    for idx, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        blocks.append((name, block))
    return blocks


def find_course_block_by_name(query: str) -> Optional[Tuple[str, str]]:
    """Возвращает (точное_название_курса, текст_блока) по запросу названия.
    Ищем строго в `bot/docs/courses_table.txt`, чтобы не путать демо-ссылки между курсами.
    """
    docs_path = DOCS_DIR / "courses_table.txt"
    if not docs_path.exists():
        return None
    try:
        content = docs_path.read_text(encoding="utf-8")
    except Exception:
        return None

    normalized_query = _normalize_course_name(query)
    best_match: Optional[Tuple[str, str]] = None

    def tokens(s: str) -> set[str]:
        return {t for t in re.split(r"\s+", s) if len(t) >= 3}

    # Сначала пробуем точное совпадение нормализованных названий
    for header_name, block_text in _split_docs_by_headers(content):
        normalized_header = _normalize_course_name(header_name)
        if normalized_query and normalized_query == normalized_header:
            return (header_name, block_text)

    # Затем — пересечение значимых токенов (устойчивее, чем сырые подстроки)
    q_tokens = tokens(normalized_query)
    for header_name, block_text in _split_docs_by_headers(content):
        normalized_header = _normalize_course_name(header_name)
        if q_tokens and tokens(normalized_header) & q_tokens:
            best_match = (header_name, block_text)
            break

    return best_match


def get_course_demo_link(course_query: str) -> Optional[Tuple[str, str]]:
    """
    Возвращает (course_name, demo_link) для конкретного запроса курса, если найдено в таблице курсов.
    """
    found = find_course_block_by_name(course_query)
    if not found:
        return None
    course_name, block_text = found
    demo = extract_demo_link(block_text)
    if not demo:
        # Возможен вариант с "- Демо-ссылка:" на отдельной строке
        m = re.search(r"Демо-ссылка\s*:\s*(https?://\S+)", block_text)
        demo = m.group(1) if m else None
    if demo:
        return course_name, demo
    return None
