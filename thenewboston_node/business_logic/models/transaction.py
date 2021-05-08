from dataclasses import dataclass
from typing import Optional

from dataclasses_json import dataclass_json

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.business_logic.models import constants
from thenewboston_node.core.logging import validates
from thenewboston_node.core.utils.constants import SENTINEL
from thenewboston_node.core.utils.dataclass import fake_super_methods


# TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
def remove_key_if_optional(dict_, key, optional_values=(None,)):
    value = dict_.get(key, SENTINEL)
    if value in optional_values:
        del dict_[key]


@fake_super_methods
@dataclass_json
@dataclass
class Transaction:
    """Coin transfer between accounts"""

    recipient: str
    """Recipient's account number"""

    amount: int
    """Coins being sent to the recipient"""

    fee: Optional[bool] = None  # None value won't be serialized
    """True if transaction is fee"""

    memo: Optional[str] = None
    """Optional memo"""

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()

        remove_key_if_optional(dict_, key='fee', optional_values=(None, False))
        remove_key_if_optional(dict_, key='memo', optional_values=(None,))

        return dict_

    @validates('transaction {}')
    def validate(self):
        with validates('recipient'):
            if not self.recipient:
                raise ValidationError('Transaction recipient is not set')

        with validates('amount'):
            amount = self.amount
            if not isinstance(amount, int):
                raise ValidationError('Transaction amount must be an integer')

            if amount < 1:
                raise ValidationError('Transaction amount must be greater or equal to 1')

        with validates('fee'):
            if self.fee not in (True, False, None):
                raise ValidationError('Transaction fee value is invalid')

        with validates('memo'):
            max_len = constants.MEMO_MAX_LENGTH
            if self.memo and len(self.memo) > max_len:
                raise ValidationError(f'Transaction memo must be less than {max_len} characters')
