import argparse
import json
import sys
from pathlib import Path

import joblib
from threadpoolctl import threadpool_limits

from data import load_data, write_predictions
from model import predict, train_model

ROOT = Path(__file__).resolve().parent


def train_path(name):
    path = ROOT / f'train_{name}_34.csv'
    return path if path.is_file() else ROOT / 'dataset' / f'train_{name}_34_100000.csv'


def main(argv=None, contest=False):
    parser = argparse.ArgumentParser(description='Прогноз установившегося режима электросети')
    commands = parser.add_subparsers(dest='mode', required=True)
    train = commands.add_parser('train', help='обучить модели и рассчитать метрики')
    train.add_argument('--nodes', type=Path, default=train_path('nodes'))
    train.add_argument('--lines', type=Path, default=train_path('lines'))
    train.add_argument('--epochs', type=int, default=180)
    test = commands.add_parser('predict', help='сделать прогноз из двух CSV')
    test.add_argument('--nodes', type=Path, required=True)
    test.add_argument('--lines', type=Path, required=True)
    for cmd in (train, test):
        cmd.add_argument('--model', '--weights', type=Path, default=ROOT / 'results' / 'model.joblib')
        cmd.add_argument('--out', '--out-dir', type=Path, default=ROOT / 'results')
    args = parser.parse_args(argv)

    try:
        for path in (args.nodes, args.lines):
            if not path.is_file():
                raise FileNotFoundError(f'не найден {path}')
        with threadpool_limits(limits=4):
            if args.mode == 'train':
                if args.epochs < 1:
                    raise ValueError('--epochs должно быть положительным')
                print('Чтение исходных данных', flush=True)
                _, x, y, valid, schema, _ = load_data(args.nodes, args.lines, train=True)
                model, scores = train_model(x, y, valid, schema, args.epochs)
                args.out.mkdir(parents=True, exist_ok=True)
                args.model.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(model, args.model, compress=3)
                (args.out / 'metrics.json').write_text(json.dumps(scores, indent=2), encoding='utf-8')
            else:
                model = joblib.load(args.model)
                ids, x, _, _, schema, orders = load_data(args.nodes, args.lines, train=False, schema=model['schema'])
                pred, flags, prob = predict(model, x)
                write_predictions(args.out, ids, schema, pred, flags, prob, orders, contest)
    except (OSError, ValueError) as err:
        print(f'Ошибка: {err}', file=sys.stderr)
        return 1
    print(f'Результаты сохранены в {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
