import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from dataclasses_json import config, dataclass_json
from marshmallow import fields

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.core.logging import validates
from thenewboston_node.core.utils.cryptography import normalize_dict
from thenewboston_node.core.utils.dataclass import fake_super_methods

from .account_balance import BlockAccountBalance
from .base import MessageMixin
from .transfer_request import TransferRequest

logger = logging.getLogger(__name__)


def make_balance_lock(transfer_request):
    assert transfer_request.message
    return transfer_request.message.get_hash()


def calculate_updated_balances(get_balance_value: Callable[[str], Optional[int]],
                               transfer_request: TransferRequest) -> dict[str, BlockAccountBalance]:
    updated_balances: dict[str, BlockAccountBalance] = {}
    sent_amount = 0
    for transaction in transfer_request.message.txs:
        recipient = transaction.recipient
        amount = transaction.amount

        balance = updated_balances.get(recipient)
        if balance is None:
            balance = BlockAccountBalance(value=get_balance_value(recipient) or 0)
            updated_balances[recipient] = balance

        balance.value += amount
        sent_amount += amount

    sender = transfer_request.sender
    sender_balance = get_balance_value(sender)
    assert sender_balance is not None
    assert sender_balance >= sent_amount

    updated_balances[sender] = BlockAccountBalance(
        value=sender_balance - sent_amount, lock=make_balance_lock(transfer_request)
    )

    return updated_balances


