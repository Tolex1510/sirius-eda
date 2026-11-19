import httpx
import math
from app.modules.assistant.contracts import LanguageModel, ModelUnavailable, ModelResponseInvalid
from app.modules.assistant.quality import repetitive


class OllamaModel(LanguageModel):
    def __init__(self, url, model, embed_model, timeout=90, dimensions=1024, transport=None, host_header=None):
        self.url, self.model, self.embed_model = url.rstrip('/'), model, embed_model
        self.timeout, self.dimensions, self.transport = timeout, dimensions, transport
        self.host_header = host_header

    def _post(self, endpoint, body):
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=5), transport=self.transport, trust_env=False) as client:
                response = client.post(self.url + endpoint, json=body,
                                       headers={"Host": self.host_header} if self.host_header else None)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelUnavailable('Ollama недоступна') from exc

    def embed(self, texts):
        try:
            values = self._post('/api/embed', {'model': self.embed_model, 'input': texts, 'truncate': True, 'keep_alive': '30m', 'options': {'num_gpu': 0}})['embeddings']
            if len(values) != len(texts) or any(len(v) != self.dimensions or not all(math.isfinite(x) for x in v) for v in values):
                raise ValueError('Размерность эмбеддингов не совпадает с индексом')
            return values
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelUnavailable('Некорректные эмбеддинги') from exc

    def generate(self, messages):
        try:
            result = self._post('/api/chat', {'model': self.model, 'messages': messages, 'stream': False, 'keep_alive': '10m',
                                'options': {'temperature': 0.1, 'num_ctx': 8192, 'num_predict': 350, 'repeat_penalty': 1.15, 'seed': 7}})
            text = result['message']['content'].strip()
            if not text:
                raise ValueError('Пустой ответ')
            if repetitive(text):
                raise ModelResponseInvalid('Generation repetition loop')
            return text
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelUnavailable('Некорректный ответ модели') from exc
