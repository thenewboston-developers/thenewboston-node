import logging
from dataclasses import dataclass
from typing import Optional

from dataclasses_json import dataclass_json

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.core.logging import validates
from thenewboston_node.core.utils.constants import SENTINEL
from thenewboston_node.core.utils.dataclass import fake_super_methods

logger = logging.getLogger(__name__)


@dataclass_json
@dataclass
class AccountBalance:
    """Account balance state"""

    value: int
    """Amount balance value in coins"""

    lock: str
    """Account balance lock"""

    @validates('account balance')
    def validate(self, validate_lock=True):
        with validates('account balance attributes'):
            with validates('account balance value'):
                if not isinstance(self.value, int):
                    raise ValidationError('Account balance value must be an integer')

                if self.value < 0:
                    raise ValidationError('Account balance value must be a positive integer')

            if validate_lock:
                with validates('account balance lock'):
                    if not isinstance(self.lock, str):
                        raise ValidationError('Account balance lock must be a string')

                    if not self.lock:
                        raise ValidationError('Account balance lock must be set')


@fake_super_methods
@dataclass_json
@dataclass
class BlockAccountBalance(AccountBalance):
    lock: Optional[str] = None  # type: ignore

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()

        # TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
        value = dict_.get('lock', SENTINEL)
        if value is None:
            del dict_['lock']

        return dict_

    @validates('block account balance')
    def validate(self):
        super().validate(validate_lock=False)
