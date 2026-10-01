"""ARDA command entry point."""
import argparse
import json


def main():
    parser = argparse.ArgumentParser(description='ARDA — One plugin to rule them all.')
    parser.add_argument('command', choices=['status'])
    parser.parse_args()
    print(json.dumps({'plugin': 'arda', 'version': '0.1.0', 'protocol': 'arda/1'}))


if __name__ == '__main__':
    main()
