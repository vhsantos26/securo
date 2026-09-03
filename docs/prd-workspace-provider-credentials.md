# PRD — Credenciais de provedores por workspace

**Status:** proposta técnica para discussão  
**Escopo inicial:** Pluggy; arquitetura extensível aos demais provedores  
**Decisão de produto:** a conta Pluggy de desenvolvimento pertence ao workspace, não ao usuário e nem à instância inteira.

## Problema

Hoje o Securo lê PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET do ambiente e registra o provider no boot. Todos os workspaces de uma instalação usam, portanto, a mesma conta de desenvolvimento Pluggy.

Isso não é multi-tenant: se Hugo e João têm logins e workspaces próprios, João usaria a conta, os limites e o acesso à API de Hugo. A sessão no Meu Pluggy escolhe o titular da conexão bancária; o Client ID e o Client Secret escolhem o projeto/conta Pluggy usado pelo backend para emitir tokens e sincronizar itens.

## Estado atual confirmado

- Cada usuário recebe um workspace pessoal no cadastro e pode alternar o workspace ativo por X-Workspace-Id.
- Dados financeiros, inclusive BankConnection, já possuem workspace_id. Quem não é membro nem manager recebe 404 ao acessar o workspace.
- owner/manager administram o workspace; editor escreve dados; viewer apenas lê.
- O worker Celery já carrega o workspace_id da conexão antes do sync.
- A resolução atual de provider é global: get_provider(), _auto_register_providers() e PluggyProvider._ensure_api_key() dependem do ambiente.
- A API key do Pluggy está em cache de classe. Com duas credenciais, ela poderia cruzar workspaces.
- Uma conexão guarda o usuário que a criou; quando outro membro solicita sync, os dados ainda são importados para o dono da conexão.

## Objetivo

Permitir que owner ou manager configurem credenciais Pluggy próprias no workspace e garantir que criar token, callback, reconexão e sync usem a credencial daquele workspace, sem expor segredos e sem interromper conexões legadas.

Fluxo alvo:

1. João se cadastra e usa o workspace “Pessoal do João”, sem ser convidado ao workspace de Hugo.
2. Em Configurações do workspace → Integrações bancárias, João grava o Client ID e Client Secret Pluggy dele.
3. Ao conectar banco, o widget e o backend usam a credencial de João.
4. Hugo continua no workspace dele com outra credencial e dados isolados.
5. Convites continuam sendo compartilhamento deliberado de um mesmo workspace.

Critérios de sucesso:

- Dois workspaces sincronizam Pluggy no mesmo processo com Client IDs distintos e sem compartilhar API key.
- O Client Secret não aparece em resposta, log, telemetry ou mensagem de erro.
- Quem não acessa um workspace não consegue ler nem alterar sua integração.
- Instalações existentes continuam operando por fallback do ambiente até migrarem.

## Escopo

### Incluído

- Perfil de credencial Pluggy por workspace.
- API, tela, validação, troca e retirada segura da configuração.
- Uso do resolvedor no connect token, callback, reconnect, sync manual e worker.
- Compatibilidade temporária com o ambiente.
- Testes de isolamento, autorização, cache e regressão.

### Fora do escopo inicial

- Consolidar relatórios/saldos de workspaces distintos.
- Alterar a sessão que o usuário final mantém no Meu Pluggy.
- Credenciais por usuário dentro do mesmo workspace.
- Migrar todos os outros providers ao banco na primeira entrega.
- Permitir que editor configure ou revele credenciais.

## Decisões de produto

### Workspace próprio não é convite

Convidar João ao workspace de Hugo dá a João acesso aos dados de Hugo conforme o papel concedido. Não é o mecanismo para João possuir uma área privada.

Para uso independente, João cria ou recebe o próprio workspace. O cadastro normal já faz isso. Caso um usuário novo seja criado por convite, o backend também cria seu workspace pessoal além de adicioná-lo ao workspace convidante.

### Permissões

