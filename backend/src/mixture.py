import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from .domain import Profile

SEED = 1071
REG_COVAR = 0.025
FEATURES = ('day_temp', 'night_temp', 'day_rh', 'night_rh')


def _profile_names(model):
    # Order by warm/dry tendency rather than arbitrary mixture component indices.
    order = np.argsort(model.means_ @ np.array([1, 1, -1, -1]), kind='stable')
    profile_order = {1: [Profile.BALANCED], 2: [Profile.COOL, Profile.WARM],
                     3: [Profile.COOL, Profile.BALANCED, Profile.WARM]}[model.n_components]
    return {int(component): profile for component, profile in zip(order, profile_order)}


def _gaussian(matrix, count):
    model = GaussianMixture(n_components=count, covariance_type='diag', reg_covar=REG_COVAR,
                            n_init=10, random_state=SEED).fit(matrix)
    if not model.converged_:
        raise ValueError(f'{count} 群拟合未收敛。')
    return model


def block_features(item):
    """Four diurnal means for one block, or None when a whole day/night slot is absent."""
    readings = item.get('readings') or []
    day = [row for row in readings if row['slot'] == 'day']
    night = [row for row in readings if row['slot'] == 'night']
    if not day or not night:
        return None
    return [float(np.mean([row['temp_c'] for row in day])),
            float(np.mean([row['temp_c'] for row in night])),
            float(np.mean([row['rh_pct'] for row in day])),
            float(np.mean([row['rh_pct'] for row in night]))]


def feature_rows(snapshot):
    rows, items = [], []
    for item in snapshot:
        values = block_features(item)
        if values is None:
            continue
        rows.append(values)
        items.append(item)
    return np.array(rows, dtype=float), items


def fit_profiles(snapshot):
    features = np.array([[np.mean([r['temp_c'] for r in item['readings'] if r['slot'] == 'day']),
                          np.mean([r['temp_c'] for r in item['readings'] if r['slot'] == 'night']),
                          np.mean([r['rh_pct'] for r in item['readings'] if r['slot'] == 'day']),
                          np.mean([r['rh_pct'] for r in item['readings'] if r['slot'] == 'night'])]
                         for item in snapshot])
    scaler = StandardScaler().fit(features)
    matrix = scaler.transform(features)
    if len(np.unique(matrix, axis=0)) < 2:
        raise ValueError('采样特征无差异，无法识别微气候群落。')
    counts = range(1, min(3, len(np.unique(matrix, axis=0))) + 1)
    candidates = [GaussianMixture(n_components=k, covariance_type='diag', reg_covar=REG_COVAR,
                                  n_init=10, random_state=SEED).fit(matrix) for k in counts]
    scores = {str(m.n_components): float(m.bic(matrix)) for m in candidates if m.converged_}
    if not scores:
        raise ValueError('全部候选组数未收敛。')
    model = min((m for m in candidates if m.converged_), key=lambda m: scores[str(m.n_components)])
    centroids = scaler.inverse_transform(model.means_)
    names = _profile_names(model)
    posterior = model.predict_proba(matrix)
    return {
        'chosen_k': model.n_components, 'bic': scores, 'seed': SEED,
        'covariance_type': 'diag', 'reg_covar': REG_COVAR, 'n_init': 10, 'features': FEATURES,
        'centroids': {names[i]: dict(zip(FEATURES, row.tolist())) for i, row in enumerate(centroids)},
        'assignments': [dict(block_id=item['block_id'], code=item['code'],
                             profile=names[int(np.argmax(p))], confidence=float(max(p)))
                        for item, p in zip(snapshot, posterior)],
    }


