import base64
import csv
import os

import dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

dotenv.load_dotenv()

# 向量数据库持久化目录
PERSIST_DIR = "../../data/chroma"
COLLECTION_NAME = "images_description"


def chunk_list(lst, chunk_size):
    """将列表分块"""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def get_existing_urls():
    """
    获取Chroma数据库中已存在的所有URL
    """
    # 初始化嵌入模型
    embedding = OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=os.getenv("QIANWEN_API_KEY"),
        base_url=os.getenv("QIANWEN_API_URL"),
        check_embedding_ctx_length=False
    )

    # 加载现有数据库
    db = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding,
        persist_directory=PERSIST_DIR
    )

    # 获取所有文档
    all_docs = db.get()

    # 提取所有URL
    existing_urls = set()
    if 'metadatas' in all_docs and all_docs['metadatas']:
        for metadata in all_docs['metadatas']:
            if 'url' in metadata:
                existing_urls.add(metadata['url'])

    return existing_urls


def load_csv_to_chroma(csv_file_path, batch_size=10):
    """
    将CSV文件中的内容存入Chroma数据库
    :param csv_file_path: CSV文件路径
    :param batch_size: 批处理大小，防止超过API限制
    """
    # 初始化嵌入模型
    embedding = OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=os.getenv("QIANWEN_API_KEY"),
        base_url=os.getenv("QIANWEN_API_URL"),
        check_embedding_ctx_length=False
    )

    # 获取数据库中已存在的URL
    existing_urls = get_existing_urls()
    print(f"数据库中已存在 {len(existing_urls)} 个URL")

    # 读取CSV文件
    documents = []
    skipped_count = 0
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            description = row.get('description', '')
            url = row.get('url', '')

            if description and url:
                # 检查URL是否已存在
                if url in existing_urls:
                    print(f"跳过已存在的URL: {url}")
                    skipped_count += 1
                    continue

                # 创建Document对象，将description作为内容，url作为metadata
                doc = Document(
                    page_content=description,
                    metadata={"url": url}
                )
                documents.append(doc)

    if not documents:
        print(f"没有找到新的数据来添加到Chroma数据库，跳过了 {skipped_count} 条已存在的记录")
        return None

    print(f"准备添加 {len(documents)} 条新记录，跳过了 {skipped_count} 条已存在的记录")

    # 创建或加载Chroma数据库
    if os.path.exists(PERSIST_DIR):
        # 如果数据库已存在，则加载现有数据库
        db = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embedding,
            persist_directory=PERSIST_DIR
        )

        # 分批添加文档以避免API限制
        for i, document_batch in enumerate(chunk_list(documents, batch_size)):
            print(f"正在添加批次 {i + 1}/{(len(documents) - 1) // batch_size + 1}")
            db.add_documents(document_batch)

        print(f"成功添加 {len(documents)} 条新记录到已存在的Chroma数据库")
    else:
        # 如果数据库不存在，则创建新的
        # 分批添加文档以避免API限制
        db = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embedding,
            persist_directory=PERSIST_DIR
        )

        for i, document_batch in enumerate(chunk_list(documents, batch_size)):
            print(f"正在添加批次 {i + 1}/{(len(documents) - 1) // batch_size + 1}")
            db.add_documents(document_batch)

        print(f"成功创建Chroma数据库，包含 {len(documents)} 条记录")

    return db


def search_from_chroma(query, k=3):
    """
    通过相似度检索 Chroma数据库中的内容，得到 URL
    :param query: 查询语句
    :param k: 返回结果数量，默认为 3
    :return: 包含匹配项的列表，每个元素是一个字典，包含description和 url
    """
    # 初始化嵌入模型
    embedding = OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=os.getenv("QIANWEN_API_KEY"),
        base_url=os.getenv("QIANWEN_API_URL"),
        check_embedding_ctx_length=False
    )

    # 加载Chroma数据库
    db = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embedding,
        persist_directory=PERSIST_DIR
    )

    # 执行相似度搜索
    results = db.similarity_search_with_score(query, k=k)

    # 提取URL和描述信息
    search_results = []
    for doc, score in results:
        result_item = {
            "description": doc.page_content,
            "url": doc.metadata.get("url", ""),
            "score": score  # 相似度分数，值越小表示越相似
        }
        search_results.append(result_item)

    return search_results

# load_csv_to_chroma("../../data/images/stickers/images_description.csv")
query = ("一张银白发猫耳动漫角色的表情包。图片中角色眉头紧皱、咬牙切齿，眼神瞪得圆大，脸颊微红，明显处于生气或被惹怒的状态。"
         "这是一张充满“小暴脾气”但又萌感十足的图片，常用于表达“你惹到我了！”“气死我了！”“别再惹我啦！”的情绪，适合在朋友间"
         "打闹、吐槽、撒娇式生气时使用。表示假装生气、傲娇炸毛、可爱发怒、软萌威胁。")
print(search_from_chroma(query))