import argparse
import json
import math
from email import policy
from email.parser import BytesParser
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / 'frontend'
MAX_UPLOAD = 8 * 1024 * 1024
PREDICTION_LOCK = Lock()
ASSETS = {
    '/': ('index.html', 'text/html'),
    '/index.html': ('index.html', 'text/html'),
    '/style.css': ('style.css', 'text/css'),
    '/demo.js': ('demo.js', 'text/javascript'),
    '/app.js': ('app.js', 'text/javascript'),
}


def parse_upload(content_type, content):
    message = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + content_type.encode('ascii') + b'\r\n\r\n' + content
    )
    if message.get_content_type() != 'multipart/form-data' or not message.is_multipart():
        raise ValueError('Ожидаются два файла CSV.')
    files = {}
    for part in message.iter_parts():
        name = part.get_param('name', header='content-disposition')
        if name not in ('nodes', 'lines') or name in files or not part.get_filename():
            raise ValueError('Ожидаются один файл узлов и один файл ветвей.')
        files[name] = part.get_payload(decode=True)
    if set(files) != {'nodes', 'lines'} or not all(files.values()):
        raise ValueError('Выберите два непустых CSV-файла.')
    return files


@lru_cache(maxsize=1)
def load_model():
    import joblib

    return joblib.load(ROOT / 'results' / 'model.joblib')


def number(value):
    value = float(value)
    return value if math.isfinite(value) else None


def scenarios_from_upload(files):
    from threadpoolctl import threadpool_limits

    from data import LINE_X, NODE_X, load_data
    from model import TARGETS, predict

    with TemporaryDirectory() as directory:
        nodes_path, lines_path = (Path(directory) / f'{name}.csv' for name in ('nodes', 'lines'))
        nodes_path.write_bytes(files['nodes'])
        lines_path.write_bytes(files['lines'])
        with PREDICTION_LOCK, threadpool_limits(limits=4):
            weights = load_model()
            ids, inputs, _, _, schema, orders = load_data(
                nodes_path, lines_path, train=False, schema=weights['schema']
            )
            predictions, flags, probabilities = predict(weights, inputs)

    node_count = len(schema['nodes'])
    line_count = len(schema['lines'])
    node_columns = node_count * len(NODE_X)
    node_inputs = inputs[:, :node_columns].reshape(len(ids), node_count, len(NODE_X))
    line_inputs = inputs[:, node_columns:].reshape(len(ids), line_count, len(LINE_X))
    node_positions, line_positions = (order.argsort() for order in orders)
    voltages, angles, currents, loads = (predictions[:, TARGETS[key]] for key in ('V', 'Delta', 'Imax', 'Izagr'))

    scenarios = []
    for index, regime_id in enumerate(ids):
        nodes = [
            {'number': node_id, 'nominal': number(node_inputs[index, i, 0]),
             'voltage': number(voltages[index, i]), 'angle': number(angles[index, i]),
             'sourceOrder': int(node_positions[index * node_count + i])}
            for i, node_id in enumerate(schema['nodes'])
        ]
        lines = [
            {'number': line_id, 'from': number(line_inputs[index, i, 0]),
             'to': number(line_inputs[index, i, 1]), 'current': number(currents[index, i]),
             'load': number(loads[index, i]), 'sourceOrder': int(line_positions[index * line_count + i])}
            for i, line_id in enumerate(schema['lines'])
        ]
        scenarios.append({'id': str(regime_id), 'valid': bool(flags[index]),
                          'probability': number(probabilities[index]), 'nodes': nodes, 'lines': lines})
    return scenarios


class FrontendHandler(BaseHTTPRequestHandler):
    def send_data(self, status, content_type, body):
        self.send_response(status)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        self.send_data(status, 'application/json', json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        asset = ASSETS.get(self.path)
        if asset is None:
            self.send_error(404)
            return
        filename, content_type = asset
        self.send_data(200, content_type, (FRONTEND / filename).read_bytes())

    def do_POST(self):
        if self.path != '/api/predict':
            self.send_error(404)
            return
        origin = self.headers.get('Origin')
        if origin is not None and origin != f"http://{self.headers.get('Host')}":
            self.send_json(403, {'error': 'Откройте интерфейс по локальному адресу сервера.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size > MAX_UPLOAD:
                self.send_json(413, {'error': 'Общий размер запроса превышает 8 МиБ.'})
                return
            if size <= 0:
                raise ValueError('Выберите два CSV-файла.')
            self.connection.settimeout(15)
            content = self.rfile.read(size)
            if len(content) != size:
                raise ValueError('Файлы получены не полностью.')
            files = parse_upload(self.headers.get('Content-Type', ''), content)
            scenarios = scenarios_from_upload(files)
        except ValueError as error:
            self.send_json(400, {'error': str(error)})
        except ImportError:
            self.send_json(503, {'error': 'Для прогноза установите зависимости из requirements.txt.'})
        except OSError as error:
            self.log_error('%s', error)
            self.send_json(503, {'error': 'Сервис не смог прочитать загруженные файлы или веса модели.'})
        else:
            self.send_json(200, {'scenarios': scenarios})


def main():
    parser = argparse.ArgumentParser(description='Веб-интерфейс прогноза электросети')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), FrontendHandler) as server:
        print(f'Контур: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
