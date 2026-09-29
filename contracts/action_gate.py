# v0.2.16
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *

from dataclasses import dataclass


@gl.contract_interface
class IActionJurisdication:
    class View:
        def actionjurisdication_is_authorized_for(
            self,
            action_id: u256,
            expected_context_hash: str,
            expected_action_hash: str,
            expected_description_hash: str,
            expected_action_commitment: str,
            expected_matrix_hash: str,
        ) -> bool: ...

    class Write:
        pass


@allow_storage
@dataclass
class ExecutionReceipt:
    caller: Address
    action_id: u256
    action_hash: str
    description_hash: str
    action_commitment: str
    matrix_hash: str
    context_hash: str


def coerce_address(value) -> Address:
    """Accept Address, 0x-hex string, raw bytes, or the bare integer form some clients encode."""
    if hasattr(value, "as_bytes"):
        return value
    if isinstance(value, int):
        value = "0x" + format(value, "040x")
    elif isinstance(value, (bytes, bytearray, memoryview)):
        value = "0x" + bytes(value).hex()
    return Address(str(value).strip())


class ActionGate(gl.Contract):
    """Minimal consumer proving exact ActionJurisdication authorizations are composable."""

    action_jurisdication_address: Address
    context_hash: str
    executions: TreeMap[str, ExecutionReceipt]
    execution_count: u256

    def __init__(self, action_jurisdication_address: Address, context_hash: str):
        context = str(context_hash).strip().lower()
        if len(context) != 64:
            raise gl.vm.UserError("EXPECTED: context_hash must be 64 lowercase hex chars")
        for char in context:
            if char not in "0123456789abcdef":
                raise gl.vm.UserError("EXPECTED: context_hash must be lowercase hex")

        self.action_jurisdication_address = coerce_address(action_jurisdication_address)
        self.context_hash = context
        self.execution_count = u256(0)

    @gl.public.write
    def action_gate_execute(
        self,
        action_id: u256,
        expected_action_hash: str,
        expected_description_hash: str,
        expected_action_commitment: str,
        expected_matrix_hash: str,
    ) -> None:
        action_hash = str(expected_action_hash).strip().lower()
        description_hash = str(expected_description_hash).strip().lower()
        commitment = str(expected_action_commitment).strip().lower()
        matrix_hash = str(expected_matrix_hash).strip().lower()

        if any(len(value) != 64 for value in (action_hash, description_hash, commitment, matrix_hash)):
            raise gl.vm.UserError("EXPECTED: action, description, commitment, and matrix hashes must be 64 lowercase hex chars")
        for text in (action_hash, description_hash, commitment, matrix_hash):
            for char in text:
                if char not in "0123456789abcdef":
                    raise gl.vm.UserError("EXPECTED: hashes must be lowercase hex")

        if self.executions.get(action_hash) is not None:
            raise gl.vm.UserError("EXPECTED: action was already executed by this consumer")

        matrix = IActionJurisdication(self.action_jurisdication_address)
        if not matrix.view().actionjurisdication_is_authorized_for(
            action_id,
            str(self.context_hash),
            action_hash,
            description_hash,
            commitment,
            matrix_hash,
        ):
            raise gl.vm.UserError("EXPECTED: ActionJurisdication authorization is not valid for this consumer")

        self.executions[action_hash] = ExecutionReceipt(
            caller=gl.message.sender_address,
            action_id=action_id,
            action_hash=action_hash,
            description_hash=description_hash,
            action_commitment=commitment,
            matrix_hash=matrix_hash,
            context_hash=str(self.context_hash),
        )
        self.execution_count = u256(int(self.execution_count) + 1)

    @gl.public.view
    def action_gate_was_executed(self, action_hash: str) -> bool:
        key = str(action_hash).strip().lower()
        return self.executions.get(key) is not None

    @gl.public.view
    def action_gate_get_execution(self, action_hash: str) -> dict:
        key = str(action_hash).strip().lower()
        receipt = self.executions.get(key)
        if receipt is None:
            raise gl.vm.UserError("EXPECTED: unknown execution")
        return {
            "caller": str(receipt.caller),
            "action_id": int(receipt.action_id),
            "action_hash": str(receipt.action_hash),
            "description_hash": str(receipt.description_hash),
            "action_commitment": str(receipt.action_commitment),
            "matrix_hash": str(receipt.matrix_hash),
            "context_hash": str(receipt.context_hash),
        }
