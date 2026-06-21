# Como Conectar ao TritioCoin

## Forma mais fácil (Automática)

### 1. Instale
```
Clique duas vezes em "instalar.bat"
```

### 2. Conecte
```
Clique duas vezes em "TritioCoin.bat"
Selecione: 8 (Conectar)
```

**Pronto!** O programa busca peers automaticamente e conecta.

---

## Como funciona

```
1. Usuário clica em "Conectar"
2. Programa busca peers do GitHub
3. Programa busca peers do seeds.json
4. Conecta automaticamente
5. Baixa a blockchain
6. Sincroniza em tempo real
```

---

## Primeira vez (Criar rede)

**PC 1:**
```
1. Clique em TritioCoin.bat
2. Selecione: 2 (Criar carteira)
3. Selecione: 9 (Iniciar como SEED)
4. Anote o IP: ipconfig
```

**PC 2, 3, 4...:**
```
1. Clique em TritioCoin.bat
2. Selecione: 2 (Criar carteira)
3. Selecione: 8 (Conectar automatico)
```

---

## Se não conectar automaticamente

Edite o arquivo `seeds.json`:
```json
{
    "seeds": [
        "192.168.1.10:8333"
    ]
}
```

Ou use a opção manual no menu (opção 9 → digite IP).

---

## Hospedar lista de seeds no GitHub

1. Crie repositório público "TritioCoin-seeds"
2. Crie arquivo `seeds.json`:
```json
{
    "seeds": [
        "SEU_IP:8333",
        "IP_AMIGO:8333"
    ]
}
```
3. Pegue URL Raw e atualize em `network/discovery.py`
