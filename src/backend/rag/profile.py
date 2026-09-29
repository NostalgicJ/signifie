"""
유저 프로필 정규화 모듈
- 지역명 표기 통일 ("서울시 성북구", "성북구", "서울" -> 서울특별시 / 성북구)
- 구어체 질문에서 거주지·나이·취업상태 추출 ("성북구 사는 25살 취준생")
- 사이드바/대화/질문에서 얻은 정보를 하나의 프로필로 병합
"""

import re

SIDO_ALIASES = {
    "서울특별시": ["서울특별시", "서울시", "서울"],
    "부산광역시": ["부산광역시", "부산시", "부산"],
    "대구광역시": ["대구광역시", "대구시", "대구"],
    "인천광역시": ["인천광역시", "인천시", "인천"],
    "광주광역시": ["광주광역시", "광주시", "광주"],
    "대전광역시": ["대전광역시", "대전시", "대전"],
    "울산광역시": ["울산광역시", "울산시", "울산"],
    "세종특별자치시": ["세종특별자치시", "세종시", "세종"],
    "경기도": ["경기도", "경기"],
    "강원특별자치도": ["강원특별자치도", "강원도", "강원"],
    "충청북도": ["충청북도", "충북"],
    "충청남도": ["충청남도", "충남"],
    "전북특별자치도": ["전북특별자치도", "전라북도", "전북"],
    "전라남도": ["전라남도", "전남"],
    "경상북도": ["경상북도", "경북"],
    "경상남도": ["경상남도", "경남"],
    "제주특별자치도": ["제주특별자치도", "제주도", "제주"],
}

SIGUNGU_BY_SIDO = {
    "서울특별시": [
        "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구",
        "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구",
        "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구",
    ],
    "경기도": [
        "수원시", "성남시", "고양시", "용인시", "부천시", "안산시", "안양시", "남양주시", "화성시",
        "평택시", "의정부시", "시흥시", "파주시", "김포시", "광명시", "광주시", "군포시", "하남시",
        "오산시", "이천시", "안성시", "의왕시", "양주시", "구리시", "포천시", "동두천시", "과천시",
        "여주시", "양평군", "가평군", "연천군",
    ],
    "인천광역시": ["중구", "동구", "미추홀구", "연수구", "남동구", "부평구", "계양구", "서구", "강화군", "옹진군"],
    "부산광역시": [
        "중구", "서구", "동구", "영도구", "부산진구", "동래구", "남구", "북구", "해운대구", "사하구",
        "금정구", "강서구", "연제구", "수영구", "사상구", "기장군",
    ],
    "대전광역시": ["동구", "중구", "서구", "유성구", "대덕구"],
    "광주광역시": ["동구", "서구", "남구", "북구", "광산구"],
}

# 여러 시도에 같은 이름이 있는 구(중구, 서구 등)는 시도 없이 단독으로 쓰이면 추론하지 않습니다.
_AMBIGUOUS_SIGUNGU = {
    name
    for name in {n for names in SIGUNGU_BY_SIDO.values() for n in names}
    if sum(name in names for names in SIGUNGU_BY_SIDO.values()) > 1
}

EMPLOYMENT_STATUSES = ["재학생", "취업준비생", "직장인", "자영업자", "기타"]

# 사이드바 상태값 -> 메타데이터 플래그 키
STATUS_FLAG_KEYS = {
    "재학생": "st_student",
    "취업준비생": "st_jobseeker",
    "직장인": "st_employed",
    "자영업자": "st_self_employed",
    "기타": "st_other",
}

_STATUS_KEYWORDS = {
    "취업준비생": ["취준", "취업준비", "구직", "미취업", "백수", "무직", "졸업유예", "실업"],
    "재학생": ["대학생", "재학", "학생", "휴학"],
    "직장인": ["직장인", "회사원", "재직", "근무", "근로자", "사회초년생", "신입사원", "알바", "아르바이트"],
    "자영업자": ["자영업", "사업자", "창업", "프리랜서", "스타트업 대표"],
}

# 사이드바 소득 구간 -> 해당 구간의 하한(기준중위소득 %)
INCOME_LOWER_BOUND = {
    "50% 이하": 0,
    "50~100%": 50,
    "100~150%": 100,
    "150% 이상": 150,
}


def normalize_sido(text: str | None) -> str | None:
    if not text:
        return None
    for full, aliases in SIDO_ALIASES.items():
        # 긴 별칭부터 확인해 "광주광역시"와 경기도 "광주시" 혼동을 줄임
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in text:
                return full
    return None


