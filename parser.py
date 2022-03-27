from ttp import ttp
from pprint import pprint
import json
from deepdiff import DeepDiff

if __name__ == '__main__':

    parser = ttp('vsrx_show_interfaces.text', 'vsrx_show_interfaces.ttp')
    parser.parse()

    f = open('source.json')
    parsed_source = json.load(f)
    result = (parser.result()).pop()[0]
    try:
        assert result == parsed_source
        pprint((parser.result(format='raw')).pop()[0], width=100)
    except AssertionError as e:
        pprint(e)
        pprint(DeepDiff(result, parsed_source), width=100)
