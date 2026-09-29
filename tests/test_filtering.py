"""
메타데이터 필터링 회귀 테스트 - 타 지역/타 조건 공고가 검색되지 않는지 확인
실행: python -m pytest -q
"""

import pytest

from scripts.seed_sample_data import seed
from src.backend.rag.chain import _search_with_relaxation, get_rag_response
from src.backend.rag.profile import extract_profile_from_text, normalize_region
from src.backend.rag.vectorstore import build_where_filter


@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    seed(reset=True)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("서울시 성북구", ("서울특별시", "성북구")),
        ("성북구", ("서울특별시", "성북구")),
        ("경기 광주시", ("경기도", "광주시")),
        ("광주 사는", ("광주광역시", None)),
        ("중구", (None, None)),  # 여러 시도에 있는 구는 추론하지 않음
    ],
)
def test_normalize_region(text, expected):
    assert normalize_region(text) == expected


def test_extract_profile_from_colloquial_query():
    found = extract_profile_from_text("성북구 사는 25살 취준생인데 받을 수 있는 지원금 있어?")
    assert found == {
        "region_sido": "서울특별시",
        "region_sigungu": "성북구",
        "age": 25,
        "employment_status": "취업준비생",
    }


def test_region_is_never_relaxed():
    profile = {"region_sido": "서울특별시", "age": 25, "employment_status": "취업준비생"}
    for level in range(4):
        where = build_where_filter(profile, level)
        clauses = where.get("$and", [where])
        assert {"region_sido": {"$in": ["전국", "서울특별시"]}} in clauses


@pytest.mark.parametrize(
    "profile, query",
    [
        ({"region_sido": "서울특별시", "region_sigungu": "성북구", "age": 25, "employment_status": "취업준비생"}, "지원금"),
        ({"region_sido": "경기도", "region_sigungu": "수원시", "age": 28, "employment_status": "직장인"}, "목돈 통장"),
        ({"region_sido": "부산광역시", "age": 30, "employment_status": "직장인"}, "월세 지원"),
    ],
)
def test_results_match_profile(profile, query):
    results, _ = _search_with_relaxation(query, profile)
    assert results["metadatas"], "검색 결과가 비어 있음"
    for meta in results["metadatas"]:
        assert meta["region_sido"] in ("전국", profile["region_sido"]), meta["title"]
        assert meta["age_min"] <= profile["age"] <= meta["age_max"], meta["title"]


def test_status_filter_excludes_other_statuses():
    profile = {"region_sido": "서울특별시", "age": 25, "employment_status": "재학생"}
    results, level = _search_with_relaxation("지원", profile)
    assert level <= 1
    assert all(meta["st_student"] for meta in results["metadatas"])


def test_income_filter():
    profile = {"region_sido": "서울특별시", "age": 25, "income_level": "150% 이상"}
    results, level = _search_with_relaxation("월세", profile)
    assert level == 0
    assert all(meta["income_max_pct"] > 150 for meta in results["metadatas"])


def test_clarify_then_recommend_flow():
    first = get_rag_response("지원금 뭐 있어?", {}, [], {})
    assert first["mode"] == "clarify"
    assert "거주지" in first["answer"] and "나이" in first["answer"]

    second = get_rag_response("성북구 사는 25살 취준생이야", {}, [], first["extracted_context"])
    assert second["mode"] == "recommend"
    assert "- [ ]" in second["answer"]  # 서류 체크리스트
    assert "| 사업명 |" in second["answer"]  # 요약 표


def test_clarify_is_capped():
    ctx = {"_clarify_count": 2}
    response = get_rag_response("지원금 알려줘", {}, [], ctx)
    assert response["mode"] == "recommend"
