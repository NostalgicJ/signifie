"""
AWS Bedrock 연결 점검 스크립트
.env에 AWS 키를 넣은 뒤 실행: python -m scripts.check_bedrock
Claude 호출과 Titan 임베딩을 각각 시도하고, 실패하면 원인을 그대로 보여줍니다.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configs.settings import get_settings  # noqa: E402
from src.backend.llm.bedrock_client import _get_bedrock_runtime, call_claude, is_mock_mode  # noqa: E402


def main() -> int:
    settings = get_settings()
    if is_mock_mode():
        print("❌ AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY가 비어 있습니다 (.env 확인)")
        return 1

    print(f"리전: {settings.aws_region} | LLM: {settings.bedrock_model_id} | 임베딩: {settings.bedrock_embedding_model_id}")
    ok = True

    try:
        answer = call_claude("한 문장으로 자기소개 해줘.", max_tokens=200)
        print(f"✅ Claude 응답: {answer.strip()[:100]}")
    except Exception as e:  # noqa: BLE001 - 점검용으로 원인을 그대로 출력
        ok = False
        print(f"❌ Claude 호출 실패: {type(e).__name__}: {e}")

    try:
        response = _get_bedrock_runtime().invoke_model(
            modelId=settings.bedrock_embedding_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": "청년 월세 지원", "dimensions": 1024, "normalize": True}),
        )
        dim = len(json.loads(response["body"].read())["embedding"])
        print(f"✅ Titan 임베딩: {dim}차원")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"❌ Titan 임베딩 실패: {type(e).__name__}: {e}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
