import csv
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


ID = 'ID_опыта'
NUM = 'Номер'
VALID = 'Regime_valid'
NODE_X = ['Uном', 'Pн', 'Qн', 'Pг']
# В исходных данных I_доп отсутствует ровно у несошедшихся режимов.
LINE_X = ['Ns', 'Ne', 'type', 'R', 'X', 'B', 'Kt']
NODE_Y = ['V', 'Delta']
LINE_Y = ['Imax', 'Izagr']
LINE_OUT = ['Imax, A', 'Izarg, %']

ALIASES = {
    ID: ['id', 'experiment_id', 'scenario_id', 'id_experiment'],
    NUM: ['number', 'node_id', 'line_id', 'branch_id'],
    VALID: ['valid', 'режим_допустим'],
    'Uном': ['Uном, кВ', 'Unom', 'Vnom', 'U_nom'],
    'Pн': ['Pn', 'Pload', 'Pн, МВт'],
    'Qн': ['Qn', 'Qload', 'Qн, Мвар'],
    'Pг': ['Pg', 'Pgen', 'Pг, МВт'],
    'V': ['|V|', 'V, кВ'],
    'Delta': ['δ', 'Delta, град', 'Delta, °'],
    'Imax': ['Imax, A', 'Imax, А'],
    'Izagr': ['Izarg', 'Izagr, %', 'Izarg, %', 'Iзагр', 'Iзагр, %'],
}


def key(name):
    name = unicodedata.normalize('NFKC', name).casefold()
    name = name.translate(str.maketrans('авекморстух', 'abekmopctyx'))
    return re.sub(r'[^\w]+|_', '', name)


def csv_format(path):
    with path.open('rb') as f:
        raw = f.read(65536)
    enc = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    try:
        sample = raw.decode(enc, errors='ignore' if len(raw) == 65536 else 'strict')
        if enc == 'utf-8-sig' and raw[:raw.find(b'\n')].decode(enc, errors='replace').find('\ufffd') >= 0:
            raise UnicodeError()
    except UnicodeError:
        enc = 'cp1251'
        sample = raw.decode(enc)
    rows = [row for row in sample.splitlines() if row.strip()]
    if not rows:
        raise ValueError(f'{path.name}: пустой CSV')
    sep = max((';', ',', '\t'), key=lambda s: len(next(csv.reader(rows[:1], delimiter=s))))
    header = next(csv.reader(rows[:1], delimiter=sep))
    decimal = ',' if sep != ',' and any(re.search(r'\d,\d', row) for row in rows[1:]) else '.'
    return enc, sep, decimal, header


def read_table(path, inputs, targets, train):
    path = Path(path)
    enc, sep, decimal, header = csv_format(path)
    required = [ID, NUM, *inputs, *(targets if train else [])]
    ren = {}
    for col in required:
        names = {key(name) for name in [col, *ALIASES.get(col, [])]}
        matches = [name for name in header if key(name) in names]
        if len(matches) != 1:
            raise ValueError(f'{path.name}: ожидался один столбец {col!r}, найдено {matches}')
        ren[matches[0]] = col
    types = {name: 'float32' for name in ren}
    for name, col in ren.items():
        if col == ID:
            types[name] = 'string'
        elif col in ('type', VALID):
            types[name] = 'category'
        elif col == NUM:
            types[name] = 'int32'
    df = pd.read_csv(path, encoding=enc, sep=sep, decimal=decimal, usecols=list(ren), dtype=types)
    df = df.rename(columns=ren)
    if df.empty or df[ID].isna().any():
        raise ValueError(f'{path.name}: отсутствуют данные или ID режима')
    df[ID] = df[ID].astype('category')
    return df.sort_values([ID, NUM], ignore_index=train)


