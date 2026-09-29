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
    )


def invoke_llm(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str:
    """
    Bedrock Claude 모델을 호출하여 텍스트 응답을 반환합니다.
    AWS 키가 없으면 Mock 응답을 반환합니다.
    """
    if _is_mock_mode():
        return _mock_llm_response(prompt)

    settings = get_settings()
    client = _get_bedrock_runtime()

    messages = [{"role": "user", "content": prompt}]

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }

    if system_prompt:
        body["system"] = system_prompt

    try:
        response = client.invoke_model(
            modelId=settings.bedrock_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]
    except Exception as e:
        logger.error(f"Bedrock LLM 호출 실패: {e}")
        logger.info("Fallback - Mock 응답 반환")
        return _mock_llm_response(prompt)


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
