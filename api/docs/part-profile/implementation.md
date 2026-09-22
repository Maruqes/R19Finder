# Plano de implementação e aceitação

## Etapa 1 — Schema e persistência

- Criar `api/src/part_profile.py` com schema versionado, normalização, validação, proveniência e regras de merge.
- Acrescentar ficha/revisão a pedidos e snapshot a pesquisas em `api/db/init.sql`, respeitando a execução existente via `api/src/init_db.py`.
- Criar tabelas, índices, constraints e limpeza de rascunhos/tarefas.
- Partilhar o serviço de criação/edição entre rotas atuais e commit de rascunho.

Aceitação: base vazia e base existente migram sem perda; migração pode repetir; pedidos antigos continuam editáveis; ficheiros inválidos não deixam pedidos parcialmente criados.

## Etapa 2 — Formulário manual completo

- Expandir `frontend/templates/new.html` com secções progressivas e componentes de listas repetíveis.
- Criar `frontend/src/pages/request-form.tsx` para estado do formulário, rascunho, recuperação e revisão; respeitar a CSP atual, sem scripts inline.
- Atualizar `frontend/templates/detail.html` para mostrar a ficha, hipóteses e evidências.
- Preservar validações e limites atuais de fotografias; inputs opcionais não devem bloquear o fluxo simples.
- Na implementação visual, aplicar a skill de frontend e verificar desktop/mobile com browser.

Aceitação: criar e editar com campos opcionais, listas e fotografias; distinguir referência de quantidade; recuperar rascunho na mesma sessão; manter criação manual quando IA não está configurada.

## Etapa 3 — Transporte e tarefa IA

- Extrair de `api/src/search.py` apenas transporte realmente partilhável para módulo próprio, com regressão dos fornecedores existentes.
- Criar `api/src/part_enrichment.py` para prompt/parser/contrato e `api/src/enrichment_worker.py` para execução.
- Criar blueprint dos endpoints de rascunho/enriquecimento e registá-lo em `api/src/app.py`.
- Integrar seleção de modelos com `api/src/ai.py`/catálogo existente; acrescentar serviço em `compose.yaml`.
- Implementar idempotência, limites, cancelamento, timeouts, leases e erros seguros.

Aceitação: Codex e Open WebUI produzem propostas válidas através de adaptadores simulados; configuração inexistente, modelo removido, resposta inválida e reinício terminam em estado claro; nenhuma pesquisa de anúncios/notificação é criada.

## Etapa 4 — Aplicação e revisão

- Implementar merge em três versões: dados enviados, dados atuais e sugestões recebidas.
- Destacar preenchimentos e exigir resolução das sugestões pendentes antes do commit.
- Implementar aceitar, editar, rejeitar, manter como hipótese e desfazer.
- Guardar decisões/revisões no servidor, com verificação de conflitos entre abas.
- Invalidar contexto dependente quando o carro muda; impedir aplicação de tarefas canceladas ou antigas.

Aceitação: IA nunca substitui silenciosamente conteúdo humano; aceitação não eleva confirmação factual; repetir envio final cria uma única peça; edição não altera a peça original antes de guardar.

## Etapa 5 — Utilização nas pesquisas

- Atualizar `scheduling.enqueue_search` e `search.prompt_for` para snapshot e apresentação da ficha.
- Aproveitar nomes multilingues, referências e modelos dadores como estratégias de descoberta.
- Separar factos e hipóteses, preservando critérios atuais de disponibilidade/blacklist.
- Mostrar no histórico a ficha utilizada, com apresentação compacta.

Aceitação: pesquisa manual e agendada recebem exatamente a ficha vigente no momento de enfileirar; editar depois não altera o snapshot; pedidos antigos funcionam com ficha vazia.

## Etapa 6 — Verificação e documentação

Testes necessários, orientados para comportamento:

1. Schema: limites, campos desconhecidos, códigos com zeros, anos/unidades, referências repetidas e evidências inválidas.
2. Merge: vazio, conflito, edição durante chamada, listas por ID, rejeição e undo sem apagar alterações posteriores.
3. Rotas/DB: CSRF, isolamento entre sessões, revisão concorrente, commit idempotente, rollback e fotografias preservadas.
4. Worker: chamada única por clique, falha remota, timeout, cancelamento tardio, restart e resultado inválido.
5. Fornecedores: contratos simulados para ambos; modelos sem visão/web não recebem capacidades inventadas.
6. Pesquisa: snapshots manual/agendado, hipóteses identificadas e compatibilidade dos pedidos legados.
7. Browser: percurso completo em desktop/mobile; teclado, foco, labels, estados anunciados por leitor de ecrã; recarregar durante processamento, perder rede e recuperar.

Executar os testes existentes afetados em `api/tests/test_app.py`, `api/tests/test_ai.py`, `api/tests/test_search.py` e `api/tests/test_research_loop.py`; adicionar testes focados em ficha/enriquecimento. Verificar ao vivo cada ligação disponível com uma execução controlada quando a implementação estiver pronta, relatando explicitamente ligações não verificadas. Não confundir mocks com validação real do fornecedor.

Atualizar README com utilização, ligações suportadas, retenção de rascunhos, limites, consumo de IA e significado dos estados de verificação.

## Critério de conclusão

O utilizador consegue preencher apenas a descrição e o carro, escolher uma ligação/modelo, clicar **Fill with AI**, rever campos aplicados e hipóteses, criar a peça uma única vez e iniciar posteriormente uma pesquisa que aproveita essa informação. Falhas da IA não perdem dados nem impedem criação manual. Nenhuma compatibilidade passa a confirmada apenas porque o utilizador aceitou o preenchimento.

## Ordem de entrega

Entregar etapas 1–2 como base manual; 3–4 completam o workflow pedido; 5 torna o enriquecimento útil para encontrar mais conteúdo; 6 fecha validação e documentação. A feature só está completa quando as seis etapas estiverem concluídas.
