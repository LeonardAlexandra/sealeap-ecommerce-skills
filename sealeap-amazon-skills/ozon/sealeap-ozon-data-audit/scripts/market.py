"""Small reproducible descriptive checks; not a market demand or sales model."""
from statistics import median


def descriptive_market(document):
    """Only use after audit; one frozen snapshot per SKU/spec is required."""
    groups, seller_counts, excluded = {}, {}, []
    seen = set()
    for record in document['records']:
        if record['role'] != 'competitor':
            continue
        fields = record['fields']
        key = (record['sku'], record['spec_group'])
        if key in seen:
            raise ValueError('duplicate competitor SKU/spec; select one snapshot explicitly')
        seen.add(key)
        price, quantity = fields.get('price_discount'), fields.get('pack_quantity')
        if not price or not quantity or price['kind'] == 'UNKNOWN' or quantity['kind'] == 'UNKNOWN':
            excluded.append(record['record_id'])
            continue
        if price['currency'] != 'RUB' or quantity['value'] <= 0:
            raise ValueError('price currency or pack quantity invalid')
        groups.setdefault(record['spec_group'], []).append(price['value'] / quantity['value'])
        if record['seller_id'] is not None:
            seller_counts[record['seller_id']] = seller_counts.get(record['seller_id'], 0) + 1
    return {'price_basis': 'observed discounted price per unit; not seller revenue',
            'groups': {k: {'sample_n': len(v), 'median_rub_per_unit': median(v), 'min': min(v), 'max': max(v)}
                       for k, v in groups.items()},
            'seller_listing_counts': seller_counts, 'excluded': excluded,
            'market_size': {'value': None, 'kind': 'UNKNOWN'},
            'sales_cr5': {'value': None, 'kind': 'UNKNOWN'},
            'sales_weighted_price': {'value': None, 'kind': 'UNKNOWN'},
            'limitations': ['Listing counts and reviews are not sales or market share.']}
