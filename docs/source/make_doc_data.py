#!/usr/bin/env python3
import json
import os
import sys

import django

from thenewboston_node.business_logic.blockchain import file_blockchain
from thenewboston_node.business_logic.tests import factories

BASE_PATH = os.path.abspath(os.path.dirname(__file__))

import_models = [
    factories.BlockFactory(),
]


def get_field_data(model):
    for name in model.__dataclass_fields__.items():
        field = getattr(model, name)
        yield {
            'name': name,
            'docstring': field
            # 'type':
        }


def get_model_data():
    for model in import_models:
        breakpoint()
        yield {
            'class_name': model.__class__.__name__,
            'docstring': model.__doc__.strip(),
            'fields': list(get_field_data(model)),
        }


def get_file_blockchain_data():
    return {
        'account_root_file_subdir': file_blockchain.DEFAULT_ACCOUNT_ROOT_FILE_SUBDIR,
        'blocks_subdir': file_blockchain.DEFAULT_BLOCKS_SUBDIR,
        'block_chunk_size': file_blockchain.DEFAULT_BLOCK_CHUNK_SIZE,
        'order_of_block': file_blockchain.ORDER_OF_BLOCK,
        'block_chunk_template': file_blockchain.BLOCK_CHUNK_FILENAME_TEMPLATE,
        'get_block_chunk_filename': file_blockchain.get_block_chunk_filename,
    }


def get_data():
    data = {
        # 'models': list(get_model_data()),
        'file_blockchain': get_file_blockchain_data(),
    }
    return data


def dump_data(data):
    print(json.dumps(data))


def render(data):
    import jinja2
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(BASE_PATH))
    template = env.get_template('index.rst')
    return template.render(**data)


def setup():
    sys.path.insert(0, os.path.abspath('../..'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston_node.project.settings')
    django.setup()


def main():
    setup()
    data = get_data()
    rendered = render(data)
    print(rendered)
    # dump_data(data)


if __name__ == '__main__':
    main()