def normalize_region(text: str | None) -> tuple[str | None, str | None]:
    """
    자유 입력 지역명을 (시도, 시군구)로 정규화합니다.

    >>> normalize_region("서울시 성북구")
    ('서울특별시', '성북구')
    >>> normalize_region("성북구")
    ('서울특별시', '성북구')
    """
    if not text:
        return None, None

    text = text.strip()
    sido = normalize_sido(text)

    # "광주시"는 경기도 광주시일 수도 있어 경기도 표기가 함께 있으면 경기도 우선
    if sido == "광주광역시" and "경기" in text:
        sido = "경기도"

    sigungu = None
    candidates = SIGUNGU_BY_SIDO.get(sido, []) if sido else [
        n for names in SIGUNGU_BY_SIDO.values() for n in names
    ]
    for name in sorted(candidates, key=len, reverse=True):
        # "성북" 처럼 접미사 없이 쓴 경우도 인식 (2글자 이상 어간)
        stem = name[:-1]
        if name in text or (len(stem) >= 2 and re.search(rf"{stem}(?!\w)|{stem}\s|{stem}에|{stem}사", text)):
            sigungu = name
            break

    if sigungu and not sido:
        if sigungu in _AMBIGUOUS_SIGUNGU:
            return None, None
        sido = next(s for s, names in SIGUNGU_BY_SIDO.items() if sigungu in names)

    return sido, sigungu


def extract_profile_from_text(text: str) -> dict:
    """구어체 문장에서 거주지·나이·취업상태를 규칙 기반으로 추출합니다."""
    found: dict = {}

    sido, sigungu = normalize_region(text)
    if sido:
        found["region_sido"] = sido
    if sigungu:
        found["region_sigungu"] = sigungu

    age_match = re.search(r"(?:만\s*)?(\d{2})\s*(?:살|세)", text)
    if age_match:
        age = int(age_match.group(1))
        if 10 <= age <= 99:
            found["age"] = age
    else:
        decade = re.search(r"(\d)0대\s*(초반|중반|후반)?", text)
        if decade:
            base = int(decade.group(1)) * 10
            offset = {"초반": 2, "중반": 5, "후반": 8}.get(decade.group(2) or "", 5)
            found["age"] = base + offset

    for status, keywords in _STATUS_KEYWORDS.items():
        if any(k in text for k in keywords):
            found["employment_status"] = status
            break

    return found


def merge_profile(sidebar_profile: dict, session_context: dict, query: str) -> dict:
    """
    우선순위: 사이드바 입력 > 이번 질문에서 추출 > 이전 대화에서 확보한 정보
    반환 키: region_sido, region_sigungu, age, employment_status, income_level
    """
    merged: dict = {k: v for k, v in session_context.items() if v not in (None, "")}

    for key, value in extract_profile_from_text(query).items():
        merged[key] = value

    sidebar_sido = sidebar_profile.get("region_sido")
    if sidebar_sido:
        merged["region_sido"] = sidebar_sido
        merged["region_sigungu"] = sidebar_profile.get("region_sigungu")
    elif sidebar_profile.get("region"):
        # 자유 입력 지역(구버전 사이드바 호환)
        sido, sigungu = normalize_region(sidebar_profile["region"])
        if sido:
            merged["region_sido"], merged["region_sigungu"] = sido, sigungu

    for key in ("age", "employment_status", "income_level"):
        if sidebar_profile.get(key) not in (None, ""):
            merged[key] = sidebar_profile[key]

    return merged


def missing_required_fields(profile: dict) -> list[str]:
    """추천에 꼭 필요한데 아직 모르는 항목 (역질문 대상)"""
    missing = []
    if not profile.get("region_sido"):
        missing.append("거주지")
    if not profile.get("age"):
        missing.append("나이")
    if not profile.get("employment_status"):
        missing.append("현재 상태")
    return missing


# 질문 키워드 -> 시드 데이터 분야(category)
_CATEGORY_KEYWORDS = {
    "주거": ["월세", "전세", "주거", "집", "이사", "보증금", "자취", "원룸"],
    "자산형성": ["통장", "목돈", "저축", "적금", "계좌", "자산", "매칭"],
    "취업": ["취업", "구직", "일자리", "면접", "수당", "채용"],
    "교육훈련": ["교육", "훈련", "배움", "강의", "부트캠프", "코딩"],
    "교육": ["장학", "등록금", "학자금"],
    "창업": ["창업", "사업화", "스타트업"],
    "건강": ["상담", "마음", "우울", "심리"],
    "생활": ["교통", "문화", "공연", "복지포인트"],
}


def detect_categories(text: str) -> list[str]:
    """질문에서 관심 분야를 추출 (여러 개 가능)"""
    return [cat for cat, words in _CATEGORY_KEYWORDS.items() if any(w in text for w in words)]
