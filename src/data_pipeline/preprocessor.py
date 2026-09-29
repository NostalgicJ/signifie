"""
데이터 전처리 모듈
수집된 원시 데이터를 정제하고 Vector DB에 적재할 형식으로 변환합니다.
"""

import hashlib
import logging
import re
from typing import Any

from src.backend.rag.profile import STATUS_FLAG_KEYS, normalize_region

logger = logging.getLogger(__name__)


def _generate_doc_id(record: dict) -> str:
    """레코드 기반 고유 ID 생성"""
    raw = record.get("서비스ID") or record.get("서비스명", "") + record.get("소관기관명", "")
    return hashlib.md5(raw.encode()).hexdigest()


def _clean_text(text: str) -> str:
    """텍스트 정제 (불필요 공백, 특수문자 처리)"""
    if not text:
        return ""
    # 연속 공백/줄바꿈 제거
    text = re.sub(r"\s+", " ", text)
    # 앞뒤 공백
    text = text.strip()
    return text


def _extract_deadline(record: dict) -> str:
    """신청 기한 추출"""
    deadline = record.get("신청기간") or record.get("신청기한") or record.get("접수기간") or ""
    return _clean_text(str(deadline)) if deadline else "상시 또는 미정"


def _extract_region(record: dict) -> str:
    """지역 정보 추출"""
    region = record.get("지역") or record.get("소관기관명", "")
    # '서울특별시 성북구' 형태에서 핵심 지역명 추출
    if "전국" in region or "중앙" in region:
        return "전국"
    return _clean_text(region) if region else "전국"


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [_clean_text(str(v)) for v in value if v]
    # "주민등록등본, 통장사본" 형태의 문자열
    return [_clean_text(v) for v in re.split(r"[,\n·]", str(value)) if _clean_text(v)]


def _status_flags(statuses: list[str]) -> dict[str, bool]:
    """대상상태 리스트 -> ChromaDB에서 필터링 가능한 bool 플래그"""
    open_to_all = not statuses or "전체" in statuses
    return {
        flag: open_to_all or status in statuses
        for status, flag in STATUS_FLAG_KEYS.items()
    }


def transform_record(record: dict[str, Any]) -> dict | None:
    """
    단일 레코드를 Vector DB 적재용 형식으로 변환합니다.
    시드 데이터(data/raw/seed_policies.json)와 보조금24 API 응답 필드를 모두 지원합니다.

    Returns:
        {
            "id": str,
            "document": str,       # 임베딩될 텍스트
            "metadata": dict,      # 필터링/출처 표시용 메타데이터 (스칼라 값만)
        }
        또는 유효하지 않은 레코드면 None
    """
    title = record.get("사업명") or record.get("서비스명")
    if not title:
        return None

    target = record.get("지원대상") or ""
    benefit = record.get("지원내용") or record.get("서비스목적요약") or ""
    income_text = record.get("소득기준") or record.get("선정기준") or ""
    how_to_apply = record.get("신청방법") or ""
    required_docs = _as_list(record.get("구비서류") or record.get("제출서류"))
    tips = _as_list(record.get("신청팁"))
    statuses = record.get("대상상태") or ["전체"]

    # 지역: 시드 데이터는 시도/시군구가 분리되어 있고, API 데이터는 기관명에서 추론
    sido = record.get("시도")
    sigungu = record.get("시군구") or "전체"
    if not sido:
        region_text = _extract_region(record)
        if region_text == "전국":
            sido = "전국"
        else:
            sido, parsed_sigungu = normalize_region(region_text)
            sido = sido or "전국"
            sigungu = parsed_sigungu or "전체"

    age_min = record.get("연령_최소")
    age_max = record.get("연령_최대")
    age_min = int(age_min) if age_min is not None else 0
    age_max = int(age_max) if age_max is not None else 150
    income_pct = record.get("소득기준_퍼센트")
    income_pct = int(income_pct) if income_pct is not None else 999

    region_label = "전국" if sido == "전국" else f"{sido} {'' if sigungu == '전체' else sigungu}".strip()
    age_label = f"만 {age_min}~{age_max}세" if age_max < 150 else (f"만 {age_min}세 이상" if age_min else "연령 제한 없음")

    document_parts = [
        f"[사업명] {title}",
        f"[분야] {record.get('분야', '')}",
        f"[지역] {region_label}",
        f"[연령] {age_label}",
        f"[대상] {', '.join(statuses)}",
        f"[지원대상] {_clean_text(target)}" if target else "",
        f"[지원내용] {_clean_text(benefit)}" if benefit else "",
        f"[소득기준] {_clean_text(income_text)}" if income_text else "",
        f"[구비서류] {', '.join(required_docs)}" if required_docs else "",
        f"[신청방법] {_clean_text(how_to_apply)}" if how_to_apply else "",
    ]
    document = "\n".join(part for part in document_parts if part and not part.endswith("] "))

    if len(document) < 20:
        logger.debug(f"내용 부족으로 스킵: {title}")
        return None

    metadata = {
        "title": _clean_text(title),
        "category": record.get("분야", ""),
        "department": _clean_text(record.get("소관기관") or record.get("소관기관명", "")),
        "region_sido": sido,
        "region_sigungu": sigungu,
        "region_label": region_label,
        "age_min": age_min,
        "age_max": age_max,
        "age_label": age_label,
        "income_max_pct": income_pct,
        "income_text": _clean_text(income_text)[:200],
        "target_statuses": ", ".join(statuses),
        **_status_flags(statuses),
        "target_summary": _clean_text(target)[:300],
        "benefit": _clean_text(benefit)[:300],
        "how_to_apply": _clean_text(how_to_apply)[:200],
        "deadline": _extract_deadline(record),
        "is_open": bool(record.get("모집중", True)),
        "url": record.get("신청링크") or record.get("상세조회URL") or record.get("링크") or "",
        # ChromaDB 메타데이터는 스칼라만 허용 -> 리스트는 '|'로 직렬화
        "required_docs": "|".join(required_docs),
        "tips": "|".join(tips),
    }

    return {
        "id": record.get("id") or _generate_doc_id(record),
        "document": document,
        "metadata": metadata,
    }


def transform_batch(records: list[dict[str, Any]]) -> list[dict]:
    """
    레코드 배치를 변환합니다. 유효하지 않은 항목은 필터링됩니다.

    Args:
        records: 원시 레코드 리스트

    Returns:
        변환된 문서 리스트
    """
    transformed = []
    skipped = 0

    for record in records:
        result = transform_record(record)
        if result:
            transformed.append(result)
        else:
            skipped += 1

    logger.info(f"[transform] {len(transformed)}건 변환 완료, {skipped}건 스킵")
    return transformed
