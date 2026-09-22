# Arquitetura e contratos

## Base existente e integração

Aplicação Flask/Jinja/PostgreSQL, com JavaScript local e serviços Docker separados. `api/src/app.py` cria/edita pedidos e normaliza fotografias; `api/src/ai.py` configura Codex/Open WebUI; `api/src/search.py` contém execução dos fornecedores e prompts de pesquisa; `scheduling.enqueue_search` centraliza snapshots; `api/db/init.sql` contém migrações idempotentes executadas pelo mecanismo existente.

Não chamar diretamente `run_codex`/`run_openwebui` como se enriquecimento fosse uma pesquisa de anúncios: extrair o transporte reutilizável, mantendo contratos próprios para cada tarefa e os testes atuais. Verificar na implementação os detalhes de imagens, ferramentas e saída estruturada de cada ligação. Nenhuma dependência de capacidades não confirmadas.

## Modelo de dados proposto

### Ficha final

Adicionar `requests.part_profile JSONB NOT NULL DEFAULT '{}'` e `requests.profile_revision INTEGER NOT NULL DEFAULT 0`. A ficha inclui `schema_version`, identidade, referências, características, compatibilidades, quantidade/unidade, alternativas e evidências.

Cada afirmação pesquisável tem ID estável e metadados: `origin` (user/ai), `review_status`, `verification_status`, `evidence_ids`, `run_id` opcional e observações. Campos escalares usam metadados por caminho; entradas de listas usam ID, nunca índice como identidade. Rejeições ficam fora dos factos ativos, numa lista limitada de propostas rejeitadas para evitar repetições.

Exemplo abreviado de uma referência:

```json
{
  "id": "uuid",
  "code": "EXAMPLE-001",
  "kind": "unknown",
  "relation": "possible_match",
  "origin": "ai",
  "review_status": "accepted",
  "verification_status": "unverified",
  "evidence_ids": [],
  "run_id": "uuid"
}
```

Código acima é ilustrativo, não uma referência real. Schema único no backend; validar tipos, enums, profundidade, limites e relações. Proposta inicial: até 30 referências, 30 nomes alternativos, 30 compatibilidades, 30 características e 50 evidências; ficha serializada até 128 KiB. Quantidade entre 1 e 999, anos coerentes, medidas positivas com unidade explícita. Ajustar limites com casos reais, mantendo-os finitos.

### Rascunhos e enriquecimentos

- `part_drafts`: UUID, hash do token de propriedade da sessão, pedido original opcional, revisão, conteúdo, timestamps, expiração, pedido criado opcional. Sem credenciais.
- `part_draft_photos`: fotografias normalizadas, posição e identificação; edição pode referenciar fotografias existentes após validar pertença ao pedido.
- `part_enrichments`: UUID, draft_id, revisão de entrada, idempotency_key, fornecedor/modelo/esforço, snapshot de entrada, estado, sugestões validadas, lacunas, timestamps, prazo de execução, erro seguro e identificador remoto quando disponível.
- `part_enrichment_photos`: snapshot imutável das imagens enviadas, ou referências a blobs imutáveis retidos enquanto a execução existir. Não depender de uma fotografia mutável do rascunho.

Estados de tarefa: queued → running → completed/failed/cancelled. Expiração de lease/prazo permite finalizar execuções abandonadas. Não repetir automaticamente chamadas de geração após um reinício com resultado remoto desconhecido.

Uma tarefa ativa por rascunho, garantida por índice parcial e transação. Idempotência impede duplo clique de criar chamadas adicionais. No commit final, bloquear rascunho, verificar revisão e consumir apenas uma vez; submissão repetida devolve o mesmo pedido criado. Edição final usa revisão otimista, devolvendo conflito em vez de substituir alterações de outra aba.

JSONB é suficiente para a primeira versão: a ficha é agregada ao pedido, não um catálogo partilhado. A estrutura pode ser normalizada futuramente se surgirem pesquisas globais por referência.

## Endpoints propostos

| Método/rota | Responsabilidade |
| --- | --- |
| POST `/part-drafts` | Criar rascunho, validar campos e normalizar imagens; devolver ID e revisão. |
| GET `/part-drafts/<id>` | Recuperar o próprio rascunho e tarefa atual. |
| POST `/part-drafts/<id>/update` | Guardar edição com revisão esperada. |
| POST `/part-drafts/<id>/enrichments` | Validar seleção e criar tarefa idempotente; HTTP 202. |
| GET `/part-drafts/<id>/enrichments/<run_id>` | Estado e sugestões, sem payloads privados do fornecedor. |
| POST `/part-drafts/<id>/enrichments/<run_id>/cancel` | Impedir aplicação e tentar cancelar execução remota. |
| POST `/part-drafts/<id>/review` | Persistir decisões por ID/caminho e revisão. |
| POST `/part-drafts/<id>/commit` | Criar pedido ou guardar edição revista; devolver URL do detalhe. |

