"""
Vector DB 관리 모듈
ChromaDB를 기본으로 사용하며, 문서 저장/검색을 추상화합니다.
"""

import logging
from pathlib import Path
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings

from configs.settings import get_settings
from src.backend.llm.bedrock_client import generate_embeddings, is_mock_mode
from src.backend.rag.profile import INCOME_LOWER_BOUND, STATUS_FLAG_KEYS

logger = logging.getLogger(__name__)


class BedrockEmbeddingFunction(chromadb.EmbeddingFunction):
    """Bedrock Titan 임베딩을 ChromaDB에 연결하는 어댑터"""

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [generate_embeddings(text) for text in input]


@lru_cache()
def _get_chroma_client() -> chromadb.ClientAPI:
    """ChromaDB 클라이언트 싱글턴"""
    settings = get_settings()
    db_path = Path(settings.vector_db_path)
    db_path.mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(
        path=str(db_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def default_collection_name() -> str:
    """
    임베딩 방식별로 컬렉션을 분리합니다.
    로컬 n-gram 벡터와 Titan 벡터는 서로 다른 공간이라 한 컬렉션에 섞이면 검색이 깨집니다.
    """
    return "subsidies_local" if is_mock_mode() else "subsidies_titan"


def get_collection(collection_name: str | None = None) -> chromadb.Collection:
    """
    ChromaDB 컬렉션을 가져오거나 생성합니다.

    Args:
        collection_name: 컬렉션 이름 (기본: subsidies)

    Returns:
        ChromaDB Collection 객체
    """
    client = _get_chroma_client()
    embedding_fn = BedrockEmbeddingFunction()

    return client.get_or_create_collection(
        name=collection_name or default_collection_name(),
        embedding_function=embedding_fn,
        metadata={"description": "지자체/청년 지원사업 공고문 데이터", "hnsw:space": "cosine"},
    )


def reset_collection(collection_name: str | None = None) -> None:
    """컬렉션을 삭제합니다 (스키마/임베딩 변경 후 재적재 시 사용)"""
    client = _get_chroma_client()
    name = collection_name or default_collection_name()
    if name in [c.name for c in client.list_collections()]:
        client.delete_collection(name)
        logger.info(f"컬렉션 '{name}' 삭제 완료")


def build_where_filter(profile: dict, level: int = 0) -> dict | None:
    """
    유저 프로필로 ChromaDB where 필터를 만듭니다.

    level이 올라갈수록 조건을 완화합니다. 단, 지역 조건은 어떤 단계에서도 제거하지 않아
    타 지역 공고가 섞이지 않도록 합니다.
        0: 지역 + 연령 + 상태 + 소득
        1: 지역 + 연령 + 상태
        2: 지역 + 연령
        3: 지역만
    """
    clauses: list[dict] = []

    sido = profile.get("region_sido")
    if sido:
        clauses.append({"region_sido": {"$in": ["전국", sido]}})
        sigungu = profile.get("region_sigungu")
        if sigungu:
            clauses.append({"region_sigungu": {"$in": ["전체", sigungu]}})

    age = profile.get("age")
    if age and level <= 2:
        clauses.append({"age_min": {"$lte": int(age)}})
        clauses.append({"age_max": {"$gte": int(age)}})

    status_flag = STATUS_FLAG_KEYS.get(profile.get("employment_status") or "")
    if status_flag and level <= 1:
        clauses.append({status_flag: {"$eq": True}})

    income_lower = INCOME_LOWER_BOUND.get(profile.get("income_level") or "")
    if income_lower is not None and income_lower > 0 and level == 0:
        # 유저 소득 구간의 하한보다 기준선이 높은 사업만 (자격 가능성 있는 사업)
        clauses.append({"income_max_pct": {"$gt": income_lower}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def add_documents(
    documents: list[str],
    metadatas: list[dict],
    ids: list[str],
    collection_name: str | None = None,
) -> None:
    """
    문서를 Vector DB에 추가합니다.

    Args:
        documents: 문서 텍스트 리스트
        metadatas: 메타데이터 리스트 (출처, 기한, 담당부서 등)
        ids: 문서 고유 ID 리스트
        collection_name: 대상 컬렉션
    """
    collection = get_collection(collection_name)

    collection.upsert(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )
    logger.info(f"{len(documents)}건의 문서가 '{collection.name}' 컬렉션에 추가되었습니다.")


def search_documents(
    query: str,
    n_results: int = 5,
    where_filter: dict | None = None,
    collection_name: str | None = None,
) -> dict:
    """
    유사 문서를 검색합니다.

    Args:
        query: 검색 질의
        n_results: 반환할 결과 수
        where_filter: 메타데이터 필터 (build_where_filter() 결과)
        collection_name: 대상 컬렉션

    Returns:
        검색 결과 딕셔너리 (documents, metadatas, distances)
    """
    collection = get_collection(collection_name)

    total = collection.count()
    if total == 0:
        return {"documents": [], "metadatas": [], "distances": []}

    query_params = {
        "query_texts": [query],
        "n_results": min(n_results, total),
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)

    return {
        "documents": results["documents"][0] if results["documents"] else [],
        "metadatas": results["metadatas"][0] if results["metadatas"] else [],
        "distances": results["distances"][0] if results["distances"] else [],
    }
