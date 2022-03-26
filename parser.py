from ttp import ttp
from pprint import pprint
import json

if __name__ == '__main__':

    parser = ttp('vsrx_show_interfaces.text', 'vsrx_show_interfaces.ttp')
    parser.parse()

    pprint((parser.result(format='raw')).pop()[0], width=100)
