import logging
import warnings
from dataclasses import dataclass
from typing import Optional, Type, TypeVar

from dataclasses_json import dataclass_json

from thenewboston_node.business_logic.exceptions import ValidationError
from thenewboston_node.business_logic.models.node import PrimaryValidator, RegularNode
from thenewboston_node.business_logic.network.base import NetworkBase
from thenewboston_node.business_logic.node import get_signing_key
from thenewboston_node.core.logging import timeit_method, validates
from thenewboston_node.core.utils.cryptography import derive_verify_key
from thenewboston_node.core.utils.dataclass import fake_super_methods

from .base import MessagpackCompactableMixin, SignableMixin
from .block_message import BlockMessage
from .transfer_request import TransferRequest

T = TypeVar('T', bound='Block')

logger = logging.getLogger(__name__)


@fake_super_methods
@dataclass_json
@dataclass
class Block(SignableMixin, MessagpackCompactableMixin):
    """
    Blocks represent a description of change to the network.
    These originate from signed requests and may include:

     - a transfer of coins between accounts
     - the registration of a username
     - a new node being added to the network
     - etc...
    """

    verify_key_field_name = 'node_identifier'

    node_identifier: str
    """Public key of a node signed the block"""

    message: BlockMessage
    """Block payload"""

    message_hash: Optional[str] = None
    """Hash value of message field"""

    message_signature: Optional[str] = None
    """The signature of the node indicating the validity of the block"""

    @classmethod
    @timeit_method(level=logging.INFO, is_class_method=True)
    def from_transfer_request(cls: Type[T], blockchain, transfer_request: TransferRequest) -> T:
        signing_key = get_signing_key()
        block = cls(
            node_identifier=derive_verify_key(signing_key),
            message=BlockMessage.from_transfer_request(blockchain, transfer_request)
        )
        block.sign(signing_key)
        block.hash_message()
        return block

    @classmethod
    def from_main_transaction(
        cls: Type[T],
        blockchain,
        recipient: str,
        amount: int,
        signing_key: str,
        primary_validator: Optional[PrimaryValidator] = None,
        node: Optional[RegularNode] = None
    ) -> T:
        if primary_validator is None or node is None:
            warnings.warn('Skipping primary_validator and node is deprecated', DeprecationWarning)
            network = NetworkBase.get_instance()
            primary_validator = primary_validator or network.get_primary_validator()
            node = node or network.get_preferred_node()

        transfer_request = TransferRequest.from_main_transaction(
            blockchain=blockchain,
            recipient=recipient,
            amount=amount,
            signing_key=signing_key,
            primary_validator=primary_validator,
            node=node,
        )
        return cls.from_transfer_request(blockchain, transfer_request)

    def override_to_dict(self):  # this one turns into to_dict()
        dict_ = self.super_to_dict()
        # TODO(dmu) LOW: Implement a better way of removing optional fields or allow them in normalized message
        dict_['message'] = self.message.to_dict()
        return dict_

    def hash_message(self) -> None:
        message_hash = self.message.get_hash()
        stored_message_hash = self.message_hash
        if stored_message_hash and stored_message_hash != message_hash:
            logger.warning('Overwriting existing message hash')

        self.message_hash = message_hash

    @validates('block')
    def validate(self, blockchain):
        with validates(f'block number {self.message.block_number} (identifier: {self.message.block_identifier})'):
            self.validate_node_identifier()
            self.validate_message(blockchain)

            with validates('block signature'):
                self.validate_signature()

            self.validate_message_hash()

    @validates('block node identifier')
    def validate_node_identifier(self):
        if not self.node_identifier:
            raise ValidationError('Block node identifier must be set')

    @validates('block message on block level')
    def validate_message(self, blockchain):
        if not self.message:
            raise ValidationError('Block message must be not empty')

        self.message.validate(blockchain)

    @validates('block message hash')
    def validate_message_hash(self):
        if self.message.get_hash() != self.message_hash:
            raise ValidationError('Block message hash is invalid')
