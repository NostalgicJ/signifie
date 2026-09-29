"""
Vector DB 적재 모듈
전처리된 문서를 ChromaDB에 배치 적재합니다.
"""

import logging

from src.backend.rag.vectorstore import add_documents, get_collection

logger = logging.getLogger(__name__)

# ChromaDB 배치 크기 제한
BATCH_SIZE = 100


def load_to_vectorstore(
    transformed_docs: list[dict],
    collection_name: str | None = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    """
    전처리된 문서를 Vector DB에 적재합니다.

    Args:
        transformed_docs: transform_batch()의 출력
        collection_name: 대상 컬렉션 이름
        batch_size: 한 번에 적재할 문서 수

    Returns:
        적재된 문서 수
    """
    if not transformed_docs:
        logger.warning("적재할 문서가 없습니다.")
        return 0

    total_loaded = 0

    for i in range(0, len(transformed_docs), batch_size):
        batch = transformed_docs[i : i + batch_size]

        documents = [doc["document"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]
        ids = [doc["id"] for doc in batch]

        try:
            add_documents(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                collection_name=collection_name,
            )
            total_loaded += len(batch)
            logger.info(f"[load] 배치 적재 완료: {total_loaded}/{len(transformed_docs)}")
        except Exception as e:
            logger.error(f"[load] 배치 적재 실패 (index {i}~{i+batch_size}): {e}")
            continue

    logger.info(f"[load] 전체 적재 완료: {total_loaded}건")
    return total_loaded


def get_collection_stats(collection_name: str = "subsidies") -> dict:
    """컬렉션 상태 정보를 반환합니다."""
    collection = get_collection(collection_name)
    return {
        "name": collection.name,
        "count": collection.count(),
    }