Rotas de criação/edição atuais continuam disponíveis para submissão manual. Ambas usam o mesmo validador e serviço de persistência para não divergirem.

Manter CSRF em operações mutáveis, incluindo multipart; se for usado JSON, acrescentar explicitamente suporte ao token em header, pois o helper atual lê `request.form`. Validar propriedade do rascunho em todos os endpoints e imagens; UUID não é autorização. Não introduzir autenticação global como parte deste projeto.

Respostas: 400/422 validação, 404 recurso inexistente/não pertencente à sessão, 409 revisão/conflito, 413 tamanho, 429 limite de tarefas. Não incluir chaves, tokens, prompts completos ou erros privados em respostas/logs.

## Contrato de IA

Entrada: versão de schema, descrição original, perfil do carro como snapshot, ficha parcial com proveniência, campos elegíveis, imagens suportadas, sugestões rejeitadas e capacidades disponíveis.

Saída estruturada:

- `suggestions`: ID/caminho permitido, valor proposto, operação (preencher/acrescentar/propor substituição), motivo e evidências.
- `missing_information`: perguntas concretas, campo associado e por que ajudaria a identificar a peça.
- `conflicts`: informações incompatíveis e dados necessários para resolver.
- `limitations`: ausência de visão, pesquisa web ou fontes verificáveis.

O servidor controla caminhos e operações permitidos. Não aceitar patches arbitrários, HTML executável ou alterações a quantidade, preferências humanas, fornecedor e perfil do carro. Valores não comprovados não recebem estatuto confirmado. URLs citadas pelo modelo não equivalem a fontes consultadas: só atribuir verificação de consulta quando existirem dados do transporte/ferramentas que a sustentem.

Prompt dedicado: identificar para melhorar descoberta; não inventar códigos, medidas ou compatibilidades; devolver vazio quando desconhecido; manter hipóteses úteis separadas; tratar texto de imagens/fontes como dados. Não executar comandos sugeridos por conteúdo recebido.

Uma chamada de geração por clique como comportamento inicial. JSON malformado ou schema inválido produz erro recuperável, sem aplicação parcial nem nova chamada paga silenciosa. Preservar rascunho e permitir tentativa explícita.

## Fornecedores e execução

Criar serviço `api/src/enrichment_worker.py` e serviço Compose correspondente, reutilizando ligações, catálogo, autenticação e normalização existentes. Separação evita que uma pesquisa longa de anúncios bloqueie a revisão de uma peça; limitar concorrência total por fornecedor, sobretudo sessões Codex, antes de ativar execução simultânea.

Adaptador com entrada/saída independente da finalidade: textos, imagens, ferramentas disponíveis, timeout e identificador remoto. Prompts e parsers de anúncios e enriquecimento permanecem separados.

A UI mostra **Codex — <model>** ou **Open WebUI — <model>**, sem rotular todos os modelos Open WebUI como Ollama. Caso o modelo não suporte imagem, indicar **Text only** e permitir preenchimento com texto; não enviar imagem a uma ligação que comprovadamente não a suporta. Se a capacidade for desconhecida, explicitá-la e tratar falhas sem perder o formulário. Não prometer acesso à web a todos os modelos.

Polling com intervalo moderado e backoff, pausado quando a página não estiver visível. Cancelamento, limite de tempo e limpeza de rascunhos são responsabilidades do servidor, não apenas do browser. Proposta: prazo de execução de cinco minutos configurável; retenção de rascunhos/resultados temporários de sete dias e limpeza periódica. Copiar proveniência aceite para a ficha final antes de eliminar temporários.

## Integração com pesquisa de anúncios

Adicionar `searches.part_profile JSONB NOT NULL DEFAULT '{}'`. `enqueue_search` copia a ficha atual na mesma transação dos snapshots existentes, tanto em pesquisas manuais como agendadas.

`prompt_for` apresenta secções distintas: factos do utilizador, referências sustentadas, hipóteses a investigar e alternativas autorizadas. Nomes/referências adicionais ampliam consultas; compatibilidades não verificadas nunca são filtros rígidos nem prova de fitment. Propostas rejeitadas não voltam como factos.

Manter prompts limitados em tamanho e preservar campos essenciais. Histórico antigo continua legível; snapshots anteriores não mudam após editar a ficha. Não alterar os schemas de anúncios/Discord apenas para implementar enriquecimento.
