"""
TritioCoin GUI Wallet
Simple graphical wallet with integrated mining.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import os
import sys
import time
from pathlib import Path

DATA_DIR = Path("tritiocoin_data")


class TritioGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TritioCoin Wallet v1.1")
        self.root.geometry("800x600")
        self.root.configure(bg="#1a1a2e")

        self.is_mining = False
        self.miner_thread = None
        self.node_running = False

        self._setup_styles()
        self._create_tabs()
        self.root.mainloop()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background='#1a1a2e')
        style.configure('TNotebook.Tab', background='#16213e', foreground='white',
                       padding=[15, 5])
        style.configure('TFrame', background='#1a1a2e')
        style.configure('TLabel', background='#1a1a2e', foreground='white',
                       font=('Segoe UI', 10))
        style.configure('TButton', background='#0f3460', foreground='white',
                       font=('Segoe UI', 10, 'bold'))
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'),
                       foreground='#e94560')
        style.configure('Success.TLabel', foreground='#4ecca3')
        style.configure('Info.TLabel', foreground='#a8d8ea')

    def _create_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

        # Tabs
        self.tab_dashboard = ttk.Frame(notebook)
        self.tab_wallet = ttk.Frame(notebook)
        self.tab_send = ttk.Frame(notebook)
        self.tab_mining = ttk.Frame(notebook)
        self.tab_network = ttk.Frame(notebook)

        notebook.add(self.tab_dashboard, text="  Dashboard  ")
        notebook.add(self.tab_wallet, text="  Carteira  ")
        notebook.add(self.tab_send, text="  Enviar  ")
        notebook.add(self.tab_mining, text="  Minerar  ")
        notebook.add(self.tab_network, text="  Rede  ")

        self._build_dashboard()
        self._build_wallet()
        self._build_send()
        self._build_mining()
        self._build_network()

    def _build_dashboard(self):
        frame = self.tab_dashboard

        ttk.Label(frame, text="Dashboard", style='Header.TLabel').pack(pady=10)

        info_frame = ttk.Frame(frame)
        info_frame.pack(fill='x', padx=20, pady=10)

        self.lbl_height = ttk.Label(info_frame, text="Altura: 0")
        self.lbl_height.pack(anchor='w')

        self.lbl_balance = ttk.Label(info_frame, text="Saldo: 0.00000000 TRC")
        self.lbl_balance.pack(anchor='w')

        self.lbl_peers = ttk.Label(info_frame, text="Peers: 0")
        self.lbl_peers.pack(anchor='w')

        self.lbl_status = ttk.Label(info_frame, text="Status: Desconectado",
                                   style='Info.TLabel')
        self.lbl_status.pack(anchor='w')

        ttk.Button(frame, text="Atualizar", command=self._refresh_dashboard).pack(pady=10)

    def _build_wallet(self):
        frame = self.tab_wallet

        ttk.Label(frame, text="Carteira", style='Header.TLabel').pack(pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Criar Carteira", command=self._create_wallet).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Abrir Carteira", command=self._open_wallet).pack(side='left', padx=5)

        self.lbl_address = ttk.Label(frame, text="Endereco: N/A")
        self.lbl_address.pack(pady=5)

        self.lbl_bal = ttk.Label(frame, text="Saldo: 0.00000000 TRC")
        self.lbl_bal.pack(pady=5)

    def _build_send(self):
        frame = self.tab_send

        ttk.Label(frame, text="Enviar TRC", style='Header.TLabel').pack(pady=10)

        form = ttk.Frame(frame)
        form.pack(pady=20, padx=40)

        ttk.Label(form, text="Destinatario:").grid(row=0, column=0, sticky='w', pady=5)
        self.entry_recipient = ttk.Entry(form, width=50)
        self.entry_recipient.grid(row=0, column=1, pady=5)

        ttk.Label(form, text="Valor (TRC):").grid(row=1, column=0, sticky='w', pady=5)
        self.entry_amount = ttk.Entry(form, width=20)
        self.entry_amount.grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(form, text="Taxa (TRC):").grid(row=2, column=0, sticky='w', pady=5)
        self.entry_fee = ttk.Entry(form, width=20)
        self.entry_fee.insert(0, "0.001")
        self.entry_fee.grid(row=2, column=1, sticky='w', pady=5)

        ttk.Button(frame, text="Enviar", command=self._send_trc).pack(pady=10)

        self.lbl_send_status = ttk.Label(frame, text="")
        self.lbl_send_status.pack()

    def _build_mining(self):
        frame = self.tab_mining

        ttk.Label(frame, text="Mineracao", style='Header.TLabel').pack(pady=10)

        self.lbl_mining_status = ttk.Label(frame, text="Status: Parado",
                                          style='Info.TLabel')
        self.lbl_mining_status.pack(pady=5)

        self.lbl_hashrate = ttk.Label(frame, text="Hashrate: 0 H/s")
        self.lbl_hashrate.pack(pady=5)

        self.lbl_blocks = ttk.Label(frame, text="Blocos encontrados: 0")
        self.lbl_blocks.pack(pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)

        self.btn_mine = ttk.Button(btn_frame, text="Iniciar Mineracao",
                                  command=self._toggle_mining)
        self.btn_mine.pack(side='left', padx=5)

        self.log_text = scrolledtext.ScrolledText(frame, height=10, bg='#0f3460',
                                                  fg='white', font=('Consolas', 9))
        self.log_text.pack(fill='both', expand=True, padx=20, pady=10)

    def _build_network(self):
        frame = self.tab_network

        ttk.Label(frame, text="Rede", style='Header.TLabel').pack(pady=10)

        self.network_text = scrolledtext.ScrolledText(frame, height=20, bg='#0f3460',
                                                      fg='white', font=('Consolas', 9))
        self.network_text.pack(fill='both', expand=True, padx=20, pady=10)

        ttk.Button(frame, text="Atualizar", command=self._refresh_network).pack(pady=5)

    def _log(self, msg):
        self.log_text.insert('end', f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see('end')

    def _create_wallet(self):
        try:
            from core.wallet import Wallet
            w = Wallet.create()
            password = "tritiocoin_gui_default"
            DATA_DIR.mkdir(exist_ok=True)
            w.save(str(DATA_DIR / "wallet.json"), password)
            self.lbl_address.config(text=f"Endereco: {w.address}")
            self._log(f"Carteira criada: {w.address[:24]}...")
            messagebox.showinfo("Sucesso", f"Carteira criada!\n\nEndereco: {w.address}\n\nSalve as 24 palavras de recuperacao!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _open_wallet(self):
        try:
            from core.wallet import Wallet
            path = DATA_DIR / "wallet.json"
            if not path.exists():
                messagebox.showwarning("Aviso", "Nenhuma carteira encontrada. Crie uma primeiro.")
                return
            password = "tritiocoin_gui_default"
            w = Wallet.load(str(path), password)
            self.lbl_address.config(text=f"Endereco: {w.address}")
            self._refresh_balance(w.address)
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _refresh_balance(self, address):
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:8080/api/balance/{address}")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read().decode())
            bal = data.get("balance", 0)
            self.lbl_bal.config(text=f"Saldo: {bal:.8f} TRC")
        except Exception:
            self.lbl_bal.config(text="Saldo: N/A (node offline)")

    def _refresh_dashboard(self):
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8080/api/sync")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read().decode())
            self.lbl_height.config(text=f"Altura: {data.get('height', 0)}")
            self.lbl_peers.config(text=f"Peers: {data.get('peers', 0)}")
            self.lbl_status.config(text="Status: Conectado", style='Success.TLabel')
            self.node_running = True
        except Exception:
            self.lbl_status.config(text="Status: Desconectado", style='Info.TLabel')
            self.node_running = False

    def _send_trc(self):
        recipient = self.entry_recipient.get().strip()
        amount = self.entry_amount.get().strip()
        fee = self.entry_fee.get().strip()

        if not recipient or not amount:
            messagebox.showwarning("Aviso", "Preencha destinatario e valor.")
            return

        try:
            amount = float(amount)
            fee = float(fee)
        except ValueError:
            messagebox.showerror("Erro", "Valores invalidos.")
            return

        if not self.node_running:
            messagebox.showwarning("Aviso", "Node offline. Inicie main.py primeiro.")
            return

        try:
            import urllib.request
            # Load wallet and create tx
            from core.wallet import Wallet
            from core.transaction import Transaction, TransactionBuilder
            from core.constants import trc_to_satoshis

            path = DATA_DIR / "wallet.json"
            w = Wallet.load(str(path), "tritiocoin_gui_default")

            # Get UTXOs from node
            req = urllib.request.Request(f"http://127.0.0.1:8080/api/wallet/{w.address}")
            resp = urllib.request.urlopen(req, timeout=3)
            wallet_data = json.loads(resp.read().decode())

            if wallet_data.get("balance", 0) < amount + fee:
                messagebox.showerror("Erro", "Saldo insuficiente.")
                return

            # Build tx
            amount_sat = trc_to_satoshis(amount)
            fee_sat = trc_to_satoshis(fee)
            tx = Transaction(w.pubkey_hex(), recipient, amount, fee)
            tx_data = bytes.fromhex(tx.compute_hash())
            sigs = w.sign_tx(tx_data)
            tx.signature = sigs["ecdsa_signature"]
            tx.signature_mode = sigs["signature_mode"]
            tx.tx_hash = tx.compute_hash()

            # Send via API
            body = json.dumps(tx.to_dict()).encode('utf-8')
            req = urllib.request.Request(
                "http://127.0.0.1:8080/api/tx",
                data=body,
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=5)
            result = json.loads(resp.read().decode())

            if result.get("status") == "ok":
                self.lbl_send_status.config(text="Enviado com sucesso!", style='Success.TLabel')
                self._log(f"Enviado {amount} TRC para {recipient[:24]}...")
            else:
                self.lbl_send_status.config(text="Falha no envio", style='Info.TLabel')
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _toggle_mining(self):
        if self.is_mining:
            self.is_mining = False
            self.btn_mine.config(text="Iniciar Mineracao")
            self.lbl_mining_status.config(text="Status: Parado")
            self._log("Mineracao parada.")
        else:
            if not self.node_running:
                messagebox.showwarning("Aviso",
                    "Para minerar e transmitir blocos, inicie um node:\n\npython main.py --mode passive")
                return
            self.is_mining = True
            self.btn_mine.config(text="Parar Mineracao")
            self.lbl_mining_status.config(text="Status: Minerando...")
            self._log("Mineracao iniciada.")
            self.miner_thread = threading.Thread(target=self._mine_worker, daemon=True)
            self.miner_thread.start()

    def _mine_worker(self):
        try:
            from core.wallet import Wallet
            from core.blockchain import Blockchain
            from core.mempool import Mempool
            from core.database import Database
            from core.miner import Miner
            from core.network_config import MAINNET
            import urllib.request

            path = DATA_DIR / "wallet.json"
            w = Wallet.load(str(path), "tritiocoin_gui_default")
            db = Database(DATA_DIR / "mainnet.db")
            bc = Blockchain(MAINNET, db)
            mempool = Mempool(db)

            miner = Miner(bc, mempool)
            blocks_found = 0

            def on_block(block):
                nonlocal blocks_found
                block_data = f"{block.header.index}{block.hash}".encode()
                import hashlib
                sig = w.sign_tx(hashlib.sha256(block_data).digest())
                block.validator_signatures.append({
                    "address": w.address,
                    "signature": sig["ecdsa_signature"].hex(),
                    "signature_mode": sig["signature_mode"]
                })

                # Submit to node
                body = json.dumps(block.serialize()).encode('utf-8')
                req = urllib.request.Request(
                    "http://127.0.0.1:8080/api/block",
                    data=body,
                    headers={"Content-Type": "application/json"}
                )
                try:
                    resp = urllib.request.urlopen(req, timeout=5)
                    result = json.loads(resp.read().decode())
                    if result.get("status") == "ok":
                        blocks_found += 1
                        self.root.after(0, lambda: self._log(
                            f"Bloco #{block.header.index} mined e transmitido!"))
                        self.root.after(0, lambda: self.lbl_blocks.config(
                            text=f"Blocos encontrados: {blocks_found}"))
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"Falha ao transmitir: {e}"))

            import asyncio
            asyncio.run(miner.mine_continuous(w.address, callback=on_block))

        except Exception as e:
            self.root.after(0, lambda: self._log(f"Erro: {e}"))

    def _refresh_network(self):
        self.network_text.delete('1.0', 'end')
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8080/api/status")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read().decode())

            self.network_text.insert('end', "=== Status da Rede ===\n\n")
            self.network_text.insert('end', f"Altura: {data.get('height', 0)}\n")
            self.network_text.insert('end', f"Transacoes: {data.get('transactions', 0)}\n")
            self.network_text.insert('end', f"Dificuldade: {data.get('difficulty', 0)}\n")
            self.network_text.insert('end', f"Recompensa: {data.get('reward_trc', 0):.8f} TRC\n")
            self.network_text.insert('end', f"Supply: {data.get('circulating_trc', 0):.2f} TRC\n")
            self.network_text.insert('end', f"Validadores: {data.get('active_validators', 0)}\n")
            self.network_text.insert('end', f"Peers: {data.get('peers', 0)}\n")
            self.network_text.insert('end', f"Versao: {data.get('version', '1.1.0')}\n")

            # Peers list
            req2 = urllib.request.Request("http://127.0.0.1:8080/api/peers")
            resp2 = urllib.request.urlopen(req2, timeout=3)
            peers_data = json.loads(resp2.read().decode())
            peers = peers_data.get("peers", [])
            self.network_text.insert('end', f"\n=== Peers ({len(peers)}) ===\n")
            for p in peers:
                self.network_text.insert('end', f"  - {p}\n")
        except Exception:
            self.network_text.insert('end', "Node offline. Inicie main.py para ver dados da rede.")


if __name__ == "__main__":
    TritioGUI()
