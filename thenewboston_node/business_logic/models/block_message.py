import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from dataclasses_json import config, dataclass_json
from marshmallow import fields

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.core.utils.cryptography import normalize_dict
from thenewboston_node.core.utils.dataclass import fake_super_methods

from .account_balance import BlockAccountBalance
from .base import MessageMixin
from .transfer_request import TransferRequest

logger = logging.getLogger(__name__)


def calculate_updated_balances(get_account_balance: Callable[[str], Optional[int]],
                               transfer_request: TransferRequest) -> dict[str, BlockAccountBalance]:
    updated_balances: dict[str, BlockAccountBalance] = {}
    sent_amount = 0
    for transaction in transfer_request.message.txs:
        recipient = transaction.recipient
        amount = transaction.amount

        balance = updated_balances.get(recipient)
        if balance is None:
            balance = BlockAccountBalance(balance=get_account_balance(recipient) or 0)
            updated_balances[recipient] = balance

        balance.balance += amount
        sent_amount += amount

    sender = transfer_request.sender
    sender_balance = get_account_balance(sender)
    assert sender_balance is not None
    assert sender_balance >= sent_amount

    updated_balances[sender] = BlockAccountBalance(
        balance=sender_balance - sent_amount,
        # Transfer request message hash becomes new balance lock
        balance_lock=transfer_request.message.get_hash()
    )

    return updated_balances


@fake_super_methods
@dataclass_json
@dataclass
class BlockMessage(MessageMixin):
    transfer_request: TransferRequest
    # We need timestamp, block_number and block_identifier to be signed and hashed therefore
    # they are include in BlockMessage, not in Block
    timestamp: datetime = field(  # naive datetime in UTC
        metadata=config(
            encoder=datetime.isoformat,
            decoder=datetime.fromisoformat,
            mm_field=fields.DateTime(format='iso')
        )
    )
    block_number: int
    block_identifier: str
    updated_balances: dict[str, BlockAccountBalance]

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()
        # TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
        dict_['transfer_request'] = self.transfer_request.to_dict()
        dict_['updated_balances'] = {key: value.to_dict() for key, value in self.updated_balances.items()}
        return dict_

    @classmethod
    def from_transfer_request(cls, transfer_request: TransferRequest):
        if not transfer_request.sender:
            raise ValueError('Sender must be set')

        # TODO(dmu) HIGH: Move source of time to Blockchain?
        timestamp = datetime.utcnow()

        # TODO(dmu) LOW: Find a better way to avoid circular imports
        from ..blockchain.base import BlockchainBase  # avoid circular imports
        blockchain = BlockchainBase.get_instance()
        block_number = blockchain.get_next_block_number()
        block_identifier = blockchain.get_next_block_identifier()

        return BlockMessage(
            transfer_request=copy.deepcopy(transfer_request),
            timestamp=timestamp,
            block_number=block_number,
            block_identifier=block_identifier,
            updated_balances=calculate_updated_balances(blockchain.get_account_balance, transfer_request),
        )

    def get_normalized(self) -> bytes:
        return normalize_dict(self.to_dict())  # type: ignore

    def get_balance(self, account: str) -> Optional[BlockAccountBalance]:
        return (self.updated_balances or {}).get(account)

    def validate(self):
        self.validate_transfer_request()
        self.validate_timestamp()
        self.validate_block_number()
        self.validate_block_identifier()
        self.validate_updated_balances()

    def validate_transfer_request(self):
        transfer_request = self.transfer_request
        if transfer_request is None:
            raise ValidationError('Block message transfer request must present')

        transfer_request.validate()

    def validate_timestamp(self):
        timestamp = self.timestamp
        if timestamp is None:
            raise ValidationError('Block message timestamp must be set')

        if not isinstance(timestamp, datetime):
            raise ValidationError('Block message timestamp must be datetime type')

        if timestamp.tzinfo is not None:
            raise ValidationError('Block message timestamp must be naive datetime (UTC timezone implied)')

    def validate_block_number(self):
        block_number = self.block_number
        if block_number is None:
            raise ValidationError('Block message block number must be set')

        if not isinstance(block_number, int):
            raise ValidationError('Block message block number must be integer')

        if block_number < 0:
            raise ValidationError('Block message block number must be greater or equal to 0')

    def validate_block_identifier(self):
        block_identifier = self.block_identifier
        if block_identifier is None:
            raise ValidationError('Block message block number must be set')

        if not isinstance(block_identifier, str):
            raise ValidationError('Block message block number must be a string')

    def validate_updated_balances(self):
        updated_balances = self.updated_balances
        if updated_balances is None:
            raise ValidationError('Block message must contain updated balances')

        if len(updated_balances) < 2:
            raise ValidationError('Update balances must contain at least 2 balances')

        sender_account_balance = updated_balances.get(self.transfer_request.sender)
        if sender_account_balance is None:
            raise ValidationError('Update balances must contain sender account balance')

        if not sender_account_balance.balance_lock:
            raise ValidationError('Update balances must contain sender account balance lock')

        for account, account_balance in updated_balances.items():
            if not isinstance(account, str):
                raise ValidationError('Account must be a string')

            account_balance.validate()
