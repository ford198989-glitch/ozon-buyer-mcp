from ozon_buyer_mcp.service import _match_metrics


def test_exact_model_suffix_is_required():
    relevance, exact = _match_metrics("Genau Stride X", "Genau Stride X беговая дорожка")
    assert relevance >= 0.9
    assert exact is True

    relevance2, exact2 = _match_metrics("Genau Stride X", "Genau Stride беговая дорожка")
    assert relevance2 < 1.0
    assert exact2 is False


def test_numeric_model_is_preserved():
    relevance, exact = _match_metrics("GENAU S50 Studio", "Беговая дорожка Genau S50 Studio")
    assert relevance >= 0.9
    assert exact is True
