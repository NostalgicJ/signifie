# 🔍 시니피에 (Signifié)

> **"성북구 사는 25살 취준생인데 받을 수 있는 지원금 있어?"**
> 한 문장으로 물으면, 내 조건에 맞는 청년·지자체 지원사업과 **신청 서류 체크리스트**를 정리해 주는 대화형 RAG 비서

고려대학교 x AWS AI Innovators Challenge 출품작

---

## 해결하려는 문제

청년 지원사업은 중앙부처·광역·기초 지자체에 흩어져 있고, 공고마다 연령·거주지·소득·취업상태 조건이 다릅니다.
청년은 ① 내가 받을 수 있는 사업을 찾는 데 한 번, ② 공고문에서 제출 서류를 추리는 데 또 한 번 시간을 씁니다.
시니피에는 이 두 단계를 대화 한 번으로 줄입니다.

## 핵심 기능 (구현 완료)

| 기능 | 설명 |
|---|---|
| 구어체 조건 이해 | "성북에 사는 25살 취준생" → `서울특별시 / 성북구 / 25세 / 취업준비생` 으로 정규화 |
| 메타데이터 1차 필터링 | ChromaDB `where` 조건으로 **거주지·연령·취업상태·소득** 이 맞지 않는 공고를 검색 단계에서 제외 |
| 안전한 조건 완화 | 결과가 없으면 소득 → 상태 → 연령 순으로 완화하되 **지역 조건은 절대 풀지 않아** 타 지역 공고가 섞이지 않음 |
| 역질문 | 거주지·나이를 모르면 부족한 항목만 되묻기 (최대 2회, 이후엔 확보한 정보로 추천) |
| 체크리스트 응답 | 요약 표 + 사업별 `- [ ]` 구비서류 체크리스트 + 신청 팁 + 원본 신청 링크 |
| 멀티턴 기억 | 앞선 대화에서 말한 조건을 세션에 저장해 다시 묻지 않음 |
| 키 없이 데모 가능 | AWS 키가 없으면 결정적 로컬 임베딩 + 템플릿 응답으로 동일한 흐름 동작 |

## 아키텍처

```
 사용자 질문 ─┐
 사이드바 프로필 ─┼─▶ profile.py ── 지역/나이/상태 정규화·병합
 이전 대화 ─────┘         │
                          ├─ 필수 정보 부족 ─▶ 역질문 (CLARIFY_TEMPLATE)
                          ▼
                  vectorstore.build_where_filter()
                          │  region_sido ∈ {전국, 내 시도} AND age_min ≤ 나이 ≤ age_max
                          │  AND st_<상태> = True AND income_max_pct > 내 소득구간
                          ▼
                  ChromaDB 유사도 검색 (Titan Embed v2 / 로컬 n-gram)
                          ▼
                  AWS Bedrock Claude (RAG_QUERY_TEMPLATE)
                  └ 키 미설정·실패 시 템플릿 렌더러로 동일 형식 응답
                          ▼
             요약 표 + 📋 서류 체크리스트 + 💡 신청 팁 + 🔗 출처
```

| 영역 | 기술 |
|---|---|
| Frontend | Streamlit |
| LLM | AWS Bedrock – Anthropic Claude |
| Embedding | Amazon Titan Text Embeddings V2 (키 미설정 시 로컬 문자 n-gram 해싱 임베딩) |
| Vector DB | ChromaDB (Persistent, cosine) |
| Data | 청년정책 시드 데이터 38건 + 공공데이터포털(보조금24) API 수집 모듈 |

## 프로젝트 구조

