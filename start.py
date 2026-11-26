import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / '.venv'


def main():
    if sys.version_info < (3, 10):
        print('Для запуска нужен Python 3.10 или новее.', file=sys.stderr)
        return 1

    args = sys.argv[1:]
    exe = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    try:
        if not exe.is_file():
            subprocess.run([sys.executable, '-m', 'venv', str(ENV)], check=True)

        probe = subprocess.run([exe, '-c', 'import numpy, pandas, sklearn, joblib, threadpoolctl; '
                                'assert sklearn.__version__ == "1.7.2" and int(numpy.__version__.split(".")[0]) == 2'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode:
            subprocess.run([exe, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt'], check=True)

        if args == ['check']:
            return subprocess.run([exe, ROOT / 'smoke_test.py']).returncode
        return subprocess.run([exe, ROOT / 'main.py', *(args or ['train'])]).returncode
    except subprocess.CalledProcessError as err:
        print('Подготовка окружения завершилась ошибкой. Подробности выше.', file=sys.stderr)
        return err.returncode
    except OSError as err:
        print(f'Ошибка запуска: {err}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
