from typing import TYPE_CHECKING

from google.protobuf.descriptor import FieldDescriptor

if TYPE_CHECKING:
    from google._upb._message import FieldDescriptor as UpbFieldDescriptor


def is_repeated_field(field_descriptor: "FieldDescriptor | UpbFieldDescriptor") -> bool:
    return field_descriptor.is_repeated