@fake_super_methods
@dataclass_json
@dataclass
class BlockMessage(MessageMixin):
    """
    Contains requested changes in the network like transfer of coins, etc...
    """

    transfer_request: TransferRequest
    """Requested changes"""

    # We need timestamp, block_number and block_identifier to be signed and hashed therefore
    # they are include in BlockMessage, not in Block
    timestamp: datetime = field(  # naive datetime in UTC
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    """Block timestamp in UTC"""

    block_number: int
    """Sequential block number"""

    block_identifier: str
    """Unique block identifier"""

    updated_balances: dict[str, BlockAccountBalance]
    """New account balance values like {"`account_number`": `BlockAccountBalance`, ...}"""

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()
        # TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
        dict_['transfer_request'] = self.transfer_request.to_dict()
        dict_['updated_balances'] = {key: value.to_dict() for key, value in self.updated_balances.items()}
        return dict_

    @classmethod
    def from_transfer_request(cls, blockchain, transfer_request: TransferRequest):
        if not transfer_request.sender:
            raise ValueError('Sender must be set')

        # TODO(dmu) HIGH: Move source of time to Blockchain?
        timestamp = datetime.utcnow()

        block_number = blockchain.get_next_block_number()
        block_identifier = blockchain.get_next_block_identifier()

        return BlockMessage(
            transfer_request=copy.deepcopy(transfer_request),
            timestamp=timestamp,
            block_number=block_number,
            block_identifier=block_identifier,
            updated_balances=calculate_updated_balances(blockchain.get_balance_value, transfer_request),
        )

    def get_normalized(self) -> bytes:
        return normalize_dict(self.to_dict())  # type: ignore

    def get_balance(self, account: str) -> Optional[BlockAccountBalance]:
        return (self.updated_balances or {}).get(account)

    def get_sent_amount(self):
        assert self.transfer_request
        return self.transfer_request.get_sent_amount()

    def get_recipient_amount(self, recipient):
        assert self.transfer_request
        return self.transfer_request.get_recipient_amount(recipient)

    @validates('block message')
    def validate(self, blockchain):
        self.validate_transfer_request(blockchain)
        self.validate_block_number()

        assert self.block_number is not None
        self.validate_timestamp(blockchain)
        self.validate_block_identifier(blockchain)

        self.validate_updated_balances(blockchain)

    @validates('transfer request on block message level')
    def validate_transfer_request(self, blockchain):
        transfer_request = self.transfer_request
        if transfer_request is None:
            raise ValidationError('Block message transfer request must present')

        transfer_request.validate(blockchain, self.block_number)

    @validates('block message timestamp')
    def validate_timestamp(self, blockchain):
        timestamp = self.timestamp
        if timestamp is None:
            raise ValidationError('Block message timestamp must be set')

        if not isinstance(timestamp, datetime):
            raise ValidationError('Block message timestamp must be datetime type')

        if timestamp.tzinfo is not None:
            raise ValidationError('Block message timestamp must be naive datetime (UTC timezone implied)')

        block_number = self.block_number
        assert block_number is not None

        if block_number > 0:
            prev_block_number = block_number - 1
            prev_block = blockchain.get_block_by_number(prev_block_number)
            if prev_block is None:
                logger.debug('Partial blockchain detected')
                account_root_file = blockchain.get_closest_account_root_file(block_number)
                if account_root_file is None:
                    raise ValidationError('Unexpected could not find base account root file')

                if account_root_file.is_initial():
                    raise ValidationError('Unexpected initial account root file found')

                if account_root_file.last_block_number != prev_block_number:
                    raise ValidationError('Base account root file block number mismatch')

                assert account_root_file.last_block_timestamp
                min_timestamp = account_root_file.last_block_timestamp
            else:
                min_timestamp = prev_block.message.timestamp

            if timestamp <= min_timestamp:
                raise ValidationError('Block message timestamp must be greater than from previous block')

    @validates('block number')
    def validate_block_number(self):
        block_number = self.block_number
        if block_number is None:
            raise ValidationError('Block number must be set')

        if not isinstance(block_number, int):
            raise ValidationError('Block number must be integer')

        if block_number < 0:
            raise ValidationError('Block number must be greater or equal to 0')

    @validates('block identifier')
    def validate_block_identifier(self, blockchain):
        block_identifier = self.block_identifier
        if block_identifier is None:
            raise ValidationError('Block identifier must be set')

        if not isinstance(block_identifier, str):
            raise ValidationError('Block identifier must be a string')

        block_number = self.block_number
        assert block_number is not None

        if block_identifier != blockchain.get_expected_block_identifier(block_number):
            raise ValidationError('Invalid block identifier')

    @validates('block message updated balances')
    def validate_updated_balances(self, blockchain):

        updated_balances = self.updated_balances

        with validates('block message updated balances content'):
            if updated_balances is None:
                raise ValidationError('Block message must contain updated balances')

            if len(updated_balances) < 2:
                raise ValidationError('block message updated balances must contain at least 2 balances')

        sender = self.transfer_request.sender
        with validates('block message updated balances sender account balance'):
            sender_account_balance = updated_balances.get(sender)
            if sender_account_balance is None:
                raise ValidationError('block message updated balances must contain sender account balance')

        with validates('all account balances', is_plural_target=True):
            for account, account_balance in updated_balances.items():
                account_balance.validate()
                with validates(f'account {account} updated balance on block message level'):
                    if not isinstance(account, str):
                        raise ValidationError('Block message updated balance account must be a string')

                    is_sender = account == sender
                    self.validate_updated_balance_lock(
                        account=account, account_balance=account_balance, is_sender=is_sender
                    )
                    self.validate_updated_balance_value(
                        account=account, account_balance=account_balance, blockchain=blockchain, is_sender=is_sender
                    )

    @validates('account {account} balance lock')
    def validate_updated_balance_lock(self, *, account, account_balance, is_sender=False):
        if is_sender:
            if not account_balance.lock:
                raise ValidationError('Block message updated balances must contain sender account balance lock')

            expected_balance_lock = make_balance_lock(self.transfer_request)
            if account_balance.lock != expected_balance_lock:
                raise ValidationError(
                    f'Expected {expected_balance_lock} balance lock, but got {account_balance.lock} '
                    f'for account {account}'
                )
        else:
            if account_balance.lock:
                raise ValidationError(
                    'block message updated balances must not contain balance lock for '
                    'recipient accounts'
                )

    @validates('account {account} balance value')
    def validate_updated_balance_value(self, *, account, account_balance, blockchain, is_sender=False):
        initial_balance = blockchain.get_balance_value(account, self.block_number)
        if is_sender:
            if initial_balance is None:
                raise ValidationError(
                    f'Sender account {account} does not have balance '
                    f'on block {self.block_number}'
                )

            expected_balance_value = initial_balance - self.get_sent_amount()
        else:
            initial_balance = initial_balance or 0
            expected_balance_value = initial_balance + self.get_recipient_amount(account)

        if account_balance.value != expected_balance_value:
            raise ValidationError(
                f'Expected {expected_balance_value} balance value, but got {account_balance.value} '
                f'for account {account}'
            )
