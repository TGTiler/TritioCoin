# Como Contribuir com TritioCoin

Obrigado por querer contribuir com o TritioCoin!

---

## Comecando

### 1. Fork o repositorio

Vá ao GitHub e clique em "Fork" no canto superior direito.

### 2. Clone seu fork

```bash
git clone https://github.com/TGTiler/TritioCoin.git
cd TritioCoin
```

### 3. Crie uma branch de funcionalidade

```bash
git checkout -b minha-nova-funcionalidade
```

### 4. Faca suas mudancas

### 5. Envie um Pull Request

---

## Ambiente de Desenvolvimento

### Instalar dependencias

```bash
pip install -r requirements.txt
```

### Executar testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Testes especificos
python -m pytest tests/test_wallet.py -v
python -m pytest tests/test_blockchain.py -v
```

### Rodar o no localmente

```bash
# Terminal 1: Iniciar seed
python main.py --mode miner --become-seed

# Terminal 2: Conectar
python main.py --mode passive --seed 127.0.0.1:8333
```

---

## Estrutura do Projeto

```
TritioCoin/
├── core/               # Logica principal
│   ├── blockchain.py   # Gerenciamento da chain
│   ├── block.py        # Estrutura do bloco
│   ├── miner.py        # Mineracao Argon2id
│   ├── wallet.py       # Carteiras criptografadas
│   ├── transaction.py  # Transacoes
│   └── ...
├── network/            # Rede P2P
│   ├── p2p_node.py     # No P2P
│   ├── api.py          # API REST
│   └── dht.py          # Descoberta de peers
├── main.py             # Ponto de entrada
├── wallet.py           # CLI da carteira
└── tests/              # Testes
```

---

## Estilo de Codigo

### Geral
- Siga PEP 8 para Python
- Use type hints quando possivel
- Mantenha funcoes pequenas e focadas
- Adicione docstrings para funcoes publicas

### Exemplo de funcao
```python
def enviar_transacao(destinatario: str, valor: float) -> bool:
    """
    Envia uma transacao TRC.
    
    Args:
        destinatario: Endereco do destinatario
        valor: Valor em TRC para enviar
        
    Returns:
        True se enviou com sucesso, False caso contrario
    """
    # Codigo aqui
    pass
```

---

## Mensagens de Commit

- Use presente ("Adiciona feature" nao "Adicionou feature")
- Referencie issues quando aplicavel
- Mantenha mensagens curtas

### Exemplos
```
Adiciona validacao de saldo antes de enviar
Corrige bug na mineracao de blocos duplicados
Atualiza documentacao da API
```

---

## Pull Requests

1. Atualize a documentacao se necessario
2. Adicione testes para novas funcionalidades
3. Certifique-se de que todos os testes passam
4. Mantenha PRs focados em uma feature

### Checklist antes de enviar PR
- [ ] Todos os testes passam: `python -m pytest tests/ -v`
- [ ] Codigo segue PEP 8
- [ ] Documentacao atualizada
- [ ] Testes adicionados para mudancas
- [ ] Commit messages claras

---

## Reportar Bugs

Use GitHub Issues e inclua:
- Descricao do bug
- Passos para reproduzir
- Comportamento esperado
- Versao do Python e SO

---

## Areas para Contribuir

### Para iniciantes
- Corrigir erros de digitacao na documentacao
- Adicionar exemplos de uso
- Melhorar mensagens de erro

### Para desenvolvedores intermediarios
- Adicionar testes unitarios
- Melhorar tratamento de erros
- Otimizar performance

### Para desenvolvedores avancados
- Implementar novas features
- Melhorar seguranca
- Otimizar algoritmos

---

## Licenca

Ao contribuir, voce concorda que suas contribuicoes serao licenciadas sob a MIT License.
