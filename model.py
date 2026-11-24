import numpy as np
from sklearn.metrics import f1_score, mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.preprocessing import StandardScaler

SEED = 42
TARGETS = {'V': slice(0, 35), 'Delta': slice(35, 70),
           'Imax': slice(70, 150), 'Izagr': slice(150, 230)}


def transform(x, model):
    x = x[:, model['cols']]
    x[~np.isfinite(x)] = np.nan
    x = model['scaler'].transform(x, copy=False)
    return np.nan_to_num(x, copy=False)


def predict(model, x):
    x = transform(x, model)
    prob = model['classifier'].predict_proba(x)[:, 1]
    pred = model['regressor'].predict(x)
    pred = model['target_scaler'].inverse_transform(pred)
    return pred, (prob >= model['threshold']).astype(int), prob


def report(y, pred):
    scores = {}
    for name, sl in TARGETS.items():
        a, b = y[:, sl].ravel(), pred[:, sl].ravel()
        scores[name] = {'MAE': mean_absolute_error(a, b),
                        'RMSE': root_mean_squared_error(a, b), 'R2': r2_score(a, b)}
    return scores


def train_model(x, y, valid, schema, epochs):
    idx = np.arange(len(valid))
    if min(np.bincount(valid, minlength=2)) < 12:
        raise ValueError('Для разбиения нужно минимум 12 режимов каждого класса')
    tr, test = train_test_split(idx, test_size=0.2, stratify=valid, random_state=SEED)
    tr, val = train_test_split(tr, test_size=0.25, stratify=valid[tr], random_state=SEED)
    tr_ok = tr[valid[tr] == 1]
    test_ok = valid[test] == 1
    if not np.isfinite(y[valid == 1]).all():
        raise ValueError('В сходящихся режимах отсутствуют эталонные напряжения или токи')

    x_tr = x[tr]
    x_tr[~np.isfinite(x_tr)] = np.nan
    # Постоянные параметры сети убираем по обучающей выборке.
    observed = np.any(np.isfinite(x_tr), axis=0)
    if not np.any(observed):
        raise ValueError('Во входных данных отсутствуют числовые значения')
    scaler = StandardScaler().fit(x_tr[:, observed])
    changed = scaler.var_ > 0
    if not np.any(changed):
        raise ValueError('Во входных данных все признаки постоянны')
    cols = np.flatnonzero(observed)[changed]
    model = {'schema': schema, 'cols': cols, 'scaler': StandardScaler().fit(x_tr[:, cols]),
             'target_scaler': StandardScaler().fit(y[tr_ok])}
    del x_tr
    x_tr = transform(x[tr], model)
    opts = {'hidden_layer_sizes': (128, 128), 'max_iter': epochs,
            'random_state': SEED, 'early_stopping': len(tr_ok) >= 100,
            'n_iter_no_change': 15, 'learning_rate_init': 0.001}
    print('Обучение классификации', flush=True)
    clf = MLPClassifier(**opts).fit(x_tr, valid[tr])
    print('Обучение прогноза напряжений и токов', flush=True)
    y_tr = model['target_scaler'].transform(y[tr_ok])
    reg = MLPRegressor(**opts).fit(x_tr[valid[tr] == 1], y_tr)
    del x_tr

    prob = clf.predict_proba(transform(x[val], model))[:, 1]
    grid = np.arange(0.05, 1.00, 0.025).round(3)
    cut = max(grid, key=lambda t: (f1_score(valid[val], prob >= t, average='macro'), -abs(t - 0.5)))
    model.update(classifier=clf, regressor=reg, threshold=float(cut))
    pred, flags, _ = predict(model, x[test])
    y_test = y[test[test_ok]]
    baseline = np.broadcast_to(model['target_scaler'].mean_, y_test.shape)
    scores = {'counts': {'train': len(tr), 'validation': len(val), 'holdout': len(test),
                         'holdout_valid': int(test_ok.sum())},
              'threshold': float(cut), 'F1-macro': f1_score(valid[test], flags, average='macro'),
              'regression': report(y_test, pred[test_ok]), 'mean_baseline': report(y_test, baseline)}
    return model, scores
