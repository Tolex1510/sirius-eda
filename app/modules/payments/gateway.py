"""HTTP-адаптер ЮKassa. Повтор использует сохранённый ключ операции."""
import httpx
from app.domain.money import money
from app.modules.payments.contracts import GatewayRejected, GatewayResult, GatewayUnavailable, Payment, PaymentGateway


class YooKassaGateway(PaymentGateway):
    name = 'yookassa'

    def __init__(self, shop_id: str, secret: str, return_url: str, transport=None):
        self.auth = (shop_id, secret)
        self.return_url = return_url
        self.transport = transport

    def _request(self, method, path, key=None, body=None):
        if not all(self.auth):
            raise GatewayUnavailable("Тестовый магазин ЮKassa пока не настроен")
        try:
            with httpx.Client(base_url='https://api.yookassa.ru/v3/', auth=self.auth,
                              timeout=10, transport=self.transport) as client:
                response = client.request(method, path, json=body,
                                          headers={'Idempotence-Key': key} if key else {})
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    raise GatewayRejected('ЮKassa отклонила запрос: проверьте параметры и настройки тестового магазина')
                response.raise_for_status()
                return response.json()
        except GatewayRejected:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            # Не выдаём клиенту тело ответа и секреты. Неопределённый исход сверит worker.
            raise GatewayUnavailable('Провайдер не подтвердил результат. Проверка продолжится автоматически') from exc

    def _result(self, obj):
        try:
            if obj.get('test') is not True:
                raise ValueError('Разрешён только тестовый магазин')
            return GatewayResult(obj['id'], obj['status'], money(obj['amount']['value']),
                                 obj['amount']['currency'], int(obj['metadata']['order_id']),
                                 obj.get('confirmation', {}).get('confirmation_url'),
                                 obj.get('cancellation_details', {}).get('reason'))
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayUnavailable('Некорректный ответ тестового шлюза') from exc

    def create(self, payment):
        obj = self._request('POST', 'payments', payment.id, {
            'amount': {'value': str(payment.amount), 'currency': 'RUB'}, 'capture': True,
            'confirmation': {'type': 'redirect', 'return_url': self.return_url},
            'description': f'Сириус.Еда: заказ {payment.order_id}',
            'metadata': {'order_id': str(payment.order_id)},
        })
        return self._result(obj)

    def fetch(self, gateway_id):
        return self._result(self._request('GET', f'payments/{gateway_id}'))

    def refund(self, payment: Payment):
        if payment.refund_id:
            obj = self._request('GET', f'refunds/{payment.refund_id}')
        else:
            obj = self._request('POST', 'refunds', 'refund-' + payment.id, {
                'payment_id': payment.gateway_id,
                'amount': {'value': str(payment.amount), 'currency': 'RUB'},
            })
        try:
            if (obj.get('payment_id') != payment.gateway_id or money(obj['amount']['value']) != payment.amount
                    or obj['amount']['currency'] != 'RUB' or obj['status'] not in ('pending', 'succeeded', 'canceled')):
                raise ValueError('Данные возврата не совпадают')
            return obj['id'], obj['status']
        except (KeyError, TypeError, ValueError) as exc:
            raise GatewayUnavailable('Данные возврата не совпадают') from exc
