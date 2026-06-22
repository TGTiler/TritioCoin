# Politica de Seguranca - TritioCoin

## Versoes Suportadas

| Versao | Suportada |
|--------|-----------|
| 1.0.x  | Sim       |

---

## Como Reportar Vulnerabilidades

Se voce encontrar uma vulnerabilidade:

1. **NAO** abra um issue publico no GitHub
2. Crie um issue PRIVADO no GitHub
3. Inclua:
   - Descricao da vulnerabilidade
   - Passos para reproduzir
   - Impacto potencial
   - Sugerir correcao (se possivel)

---

## Medidas de Seguranca

### Criptografia

| Componente | Algoritmo | Descricao |
|------------|-----------|-----------|
| Armazenamento | AES-256-GCM | Criptografia da carteira |
| Derivacao de chave | PBKDF2 (600K iteracoes) | Protecao contra bruteforce |
| Transporte | TLS 1.3 | Conexao P2P criptografada |
| Assinaturas | ECDSA secp256k1 | Assinatura de transacoes |
| Quantum | WOTS+ | Protecao contra computacao quantica |
| Hashing | SHA-256 | Hash de blocos e Merkle trees |

### Como sua carteira e protegida

```
1. Sua chave privada e criptografada com AES-256-GCM
2. A senha e processada com PBKDF2 (600.000 iteracoes)
3. Mesmo se roubarem o arquivo, precisam da senha
4. Cada carteira tem salt e nonce unicos
```

### Rede

| Medida | Descricao |
|--------|-----------|
| Rate Limiting | 100 mensagens/10s por peer |
| Reputacao | Ban automatico de peers maliciosos |
| Validacao | Todas as mensagens sao validadas |
| Tamanho maximo | 10MB por mensagem |

### Consenso

| Protecao | Como funciona |
|----------|---------------|
| Double-spend | UTXO previne gasto duplo |
| Validacao | Todos os blocos e transacoes sao validados |
| Supply cap | Limite de 19M TRC forçado pelo consenso |
| Bloco duplicado | Blocos com mesmo hash ou height sao rejeitados |

### Armazenamento

| Medida | Descricao |
|--------|-----------|
| Escrita atomica | Operacoes seguras contra crashes |
| WAL Mode | SQLite com consistencia garantida |
| Backup | Recuperacao via BIP39 mnemonico |
| Pruning | Limpeza de blocos antigos para economizar espaco |

---

## Por que TritioCoin e Segura

### 1. Contra computacao quantica
```
Atualmente:  ECDSA protege suas chaves
Futuro:      WOTS+ continua protegendo
Resultado:   Suas moedas estao seguras mesmo com computadores quantonicos
```

### 2. Contra hackers
```
Carteira criptografada com AES-256-GCM
Senha processada com 600.000 iteracoes
Precisariam de bilhoes de anos para quebrar
```

### 3. Contra censura
```
Rede descentralizada - sem autoridade central
Ninguem pode bloquear transacoes
Ninguem pode confiscar moedas
```

### 4. Contra inflacao
```
Supply maximo: 19.000.000 TRC (para sempre)
Halving: Recompensa diminui pela metade a cada 190K blocos
Queima: 10% das taxas sao destruidas
```

---

## Seus Dereitos

- **Sua chave = suas moedas** - Ninguem pode tomar
- **Privacidade** - Transacoes nao precisam de dados pessoais
- **Portabilidade** - Use em qualquer computador com as 24 palavras
- **Verificacao** - Qualquer pessoa pode verificar a blockchain

---

## Limitacoes Conhecidas

1. Certificados TLS auto-assinados (nao verificados por CA)
2. Sem hardware wallet ainda
3. Sem auditoria de seguranca formal

---

## Politica de Atualizacao

Atualizacoes de seguranca serao lancadas o mais rapido possivel apos a divulgacao de vulnerabilidades.

---

## Dicas de Seguranca para Usuarios

1. **Nunca compartilhe suas 24 palavras**
2. **Use senha forte na carteira**
3. **Mantenha backup das 24 palavras em local seguro**
4. **Nao use o mesmo PC para tudo**
5. **Verifique sempre o endereco do destinatario**
6. **Nao clique em links suspeitos**