def blind_compare(train_snapshot, test_snapshot, published_labels, coverage, block_names=None):
    """Fit two- and three-group models on the earlier window, then only assign the later one.

    The scaler and both mixtures see training rows alone. The test window is transformed with
    that scaler and labelled with the frozen models; it never contributes to fitting.
    """
    block_names = block_names or {}
    train_rows, train_items = feature_rows(train_snapshot)
    if len(train_items) < 3:
        raise ValueError('训练窗口可用于拟合的地块不足 3 个。')
    if len(np.unique(train_rows, axis=0)) < 3:
        raise ValueError('训练窗口特征不足以区分三群。')
    scaler = StandardScaler().fit(train_rows)
    train_matrix = scaler.transform(train_rows)
    models, names, schemes = {}, {}, {}
    for count in (2, 3):
        model = _gaussian(train_matrix, count)
        models[count] = model
        names[count] = _profile_names(model)
        centroids = scaler.inverse_transform(model.means_)
        schemes[str(count)] = {
            'bic': float(model.bic(train_matrix)),
            'centroids': {names[count][i]: dict(zip(FEATURES, row.tolist()))
                          for i, row in enumerate(centroids)},
        }

    test_rows, test_items = feature_rows(test_snapshot)
    test_matrix = scaler.transform(test_rows) if len(test_rows) else np.empty((0, len(FEATURES)))
    predictions = {}
    for count in (2, 3):
        if len(test_rows):
            posterior = models[count].predict_proba(test_matrix)
            for item, probabilities in zip(test_items, posterior):
                predictions.setdefault(int(item['block_id']), {})[count] = (
                    names[count][int(np.argmax(probabilities))], float(max(probabilities)))

    coverage_by_block = {int(entry['block_id']): entry for entry in coverage if 'block_id' in entry}
    published = {int(row['block_id']): row['profile'] for row in published_labels}
    covered = {int(item['block_id']) for item in train_items}
    blocks = []
    for item in test_snapshot:
        block_id = int(item['block_id'])
        readings = item.get('readings') or []
        entry = coverage_by_block.get(block_id)
        expected = int(entry['expected']) if entry else 6
        received = int(entry['received']) if entry else len(readings)
        computable = block_features(item) is not None
        missing = received < expected or not computable
        two = predictions.get(block_id, {}).get(2)
        three = predictions.get(block_id, {}).get(3)
        truth = published.get(block_id)
        eligible = truth is not None and not missing and two is not None and three is not None
        blocks.append({
            'block_id': block_id,
            'code': item.get('code'),
            'name': block_names.get(str(block_id)) or block_names.get(block_id),
            'published': truth,
            'predicted_2': two[0] if two else None,
            'predicted_3': three[0] if three else None,
            'confidence_2': two[1] if two else None,
            'confidence_3': three[1] if three else None,
            'received': received,
            'expected': expected,
            'coverage': f'{received}/{expected}',
            'missing': missing,
            'eligible': eligible,
            'hit_2': (two[0] == truth) if eligible else None,
            'hit_3': (three[0] == truth) if eligible else None,
        })

    eligible = [row for row in blocks if row['eligible']]
    total = len(eligible)
    hit_two = sum(1 for row in eligible if row['hit_2'])
    hit_three = sum(1 for row in eligible if row['hit_3'])
    return {
        'seed': SEED, 'covariance_type': 'diag', 'reg_covar': REG_COVAR, 'n_init': 10,
        'features': list(FEATURES), 'schemes': schemes,
        'preferred_k': min((2, 3), key=lambda k: schemes[str(k)]['bic']),
        'blocks': blocks,
        'train': {
            'blocks': len(train_items),
            'excluded': [item.get('code') for item in train_snapshot
                         if int(item['block_id']) not in covered],
        },
        'summary': {
            'eligible': total,
            'missing': [row['code'] for row in blocks if row['missing']],
            'without_label': [row['code'] for row in blocks
                              if not row['missing'] and row['published'] is None],
            'hit_2': hit_two, 'hit_3': hit_three,
            'rate_2': hit_two / total if total else None,
            'rate_3': hit_three / total if total else None,
            'improved': [row['code'] for row in eligible if row['hit_3'] and not row['hit_2']],
            'worsened': [row['code'] for row in eligible if row['hit_2'] and not row['hit_3']],
        },
    }
