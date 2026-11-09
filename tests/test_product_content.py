import json
from ozon_buyer_mcp.parsers import parse_details


def page(**data):
    return {'widgetStates': {name + '-1': json.dumps(value) for name, value in data.items()}}


def test_details_extract_page2():
    base = page(webShortCharacteristics={'items': [{'name': 'Width, cm', 'value': '40'}]})
    more = page(webCharacteristics={'groups': [{'title': 'Dimensions', 'characteristics': [
        {'name': 'Height, cm', 'values': [{'text': '80'}]},
        {'name': 'Width, cm', 'values': [{'text': '40'}]},
        {'name': 'Material', 'values': [{'text': 'Wood'}, {'text': 'Metal'}]},
    ]}]}, webDescription={'text': '<p>Product &amp; details</p>', 'images': [{'src': 'https://cdn.test/a.jpg'}]})
    result = parse_details(base, more)
    assert result.characteristics == {'Width, cm': '40', 'Height, cm': '80', 'Material': 'Wood; Metal'}
    assert result.description.text == 'Product & details'
    assert result.description.images == ['https://cdn.test/a.jpg']


def test_details_ignore_unrelated_widgets_and_malformed_data():
    data = page(menu={'text': 'Menu', 'name': 'Bad', 'value': 'Bad'},
                recommendations={'text': 'Other product'},
                webCharacteristics={'items': [None, {'name': 'Missing'}, {'name': 'Count', 'value': 2}]})
    data['widgetStates']['webDescription-broken'] = '{'
    data['widgetStates']['webDescription-valid'] = json.dumps({'text': 'Actual description'})
    result = parse_details(data)
    assert result.characteristics == {'Count': '2'}
    assert result.description.text == 'Actual description'


def test_details_bounds_and_deduplication():
    data = page(webDescription={'text': 'x' * 50000}, webCharacteristics={'items': [
        {'name': str(n), 'value': 'v'} for n in range(500)]})
    result = parse_details(data, data)
    assert len(result.characteristics) == 200
    assert len(result.description.text) == 12000
