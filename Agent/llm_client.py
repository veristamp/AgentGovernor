#!/usr/bin/env python3
"""
Module for interfacing with the local LLM.
"""
from __future__ import annotations

import logging
import re
import sys
import requests
from typing import Any, Dict, List

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s llm_client :: %(message)s")
log = logging.getLogger("llm_client")

def get_llm_completion(
    system_prompt: str,
    user_prompt: str,
) -> str:
    """
    Gets a completion from the OpenAI-compatible local LLM.
    """
    url = f"{config.LLM_API_BASE}/chat/completions"
    payload = {
        "model": config.LLM_MODEL_NAME,
        "temperature": config.LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    
    log.info(f"Sending completion request to {url} for model {config.LLM_MODEL_NAME}")
    try:
        headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=config.LLM_TIMEOUT)

        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        log.info("Successfully received LLM completion.")
        return content
    except requests.exceptions.RequestException as e:
        log.error(f"API call failed: {e}")
        # This is a critical failure for the planner
        return f"Error: API call failed. {e}"
    except (KeyError, IndexError) as e:
        log.error(f"Invalid response structure from LLM API: {e}")
        return f"Error: Invalid LLM API response. {e}"

def extract_yaml_block(text: str) -> str:
    """
    Pulls the *last* fenced YAML block from model output.
    This is more robust, as LLMs sometimes output text or
    a "thinking" block before the final code.
    """
    matches = re.findall(r"```(yaml|yml)?\s*(.+?)\s*```", text, flags=re.S | re.I)
    
    if not matches:
        log.warning("No YAML block found in LLM output. Returning raw text.")
        return text.strip()
    
    # Return the content of the *last* match
    log.info("Extracted last YAML block from LLM output.")
    return matches[-1][1].strip()