Somente owner e manager podem salvar, trocar, retirar ou migrar uma credencial. Editor mantém a permissão atual de conectar bancos quando o workspace já possui uma integração configurada; isso preserva workspaces colaborativos. A interface deve alertar owners de que editores podem criar conexões usando a credencial ativa do workspace.

### Credenciais são versionadas

Trocar o Client ID ativo deve afetar apenas novas conexões. Uma conexão existente fica ligada ao perfil com o qual nasceu e continua usando-o até ser reconectada ou removida.

Essa regra evita que a mudança feita para novas contas quebre silenciosamente conexões importadas. Perfis antigos só podem ser retirados quando nenhuma conexão os referencia.

## Arquitetura

### Modelo de dados

Criar a migration 091 e a tabela workspace_provider_credentials:

| Coluna | Regra |
|---|---|
| id | UUID, chave primária |
| workspace_id | FK workspaces, ON DELETE CASCADE, index |
| provider | varchar(50), inicialmente pluggy |
| client_id | varchar(255), obrigatório, retornado somente mascarado |
| client_secret_encrypted | text, obrigatório, nunca retornado |
| is_active | boolean; somente um ativo por workspace/provider |
| created_by_user_id / updated_by_user_id | FK users para auditoria |
| created_at / updated_at | timestamp com timezone |
| retired_at | nulo enquanto o perfil estiver utilizável |

Adicionar bank_connections.provider_credential_id, FK opcional para workspace_provider_credentials, ON DELETE RESTRICT. Conexões atuais ficam com NULL, significando fallback de ambiente; novas conexões recebem o perfil utilizado.

Criar índice único parcial em (workspace_id, provider) para perfis ativos não aposentados. O serviço também serializa a ativação concorrente.

### Criptografia e apresentação

Reutilizar Fernet derivado de SECRET_KEY, porém com um salt próprio, por exemplo securo-workspace-provider-credentials-v1. Assim as credenciais do Pluggy não compartilham domínio criptográfico com chaves de agentes.

A resposta de leitura contém apenas provider, configured, source (workspace/environment/none), client_id_hint, active_credential_id e updated_at. O Client Secret é write-only; o Client ID também deve ser mascarado.

Falha ao decifrar após rotação de SECRET_KEY significa configuração indisponível e solicita nova entrada. Nunca deve haver fallback para a credencial de outro workspace.

### Serviço resolvedor e registry

Criar app/services/provider_credential_service.py com responsabilidades:

- obter perfil ativo por workspace/provider;
- obter perfil fixado em uma BankConnection;
- salvar, validar, ativar, aposentar e listar estado sem segredos;
- resolver uma instância configurada de provider;
- contar conexões legadas e perfis em uso.

A precedência na resolução é:

1. perfil explicitamente fixado na conexão;
2. perfil ativo do workspace;
3. ambiente somente para conexão/configuração legada;
4. ProviderNotConfiguredError acionável.

O registry deixa de registrar providers condicionalmente no import. Ele passa a fornecer factories de providers conhecidos, e a disponibilidade é calculada de modo assíncrono por workspace.

PluggyProvider recebe Client ID e Client Secret no construtor. O cache de API keys é indexado por impressão não reversível de Client ID + secret e expiração; API keys não são persistidas. Uma rotação muda a impressão e evita token antigo em qualquer processo.

### Pontos que precisam propagar workspace e perfil

| Fluxo | Regra |
|---|---|
| GET /connections/providers | status calculado no workspace ativo |
| Connect token | usa perfil ativo e retorna provider_credential_id opaco |
| Callback inicial do widget | valida o ID opaco no workspace e o grava na conexão |
| OAuth URL | guarda provider_credential_id no estado Redis |
| Callback OAuth | usa o perfil salvo no estado |
| Reconnect token/callback | usa o perfil fixado na conexão, não o perfil ativo novo |
| Listar instituições | resolve perfil do workspace quando o provider exigir auth |
| Sync manual | resolve pelo perfil da conexão |
| Sync Celery | resolve pelo mesmo perfil e workspace_id já carregado |
| Holdings e bills | reutilizam a instância resolvida do sync, sem novo get_provider() global |

