import sys

from main import main


if __name__ == '__main__':
    sys.exit(main(['predict', *sys.argv[1:]], contest=True))
