# OPC UA Plugin - Funcionalidades Presentes em opcua_plugin.py

## Visão Geral

O arquivo `opcua_plugin.py` é a implementação funcional atual do plugin OPC UA para o OpenPLC Runtime. Ele implementa um servidor OPC UA completo com suporte a segurança, autenticação, sincronização bidirecional e gerenciamento de variáveis PLC.

---

## 1. Arquitetura Geral

### 1.1 Componentes Principais

```
opcua_plugin.py
├── Logging (log_info, log_warn, log_error)
├── OpenPLCUserManager (Autenticação)
├── OpcuaServer (Gerenciador do servidor)
├── Plugin Interface (init, start_loop, stop_loop, cleanup)
└── Thread Management (server_thread_main)
```

### 1.2 Fluxo de Inicialização

1. **init()** - Extrai argumentos do runtime, cria buffer accessor, carrega configuração
2. **start_loop()** - Inicia thread do servidor
3. **server_thread_main()** - Executa setup, cria nós, inicia loops de sincronização
4. **stop_loop()** - Para o servidor gracefully
5. **cleanup()** - Libera recursos

---

## 2. Funcionalidades de Logging

### 2.1 Sistema de Logging Integrado

```python
def log_info(message: str) -> None
def log_warn(message: str) -> None
def log_error(message: str) -> None
```

**Características:**
- Integração com sistema de logging do runtime via `SafeLoggingAccess`
- Fallback para stdout/stderr se logging do runtime não estiver disponível
- Prefixos de contexto: `(INFO)`, `(WARN)`, `(ERROR)`

**Uso:**
```python
log_info("OPC-UA Plugin - Initializing...")
log_error(f"Failed to extract runtime args: {error_msg}")
```

---

## 3. Autenticação e Autorização

### 3.1 OpenPLCUserManager

Implementa a interface `UserManager` do asyncua com suporte a múltiplos métodos de autenticação.

#### 3.1.1 Métodos de Autenticação Suportados

1. **Username/Password**
   - Validação com bcrypt (com fallback para comparação direta)
   - Usuários configurados em `config.users`

2. **Certificate-Based**
   - Extração de fingerprint SHA256 do certificado
   - Comparação com certificados confiáveis configurados
   - Suporte a múltiplos certificados de cliente

3. **Anonymous**
   - Permitido apenas em perfis de segurança que o habilitam
   - Mapeado para role "viewer" (read-only)

#### 3.1.2 Mapeamento de Roles

```python
ROLE_MAPPING = {
    "viewer": UserRole.User,      # Read-only
    "operator": UserRole.User,    # Read/write (controlado por callbacks)
    "engineer": UserRole.Admin    # Full access
}
```

#### 3.1.3 Resolução de Perfil de Segurança

- Mapeia URI de política de segurança para perfil configurado
- Fallback automático se perfil não puder ser resolvido
- Valida que o método de autenticação é permitido no perfil

**Métodos principais:**
- `get_user()` - Autentica usuário
- `_extract_cert_id()` - Extrai ID do certificado
- `_get_profile_for_session()` - Resolve perfil de segurança
- `_validate_password()` - Valida senha com bcrypt

---

## 4. Gerenciamento do Servidor OPC UA

### 4.1 Classe OpcuaServer

Gerencia o ciclo de vida completo do servidor OPC UA.

#### 4.1.1 Inicialização do Servidor

```python
async def setup_server() -> bool
```

**Etapas:**
1. Cria instância do servidor com user manager
2. Configura endpoint URL (com normalização)
3. Define nome do servidor e URIs
4. Configura segurança (políticas, certificados)
5. Inicializa o servidor
6. Define build info
7. Registra namespace
8. Configura callbacks de auditoria

#### 4.1.2 Configuração de Segurança

```python
async def _setup_callbacks() -> None
```

**Callbacks implementados:**
- `_on_pre_read()` - Valida permissões de leitura
- `_on_pre_write()` - Valida permissões de escrita

**Validação de Permissões:**
- Extrai role do usuário autenticado
- Verifica permissões configuradas para o nó
- Nega acesso se permissão não for concedida
- Log de tentativas de acesso negado

---

## 5. Criação de Nós OPC UA

### 5.1 Tipos de Nós Suportados

#### 5.1.1 Variáveis Simples

