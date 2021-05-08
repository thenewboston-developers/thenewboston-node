from dataclasses import dataclass

from dataclasses_json import dataclass_json

from thenewboston_node.business_logic.enums import NodeType


@dataclass_json
@dataclass
class Node:
    identifier: str
    """Node's public key"""

    fee_amount: int
    """Validation fee taking by the node"""

    type_: str
    """Node type"""


@dataclass_json
@dataclass
class PrimaryValidator(Node):
    type_: str = NodeType.PRIMARY_VALIDATOR.value


@dataclass_json
@dataclass
class RegularNode(Node):
    type_: str = NodeType.REGULAR_NODE.value
