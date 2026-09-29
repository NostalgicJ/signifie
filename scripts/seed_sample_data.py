"""
시드 데이터(data/raw/seed_policies.json) -> 전처리 -> ChromaDB 적재
API 키 없이도 실제 정책 데이터로 RAG 검색을 검증할 수 있습니다.

실행: python -m scripts.seed_sample_data [--reset]
"""

import hashlib
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from configs.settings import get_settings  # noqa: E402
from src.backend.rag.vectorstore import get_collection, reset_collection  # noqa: E402
from src.data_pipeline.loader import load_to_vectorstore  # noqa: E402
from src.data_pipeline.preprocessor import transform_batch  # noqa: E402

SEED_PATH = PROJECT_ROOT / "data" / "raw" / "seed_policies.json"

logger = logging.getLogger(__name__)


def seed_file_hash() -> str:
    """시드 데이터 내용 해시 - 데이터가 바뀌었는지 판단하는 기준"""
    return hashlib.md5(SEED_PATH.read_bytes()).hexdigest()


def _hash_marker_path() -> Path:
    return Path(get_settings().vector_db_path) / "seed_hash.txt"


def seed(reset: bool = False) -> int:
    """시드 데이터를 적재하고 컬렉션 문서 수를 반환합니다."""
    if reset:
        reset_collection()

    with open(SEED_PATH, encoding="utf-8") as f:
        records = json.load(f)

    transformed = transform_batch(records)
    load_to_vectorstore(transformed)

    marker = _hash_marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(seed_file_hash())

    count = get_collection().count()
    logger.info(f"ChromaDB 적재 완료: {count}건")
    return count


def ensure_seeded() -> None:
    """
    컬렉션이 비어 있거나 시드 데이터가 바뀌었으면 다시 적재합니다.
    배포 환경에서 seed_policies.json만 수정해 push해도 자동 반영됩니다.
    """
    marker = _hash_marker_path()
    stale = not marker.exists() or marker.read_text().strip() != seed_file_hash()
    if stale or get_collection().count() == 0:
        seed(reset=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    total = seed(reset="--reset" in sys.argv)
    print(f"Loaded {total} documents into ChromaDB")
