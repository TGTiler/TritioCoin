"""
TritioCoin GUI Wallet
Simple graphical wallet with integrated mining.
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
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
        self.root.geometry("850x650")
        self.root.configure(bg="#1a1a2e")

        self.is_mining = False
        self.miner_thread = None
        self.node_running = False
        self.current_wallet = None
        self.wallet_password = None

        self._setup_styles()
        self._create_tabs()
        self._try_load_wallet()
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
        style.configure('Warn.TLabel', foreground='#f39c12')

    def _create_tabs(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)

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

    def _get_password(self, prompt="Senha da carteira:"):
        return simpledialog.askstring("Senha", prompt, show='*')

    def _try_load_wallet(self):
        path = DATA_DIR / "wallet.json"
        if path.exists():
            pw = self._get_password("Carteira encontrada. Digite a senha:")
            if pw:
                try:
                    from core.wallet import Wallet
                    w = Wallet.load(str(path), pw)
                    self.current_wallet = w
                    self.wallet_password = pw
                    self.lbl_address.config(text=f"Endereco: {w.address}")
                    self._log(f"Carteira carregada: {w.address[:24]}...")
                    self._refresh_balance()
                except Exception:
                    self._log("Senha incorreta ou carteira corrompida.")

    # ========== DASHBOARD ==========
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

    # ========== WALLET ==========
    def _build_wallet(self):
        frame = self.tab_wallet
        ttk.Label(frame, text="Carteira", style='Header.TLabel').pack(pady=10)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Criar Carteira", command=self._create_wallet).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Abrir Carteira", command=self._open_wallet).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Recuperar Carteira", command=self._recover_wallet).pack(side='left', padx=5)

        self.lbl_address = ttk.Label(frame, text="Endereco: N/A")
        self.lbl_address.pack(pady=5)
        self.lbl_bal = ttk.Label(frame, text="Saldo: 0.00000000 TRC")
        self.lbl_bal.pack(pady=5)

        ttk.Label(frame, text="Historico de Transacoes", style='Header.TLabel').pack(pady=(15,5))
        self.history_text = scrolledtext.ScrolledText(frame, height=12, bg='#0f3460',
                                                      fg='white', font=('Consolas', 9))
        self.history_text.pack(fill='both', expand=True, padx=20, pady=5)
        ttk.Button(frame, text="Atualizar Historico", command=self._refresh_history).pack(pady=5)

    # ========== SEND ==========
    def _build_send(self):
        frame = self.tab_send
        ttk.Label(frame, text="Enviar TRC", style='Header.TLabel').pack(pady=10)

        form = ttk.Frame(frame)
        form.pack(pady=20, padx=40)

        ttk.Label(form, text="Destinatario:").grid(row=0, column=0, sticky='w', pady=5)
        self.entry_recipient = ttk.Entry(form, width=55)
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

    # ========== MINING ==========
    def _build_mining(self):
        frame = self.tab_mining
        ttk.Label(frame, text="Mineracao", style='Header.TLabel').pack(pady=10)

        self.lbl_mining_status = ttk.Label(frame, text="Status: Parado", style='Info.TLabel')
        self.lbl_mining_status.pack(pady=5)
        self.lbl_hashrate = ttk.Label(frame, text="Hashrate: 0 H/s")
        self.lbl_hashrate.pack(pady=5)
        self.lbl_blocks_mined = ttk.Label(frame, text="Blocos encontrados: 0")
        self.lbl_blocks_mined.pack(pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)
        self.btn_mine = ttk.Button(btn_frame, text="Iniciar Mineracao", command=self._toggle_mining)
        self.btn_mine.pack(side='left', padx=5)

        self.log_text = scrolledtext.ScrolledText(frame, height=10, bg='#0f3460',
                                                  fg='white', font=('Consolas', 9))
        self.log_text.pack(fill='both', expand=True, padx=20, pady=10)

    # ========== NETWORK ==========
    def _build_network(self):
        frame = self.tab_network
        ttk.Label(frame, text="Rede", style='Header.TLabel').pack(pady=10)
        self.network_text = scrolledtext.ScrolledText(frame, height=20, bg='#0f3460',
                                                      fg='white', font=('Consolas', 9))
        self.network_text.pack(fill='both', expand=True, padx=20, pady=10)
        ttk.Button(frame, text="Atualizar", command=self._refresh_network).pack(pady=5)

    # ========== HELPERS ==========
    def _log(self, msg):
        self.log_text.insert('end', f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see('end')

    def _ensure_wallet(self):
        if not self.current_wallet:
            messagebox.showwarning("Aviso", "Nenhuma carteira carregada. Crie ou abra uma carteira primeiro.")
            return False
        return True

    # ========== WALLET OPERATIONS ==========
    def _create_wallet(self):
        try:
            from core.wallet import Wallet
            pw = self._get_password("Crie uma senha para a carteira:")
            if not pw:
                return
            pw2 = self._get_password("Confirme a senha:")
            if pw != pw2:
                messagebox.showerror("Erro", "Senhas nao conferem!")
                return

            w = Wallet.create()
            DATA_DIR.mkdir(exist_ok=True)
            w.save(str(DATA_DIR / "wallet.json"), pw)

            self.current_wallet = w
            self.wallet_password = pw
            self.lbl_address.config(text=f"Endereco: {w.address}")

            # Show mnemonic in a scrollable dialog
            mnemonic_win = tk.Toplevel(self.root)
            mnemonic_win.title("IMPORTANTE - Anote as 24 palavras!")
            mnemonic_win.geometry("500x300")
            mnemonic_win.configure(bg="#1a1a2e")

            tk.Label(mnemonic_win, text="ANOTE ESTAS 24 PALAVRAS!",
                    bg="#1a1a2e", fg="#e94560", font=('Segoe UI', 14, 'bold')).pack(pady=10)
            tk.Label(mnemonic_win, text="Sem elas, voce PERDE sua carteira para sempre!",
                    bg="#1a1a2e", fg="#f39c12", font=('Segoe UI', 10)).pack(pady=5)

            mnemonic_text = tk.Text(mnemonic_win, height=4, bg='#0f3460', fg='white',
                                   font=('Consolas', 12), wrap='word')
            mnemonic_text.insert('end', w.mnemonic)
            mnemonic_text.config(state='disabled')
            mnemonic_text.pack(padx=20, pady=10, fill='x')

            tk.Label(mnemonic_win, text=f"Endereco: {w.address}",
                    bg="#1a1a2e", fg="white", font=('Segoe UI', 9)).pack(pady=5)

            tk.Button(mnemonic_win, text="Fechar (ja anotei?)", command=mnemonic_win.destroy,
                     bg='#0f3460', fg='white', font=('Segoe UI', 10, 'bold')).pack(pady=10)

            self._log(f"Carteira criada: {w.address[:24]}...")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _open_wallet(self):
        try:
            from core.wallet import Wallet
            path = DATA_DIR / "wallet.json"
            if not path.exists():
                messagebox.showwarning("Aviso", "Nenhuma carteira encontrada. Crie uma primeiro.")
                return
            pw = self._get_password("Digite a senha da carteira:")
            if not pw:
                return
            w = Wallet.load(str(path), pw)
            self.current_wallet = w
            self.wallet_password = pw
            self.lbl_address.config(text=f"Endereco: {w.address}")
            self._log(f"Carteira aberta: {w.address[:24]}...")
            self._refresh_balance()
            self._refresh_history()
        except Exception as e:
            messagebox.showerror("Erro", f"Senha incorreta ou carteira corrompida.\n{e}")

    def _recover_wallet(self):
        try:
            from core.wallet import Wallet
            words = simpledialog.askstring("Recuperar Carteira",
                "Digite as 24 palavras de recuperacao (separadas por espaco):")
            if not words or len(words.split()) != 24:
                messagebox.showerror("Erro", "Precisa de exatamente 24 palavras!")
                return

            pw = self._get_password("Crie uma senha para a nova carteira:")
            if not pw:
                return
            pw2 = self._get_password("Confirme a senha:")
            if pw != pw2:
                messagebox.showerror("Erro", "Senhas nao conferem!")
                return

            w = Wallet.from_mnemonic(words)
            DATA_DIR.mkdir(exist_ok=True)
            w.save(str(DATA_DIR / "wallet.json"), pw)

            self.current_wallet = w
            self.wallet_password = pw
            self.lbl_address.config(text=f"Endereco: {w.address}")
            self._log(f"Carteira recuperada: {w.address[:24]}...")
            messagebox.showinfo("Sucesso", f"Carteira recuperada!\n\nEndereco: {w.address}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # ========== BALANCE / HISTORY ==========
    def _refresh_balance(self):
        if not self.current_wallet:
            return
        addr = self.current_wallet.address
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:8080/api/balance/{addr}")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read().decode())
            bal = data.get("balance", 0)
            self.lbl_bal.config(text=f"Saldo: {bal:.8f} TRC (via node)")
        except Exception:
            try:
                from core.blockchain import Blockchain
                from core.database import Database
                from core.network_config import MAINNET
                db = Database(DATA_DIR / "mainnet.db")
                bc = Blockchain(MAINNET, db)
                bal = bc.balance(addr)
                self.lbl_bal.config(text=f"Saldo: {bal:.8f} TRC (local)")
            except Exception:
                self.lbl_bal.config(text="Saldo: N/A")

    def _refresh_history(self):
        self.history_text.delete('1.0', 'end')
        if not self.current_wallet:
            self.history_text.insert('end', "Nenhuma carteira carregada.")
            return

        addr = self.current_wallet.address
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:8080/api/address/{addr}")
            resp = urllib.request.urlopen(req, timeout=3)
            data = json.loads(resp.read().decode())
            txs = data.get("transactions", [])

            if not txs:
                self.history_text.insert('end', "Nenhuma transacao encontrada.\n")
                return

            self.history_text.insert('end', f"{'Bloco':<8} {'Tipo':<8} {'Valor':<14} {'Hash':<20}\n")
            self.history_text.insert('end', "-" * 55 + "\n")

            for tx in txs:
                block = tx.get("block_height", "?")
                sender = tx.get("sender", "")
                recipient = tx.get("recipient", "")
                amount = tx.get("amount", 0)
                tx_hash = tx.get("tx_hash", "")[:16]

                if sender == "COINBASE":
                    tx_type = "REWARD"
                elif sender == addr:
                    tx_type = "ENVIADO"
                else:
                    tx_type = "RECEBIDO"

                self.history_text.insert('end',
                    f"{block:<8} {tx_type:<8} {amount:<14.8f} {tx_hash}...\n")

            self.history_text.insert('end', f"\nFonte: Node (tempo real)")
        except Exception:
            try:
                from core.blockchain import Blockchain
                from core.database import Database
                from core.network_config import MAINNET
                db = Database(DATA_DIR / "mainnet.db")
                bc = Blockchain(MAINNET, db)
                hist = bc.history(self.current_wallet.pubkey_hex()) + bc.history(addr)

                if not hist:
                    self.history_text.insert('end', "Nenhuma transacao encontrada.\n")
                    return

                self.history_text.insert('end', f"{'Bloco':<8} {'De':<18} {'Para':<18} {'Valor':<12}\n")
                self.history_text.insert('end', "-" * 60 + "\n")

                for h in sorted(hist, key=lambda x: x['block']):
                    frm = h['from'][:16]
                    to = h['to'][:16]
                    self.history_text.insert('end',
                        f"{h['block']:<8} {frm:<18} {to:<18} {h['amount']:<12.4f}\n")

                self.history_text.insert('end', f"\nFonte: Dados locais")
            except Exception as e:
                self.history_text.insert('end', f"Erro ao carregar historico: {e}")

    # ========== DASHBOARD ==========
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
            self._refresh_balance()
        except Exception:
            self.lbl_status.config(text="Status: Desconectado (inicie main.py)", style='Warn.TLabel')
            self.node_running = False

    # ========== SEND ==========
    def _send_trc(self):
        if not self._ensure_wallet():
            return

        recipient = self.entry_recipient.get().strip()
        amount_str = self.entry_amount.get().strip()
        fee_str = self.entry_fee.get().strip()

        if not recipient or not amount_str:
            messagebox.showwarning("Aviso", "Preencha destinatario e valor.")
            return

        try:
            amount = float(amount_str)
            fee = float(fee_str)
        except ValueError:
            messagebox.showerror("Erro", "Valores invalidos.")
            return

        if not self.node_running:
            messagebox.showwarning("Aviso", "Node offline. Inicie main.py primeiro.")
            return

        try:
            import urllib.request
            from core.transaction import Transaction
            from core.constants import trc_to_satoshis

            w = self.current_wallet
            tx = Transaction(w.pubkey_hex(), recipient, amount, fee)
            tx_data = bytes.fromhex(tx.compute_hash())
            sigs = w.sign_tx(tx_data)
            tx.signature = sigs["ecdsa_signature"]
            tx.signature_mode = sigs["signature_mode"]
            tx.tx_hash = tx.compute_hash()

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
                self._refresh_balance()
            else:
                self.lbl_send_status.config(text="Falha no envio", style='Warn.TLabel')
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    # ========== MINING ==========
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
            if not self._ensure_wallet():
                return
            self.is_mining = True
            self.btn_mine.config(text="Parar Mineracao")
            self.lbl_mining_status.config(text="Status: Minerando...")
            self._log("Mineracao iniciada.")
            self.miner_thread = threading.Thread(target=self._mine_worker, daemon=True)
            self.miner_thread.start()

    def _mine_worker(self):
        try:
            from core.blockchain import Blockchain
            from core.mempool import Mempool
            from core.database import Database
            from core.miner import Miner
            from core.network_config import MAINNET
            import urllib.request

            db = Database(DATA_DIR / "mainnet.db")
            bc = Blockchain(MAINNET, db)
            mempool = Mempool(db)
            w = self.current_wallet

            miner = Miner(bc, mempool)
            blocks_found = 0

            def on_block(block):
                nonlocal blocks_found
                import hashlib
                block_data = f"{block.header.index}{block.hash}".encode()
                sig = w.sign_tx(hashlib.sha256(block_data).digest())
                block.validator_signatures.append({
                    "address": w.address,
                    "signature": sig["ecdsa_signature"].hex(),
                    "signature_mode": sig["signature_mode"]
                })

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
                        self.root.after(0, lambda: self.lbl_blocks_mined.config(
                            text=f"Blocos encontrados: {blocks_found}"))
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"Falha ao transmitir: {e}"))

            import asyncio
            asyncio.run(miner.mine_continuous(w.address, callback=on_block))

        except Exception as e:
            self.root.after(0, lambda: self._log(f"Erro: {e}"))

    # ========== NETWORK ==========
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
