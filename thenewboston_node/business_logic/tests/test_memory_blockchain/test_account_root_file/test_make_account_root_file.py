import pytest

from thenewboston_node.business_logic.blockchain.base import BlockchainBase
from thenewboston_node.business_logic.models.block import Block


@pytest.mark.usefixtures('forced_mock_network', 'get_primary_validator_mock', 'get_preferred_node_mock')
def test_can_make_root_account_file_on_last_block(
    forced_memory_blockchain: BlockchainBase, initial_account_root_file, treasury_account_key_pair,
    user_account_key_pair, primary_validator, preferred_node
):
    blockchain = forced_memory_blockchain
    user_account = user_account_key_pair.public
    treasury_account = treasury_account_key_pair.public
    treasury_initial_balance = blockchain.get_balance_value(treasury_account)
    assert treasury_initial_balance is not None

    assert blockchain.get_closest_account_root_file() == initial_account_root_file
    assert blockchain.get_closest_account_root_file(-1) == initial_account_root_file
    assert initial_account_root_file.accounts[treasury_account].lock == treasury_account
    assert blockchain.get_account_root_file_count() == 1

    blockchain.make_account_root_file()
    assert blockchain.get_account_root_file_count() == 1

    block0 = Block.from_main_transaction(blockchain, user_account, 30, signing_key=treasury_account_key_pair.private)
    blockchain.add_block(block0)

    blockchain.make_account_root_file()
    assert blockchain.get_account_root_file_count() == 2
    blockchain.make_account_root_file()
    assert blockchain.get_account_root_file_count() == 2

    account_root_file = blockchain.get_last_account_root_file()
    assert account_root_file is not None
    assert account_root_file.last_block_number == 0
    assert account_root_file.last_block_identifier == block0.message.block_identifier
    assert account_root_file.next_block_identifier == block0.message_hash

    assert len(account_root_file.accounts) == 4
    assert account_root_file.accounts.keys() == {
        user_account, treasury_account, primary_validator.identifier, preferred_node.identifier
    }
    assert account_root_file.accounts[user_account].value == 30
    assert account_root_file.accounts[user_account].lock == user_account

    assert account_root_file.accounts[treasury_account].value == treasury_initial_balance - 30 - 4 - 1
    assert account_root_file.accounts[treasury_account].lock != treasury_account

    assert account_root_file.accounts[primary_validator.identifier].value == 4
    assert account_root_file.accounts[primary_validator.identifier].lock == primary_validator.identifier

    assert account_root_file.accounts[preferred_node.identifier].value == 1
    assert account_root_file.accounts[preferred_node.identifier].lock == preferred_node.identifier

    block1 = Block.from_main_transaction(blockchain, treasury_account, 20, signing_key=user_account_key_pair.private)
    blockchain.add_block(block1)

    block2 = Block.from_main_transaction(
        blockchain, primary_validator.identifier, 2, signing_key=treasury_account_key_pair.private
    )
    blockchain.add_block(block2)

    blockchain.make_account_root_file()
    account_root_file = blockchain.get_last_account_root_file()

    assert account_root_file is not None
    assert account_root_file.last_block_number == 2
    assert account_root_file.last_block_identifier == block2.message.block_identifier
    assert account_root_file.next_block_identifier == block2.message_hash

    assert len(account_root_file.accounts) == 4
    assert account_root_file.accounts.keys() == {
        user_account, treasury_account, primary_validator.identifier, preferred_node.identifier
    }
    assert account_root_file.accounts[user_account].value == 5
    assert account_root_file.accounts[user_account].lock != user_account

    assert account_root_file.accounts[treasury_account].value == treasury_initial_balance - 30 - 4 - 1 + 20 - 2 - 4 - 1
    assert account_root_file.accounts[treasury_account].lock != treasury_account

    assert account_root_file.accounts[primary_validator.identifier].value == 4 + 4 + 4 + 2
    assert account_root_file.accounts[primary_validator.identifier].lock == primary_validator.identifier

    assert account_root_file.accounts[preferred_node.identifier].value == 1 + 1 + 1
    assert account_root_file.accounts[preferred_node.identifier].lock == preferred_node.identifier
