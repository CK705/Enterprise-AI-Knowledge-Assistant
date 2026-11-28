"""Same-model credential failover for direct Groq and Gemini requests."""

import logging
import os

import httpx
from google.genai.errors import APIError as GoogleAPIError
from groq import APIConnectionError, InternalServerError, RateLimitError
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai._common import GoogleGenerativeAIError
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)


def provider_keys(name: str, primary_alias: str | None = None) -> list[str]:
    primary = os.getenv(name, "").strip()
    if not primary and primary_alias:
        primary = os.getenv(primary_alias, "").strip()
    keys = [primary, os.getenv(f"{name}_2", "").strip(), os.getenv(f"{name}_3", "").strip()]
    if not primary:
        raise ValueError(f"{name} must be configured.")
    return list(dict.fromkeys(filter(None, keys)))


def invoke_with_failover(clients, operation, provider, is_retryable):
    for index, client in enumerate(clients, start=1):
        try:
            return operation(client)
        except Exception as exc:
            if index == len(clients) or not is_retryable(exc):
                raise
            logger.warning(
                "%s credential slot %d failed with %s. Trying the next slot.",
                provider,
                index,
                type(exc).__name__,
            )


def build_chat(model="openai/gpt-oss-120b"):
    keys = provider_keys("GROQ_API_KEY")
    clients = [
        ChatGroq(model=model, temperature=0, api_key=key,
                 max_retries=0 if len(keys) > 1 else 2)
        for key in keys
    ]
    if len(clients) == 1:
        return clients[0]

    def invoke(prompt, config: RunnableConfig):
        return invoke_with_failover(
            clients,
            lambda client: client.invoke(prompt, config=config),
            "Groq",
            lambda exc: isinstance(exc, (RateLimitError, InternalServerError, APIConnectionError)),
        )

    return RunnableLambda(invoke, name="groq_credential_failover")


def is_retryable_google_error(error: Exception) -> bool:
    cause = error.__cause__ if isinstance(error, GoogleGenerativeAIError) else error
    if isinstance(cause, GoogleAPIError):
        return cause.code in {429, 500, 502, 503, 504}
    return isinstance(cause, (httpx.TransportError, TimeoutError))


class GeminiEmbeddingFailover(Embeddings):
    def __init__(self, clients: list[GoogleGenerativeAIEmbeddings]):
        self.clients = clients

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return invoke_with_failover(
            self.clients, lambda client: client.embed_documents(texts),
            "Gemini", is_retryable_google_error,
        )

    def embed_query(self, text: str) -> list[float]:
        return invoke_with_failover(
            self.clients, lambda client: client.embed_query(text),
            "Gemini", is_retryable_google_error,
        )


def build_embeddings() -> Embeddings:
    keys = provider_keys("GOOGLE_API_KEY", primary_alias="GEMINI_API_KEY")
    clients = [
        GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=key)
        for key in keys
    ]
    return clients[0] if len(clients) == 1 else GeminiEmbeddingFailover(clients)
