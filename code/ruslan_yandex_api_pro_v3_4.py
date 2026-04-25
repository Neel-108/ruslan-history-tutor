"""
yandex_api_pro.py
YandexGPT Pro API wrapper with rate limiting and retry logic
Based on English Tutor yandex_api.py
"""

import asyncio
import aiohttp
import logging

from config_ruslan import (
    YANDEX_API_KEY,
    YANDEX_API_URL,
    YANDEX_OPERATIONS_URL,
    YANDEX_MODEL_URI_PRO,
    TEMPERATURE,
    RATE_LIMIT_DELAY
)

logger = logging.getLogger(__name__)

# Global rate limiting
_last_request_time = 0.0


async def call_yandex_gpt_pro(prompt: str, max_tokens: int = 500) -> dict:
    """
    Call YandexGPT Pro with rate limiting and retry logic
    
    YandexGPT uses async mode:
    1. Submit request → get operation_id
    2. Poll operation status until done
    3. Extract answer and token counts
    
    Args:
        prompt: Complete prompt (static + dynamic)
        max_tokens: Maximum tokens for response
        
    Returns:
        {
            'answer': str,
            'tokens': {
                'input': int,
                'output': int,
                'total': int
            }
        }
        
    Raises:
        Exception: If all retries exhausted or critical error
    """
    global _last_request_time
    
    # ========================================================================
    # RATE LIMITING: Enforce minimum delay between requests
    # ========================================================================
    current_time = asyncio.get_event_loop().time()
    time_since_last = current_time - _last_request_time
    
    if time_since_last < RATE_LIMIT_DELAY:
        delay_needed = RATE_LIMIT_DELAY - time_since_last
        await asyncio.sleep(delay_needed)
    
    _last_request_time = asyncio.get_event_loop().time()
    
    # ========================================================================
    # PREPARE API REQUEST
    # ========================================================================
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "modelUri": YANDEX_MODEL_URI_PRO,
        "completionOptions": {
            "temperature": TEMPERATURE,
            "maxTokens": max_tokens
        },
        "messages": [
            {
                "role": "user",
                "text": prompt
            }
        ]
    }
    
    # ========================================================================
    # SUBMIT REQUEST WITH RETRY LOGIC
    # ========================================================================
    max_submit_retries = 3
    operation_id = None
    
    for submit_attempt in range(max_submit_retries):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.post(
                    YANDEX_API_URL, 
                    headers=headers, 
                    json=payload
                ) as response:
                    data = await response.json()
                    
                    # Handle rate limiting (HTTP 429)
                    if response.status == 429:
                        wait_time = 2 ** submit_attempt
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    # Handle other errors
                    if response.status != 200:
                        raise Exception(f"YandexGPT error: {data}")
                    
                    # Success - got operation_id
                    operation_id = data['id']
                    logger.info(f"Request submitted, operation_id: {operation_id}")
                    break
                    
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if submit_attempt == max_submit_retries - 1:
                raise Exception(f"Failed to submit request after {max_submit_retries} attempts: {e}")
            await asyncio.sleep(1)
    
    if not operation_id:
        raise Exception("Failed to get operation ID from YandexGPT")
    
    # ========================================================================
    # POLL FOR RESULT WITH EXPONENTIAL BACKOFF
    # ========================================================================
    result_url = f"{YANDEX_OPERATIONS_URL}/{operation_id}"
    max_poll_attempts = 40
    base_delay = 2
    
    for poll_attempt in range(max_poll_attempts):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                async with session.get(result_url, headers=headers) as response:
                    result_data = await response.json()
                    
                    # Check if operation is complete
                    if result_data.get('done'):
                        # Check for errors
                        if 'error' in result_data:
                            error_msg = result_data['error'].get('message', 'Unknown error')
                            raise Exception(f"YandexGPT API error: {error_msg}")
                        
                        # Extract answer and token counts
                        answer = result_data['response']['alternatives'][0]['message']['text']
                        usage = result_data['response']['usage']
                        
                        tokens = {
                            'input': int(usage['inputTextTokens']),
                            'output': int(usage['completionTokens']),
                            'total': int(usage['inputTextTokens']) + int(usage['completionTokens'])
                        }
                        
                        cost_current = tokens['total'] / 1000 * 0.61  # Current discounted rate
                        cost_future = tokens['total'] / 1000 * 0.40   # Future non-discounted rate
                        
                        logger.info("=" * 70)
                        logger.info("YandexGPT Pro Response")
                        logger.info("=" * 70)
                        logger.info(f"Tokens - Input: {tokens['input']}, Output: {tokens['output']}, Total: {tokens['total']}")
                        logger.info(f"Cost: Current (0.61/1k): {cost_current:.2f} RUB | Future (0.40/1k): {cost_future:.2f} RUB")
                        logger.info("=" * 70)
                        
                        return {
                            'answer': answer,
                            'tokens': tokens
                        }
                    
                    # Operation still processing - wait with exponential backoff
                    if poll_attempt < 5:
                        delay = base_delay * (1.5 ** poll_attempt)
                    else:
                        delay = 3
                    
                    await asyncio.sleep(min(delay, 10))
                    
        except asyncio.TimeoutError:
            if poll_attempt == max_poll_attempts - 1:
                raise Exception("YandexGPT timeout - no response after 120 seconds")
            await asyncio.sleep(2)
            
        except aiohttp.ClientError as e:
            if poll_attempt == max_poll_attempts - 1:
                raise Exception(f"Network error polling YandexGPT: {e}")
            await asyncio.sleep(2)
    
    raise Exception("YandexGPT timeout - exceeded maximum polling attempts")