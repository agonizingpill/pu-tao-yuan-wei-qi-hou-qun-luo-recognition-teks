import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from .domain import Profile

SEED = 1071
REG_COVAR = 0.025
FEATURES = ('day_temp', 'night_temp', 'day_rh', 'night_rh')


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
    # Order by warm/dry tendency rather than arbitrary mixture component indices.
    order = np.argsort(model.means_ @ np.array([1, 1, -1, -1]), kind='stable')
    profile_order = {1: [Profile.BALANCED], 2: [Profile.COOL, Profile.WARM],
                     3: [Profile.COOL, Profile.BALANCED, Profile.WARM]}[model.n_components]
    names = dict(zip(order, profile_order))
    posterior = model.predict_proba(matrix)
    return {
        'chosen_k': model.n_components, 'bic': scores, 'seed': SEED,
        'covariance_type': 'diag', 'reg_covar': REG_COVAR, 'n_init': 10, 'features': FEATURES,
        'centroids': {names[i]: dict(zip(FEATURES, row.tolist())) for i, row in enumerate(centroids)},
        'assignments': [dict(block_id=item['block_id'], code=item['code'],
                             profile=names[int(np.argmax(p))], confidence=float(max(p)))
                        for item, p in zip(snapshot, posterior)],
    }