```python
async def _create_simple_variable(self, parent_node: Node, var: SimpleVariable) -> None
```

**Características:**
- Mapeamento de tipo PLC para OPC UA
- Conversão de valor inicial
- Configuração de atributos (DisplayName, Description)
- Aplicação de permissões de escrita

#### 5.1.2 Estruturas (Structs)

```python
async def _create_struct(self, parent_node: Node, struct: StructVariable) -> None
async def _create_struct_field(self, parent_node: Node, struct_node_id: str, field: VariableField) -> None
```

**Características:**
- Cria objeto OPC UA para a estrutura
- Cria variáveis para cada campo
- Suporta aninhamento de estruturas
- Permissões por campo

#### 5.1.3 Arrays

```python
async def _create_array(self, parent_node: Node, arr: ArrayVariable) -> None
```

**Características:**
- Cria nó com valor array
- Suporta arrays de qualquer tipo suportado
- Inicialização com valor padrão replicado
- Permissões de escrita para array completo

### 5.2 Mapeamento de Tipos

```python
def map_plc_to_opcua_type(plc_type: str) -> ua.VariantType
```

**Tipos suportados:**
- BOOL → Boolean
- BYTE → Byte
- INT → Int16
- DINT/INT32 → Int32
- LINT → Int64
- FLOAT → Float
- STRING → String

---

## 6. Sincronização Bidirecional

### 6.1 PLC → OPC UA (Leitura de Valores)

```python
async def update_variables_from_plc() -> None
```

**Dois modos de operação:**

#### 6.1.1 Acesso Direto à Memória (Otimizado)

```python
async def _update_via_direct_memory_access() -> None
```

**Vantagens:**
- Zero chamadas C por variável
- Acesso direto via endereço de memória
- Máxima performance
- Requer cache de metadados válido

**Processo:**
1. Lê metadados do cache (endereço, tamanho)
2. Acessa memória diretamente com `read_memory_direct()`
3. Atualiza nó OPC UA

#### 6.1.2 Operações em Lote (Fallback)

```python
async def _update_via_batch_operations() -> None
```

**Características:**
- Uma única chamada C para todas as variáveis
- Muito mais eficiente que leitura individual
- Fallback automático se cache não disponível

**Processo:**
1. Coleta índices de todas as variáveis
2. Chamada única `get_var_values_batch()`
3. Processa resultados e atualiza nós

### 6.2 OPC UA → PLC (Escrita de Valores)

```python
async def sync_opcua_to_runtime() -> None
```

**Características:**
- Filtra apenas nós com permissão de escrita
- Lê valores atuais dos nós OPC UA
- Converte para formato PLC
- Escreve em lote no PLC

**Tratamento de Erros:**
- Continua com outras variáveis se uma falhar
- Log de falhas individuais (limitado para evitar spam)
- Resumo de falhas ao final

### 6.3 Loops de Sincronização

```python
async def run_update_loop() -> None          # PLC → OPC UA
async def run_opcua_to_runtime_loop() -> None # OPC UA → PLC
```

**Características:**
- Ciclo configurável (padrão 100ms)
- Execução paralela de ambos os loops
- Tratamento de exceções com retry
- Pausa em caso de erro

---

## 7. Conversão de Tipos

### 7.1 Conversão PLC → OPC UA

```python
def convert_value_for_opcua(datatype: str, value: Any) -> Any
```

**Conversões:**
- BOOL: Converte para boolean Python
- Inteiros: Clamping para range correto
- FLOAT: Desempacota representação inteira
- STRING: Converte para string

### 7.2 Conversão OPC UA → PLC

```python
def convert_value_for_plc(datatype: str, value: Any) -> Any
```

**Conversões:**
- BOOL: Converte para 0/1
- Inteiros: Clamping para range correto
- FLOAT: Empacota como representação inteira
- STRING: Converte para string

### 7.3 Tratamento de Erros

- Try/catch em todas as conversões
- Retorna valor padrão seguro em caso de erro
- Log de falhas de conversão

---

## 8. Gerenciamento de Certificados

### 8.1 OpcuaSecurityManager

Gerencia certificados e políticas de segurança.

#### 8.1.1 Geração de Certificados

```python
async def generate_server_certificate(
    cert_path: str,
    key_path: str,
    common_name: str = "OpenPLC OPC-UA Server",
    key_size: int = 2048,
    valid_days: int = 365,
    app_uri: str = None
) -> bool
```

