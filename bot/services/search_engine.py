import os
from pathlib import Path
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.vectorstores.base import VectorStoreRetriever
from bot.config import load_config

config = load_config()

DATA_DIR = Path("bot/data")
CHUNKS_DB = DATA_DIR / "knowledge_chunks.db"
DOCS_DIR = Path("bot/docs")

os.environ["OPENAI_API_KEY"] = config.OPENAI_API_KEY


def load_and_split_documents():
    # Загрузка всех .txt файлов в папке
    loader = DirectoryLoader(
        path=str(DOCS_DIR),
        glob="**/*.txt",
        loader_cls=TextLoader
    )
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100
    )
    return splitter.split_documents(documents)


def create_vector_db():
    documents = load_and_split_documents()
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_documents(documents, embeddings)
    vectorstore.save_local(str(CHUNKS_DB))
    print("✅ Векторная база успешно создана")


def get_retriever() -> VectorStoreRetriever:
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.load_local(
        str(CHUNKS_DB),
        embeddings,
        allow_dangerous_deserialization=True
    )
    return vectorstore.as_retriever(search_type="similarity", k=5)


import logging
import re

logger = logging.getLogger(__name__)

async def search_knowledge(query: str) -> str:
    retriever = get_retriever()
    results = retriever.invoke(query)
    
    result_texts = "\n\n".join([doc.page_content for doc in results])
    logger.info(f"🔍 Поиск по запросу '{query}' вернул {len(results)} результатов.")

    # Попытка найти ссылку на демо (если она есть)
    demo_link = extract_demo_link(result_texts)

    if demo_link:
        logger.info(f"🔗 Найдена ссылка на демо: {demo_link}")
        result_texts += f"\n\nСсылка на демо: {demo_link}"

    return result_texts.strip()


def extract_demo_link(text: str) -> str | None:
    """
    Пытается найти первую ссылку на демо в виде:
    https://codim.online/teach/control/stream/view/id/...
    """
    match = re.search(r"https://codim\.online/teach/control/stream/view/id/\d+", text)
    return match.group(0) if match else None
