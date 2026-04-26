"""
classifier_v3_4.py
Tier-1 intent classifier for RUSLAN using YandexGPT Lite
Returns: (label, tokens_used)
"""

import aiohttp
import asyncio
import logging



from config_ruslan import (
    YANDEX_API_KEY,
    YANDEX_FOLDER_ID,
    YANDEX_API_URL,
    YANDEX_OPERATIONS_URL,
    YANDEX_MODEL_URI_LITE
)

logger = logging.getLogger(__name__)

async def classify_intent(user_input: str, last_response: str = None, timeout: float = 10.0) -> tuple[str, int]:
    """
    Classify user message intent using YandexGPT Lite (async mode)
    
    Args:
        user_input: User's input text
        last_response: Last bot response (for context-aware CONTINUE detection)
        timeout: Max wait time in seconds (default 10.0)
        
    Returns:
        (label, tokens_used)
        label: CASUAL, ABUSE, TEACH, CONTINUE, REVISION, MIXED
        tokens_used: Actual tokens consumed by Lite call
        
    On failure: Returns ("TEACH", 0) - safer to process than block
    """
    
    # Context-aware classifier prompt
    if last_response:
        classifier_prompt = f"""Previous bot answer: "{last_response[:100]}..."

User's new message: "{user_input}"

Is this CONTINUE (wants more on same topic) or new question?

Categories: CASUAL, ABUSE, TEACH, CONTINUE, REVISION, MIXED

Answer ONE word only:"""
    else:
        # No context - standard classification
        classifier_prompt = f"""Classify this message into ONE word only:

Categories: CASUAL, ABUSE, TEACH, CONTINUE, REVISION, MIXED

Message: {user_input}

Answer with one word only:"""
    
    # Prepare API request for YandexGPT Lite
    request_data = {
        "modelUri": YANDEX_MODEL_URI_LITE,
        "completionOptions": {
            "temperature": 0,  # Deterministic classification
            "maxTokens": 5     # Only need one word response
        },
        "messages": [
            {
                "role": "user",
                "text": classifier_prompt
            }
        ]
    }
    
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            
            # Submit async request
            async with session.post(
                YANDEX_API_URL,
                headers=headers,
                json=request_data
            ) as response:
                if response.status != 200:
                    logger.error(f"Classifier API error: {response.status}")
                    return ("TEACH", 0)
                
                result = await response.json()
                operation_id = result['id']
                logger.info(f"Classifier request submitted, operation_id: {operation_id}")
            
            # Poll for result
            result_url = f"{YANDEX_OPERATIONS_URL}/{operation_id}"
            
            for attempt in range(20):  # Try 20 times (10 seconds total)
                await asyncio.sleep(0.5)
                
                async with session.get(result_url, headers=headers) as poll_response:
                    if poll_response.status != 200:
                        continue
                    
                    poll_data = await poll_response.json()
                    
                    if poll_data.get('done'):
                        # Extract answer
                        answer = poll_data['response']['alternatives'][0]['message']['text'].strip().upper()
                        
                        # Extract token usage
                        usage = poll_data['response']['usage']
                     #   tokens_used = int(usage['inputTextTokens']) + int(usage['completionTokens'])
                        tokens_used = usage.get('inputTextTokens', 0) + usage.get('completionTokens', 0)
                        cost = int(tokens_used) / 1000 * 0.10  # Lite rate

                        logger.info(f"Classified as: {answer}, tokens: {tokens_used}, cost: {cost:.3f} RUB")
                        
                        # Validate response
                        valid_labels = ["CASUAL", "ABUSE", "TEACH", "CONTINUE", "REVISION", "MIXED"]
                        
                        if answer in valid_labels:
                            #logger.info(f"Classified as: {answer}, tokens: {tokens_used}")
                            return (answer, tokens_used)
                        else:
                            logger.warning(f"Invalid classifier response: {answer}, defaulting to TEACH")
                            return ("TEACH", tokens_used)
            
            # Timeout - polling exhausted
            logger.warning(f"Classifier polling timeout, defaulting to TEACH")
            return ("TEACH", 0)
    
    except asyncio.TimeoutError:
        logger.warning(f"Classifier timeout after {timeout}s, defaulting to TEACH")
        return ("TEACH", 0)
    except Exception as e:
        logger.error(f"Classifier error: {str(e)}, defaulting to TEACH")
        return ("TEACH", 0)
