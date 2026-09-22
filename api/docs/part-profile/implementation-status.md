# Implementação e validação

## Entregue

- Ficha opcional em criação e edição, com identificação, referências múltiplas, nomes alternativos, variante, medidas, material, fixações, modelos dadores, quantidade, unidade de compra, acessórios, alternativas, notas e fontes.
- Interface em inglês; criação manual continua disponível sem JavaScript.
- `Fill with AI` com catálogo Codex/Open WebUI, esforço Codex e escolha de incluir fotografias.
- Tarefas persistentes separadas em `part_enrichments`, worker Compose `enrichment`, idempotência, cancelamento e prazo de cinco minutos.
- Rascunhos próprios da sessão, fotografias normalizadas, recuperação por URL/sessão e retenção de sete dias.
- Merge entre dados enviados, valores atuais e propostas; revisão de conflitos, aceitação como hipótese, confirmação factual separada e undo que preserva edições posteriores.
- Ficha no detalhe e snapshots imutáveis em pesquisas manuais/agendadas e respetivo histórico.
- Validação no servidor, CSRF, isolamento de rascunhos, revisão otimista e commit transacional idempotente.

## Decisões finais em relação ao desenho inicial

- Referências, medidas e modelos dadores são entradas descritivas repetíveis dentro de grupos estruturados. O formulário pede explicitamente código/fabricante/tipo, medida/unidade e modelo/anos/motor/restrições. Esses componentes ainda não são colunas independentes nem filtros de catálogo.
- A proveniência é guardada por facto, com fontes anexadas; uma URL citada não recebe automaticamente estatuto de fonte verificada. Os estados factuais disponíveis são não verificado e confirmado pelo utilizador.
- O transporte Codex existente foi parametrizado com prompt/schema próprios, mantendo por omissão o comportamento de pesquisa. O transporte Open WebUI de enriquecimento usa o endpoint de completions estruturadas sem ferramentas em `api/src/part_enrichment.py`; a pesquisa de anúncios mantém o seu transporte com ferramentas e histórico remoto.
- Open WebUI/Ollama preenche a partir de conhecimento do modelo, sem navegação. Codex pode pesquisar fontes. A distinção aparece no formulário.
- A geração é serializada entre os workers de pesquisa e preenchimento para proteger sessões partilhadas. Há filas separadas, mas uma pesquisa longa pode atrasar o preenchimento.
- Acesso ao rascunho exige a mesma sessão do browser. O URL por si só não permite partilha. Criação de contas e sincronização entre dispositivos continuam fora do âmbito.

## Verificação

Testes Python cobrem validação, preservação de códigos, bloqueio de preferências por IA, fontes inválidas, rascunhos/fotografias, CSRF, isolamento, revisão, idempotência, cancelamento, workers, transporte estruturado e snapshots manual/agendado. Testes JavaScript verificam aplicação de listas, alterações durante a geração, conflitos, deduplicação, recuperação e undo.

Foram verificadas a renderização desktop/mobile e uma geração real com Codex, incluindo revisão e criação sem iniciar pesquisa de anúncios. O primeiro teste Open WebUI com o transporte de pesquisa terminou sem resposta, motivando a separação para completions estruturadas. Depois da correção, a instalação Open WebUI devolveu HTTP 504 nos testes reais com qwen3.5:4b e qwen3.5:0.8b. O transporte de completions passou nos testes simulados, mas a geração real por Ollama não ficou validada nesta instalação; os rascunhos foram preservados.

Para executar testes, usar uma base de dados PostgreSQL isolada com `api/db/init.sql` aplicado e as dependências do projeto:

```sh
PYTHONPATH=api/src python -m unittest discover -s api/tests
node --test frontend/tests/test_part_profile_merge.js
```

Os testes Python usam transações com rollback. Não executar contra filas de produção ativas: os testes existentes de Discord pressupõem uma base isolada.