Para o widget, POST /connections/connect-token passa a retornar provider_credential_id. O frontend guarda esse valor somente enquanto o modal está aberto e o envia junto com o callback. O backend valida workspace e provider. Isso impede que uma troca de perfil enquanto o widget está aberto associe o Item à credencial errada.

## API proposta

| Rota | Papel | Comportamento |
|---|---|---|
| GET /api/workspaces/{id}/integrations | membro | status mascarado, sem segredo |
| PUT /api/workspaces/{id}/integrations/pluggy | owner/manager | salva perfil ativo; body tem client_id e client_secret |
| POST /api/workspaces/{id}/integrations/pluggy/verify | owner/manager | valida no endpoint /auth, sem persistir API key |
| POST /api/workspaces/{id}/integrations/pluggy/activate | owner/manager | torna perfil existente ativo para novas conexões |
| DELETE /api/workspaces/{id}/integrations/pluggy/{credential_id} | owner/manager | aposenta/remove somente perfil sem conexão |
| POST /api/workspaces/{id}/integrations/pluggy/adopt-environment | owner/manager | vincula conexões legadas após confirmação |

A tela pode oferecer “Salvar e validar” combinando PUT e verify, mas o serviço mantém as operações separadas e testáveis.

Erros:

- 403: papel sem permissão;
- 404: workspace/perfil inacessível, sem enumeração;
- 409: perfil ainda tem conexões vinculadas;
- 422: credencial vazia, longa ou inválida;
- 502: Pluggy rejeitou ou não respondeu ao verify;
- 503: não há credencial efetiva para conectar/sincronizar.

## UX

Adicionar a seção Integrações bancárias em WorkspaceSettingsPage, antes da gestão de membros.

### Owner e manager

- Card Pluggy: Não configurado, Configurado neste workspace, Fallback legado de ambiente ou Requer nova credencial.
- Campos Client ID e Client Secret, com “Salvar e validar”.
- Após salvar, o secret volta vazio e não existe ação para revelá-lo.
- Mostrar somente últimos caracteres do Client ID e a data de atualização.
- Aviso explícito: editores podem conectar bancos usando a integração ativa.
- Na troca do Client ID: confirmação de que só novas conexões usam o novo perfil.
- Lista de perfis anteriores com ID mascarado, data e número de conexões; remoção apenas quando o número é zero.
- Diagnóstico para conexões legadas e ação “Adotar conexões legadas”.

### Editor e viewer

- Editor vê Pluggy disponível e pode conectar quando existir credencial efetiva, mas não vê campos nem histórico de perfil.
- Viewer não recebe ações de escrita.

## Migração e compatibilidade

1. A migration é aditiva: cria tabela e FK anulável, sem alterar conexões existentes.
2. O ambiente continua como fallback para conexões sem provider_credential_id.
3. Novos workspaces configuram Pluggy no UI sem qualquer variável de ambiente.
4. Workspaces legados configuram um perfil próprio; novas conexões já ficam fixadas.
5. Para retirar o ambiente, toda conexão Pluggy legada precisa ser explicitamente adotada por um perfil de workspace ou removida.

Não copiar automaticamente o segredo global do ambiente para o banco: não é possível inferir com segurança a qual workspace ele pertence. A adoção só vincula conexões a um perfil ativo escolhido pelo owner; não devolve segredo.

Como rollback, manter as variáveis de ambiente até a versão nova estar estável. A migration suporta rollback de aplicação; em produção, evitar downgrade físico que descarte perfis já criados.

## Segurança e observabilidade

- Usar SecretStr nos schemas de entrada.
- Não reutilizar AppSetting: a API genérica de settings devolve valor e é imprópria para segredo.
- Auditar criador, última alteração e datas, sem armazenar payload em log.
- Logs de sync podem conter workspace_id, connection_id e credential_id, mas nunca Client ID, secret, fingerprint ou API key.
- O verify deve respeitar rate limit, pois chama a API Pluggy.
- Todos os containers backend/worker devem compartilhar SECRET_KEY e banco, como já é necessário para a aplicação.
- A troca de secret não depende de invalidação distribuída: a chave do cache muda com a impressão das credenciais.

