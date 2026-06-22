# Como Conectar ao TritioCoin

## Guia para Iniciantes

### O que voce precisa

- Windows 10/11, Linux ou Mac
- Python 3.8 ou superior
- Conexao com a internet (para descobrir peers)

---

## Passo 1: Instalar

### Windows
```
1. Clique duas vezes em "instalar.bat"
2. Aguarde a instalacao terminar
```

### Linux/Mac
```bash
pip install -r requirements.txt
```

---

## Passo 2: Criar Carteira

### Via Menu (Windows)
```
1. Clique duas vezes em "TritioCoin.bat"
2. Selecione: 2 (Criar carteira)
3. Digite uma senha forte (minimo 8 caracteres)
4. Confirme a senha
5. ANOTE as 24 palavras em um local SEGURO
```

### Via Comando (Linux/Mac)
```bash
python wallet.py create
```

**IMPORTANTE:** As 24 palavras sao sua unica forma de recuperar a carteira. Se perder, perde tudo!

---

## Passo 3: Conectar a Rede

### Opcao Automatica (Recomendado)
```
1. Abra TritioCoin.bat
2. Selecione: 8 (Conectar automatico)
3. Aguarde o programa buscar e conectar aos peers
4. Pronto! Voce esta na rede
```

### Como funciona a conexao automatica
```
1. Programa busca peers na lista do GitHub
2. Programa busca peers no arquivo seeds.json local
3. Conecta aos peers encontrados
4. Baixa a blockchain
5. Sincroniza em tempo real
```

---

## Passo 4: Minerar (Opcional)

```
1. Abra TritioCoin.bat
2. Selecione: 12 (Minerar blocos)
3. Seu PC vai trabalhar encontrando blocos
4. Quando encontrar, ganha 45 TRC
5. Ctrl+C para parar
```

---

## Primeira Vez Criando a Rede

Se ninguem ainda esta na rede, voce precisa criar:

### PC 1 (Seed/Server)
```
1. Abra TritioCoin.bat
2. Selecione: 2 (Criar carteira)
3. Selecione: 9 (Iniciar como SEED)
4. Anote o IP: Abra cmd e digite "ipconfig"
5. Procure "IPv4 Address" - e o seu IP
6. Exemplo: 192.168.1.10
```

### PC 2, 3, 4... (Clientes)
```
1. Abra TritioCoin.bat
2. Selecione: 2 (Criar carteira)
3. Selecione: 8 (Conectar automatico)
4. Se nao conectar, edite seeds.json (veja abaixo)
```

---

## Se Nao Conectar Automaticamente

### Metodo 1: Editar seeds.json
Abra o arquivo `seeds.json` e adicione o IP do seed:
```json
{
    "seeds": [
        "192.168.1.10:8333"
    ]
}
```

### Metodo 2: Passar IP direto
```bash
python main.py --seed 192.168.1.10:8333
```

### Metodo 3: No Windows
```
1. Abra TritioCoin.bat
2. Selecione: 9 (Iniciar como SEED)
3. Digite o IP quando solicitado
```

---

## Hospedar Lista de Seeds no GitHub

Isso permite que novos peers encontrem a rede automaticamente:

1. Crie um repositorio publico chamado "TritioCoin-seeds"
2. Crie um arquivo `seeds.json`:
```json
{
    "seeds": [
        "SEU_IP_PUBLICO:8333",
        "IP_AMIGO:8333"
    ]
}
```
3. Pegue a URL Raw do arquivo
4. Atualize em `network/discovery.py` a variavel `SEED_URL`

---

## Portas

| Porta | Protocolo | Descricao |
|-------|-----------|-----------|
| 8333 | TCP | P2P (conexao entre nos) |
| 8334 | TCP | DHT (descoberta de peers) |
| 8080 | TCP | API (explorador e API) |

**IMPORTANTE:** Abra essas portas no seu firewall/router!

---

## Verificar se Esta Conectado

### Via Menu
```
1. Abra TritioCoin.bat
2. Selecione: 10 (Ver info da rede)
3. Veja "Peers: X" - se X > 0, esta conectado
```

### Via Comando
```bash
python wallet.py peers
```

### Via API
```bash
curl http://localhost:8080/api/peers
```

---

## Erros Comuns

### "Porta ja em uso"
Outro programa esta usando a porta 8333. Feche o programa ou mude a porta.

### "Nenhum peer encontrado"
- Verifique se tem internet
- Adicione IPs manualmente no seeds.json
- Verifique se as portas estao abertas

### "Carteira nao encontrada"
Crie uma carteira primeiro (opcao 2 do menu).

### "Senha incorreta"
Voce esqueceu a senha. Se tiver as 24 palavras, use "recuperar carteira".

---

## Dicas

1. **Mantenha o seed ligado** - Outros peers dependem dele
2. **Use senha forte** - Proteja suas moedas
3. **Anote as 24 palavras** - Guarda em local seguro (nao no PC!)
4. **Minere 24h** - Quanto mais tempo, mais blocos
5. **Use o explorer** - Acesse http://localhost:8080/explorer
