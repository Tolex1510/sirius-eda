def test_latency_histogram_distinguishes_slow_requests(client):
    client.get('/menu/items')
    metrics = client.get('/metrics').text
    # A one-second last finite bucket caps histogram_quantile, hiding overload.
    assert 'le="5.0"' in metrics
    assert 'le="30.0"' in metrics
