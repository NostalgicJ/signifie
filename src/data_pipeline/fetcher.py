"""
공공데이터 API 수집 모듈
data.go.kr의 지자체/청년 지원사업 정보를 수집합니다.
"""

import logging
from typing import Any

import httpx

from configs.settings import get_settings

logger = logging.getLogger(__name__)

# 공공데이터포털 - 정부24 보조금24 서비스 목록 조회 API (예시 엔드포인트)
BASE_URL = "https://api.odcloud.kr/api"


def fetch_subsidy_list(
    page: int = 1,
    per_page: int = 100,
    service_type: str = "청년",
) -> list[dict[str, Any]]:
    """
    보조금24 또는 지자체 지원사업 목록을 페이지 단위로 수집합니다.

    Args:
        page: 페이지 번호
        per_page: 페이지당 건수
        service_type: 검색 키워드 필터 (예: "청년", "주거", "취업")

    Returns:
        공고 데이터 리스트 (각 항목은 dict)
    """
    settings = get_settings()

    params = {
        "serviceKey": settings.data_go_kr_api_key,
        "page": page,
        "perPage": per_page,
        "cond[서비스명::LIKE]": service_type,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{BASE_URL}/15112592/v1/uddi:56467884-14fa-4191-8e7c-56a234de47c4",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        records = data.get("data", [])
        logger.info(f"[fetch] {len(records)}건 수집 완료 (page={page}, keyword={service_type})")
        return records

    except httpx.HTTPStatusError as e:
        logger.error(f"API HTTP 에러: {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        logger.error(f"API 수집 실패: {e}")
        return []


def fetch_all_subsidies(
    service_types: list[str] | None = None,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """
    여러 키워드와 페이지에 걸쳐 전체 공고 데이터를 수집합니다.

    Args:
        service_types: 수집할 키워드 목록 (기본: 청년 관련)
        max_pages: 키워드당 최대 수집 페이지 수

    Returns:
        전체 수집된 공고 리스트
    """
    if service_types is None:
        service_types = ["청년", "취업", "주거", "창업", "교육훈련"]

    all_records = []

    for keyword in service_types:
        for page in range(1, max_pages + 1):
            records = fetch_subsidy_list(page=page, service_type=keyword)
            if not records:
                break
            all_records.extend(records)

    # 중복 제거 (서비스ID 기준)
    seen_ids = set()
    unique_records = []
    for record in all_records:
        record_id = record.get("서비스ID") or record.get("id") or str(record)
        if record_id not in seen_ids:
            seen_ids.add(record_id)
            unique_records.append(record)

    logger.info(f"[fetch_all] 총 {len(unique_records)}건 수집 (중복 제거 후)")
    return unique_records
