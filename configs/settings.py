"""
시니피에 프로젝트 전역 설정 (Pydantic Settings 기반)
환경 변수 또는 .env 파일에서 자동 로드됩니다.
"""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """앱 전역 설정"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- AWS Bedrock ---
    aws_region: str = "ap-northeast-2"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    bedrock_model_id: str = "anthropic.claude-opus-5-5"
    bedrock_effort: str = "low"  # low | medium | high (채팅 응답 속도 우선)
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    # --- Vector DB ---
    vector_db_type: str = "chromadb"  # "chromadb" | "faiss"
    vector_db_path: str = str(PROJECT_ROOT / "data" / "vectorstore")

    # --- 공공데이터 API ---
    data_go_kr_api_key: str = ""

    # --- 앱 ---
    app_env: str = "development"
    log_level: str = "INFO"
    streamlit_port: int = 8501


@lru_cache()
def get_settings() -> Settings:
    """싱글턴 패턴으로 Settings 인스턴스 반환"""
    return Settings()