## Plano de entrega

### Etapa 1 — Base segura

1. Modelo, export, schemas e migration 091.
2. Helper de criptografia com salt dedicado.
3. Serviço de perfis e resolvedor assíncrono.
4. Registry factory-based e PluggyProvider com configuração injetada/cache segmentado.

### Etapa 2 — Ciclo de conexão

1. Propagar sessão/workspace em connect token, OAuth, institutions, callback e reconnect.
2. Fixar provider_credential_id em novas conexões e no estado OAuth.
3. Resolver o perfil da conexão no sync manual e Celery.
4. Reutilizar provider resolvido em holdings e bills.

### Etapa 3 — API e interface

1. Rotas de integração no router de workspaces, com gate owner/manager.
2. Cliente HTTP, tipos, i18n e card em Workspace Settings.
3. Atualizar BankConnectDialog para reter o ID opaco.
4. Confirmações de troca/retirada e diagnóstico de legado.

### Etapa 4 — Rollout

1. Migrations em banco limpo e em banco com conexão Pluggy legada.
2. Testes backend, lint e build frontend.
3. Sandbox com dois workspaces e dois projetos Pluggy distintos.
4. Documentar retirada gradual das variáveis de ambiente.

## Testes de aceitação

| Cenário | Resultado |
|---|---|
| Dois workspaces, Client IDs diferentes | Cada auth/connect token usa o perfil correto |
| Dois syncs concorrentes | API key não cruza workspaces |
| Editor salva credencial | 403 |
| Usuário externo lê integração | 404/sem enumeração |
| Editor conecta banco em workspace configurado | comportamento atual preservado |
| Viewer cria connect token | bloqueado pelo write gate |
| Troca de Client ID | antigas mantêm perfil; novas usam o novo |
| Reconnect de conexão antiga | usa perfil original |
| Remoção de perfil em uso | 409, sem perda de dados |
| Conexão legada + ambiente | sync continua |
| Conexão legada sem ambiente | 503 acionável, sem marcar erro bancário |
| Secret ou Client ID em erro/log | nunca aparece |
| Callback com perfil de outro workspace | rejeitado |
| SECRET_KEY rotacionada | solicita nova credencial, sem fallback cruzado |

## Arquivos prováveis

- backend/alembic/versions/091_workspace_provider_credentials.py
- backend/app/models/workspace_provider_credential.py
- backend/app/models/bank_connection.py e models/__init__.py
- backend/app/services/provider_credential_service.py
- backend/app/providers/__init__.py e providers/pluggy.py
- backend/app/services/connection_service.py
- backend/app/api/connections.py e api/workspaces.py
- backend/app/schemas/workspace.py e schemas/bank_connection.py
- backend/app/tasks/sync_tasks.py
- testes de workspace, connections, Pluggy e worker
- frontend/src/pages/workspace-settings.tsx
- frontend/src/components/bank-connect-dialog.tsx
- frontend/src/lib/api.ts, frontend/src/types/index.ts e locales

## Decisões pendentes

1. Editor deve continuar podendo conectar banco em workspace compartilhado? A PRD preserva o comportamento atual.
2. Devemos exibir perfis históricos na primeira UI ou bloquear troca de Client ID enquanto houver conexões? A PRD recomenda histórico versionado por ser mais seguro.
3. A Pluggy permite contratualmente que uma instalação compartilhada hospede projetos de desenvolvimento independentes? Confirmar antes de produção.

## Recomendação

Implementar perfil versionado por workspace e fixar seu ID em cada conexão. É mais robusto que sobrescrever uma linha de configuração: uma troca feita por João não pode parar, redirecionar ou expor conexões já existentes de Hugo. O fallback mantém a entrega incremental e sem migração disruptiva.

