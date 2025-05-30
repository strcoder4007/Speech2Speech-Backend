from flask import Flask, request, jsonify
import re
import requests
import uuid
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flask_cors import CORS
import time
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, SystemMessage
import asyncio
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages import AIMessage, BaseMessage
from typing import List, Optional, Any
from pydantic import Field
import traceback

app = Flask(__name__)
CORS(app)
load_dotenv('.env')

memory = ConversationBufferWindowMemory(
    memory_key="chat_history",
    return_messages=True,
    k=2
)

class QwenChatModel(BaseChatModel):
    api_url: str = Field(default="http://45.198.14.143:8002/v1/chat/completions")
    model: str = Field(default="Qwen/Qwen2.5-14B-Instruct-AWQ")
    temperature: float = Field(default=0.1)
    streaming: bool = Field(default=False)
    verbose: bool = Field(default=True)
    max_tokens: int = Field(default=60)

    def __init__(
        self,
        api_url: str = "http://45.198.14.143:8002/v1/chat/completions",
        model: str = "Qwen/Qwen2.5-14B-Instruct-AWQ",
        temperature: float = 0.1,
        streaming: bool = False,
        verbose: bool = True,
        max_tokens: int = 60,
    ):
        super().__init__()
        self.api_url = api_url
        self.model = model
        self.temperature = temperature
        self.streaming = streaming
        self.verbose = verbose
        self.max_tokens = max_tokens

    def _convert_message_to_dict(self, message: BaseMessage) -> dict:
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": message.content}
        elif isinstance(message, HumanMessage):
            return {"role": "user", "content": message.content}
        elif isinstance(message, AIMessage):
            return {"role": "assistant", "content": message.content}
        else:
            print(f"Warning: Unhandled message type: {type(message)}")
            return {"role": "user", "content": str(message.content)}

    def _generate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any
    ) -> ChatResult:
        formatted_messages = [self._convert_message_to_dict(m) for m in messages]

        # Count tokens (simple whitespace split as proxy)
        total_tokens = sum(len(m["content"].split()) for m in formatted_messages if "content" in m)
        print(f"Total tokens sent to LLM (approximate): {total_tokens}")

        if self.verbose:
            print(f"Sending request to Qwen API (sync): {formatted_messages}")

        payload = {
            "messages": formatted_messages,
            "temperature": self.temperature,
            "model": self.model,
            "stream": self.streaming,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens)
        }

        if stop:
            payload["stop"] = stop

        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            response_data = response.json()

            if self.verbose:
                print(f"Received response (sync): {response_data}")

            choices = response_data.get("choices", [])
            if not choices:
                raise ValueError("API response missing 'choices' field.")
            message_data = choices[0].get("message", {})
            message_content = message_data.get("content", "")

            ai_message = AIMessage(content=message_content)
            generation = ChatGeneration(message=ai_message)
            return ChatResult(generations=[generation], llm_output=response_data.get("usage"))

        except requests.exceptions.RequestException as e:
            error_msg = f"Error in Qwen API request (sync): {e}"
            print(error_msg)
            raise ConnectionError(error_msg) from e
        except Exception as e:
            error_msg = f"Error processing Qwen API response (sync): {e}"
            print(error_msg)
            raise ValueError(error_msg) from e

    async def _agenerate(
        self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs: Any
    ) -> ChatResult:
        formatted_messages = [self._convert_message_to_dict(m) for m in messages]

        # Count tokens (simple whitespace split as proxy)
        total_tokens = sum(len(m["content"].split()) for m in formatted_messages if "content" in m)
        print(f"Total tokens sent to LLM (approximate): {total_tokens}")

        if self.verbose:
            print(f"Sending request to Qwen API (async): {formatted_messages}")

        payload = {
            "messages": formatted_messages,
            "temperature": self.temperature,
            "model": self.model,
            "stream": self.streaming,
            "max_tokens": kwargs.get("max_tokens", self.max_tokens)
        }

        if stop:
            payload["stop"] = stop

        headers = {"Content-Type": "application/json"}

        try:
            response = await asyncio.to_thread(
                requests.post, self.api_url, headers=headers, json=payload
            )
            response.raise_for_status()
            response_data = response.json()

            if self.verbose:
                print(f"Received response (async): {response_data}")

            choices = response_data.get("choices", [])
            if not choices:
                 raise ValueError("API response missing 'choices' field.")
            message_data = choices[0].get("message", {})
            message_content = message_data.get("content", "")

            ai_message = AIMessage(content=message_content)
            generation = ChatGeneration(message=ai_message)
            return ChatResult(generations=[generation], llm_output=response_data.get("usage"))

        except requests.exceptions.RequestException as e:
            error_msg = f"Error in Qwen API request (async): {e}"
            print(error_msg)
            raise ConnectionError(error_msg) from e
        except Exception as e:
            error_msg = f"Error processing Qwen API response (async): {e}"
            print(error_msg)
            raise ValueError(error_msg) from e

    @property
    def _llm_type(self) -> str:
        return "qwen-chat"

