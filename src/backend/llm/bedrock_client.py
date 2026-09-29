"""
AWS Bedrock LLM 클라이언트
Claude 모델 호출 및 임베딩 생성을 담당합니다.
Mock 모드: AWS 키가 없으면 LLM 호출을 생략하고, 임베딩은 결정적 로컬 n-gram 임베딩을 사용합니다.
"""

import hashlib
import json
import logging
import math
import re
from functools import lru_cache

import anthropic
import boto3
from configs.settings import get_settings

logger = logging.getLogger(__name__)


def _is_mock_mode() -> bool:
    """AWS 키가 설정되지 않았으면 Mock 모드로 동작"""
    settings = get_settings()
    no_access = not settings.aws_access_key_id or settings.aws_access_key_id == "your-access-key-id"
    no_secret = not settings.aws_secret_access_key or settings.aws_secret_access_key == "your-secret-access-key"
    return no_access or no_secret


def _mock_llm_response(prompt: str) -> str:
    """
    Mock LLM 응답.
    실제 답변 생성은 chain.py가 검색 결과로 직접 렌더링하므로(키 미설정 데모 모드),
    여기서는 호출 실패를 알리는 빈 문자열만 반환합니다.
    """
    logger.info("[MOCK MODE] LLM 호출 생략")
    return ""


def is_mock_mode() -> bool:
    """외부 모듈에서 Mock 여부를 확인할 때 사용"""
    return _is_mock_mode()


EMBEDDING_DIM = 1024


def _local_embedding(text: str) -> list[float]:
    """
    결정적(deterministic) 로컬 임베딩 - 한국어 문자 n-gram 해싱 벡터.
    - 같은 텍스트는 어느 프로세스에서든 같은 벡터 (md5 사용, 파이썬 hash() 미사용)
    - "월세"·"청년수당" 같은 어휘가 겹치면 코사인 유사도가 높아져 키 없이도 검색 품질 검증 가능
    """
    vec = [0.0] * EMBEDDING_DIM
    normalized = re.sub(r"[^0-9a-zA-Z가-힣 ]", " ", text.lower())
    tokens = normalized.split()

    features: list[tuple[str, float]] = [(f"w:{t}", 1.5) for t in tokens]
    for token in tokens:
        for n, weight in ((2, 1.0), (3, 0.7)):
            for i in range(len(token) - n + 1):
                features.append((f"{n}:{token[i:i + n]}", weight))

    for feature, weight in features:
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
        sign = 1.0 if digest[4] & 1 else -1.0
        vec[index] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@lru_cache()
def _get_bedrock_runtime():
    """Bedrock Runtime 클라이언트 싱글턴"""
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        aws_session_token=settings.aws_session_token or None,
    )


@lru_cache()
def _get_claude_client() -> anthropic.AnthropicBedrockMantle:
    """Anthropic SDK의 Bedrock(Mantle) 클라이언트 싱글턴"""
    settings = get_settings()
    return anthropic.AnthropicBedrockMantle(
        aws_access_key=settings.aws_access_key_id or None,
        aws_secret_key=settings.aws_secret_access_key or None,
        aws_session_token=settings.aws_session_token or None,
        aws_region=settings.aws_region,
        timeout=60.0,
    )


def call_claude(prompt: str, system_prompt: str = "", max_tokens: int = 2048) -> str:
    """
    Bedrock Claude를 호출해 텍스트를 반환합니다. 실패하면 예외를 그대로 올립니다.
    (연결 점검 스크립트에서 원인 확인용으로 사용)
    """
    settings = get_settings()
    params = {
        "model": settings.bedrock_model_id,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        # 대화형 응답이라 속도 우선 (최신 모델은 temperature 대신 effort로 조절)
        "output_config": {"effort": settings.bedrock_effort},
    }
    if system_prompt:
        params["system"] = system_prompt

    response = _get_claude_client().messages.create(**params)
    if response.stop_reason == "refusal":
        logger.warning("Claude가 응답을 거절했습니다 (refusal)")
        return ""
    return "".join(block.text for block in response.content if block.type == "text")


def invoke_llm(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,  # noqa: ARG001 - 최신 Claude는 sampling 파라미터 미지원, 호환용으로만 유지
) -> str:
    """
    Bedrock Claude 모델을 호출하여 텍스트 응답을 반환합니다.
    AWS 키가 없거나 호출이 실패하면 빈 문자열을 반환하고, chain.py가 템플릿 응답으로 대체합니다.
    """
    if _is_mock_mode():
        return _mock_llm_response(prompt)

    try:
        return call_claude(prompt, system_prompt=system_prompt, max_tokens=max_tokens)
    except anthropic.APIStatusError as e:
        logger.error(f"Bedrock Claude 호출 실패 ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError as e:
        logger.error(f"Bedrock 연결 실패: {e}")
    logger.info("Fallback - 템플릿 응답 사용")
    return ""


def generate_embeddings(text: str) -> list[float]:
    """
    Bedrock Titan Embedding 모델로 텍스트 임베딩 벡터를 생성합니다.
    AWS 키가 없으면 로컬 n-gram 임베딩을 반환합니다.
    """
    if _is_mock_mode():
        return _local_embedding(text)

    settings = get_settings()
    client = _get_bedrock_runtime()

    body = {
        "inputText": text,
        "dimensions": 1024,
        "normalize": True,
    }

    try:
        response = client.invoke_model(
            modelId=settings.bedrock_embedding_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        response_body = json.loads(response["body"].read())
        return response_body["embedding"]
    except Exception as e:
        logger.error(f"Bedrock 임베딩 생성 실패: {e}")
        logger.info("Fallback - Mock 임베딩 반환")
        return _local_embedding(text)
