import logging
import sys
import json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data_pipeline.fetcher import fetch_all_subsidies
from src.data_pipeline.preprocessor import transform_batch
from src.data_pipeline.loader import load_to_vectorstore, get_collection_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_seed_data():
    """시드 데이터 로드 (API 키 없을 때 사용)"""
    seed_path = project_root / "data" / "raw" / "seed_policies.json"
    if seed_path.exists():
        with open(seed_path, encoding="utf-8") as f:
            return json.load(f)
    return []


def run_pipeline(use_seed=False):
    logger.info("=" * 60)
    logger.info("시니피에 데이터 파이프라인 시작")
    logger.info("=" * 60)

    if use_seed:
        logger.info("[Step 1/3] 시드 데이터 로드 중...")
        raw_records = load_seed_data()
    else:
        logger.info("[Step 1/3] 공공데이터 API 수집 중...")
        raw_records = fetch_all_subsidies(
            service_types=["청년", "취업", "주거", "창업", "교육"],
            max_pages=5,
        )

    logger.info(f"  -> 수집 완료: {len(raw_records)}건")

    if not raw_records:
        logger.warning("수집된 데이터가 없습니다.")
        return

    logger.info("[Step 2/3] 데이터 전처리 중...")
    transformed = transform_batch(raw_records)
    logger.info(f"  -> 전처리 완료: {len(transformed)}건")

    if not transformed:
        logger.warning("전처리 후 유효한 데이터가 없습니다.")
        return

    logger.info("[Step 3/3] Vector DB 적재 중...")
    loaded_count = load_to_vectorstore(transformed)
    logger.info(f"  -> 적재 완료: {loaded_count}건")

    stats = get_collection_stats()
    logger.info("=" * 60)
    logger.info(f"파이프라인 완료! DB 현재 상태: {stats['count']}건")
    logger.info("=" * 60)


if __name__ == "__main__":
    use_seed = "--seed" in sys.argv or "--local" in sys.argv
    if not use_seed:
        from configs.settings import get_settings
        s = get_settings()
        if not s.data_go_kr_api_key or s.data_go_kr_api_key == "your-data-go-kr-api-key":
            logger.info("API 키 미설정 -> 시드 데이터 모드로 전환")
            use_seed = True
    run_pipeline(use_seed=use_seed)