**Características:**
- Gera certificado auto-assinado com SANs
- Inclui hostname do sistema
- Inclui URIs de aplicação
- Suporta múltiplos endereços IP

#### 8.1.2 Validação de Certificados

```python
def _validate_certificate_format() -> bool
```

**Validações:**
- Formato PEM/DER
- Expiração
- Extensões obrigatórias (SAN, Key Usage)
- Compatibilidade com OPC UA

#### 8.1.3 Certificados de Cliente

```python
def validate_client_certificate(client_cert_pem: str) -> bool
```

**Características:**
- Comparação de fingerprint SHA256
- Suporte a múltiplos certificados confiáveis
- Modo "trust all" configurável

---

## 9. Configuração

### 9.1 Estrutura de Configuração

```python
OpcuaMasterConfig
├── server
│   ├── name
│   ├── endpoint_url
│   ├── application_uri
│   ├── product_uri
│   └── security_profiles[]
├── security
│   ├── server_certificate_strategy
│   ├── server_certificate_custom
│   ├── server_private_key_custom
│   └── trusted_client_certificates[]
├── users[]
├── address_space
│   ├── namespace_uri
│   ├── variables[]
│   ├── structures[]
│   └── arrays[]
└── cycle_time_ms
```

### 9.2 Perfis de Segurança

```python
SecurityProfile
├── name
├── enabled
├── security_policy (None, Basic256Sha256, etc)
├── security_mode (None, Sign, SignAndEncrypt)
└── auth_methods[] (Anonymous, Username, Certificate)
```

---

## 10. Cache de Metadados

### 10.1 Inicialização do Cache

```python
async def _initialize_variable_cache(self, indices: List[int]) -> None
```

**Dados Armazenados:**
- Índice da variável
- Endereço de memória
- Tamanho em bytes
- Tipo inferido

### 10.2 Uso do Cache

- Acesso direto à memória sem chamadas C
- Fallback automático se cache inválido
- Atualização sob demanda

---

## 11. Tratamento de Erros e Exceções

### 11.1 Estratégias de Tratamento

1. **Inicialização**: Falha rápida com mensagens claras
2. **Loops de Sincronização**: Continua com retry após pausa
3. **Operações de Nó**: Continua com próximo nó
4. **Conversão de Tipos**: Retorna valor padrão seguro

### 11.2 Logging de Erros

- Mensagens descritivas com contexto
- Stack traces em casos críticos
- Limitação de spam em loops

---

## 12. Endpoints e Conectividade

### 12.1 Normalização de Endpoints

```python
def normalize_endpoint_url(endpoint_url: str) -> str
```

- Substitui 0.0.0.0 por localhost para compatibilidade
- Preserva porta e caminho

### 12.2 Sugestões de Endpoints para Cliente

```python
def suggest_client_endpoints(server_endpoint: str) -> Dict[str, str]
```

**Variações sugeridas:**
- Local connection (localhost)
- Same machine (127.0.0.1)
- Network hostname
- Network IP

---

## 13. Limpeza de Recursos

### 13.1 Cleanup de Certificados Temporários

```python
def _cleanup_temp_files(self) -> None
```

- Remove arquivos temporários de certificados
- Executado ao parar o servidor

### 13.2 Shutdown Graceful

- Aguarda threads com timeout
- Libera recursos do servidor
- Limpa referências globais

---

## 14. Problemas Conhecidos e Limitações

### 14.1 Código Inchado

- Muita lógica em um único arquivo
- Difícil de testar componentes isoladamente
- Difícil de manter e debugar

### 14.2 Falta de Modularização

- Sem separação clara de responsabilidades
- Sem interfaces bem definidas
- Difícil de reutilizar componentes

### 14.3 Testabilidade

- Difícil de mockar dependências
- Sem injeção de dependência
- Acoplamento forte com asyncua

---

## 15. Próximos Passos para Refatoração

Ver documento `OPCUA_PLUGIN_REFACTORING.md` para instruções de reorganização em `plugin.py`.

---

## Referências

- **asyncua**: https://github.com/FreeOpcUa/opcua-asyncio
- **OPC UA Specification**: https://opcfoundation.org/
- **IEC 61131-3**: Standard for PLC programming languages
