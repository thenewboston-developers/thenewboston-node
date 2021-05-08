import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from dataclasses_json import config, dataclass_json
from marshmallow import fields

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.core.logging import validates
from thenewboston_node.core.utils.constants import SENTINEL
from thenewboston_node.core.utils.cryptography import hash_normalized_dict, normalize_dict
from thenewboston_node.core.utils.dataclass import fake_super_methods

from .account_balance import AccountBalance
from .base import MessagpackCompactableMixin

logger = logging.getLogger(__name__)


@fake_super_methods
@dataclass_json
@dataclass
class AccountRootFile(MessagpackCompactableMixin):
    """Historical snapshot of all account balances at any point in time"""

    accounts: dict[str, AccountBalance]
    """Dict like {"`account_number`": `AccountBalance`, ...}"""

    last_block_number: Optional[int] = None
    """Block number at which snapshot was taken"""

    # TODO(dmu) MEDIUM: Do we really need last_block_identifier?
    last_block_identifier: Optional[str] = None
    """Block identifier at which snapshot was taken"""

    last_block_timestamp: Optional[datetime] = field(
        metadata=config(
            encoder=lambda x: None if x is None else x.isoformat(),
            decoder=lambda x: None if x is None else datetime.fromisoformat(x),
            mm_field=fields.DateTime(format='iso')
        ),
        default=None,
    )
    """Naive datetime in UTC"""

    next_block_identifier: Optional[str] = None
    """Next block identifier"""

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()

        # TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
        for attr in ('last_block_number', 'last_block_identifier', 'next_block_identifier', 'last_block_timestamp'):
            value = dict_.get(attr, SENTINEL)
            if value is None:
                del dict_[attr]

        return dict_

    def get_balance(self, account: str) -> Optional[AccountBalance]:
        return self.accounts.get(account)

    def get_balance_value(self, account: str) -> Optional[int]:
        balance = self.get_balance(account)
        if balance is not None:
            return balance.value

        return None

    def get_balance_lock(self, account: str) -> str:
        balance = self.get_balance(account)
        if balance is not None:
            return balance.lock

        return account

    def get_next_block_number(self) -> int:
        last_block_number = self.last_block_number
        return 0 if last_block_number is None else last_block_number + 1

    def get_next_block_identifier(self) -> str:
        next_block_identifier = self.next_block_identifier
        if next_block_identifier:
            return next_block_identifier

        return self.get_hash()  # initial account root file case

    def get_normalized(self) -> bytes:
        return normalize_dict(self.to_dict())  # type: ignore

    def get_hash(self):
        return hash_normalized_dict(self.get_normalized())

    def is_initial(self) -> bool:
        return (
            self.last_block_number is None and self.last_block_identifier is None and
            self.next_block_identifier is None and self.last_block_timestamp is None
        )

    @validates('account root file')
    def validate(self, is_initial=False):
        self.validate_attributes(is_initial=is_initial)
        self.validate_accounts()

    @validates('account root file attributes', is_plural_target=True)
    def validate_attributes(self, is_initial=False):
        self.validate_last_block_number(is_initial)
        self.validate_last_block_identifier(is_initial)
        self.validate_last_block_timestamp(is_initial)
        self.validate_next_block_identifier(is_initial)

    @validates('account root file last_block_number')
    def validate_last_block_number(self, is_initial):
        if is_initial:
            if self.last_block_number is not None:
                raise ValidationError(
                    'Account root file last block number must not be set for initial account root file'
                )
        else:
            if not isinstance(self.last_block_number, int):
                raise ValidationError('Account root file last block number must be an integer')
            if self.last_block_number < 0:
                raise ValidationError('Account root file last block number must be a non-negative integer')

    @validates('account root file last_block_identifier')
    def validate_last_block_identifier(self, is_initial):
        if is_initial:
            if self.last_block_identifier is not None:
                raise ValidationError(
                    'Account root file last block identifier must not be set for initial account root file'
                )
        else:
            if not isinstance(self.last_block_identifier, str):
                raise ValidationError('Account root file last block identifier must be a string')

    @validates('account root file last_block_timestamp')
    def validate_last_block_timestamp(self, is_initial):
        if is_initial:
            if self.last_block_timestamp is not None:
                raise ValidationError(
                    'Account root file last block timestamp must not be set for initial account root file'
                )
        else:
            timestamp = self.last_block_timestamp
            if timestamp is None:
                raise ValidationError('Account root file last block timestamp must be set')

            if not isinstance(timestamp, datetime):
                raise ValidationError('Account root file last block timestamp must be datetime type')

            if timestamp.tzinfo is not None:
                raise ValidationError(
                    'Account root file last block timestamp must be naive datetime (UTC timezone implied)'
                )

    @validates('account root file next_block_identifier')
    def validate_next_block_identifier(self, is_initial):
        if is_initial:
            if self.next_block_identifier is not None:
                raise ValidationError(
                    'Account root file next block identifier must not be set for initial account root file'
                )
        else:
            if not isinstance(self.next_block_identifier, str):
                raise ValidationError('Account root file next block identifier must be a string')

    @validates('account root file accounts', is_plural_target=True)
    def validate_accounts(self):
        for account, balance in self.accounts.items():
            with validates(f'account root file account {account}'):
                if not isinstance(account, str):
                    raise ValidationError('Account root file account number must be a string')
                balance.validate()
