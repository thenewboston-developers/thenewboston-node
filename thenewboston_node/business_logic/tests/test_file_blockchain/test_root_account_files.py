import os.path

import pytest

from thenewboston_node.business_logic.blockchain.file_blockchain import FileBlockchain
from thenewboston_node.business_logic.models.block import Block
from thenewboston_node.core.utils.cryptography import KeyPair


@pytest.mark.usefixtures('forced_mock_network', 'get_primary_validator_mock', 'get_preferred_node_mock')
def test_root_account_file_is_created_every_x_block(
    blockchain_path,
    initial_account_root_file,
    treasury_account_key_pair: KeyPair,
    user_account_key_pair: KeyPair,
):
    assert not os.path.isfile(str(blockchain_path / 'account-root-files/0/0/0/0/0/0/0/0/000000000.-arf.msgpack'))
    blockchain = FileBlockchain(
        base_directory=str(blockchain_path),
        arf_creation_period_in_blocks=5,
        account_root_files_subdir='account-root-files',
        account_root_files_storage_kwargs={'compressors': ()}
    )
    blockchain.add_account_root_file(initial_account_root_file)
    assert os.path.isfile(str(blockchain_path / 'account-root-files/0/0/0/0/0/0/0/0/000000000.-arf.msgpack'))
    blockchain.validate()

    user_account = user_account_key_pair.public

    for _ in range(4):
        block = Block.from_main_transaction(
            blockchain, user_account, 30, signing_key=treasury_account_key_pair.private
        )
        assert not os.path.isfile(
            str(
                blockchain_path /
                f'account-root-files/0/0/0/0/0/0/0/0/000000000{block.message.block_number}-arf.msgpack'
            )
        )
        blockchain.add_block(block)

    block = Block.from_main_transaction(blockchain, user_account, 30, signing_key=treasury_account_key_pair.private)
    blockchain.add_block(block)
    assert os.path.isfile(
        str(blockchain_path / f'account-root-files/0/0/0/0/0/0/0/0/000000000{block.message.block_number}-arf.msgpack')
    )

    for _ in range(4):
        block = Block.from_main_transaction(
            blockchain, user_account, 30, signing_key=treasury_account_key_pair.private
        )
        assert not os.path.isfile(
            str(
                blockchain_path /
                f'account-root-files/0/0/0/0/0/0/0/0/000000000{block.message.block_number}-arf.msgpack'
            )
        )
        blockchain.add_block(block)

    block = Block.from_main_transaction(blockchain, user_account, 30, signing_key=treasury_account_key_pair.private)
    blockchain.add_block(block)
    assert os.path.isfile(
        str(blockchain_path / f'account-root-files/0/0/0/0/0/0/0/0/000000000{block.message.block_number}-arf.msgpack')
    )
