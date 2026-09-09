"""
LM Studio Client for MathriSurakshaAI.
Communicates with locally running LM Studio OpenAI-compatible REST server.
"""

import requests
from typing import List, Dict, Any, Optional
from config import LM_STUDIO_BASE_URL, LM_STUDIO_MODEL, LM_STUDIO_TIMEOUT, LM_STUDIO_API_KEY


class LMStudioError(Exception):
    """Base exception for LM Studio client errors."""
    pass


class LMStudioConnectionError(LMStudioError):
    """Raised when connecting to the LM Studio server fails."""
    pass


class LMStudioTimeoutError(LMStudioError):
    """Raised when an LM Studio request times out."""
    pass


class LMStudioAPIError(LMStudioError):
    """Raised when LM Studio returns an HTTP error."""
    pass


class LMStudioClient:
    """Client for querying local LM Studio server via OpenAI-compatible endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        default_model: Optional[str] = None,
    ):
        self.base_url = (base_url or LM_STUDIO_BASE_URL).rstrip("/")
        self.api_key = api_key or LM_STUDIO_API_KEY
        self.timeout = timeout or LM_STUDIO_TIMEOUT
        self.default_model = default_model if default_model is not None else LM_STUDIO_MODEL

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def check_connection(self, timeout: float = 2.0) -> Dict[str, Any]:
        """
        Quick diagnostic check to verify whether the LM Studio server is running.
        Returns a dict with status, available models, and diagnostic messages.
        """
        url = f"{self.base_url}/models"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=timeout)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                models = [item.get("id", "") for item in data if isinstance(item, dict) and "id" in item]
                active_model = self.default_model or (models[0] if models else "local-model")
                return {
                    "online": True,
                    "models": models,
                    "active_model": active_model,
                    "message": f"Connected to LM Studio at {self.base_url}",
                }
            else:
                return {
                    "online": False,
                    "models": [],
                    "active_model": None,
                    "message": f"LM Studio responded with HTTP {resp.status_code}: {resp.text}",
                }
        except requests.exceptions.Timeout:
            return {
                "online": False,
                "models": [],
                "active_model": None,
                "message": f"Connection timed out when reaching LM Studio at {self.base_url}.",
            }
        except requests.exceptions.ConnectionError:
            return {
                "online": False,
                "models": [],
                "active_model": None,
                "message": f"Cannot connect to LM Studio at {self.base_url}. Please ensure LM Studio is open and the local server is started.",
            }
        except Exception as e:
            return {
                "online": False,
                "models": [],
                "active_model": None,
                "message": f"Error connecting to LM Studio: {str(e)}",
            }

    def get_models(self) -> List[str]:
        """Fetch list of model identifiers loaded in LM Studio."""
        url = f"{self.base_url}/models"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [m.get("id") for m in data if isinstance(m, dict) and "id" in m]
        except Exception:
            return []

    def create_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """
        Send a chat completion request to LM Studio and return the generated text.
        """
        chosen_model = model or self.default_model
        if not chosen_model:
            available = self.get_models()
            chosen_model = available[0] if available else "local-model"

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise LMStudioAPIError("LM Studio returned empty choices.")
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        except requests.exceptions.Timeout:
            raise LMStudioTimeoutError(
                f"LM Studio request timed out after {self.timeout} seconds. The model may be generating slowly or overloaded."
            )
        except requests.exceptions.ConnectionError:
            raise LMStudioConnectionError(
                f"Failed to connect to LM Studio server at {self.base_url}. Please ensure the server is active."
            )
        except requests.exceptions.HTTPError as e:
            raise LMStudioAPIError(f"LM Studio API returned an error: {e.response.text if hasattr(e, 'response') else str(e)}")
        except Exception as e:
            if isinstance(e, LMStudioError):
                raise
            raise LMStudioError(f"Unexpected error communicating with LM Studio: {str(e)}")