llm = QwenChatModel(
    api_url="http://45.198.14.143:8002/v1/chat/completions",
    model="Qwen/Qwen2.5-14B-Instruct-AWQ",
    temperature=0.1,
    streaming=False,
    verbose=False,
)

qa_system_prompt = """You are an expert real estate agent and consultant specializing in helping clients optimize their spaces and maximize revenue. Provide insightful, practical advice on property usage, layout improvements, and strategies to increase profitability for various types of real estate (residential, commercial, retail, etc.). You may leverage data from Google Maps, Salesforce, and any other relevant sources to determine and optimize your recommendations. Your response must be strictly no more than 50 words. Respond to user queries with clear, actionable recommendations, and maintain a friendly, professional, and consultative tone. If you are unsure about an answer, acknowledge it honestly and suggest how the user might find more information."""

qa_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", qa_system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

def replace_decimal_with_parentheses(input_string):
    pattern = r'(\d+)\.(\d+)'
    matches = list(re.finditer(pattern, input_string))
    if not matches:
        return input_string
    result = re.sub(pattern, r'\1(\2)', input_string)
    return result

@app.route('/chatbot', methods=['POST']) # Changed route name
async def text_querytest():
    start_time_req = time.time()
    query = None
    lang = None
    name = None
    holoboxId = None
    chatId = str(uuid.uuid4())
    metadata = {}

    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Request body must be JSON', 'chatId': chatId}), 400

        query = data.get('query')
        lang = data.get('lang', 'en')
        name = data.get('name', 'testing')
        holoboxId = data.get('holoboxId', 'testing')

        if not query:
            return jsonify({'error': 'No query provided', 'chatId': chatId}), 400
        if not holoboxId:
             return jsonify({'error': 'holoboxId is required', 'chatId': chatId}), 400

        print(f"\n=================== [New Request] ===================")

        processed_query = replace_decimal_with_parentheses(query)
        if processed_query != query:
            print(f"Processed query: '{processed_query}'")

        start_generation = time.time()
        chat_history = memory.load_memory_variables({}).get("chat_history", [])
        if not isinstance(chat_history, list):
            chat_history = []

        # Simplified invocation:
        messages = qa_prompt.format_messages(input=processed_query, chat_history=chat_history)
        

        response = await llm.ainvoke(messages)
        answer = response.content 

        gpt_duration = time.time() - start_generation
        metadata['gptDuration'] = round(gpt_duration, 3)
        print(f"Generated answer in {gpt_duration:.3f} seconds.")

        total_duration = time.time() - start_time_req
        metadata['totalDuration'] = round(total_duration, 3)

        final_answer_str = str(answer) if answer else "Error: No answer generated."
        memory.save_context({'input': processed_query}, {'output': final_answer_str})

        # Removed logging task

        print("*************************************")
        print(f"[QUESTION]: {str(processed_query).encode('utf-8', errors='replace').decode('utf-8')}")
        print(f"[ANSWER]: {str(final_answer_str).encode('utf-8', errors='replace').decode('utf-8')}")
        print(f"NO. OF WORDS: {len(final_answer_str.split())}")
        print(f"Total time: {total_duration:.3f} seconds")
        print("*************************************")

        return jsonify({
            'answer': final_answer_str,
            'chatId': chatId,
            'metadata': metadata
        })

    except Exception as e:
        error_details = traceback.format_exc()
        print(f"!!! Critical Error in /chatbot endpoint for chatId {chatId}: {e}\n{error_details}") # Changed route name in log
        total_duration_error = time.time() - start_time_req

        error_type_name = type(e).__name__
        error_message_str = str(e)


        return jsonify({
            'error': f"An internal server error occurred. Please try again later. Error ID: {chatId}",
            'chatId': chatId
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8003, debug=False)
