"""
TritioCoin UTXO Manager
Handles UTXO selection and transaction creation using satoshis.
"""
import logging
from typing import List, Tuple, Optional
from core.database import Database
from core.transaction import Transaction, TransactionBuilder
from core.wallet import Wallet
from core.constants import SATOSHIS_PER_TRC, trc_to_satoshis, satoshis_to_trc, format_trc

logger = logging.getLogger("UTXO")


class UTXOManager:
    """Manages UTXO selection and transaction creation."""

    def __init__(self, db: Database):
        self.db = db

    def get_balance(self, address: str) -> float:
        """Get confirmed balance in TRC."""
        return satoshis_to_trc(self.db.get_utxo_balance(address))

    def get_balance_satoshis(self, address: str) -> int:
        """Get confirmed balance in satoshis."""
        return self.db.get_utxo_balance(address)

    def get_utxos(self, address: str) -> List[dict]:
        """Get all unspent outputs for an address."""
        return self.db.get_unspent_utxos(address)

    def create_transaction(self, sender_wallet: Wallet, recipient: str,
                           amount_trc: float, fee_trc: float = 0.001,
                           data: str = "") -> Optional[Transaction]:
        """
        Create a transaction with proper UTXO selection.
        Handles change outputs automatically.
        """
        sender = sender_wallet.pubkey_hex()
        amount_sat = trc_to_satoshis(amount_trc)
        fee_sat = trc_to_satoshis(fee_trc)

        try:
            inputs, change_sat = self.db.create_transaction_inputs(sender, amount_sat, fee_sat)
        except ValueError as e:
            logger.warning(f"Transaction failed: {e}")
            return None

        # Create the transaction
        tx = TransactionBuilder.create_transfer(
            sender_pubkey=sender,
            recipient=recipient,
            amount_satoshis=amount_sat,
            fee_satoshis=fee_sat,
            inputs=inputs
        )

        # Sign the transaction
        tx_data = bytes.fromhex(tx.compute_hash())
        sigs = sender_wallet.sign_tx(tx_data)
        tx.signature = sigs["ecdsa_signature"]
        tx.signature_mode = sigs["signature_mode"]
        tx.tx_hash = tx.compute_hash()

        # Store inputs and change
        tx.inputs = inputs
        tx.change_satoshis = change_sat

        logger.info(f"Transaction created: {tx}")
        logger.info(f"  Inputs: {len(inputs)} UTXOs ({TransactionBuilder.format_amount(sum(i['amount'] for i in inputs))})")
        logger.info(f"  Output: {TransactionBuilder.format_amount(amount_sat)} to {recipient[:16]}...")
        if change_sat > 0:
            logger.info(f"  Change: {TransactionBuilder.format_amount(change_sat)} back to sender")

        return tx

    def validate_transaction(self, tx: Transaction) -> Tuple[bool, str]:
        """
        Validate a transaction against UTXO rules.
        Returns (is_valid, error_message).
        """
        if tx.sender_pubkey == "COINBASE":
            return True, "coinbase"

        # Check basic validity
        if not tx.is_valid():
            return False, "Invalid signature"

        # Check if sender has sufficient balance
        sender_balance = self.get_balance_satoshis(tx.sender_pubkey)
        needed = tx.amount_satoshis + tx.fee_satoshis
        if sender_balance < needed:
            return False, f"Insufficient balance: {format_trc(sender_balance)} < {format_trc(needed)}"

        # Check if UTXO is already spent
        if self.db.is_utxo_spent(tx.tx_hash):
            return False, "UTXO already spent"

        return True, "valid"

    def get_transaction_history(self, address: str, limit: int = 50) -> List[dict]:
        """
        Get transaction history for an address.
        Shows both incoming and outgoing transactions.
        """
        utxos = self.get_utxos(address)
        spent = self.db.get_address_txs(address)

        history = []

        # Add unspent outputs (received)
        for utxo in utxos:
            history.append({
                "type": "received",
                "tx_hash": utxo["tx_hash"],
                "amount": utxo["amount"],
                "amount_trc": satoshis_to_trc(utxo["amount"]),
                "from": utxo["sender"][:16] + "...",
                "block": utxo["block_height"],
                "spent": False
            })

        # Add spent outputs (sent)
        for tx in spent:
            if tx["sender"] == address:
                history.append({
                    "type": "sent",
                    "tx_hash": tx["tx_hash"],
                    "amount": tx["amount"],
                    "amount_trc": satoshis_to_trc(tx["amount"]),
                    "to": tx["recipient"][:16] + "...",
                    "fee": tx["fee"],
                    "fee_trc": satoshis_to_trc(tx["fee"]),
                    "block": tx["block_height"],
                    "spent": True
                })

        # Sort by block height descending
        history.sort(key=lambda x: x.get("block", 0), reverse=True)

        return history[:limit]