```
Signifié/
├── app.py                         # Streamlit 엔트리포인트 (Vector DB 비어 있으면 자동 적재)
├── configs/settings.py            # Pydantic Settings (.env / 환경변수)
├── data/raw/seed_policies.json    # 청년 지원사업 38건 (전국 16 · 서울 9 · 경기 5 · 부산/인천/대전/광주 각 2)
├── src/
│   ├── backend/
│   │   ├── llm/bedrock_client.py  # Claude 호출, Titan 임베딩, 로컬 임베딩 fallback
│   │   └── rag/
│   │       ├── profile.py         # 지역명 정규화, 구어체 조건 추출, 프로필 병합
│   │       ├── vectorstore.py     # ChromaDB 저장/검색, where 필터 생성
│   │       ├── prompts.py         # 시스템/추천/역질문/정보추출 프롬프트
│   │       └── chain.py           # 역질문 ↔ 검색 ↔ 생성 파이프라인
│   ├── data_pipeline/
│   │   ├── fetcher.py             # 공공데이터포털 API 수집
│   │   ├── preprocessor.py        # 시드/API 레코드 → 문서 + 필터용 메타데이터
│   │   └── loader.py              # ChromaDB 배치 적재
│   └── frontend/
│       ├── chat_ui.py             # 채팅 UI, 예시 질문, 출처 표시
│       └── sidebar.py             # 시/도·시/군/구·나이·상태·소득 입력
├── scripts/
│   ├── seed_sample_data.py        # 시드 데이터 적재 (--reset 으로 재생성)
│   └── ingest_data.py             # API 수집 → 전처리 → 적재 파이프라인
└── tests/test_filtering.py        # 지역/연령/상태/소득 필터 및 역질문 흐름 테스트 (14개)
```

### 메타데이터 스키마

ChromaDB 메타데이터는 스칼라 값만 필터링할 수 있어 조건을 평탄화해 저장합니다.

| 키 | 예시 | 필터 |
|---|---|---|
| `region_sido` / `region_sigungu` | `서울특별시` / `전체` | `$in [전국, 내 시도]`, `$in [전체, 내 시군구]` |
| `age_min` / `age_max` | `19` / `34` | `age_min ≤ 나이 ≤ age_max` |
| `st_student`, `st_jobseeker`, `st_employed`, `st_self_employed`, `st_other` | `True` | 내 상태 플래그 `= True` |
| `income_max_pct` | `150` (제한 없음 `999`) | 내 소득구간 하한 `<` 기준선 |
| `required_docs`, `tips` | `"주민등록등본\|통장 사본"` | 체크리스트 렌더링용 |

## 실행 방법

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # AWS 키를 넣으면 Bedrock 모드, 비워두면 데모 모드
python -m scripts.seed_sample_data --reset
streamlit run app.py
```

테스트:

```bash
pip install pytest && python -m pytest -q
```

### 배포 (Streamlit Community Cloud)

1. 이 저장소를 연결하고 Main file을 `app.py`로 지정합니다.
2. (선택) Secrets에 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_MODEL_ID`를 넣으면 Bedrock 모드로 동작합니다.
3. 첫 실행 시 Vector DB가 비어 있으면 시드 데이터를 자동 적재합니다.

## 데모 시나리오

1. "지원금 뭐 있어?" → 거주지·나이·상태를 되묻고, 우선 전국 공통 사업 이름을 보여줌
2. "성북구 사는 25살 취준생이야" → 서울·전국 사업만 표로 정리, 서울시 청년수당 등 상세 체크리스트
3. 사이드바에서 경기도 / 직장인으로 바꾸고 "목돈 모을 통장 있어?" → 경기 청년 노동자 통장, 청년내일저축계좌 추천 (서울 사업 제외)

## 현재 한계와 다음 단계

- **데이터 최신성**: 시드 데이터는 2025년 공고 기준 요약으로, 금액·기간이 연도별로 바뀔 수 있습니다. 응답마다 원문 확인 안내와 신청 링크를 붙였습니다.
  → 다음 단계: 온통청년 청년정책 Open API / 보조금24 API 정기 수집으로 교체 (`fetcher.py` → `preprocessor.py` 경로는 이미 API 필드를 지원)
- **기초 지자체 사업**: 스키마와 필터는 시/군/구 단위를 지원하지만, 시드 데이터에는 아직 광역 단위 사업만 있습니다.
- **Bedrock 모드**: 코드 경로는 구현되어 있으며, 대회 데모는 AWS 키 없이 로컬 임베딩 + 템플릿 응답 모드로 동작합니다.
- 다음 단계: 응답 스트리밍, 중복 수급 자동 판정, 신청 마감 알림.

## 라이선스

MIT
