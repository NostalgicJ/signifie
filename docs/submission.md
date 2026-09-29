# 제출 정보 (팀 정보 작성용)

- **팀 이름**: 시니피에
- **서비스명**: 시니피에 (Signifié)
- **소개 (300자 이내)**:

"성북구 사는 25살 취준생인데 받을 수 있는 지원금 있어?" 한 문장이면 충분합니다. 시니피에는 구어체 질문에서 거주지·나이·취업상태를 추출하고, 부족하면 되물은 뒤 ChromaDB 메타데이터 필터로 자격이 맞지 않는 타 지역·타 조건 공고를 검색 단계에서 제외합니다. AWS Bedrock(Claude, Titan Embeddings) 기반 RAG로 추천 사업을 요약 표와 구비서류 체크리스트, 신청 팁, 원문 링크까지 한 번에 정리해 주는 청년 지원금 AI 비서입니다.

## 제출물
- 서비스 소개서: `docs/signifie_service_intro.pdf` (10장)
- 소스: https://github.com/NostalgicJ/signifie
- 배포 주소: https://signifie.streamlit.app/