def pack(path, inputs, targets, size, train, kinds=None):
    df = read_table(path, inputs, targets, train)
    if len(df) % size:
        raise ValueError(f'{Path(path).name}: в каждом режиме должно быть {size} строк')
    codes = df[ID].cat.codes.to_numpy().reshape(-1, size)
    ids = df[ID].cat.categories.to_numpy()[codes[:, 0]]
    nums = df[NUM].to_numpy().reshape(-1, size)
    if (np.any(codes != codes[:, :1]) or len(np.unique(ids)) != len(ids)
            or np.any(nums != nums[0]) or np.any(np.diff(nums[0]) <= 0)):
        raise ValueError(f'{Path(path).name}: проверьте состав и номера элементов в каждом режиме')

    x = np.empty((len(ids), size, len(inputs)), dtype=np.float32)
    for i, col in enumerate(inputs):
        if col == 'type':
            if kinds is None:
                kinds = list(df[col].cat.categories)
            cat = pd.Categorical(df[col], categories=kinds)
            if np.any((cat.codes < 0) & df[col].notna().to_numpy()):
                raise ValueError(f'{Path(path).name}: найден неизвестный тип ветви')
            x[:, :, i] = np.where(cat.codes < 0, np.nan, cat.codes).reshape(-1, size)
        else:
            x[:, :, i] = df[col].to_numpy().reshape(-1, size)

    y = [df[col].to_numpy().reshape(-1, size) for col in targets if train and col != VALID]
    valid = None
    if train and VALID in targets:
        labels = {str(v).strip().casefold(): i for i, vals in enumerate(
            [('0', '0.0', 'false', 'нет'), ('1', '1.0', 'true', 'да')]) for v in vals}
        cats = df[VALID].cat.categories
        mapping = np.array([labels.get(str(v).strip().casefold(), -1) for v in cats] + [-1])
        flags = mapping[df[VALID].cat.codes.to_numpy()].reshape(-1, size)
        if np.any(flags < 0) or np.any(flags != flags[:, :1]):
            raise ValueError(f'{Path(path).name}: проверьте флаг {VALID} у всех узлов режима')
        valid = flags[:, 0].copy()
    order = None
    if not train:
        order = np.empty(len(df), dtype=np.intp)
        order[df.index.to_numpy()] = np.arange(len(df), dtype=np.intp)
    return ids, nums[0].copy(), x.reshape(len(ids), -1), y, valid, kinds, order


def load_data(nodes, lines, train, schema=None):
    ids, node_nums, nx, ny, valid, _, node_order = pack(nodes, NODE_X, [*NODE_Y, VALID], 35, train)
    line_ids, line_nums, lx, ly, _, kinds, line_order = pack(lines, LINE_X, LINE_Y, 80, train,
                                                            None if schema is None else schema['types'])
    if not np.array_equal(ids, line_ids):
        raise ValueError('Списки ID режимов в файлах узлов и ветвей различаются')
    actual = {'nodes': node_nums.tolist(), 'lines': line_nums.tolist(), 'types': kinds}
    if schema is not None and actual != schema:
        raise ValueError('Номера узлов или ветвей отличаются от схемы обучения')
    y = np.concatenate([*ny, *ly], axis=1) if train else None
    return ids, np.concatenate([nx, lx], axis=1), y, valid, actual, (node_order, line_order)


def write_predictions(out, ids, schema, pred, flags, prob, orders, contest=False):
    out.mkdir(parents=True, exist_ok=True)
    for name, cols, vals, order in [
        ('nodes', NODE_Y, (pred[:, :35], pred[:, 35:70]), orders[0]),
        ('lines', LINE_OUT, (pred[:, 70:150], pred[:, 150:]), orders[1]),
    ]:
        path = out / f'pred_{name}.csv'
        nums = np.asarray(schema[name])
        for start in range(0, len(order), 100_000):
            exp, elem = np.divmod(order[start:start + 100_000], len(nums))
            frame = pd.DataFrame({ID: ids[exp], NUM: nums[elem]})
            for col, val in zip(cols, vals):
                frame[col] = val[exp, elem]
            if name == 'nodes':
                frame[VALID] = flags[exp]
            frame.to_csv(path, mode='a' if start else 'w', header=start == 0, index=False, encoding='utf-8')
    if not contest:
        pd.DataFrame({ID: ids, VALID: flags, 'probability_valid': prob}).to_csv(
            out / 'pred_regimes.csv', index=False, encoding='utf-8')
