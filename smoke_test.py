import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from data import ID, LINE_Y, NODE_Y, NUM, VALID


def sample(folder):
    rng = np.random.default_rng(42)
    nodes, lines = [], []
    for i in range(600):
        exp = f'{i:05d}'
        load = rng.uniform(0, 2)
        power = rng.uniform(0, 0.1, 35) + load
        valid = load < 1
        for j, p in enumerate(power):
            u = (110, 220, 500)[j % 3]
            nodes.append([exp, j - 1, u, p, p / 3, 0, u - 3 * p if valid else None,
                          -2 * p if valid else None, 'true' if valid else 'false'])
        for j in range(80):
            ns, ne = j % 35, (j + 1) % 35
            current = 40 * (power[ns] + power[ne])
            lines.append([exp, j, ns - 1, ne - 1, 'ЛЭП', 0.1, 0.4, 0.001, 1, 200,
                          current if valid else None, current / 2 if valid else None])

    frames = [
        ('nodes', pd.DataFrame(nodes, columns=[ID, NUM, 'Uном', 'Pн', 'Qн', 'Pг', *NODE_Y, VALID]),
         [*NODE_Y, VALID]),
        ('lines', pd.DataFrame(lines, columns=[ID, NUM, 'Ns', 'Ne', 'type', 'R', 'X', 'B', 'Kt',
                                              'Iдоп, А', 'Imax, A', 'Izarg, %']),
         ['Imax, A', 'Izarg, %']),
    ]
    for name, frame, targets in frames:
        frame.sample(frac=1, random_state=42).to_csv(folder / f'train_{name}.csv', index=False,
                                                    encoding='cp1251', sep=';', decimal=',')
        frame[frame[ID].isin(['00000', '00001', '00002'])].drop(columns=targets).to_csv(
            folder / f'test_{name}.csv', index=False, encoding='utf-8-sig')


def run(mode, split, folder, out):
    args = [sys.executable, str(Path(__file__).with_name('start.py')), mode,
            '--nodes', str(folder / f'{split}_nodes.csv'), '--lines', str(folder / f'{split}_lines.csv'),
            '--model', str(out / 'model.joblib'), '--out', str(out)]
    subprocess.run(args, check=True)


def main():
    out = Path(__file__).resolve().parent / 'results' / 'check'
    with TemporaryDirectory() as tmp:
        folder = Path(tmp)
        sample(folder)
        run('train', 'train', folder, out)
        scores = json.loads((out / 'metrics.json').read_text(encoding='utf-8'))
        assert scores['F1-macro'] > 0.8, scores
        assert sum(scores['counts'][k] for k in ('train', 'validation', 'holdout')) == 600
        for name in [*NODE_Y, *LINE_Y]:
            assert scores['regression'][name]['MAE'] < scores['mean_baseline'][name]['MAE'], scores
        run('predict', 'test', folder, out)
        for name, size, targets in [('nodes', 35, NODE_Y), ('lines', 80, LINE_Y),
                                    ('regimes', 1, ['probability_valid'])]:
            frame = pd.read_csv(out / f'pred_{name}.csv', dtype={ID: str})
            assert frame.groupby(ID).size().to_dict() == {'00000': size, '00001': size, '00002': size}
            assert np.isfinite(frame[targets].to_numpy()).all()
        print('Проверка обучения и прогноза пройдена.')


if __name__ == '__main__':
    main()
